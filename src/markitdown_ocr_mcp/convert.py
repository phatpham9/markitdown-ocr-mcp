"""OCR-enabled PDF conversion: MarkItDown + markitdown-ocr plugin + oMLX."""

import os
import re
import tempfile
from pathlib import Path

import pymupdf
from markitdown import MarkItDown
from openai import OpenAI

from .config import settings


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

    Prefers PaddleOCR-VL, then GLM-OCR, then the first listed model.
    Falls back to the default id if discovery fails.
    """
    if settings.omlx_model:
        return settings.omlx_model

    try:
        ids = [model.id for model in client.models.list().data]
    except Exception as exc:
        raise OmlxUnavailableError(
            f"Cannot reach oMLX at {settings.omlx_url} — is it running? (`omlx start`)"
        ) from exc

    for prefix in ("PaddleOCR", "GLM-OCR"):
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
    ) -> str:
        pdf_path = _validate_pdf_path(path)
        source = _extract_page_range(pdf_path, pages) if pages else pdf_path
        try:
            result = self.markitdown.convert(str(source))
        finally:
            if source != pdf_path:
                source.unlink(missing_ok=True)
        text = result.text_content

        if out_path:
            out = Path(out_path)
            out.write_text(text, encoding="utf-8")
            return (
                f"Conversion complete. Model: {self.model}. Wrote {len(text)} characters to {out}"
            )
        return text


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


def _extract_page_range(pdf_path: Path, spec: str) -> Path:
    """Build a sub-PDF containing the requested 1-based pages.

    `spec` is a comma-separated list of single pages and ranges, e.g. "1-5,9".
    """
    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise ValueError(f"PDF is password-protected: {pdf_path}")
        count = doc.page_count
        zero_based = _parse_page_spec(spec, count)
        # select() mutates in place — fine, this document is a throwaway copy.
        doc.select(zero_based)

        fd, tmp_name = tempfile.mkstemp(suffix=".pdf", prefix="ocr-pages-")
        os.close(fd)
        try:
            doc.save(tmp_name)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    return Path(tmp_name)


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
