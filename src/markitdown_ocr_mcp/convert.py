"""OCR-enabled PDF conversion: hybrid MarkItDown + direct oMLX OCR.

Per page: pages with a real text layer go through MarkItDown (exact text);
scanned/mixed pages are rendered and OCR'd directly by the vision model at a
pixel-capped DPI. The markitdown-ocr plugin's own scanned-page path is not
used — its hardcoded 300 DPI rendering blows oMLX's prefill memory guard on
this machine, and the plugin swallows the resulting errors silently.
"""

import base64
import os
import re
import tempfile
from pathlib import Path

import pymupdf
from markitdown import MarkItDown
from openai import OpenAI

from .config import settings
from .inspect import classify_page


class OmlxUnavailableError(RuntimeError):
    """Raised when oMLX cannot be reached or serves no usable model."""


def _new_client() -> OpenAI:
    return OpenAI(
        base_url=settings.omlx_url,
        api_key=settings.omlx_api_key,
        timeout=600.0,  # vision inference on CPU-class hardware is not instant
    )


def resolve_model(client: OpenAI) -> str:
    """Pick the OCR model id: env override, else discover from /v1/models.

    Prefers GLM-OCR (small prefill footprint that fits oMLX's memory guard
    on this machine), then the first listed model, then the default id.
    """
    if settings.omlx_model:
        return settings.omlx_model

    try:
        ids = [model.id for model in client.models.list().data]
    except Exception as exc:
        raise OmlxUnavailableError(
            f"Cannot reach oMLX at {settings.omlx_url} — is it running? (`omlx start`)"
        ) from exc

    for prefix in ("GLM-OCR",):
        match = next((mid for mid in ids if prefix.lower() in mid.lower()), None)
        if match:
            return match
    if ids:
        return ids[0]
    raise OmlxUnavailableError(f"oMLX is up at {settings.omlx_url} but lists no models.")


class OcrConverter:
    """Singleton: resolves the model once, reuses the MarkItDown instance."""

    def __init__(self) -> None:
        self.client = _new_client()
        self.model = resolve_model(self.client)
        self.markitdown = MarkItDown(
            enable_plugins=True,
            llm_client=self.client,
            llm_model=self.model,
            llm_prompt=settings.omlx_prompt,
        )

    def convert_pdf(
        self,
        path: str,
        pages: str | None = None,
        out_path: str | None = None,
        dpi: int | None = None,
    ) -> str:
        """Convert a PDF to Markdown, OCR-ing scanned/image pages.

        Pages are classified without OCR first; see module docstring for the
        per-kind strategy. `pages` ("1-5,9") limits conversion to a subset.
        """
        pdf_path = _validate_pdf_path(path)
        dpi = dpi or settings.ocr_dpi

        with pymupdf.open(pdf_path) as doc:
            if doc.needs_pass:
                raise ValueError(f"PDF is password-protected: {pdf_path}")
            count = doc.page_count
            indexes = _parse_page_spec(pages, count) if pages else list(range(count))

            # Page objects are only valid while the document is open, so the
            # whole per-page loop lives inside the context manager.
            parts: list[str] = []
            stats: list[dict] = []
            for index in indexes:
                number = index + 1
                page = doc[index]
                info = classify_page(page)
                if info["kind"] == "blank":
                    text, source = "", "blank"
                elif info["kind"] == "text":
                    text = self._convert_text_page(pdf_path, index)
                    source = "markitdown"
                else:  # scanned / mixed
                    text = self._ocr_page_direct(page, number, dpi)
                    source = "ocr"
                parts.append(f"<!-- Page {number} -->\n\n{text.strip()}")
                stats.append(
                    {"page": number, "source": source, "chars": len(text), "kind": info["kind"]}
                )

        markdown = "\n\n".join(parts) + "\n"

        if out_path:
            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(markdown, encoding="utf-8")
            return (
                f"Conversion complete. Model: {self.model}. "
                f"Wrote {len(markdown)} characters to {out}. "
                f"Per-page sources: {stats}"
            )
        return markdown

    def _convert_text_page(self, pdf_path: Path, index: int) -> str:
        """Extract one text-layer page via MarkItDown (1-page sub-PDF)."""
        with pymupdf.open(pdf_path) as sub:
            sub.select([index])
            fd, tmp_name = tempfile.mkstemp(suffix=".pdf", prefix="ocr-page-")
            os.close(fd)
            try:
                sub.save(tmp_name)
            except Exception:
                Path(tmp_name).unlink(missing_ok=True)
                raise
        try:
            return self.markitdown.convert(tmp_name).text_content
        finally:
            Path(tmp_name).unlink(missing_ok=True)

    def _ocr_page_direct(self, page: pymupdf.Page, number: int, dpi: int) -> str:
        """Render one page and OCR it with the vision model directly.

        The effective DPI is clamped so the long side stays within
        settings.ocr_max_long_side pixels — beyond that, oMLX's memory guard
        rejects the vision prefill.
        """
        effective_dpi = int(
            min(
                dpi,
                settings.ocr_max_long_side * 72.0 / max(page.rect.width, page.rect.height),
            )
        )
        pix = page.get_pixmap(dpi=effective_dpi)
        png = pix.tobytes("png")
        data_uri = f"data:image/png;base64,{base64.b64encode(png).decode()}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": settings.omlx_prompt},
                    ],
                }
            ],
            temperature=0,
            max_tokens=8192,
        )
        content = response.choices[0].message.content
        if not content:
            # The model reports nothing on this page (blank / photo-only).
            # Not fatal — surfaced as chars=0 in the per-page stats.
            return ""
        return content


_converter: OcrConverter | None = None


def get_converter() -> OcrConverter:
    global _converter
    if _converter is None:
        _converter = OcrConverter()
    return _converter


def list_models() -> dict:
    """oMLX health check: available models + the resolved OCR model."""
    try:
        converter = get_converter()
        ids = [model.id for model in converter.client.models.list().data]
        return {
            "ok": True,
            "omlx_url": settings.omlx_url,
            "models": ids,
            "resolved_ocr_model": converter.model,
        }
    except Exception as exc:
        return {"ok": False, "omlx_url": settings.omlx_url, "error": str(exc)}


def _validate_pdf_path(path: str) -> Path:
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    return pdf_path


def _parse_page_spec(spec: str, page_count: int) -> list[int]:
    """Parse "1-5,9" into 0-based page indexes (in spec order, no duplicates)."""
    indexes: list[int] = []
    seen: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if m := re.fullmatch(r"(\d+)\s*-\s*(\d+)", part):
            first, last = int(m.group(1)), int(m.group(2))
            if first > last:
                raise ValueError(f"Invalid page range: {part}")
        elif m := re.fullmatch(r"(\d+)", part):
            first = last = int(m.group(1))
        else:
            raise ValueError(f"Invalid page spec: {part!r} (expected e.g. '1-5,9')")
        if first < 1 or last > page_count:
            raise ValueError(f"Page {part} out of range: document has {page_count} pages")
        for page in range(first, last + 1):
            if page - 1 not in seen:
                seen.add(page - 1)
                indexes.append(page - 1)
    if not indexes:
        raise ValueError(f"Empty page spec: {spec!r}")
    return indexes
