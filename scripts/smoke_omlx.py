"""Live smoke test: oMLX health, model discovery, real OCR of a scanned page.

Usage: uv run python scripts/smoke_omlx.py
Requires oMLX to be running with a vision model loaded.
"""

import sys
import tempfile
from pathlib import Path

import pymupdf

from markitdown_ocr_mcp.convert import get_converter, list_models

EXPECTED_PHRASE = "the quick brown fox jumps over the lazy dog"


def build_scanned_pdf(path: Path) -> None:
    """One-page PDF that is a single full-page image (simulated scan)."""
    src = pymupdf.open()
    try:
        page = src.new_page()
        y = 72
        for line in (
            "SMOKE TEST DOCUMENT",
            "",
            EXPECTED_PHRASE,
            "OCR should extract this line.",
            "Tables and 123 numbers should survive.",
        ):
            page.insert_text((72, y), line, fontsize=14)
            y += 28
        png = page.get_pixmap(dpi=200).tobytes("png")
    finally:
        src.close()

    out = pymupdf.open()
    try:
        target = out.new_page()
        target.insert_image(target.rect, stream=png)
        out.save(path)
    finally:
        out.close()


def main() -> int:
    status = list_models()
    if not status["ok"]:
        print(f"oMLX unreachable: {status['error']}")
        return 1
    print(f"oMLX models: {status['models']}")

    scanned = Path(tempfile.mkdtemp()) / "scanned.pdf"
    build_scanned_pdf(scanned)

    converter = get_converter()
    print(f"resolved OCR model: {converter.model}")

    text = converter.convert_pdf(str(scanned))
    print("--- OCR output ---")
    print(text)
    print("---")

    if EXPECTED_PHRASE in text.lower():
        print("SMOKE PASS")
        return 0
    print("SMOKE FAIL: expected phrase not found in OCR output")
    return 1


if __name__ == "__main__":
    sys.exit(main())
