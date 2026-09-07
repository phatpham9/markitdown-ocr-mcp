"""Session-scoped synthetic PDF fixtures, generated with PyMuPDF.

- digital.pdf: two pages with a real text layer
- scanned.pdf: one page that is a single full-page image (simulated scan)
- mixed.pdf: one page with a text layer plus an image covering ~40%
- blank.pdf: one empty page
"""

from pathlib import Path

import pymupdf
import pytest

LINES = [
    "Quarterly Report Summary",
    "",
    "Revenue grew 12 percent year over year, driven primarily by the",
    "enterprise segment. Operating margin expanded by 210 basis points.",
    "",
    "The board approved a new share buyback program and raised the",
    "dividend for the fourth consecutive year. Guidance for next",
    "quarter remains unchanged at 1.4 billion to 1.6 billion.",
]


def _write_text(page: pymupdf.Page, offset: float = 72.0) -> None:
    y = offset
    for line in LINES:
        page.insert_text((72, y), line, fontsize=12)
        y += 20


def _page_image_bytes(landscape: bool = False) -> bytes:
    """Render a text page to PNG (in a throwaway doc) for use as an image."""
    doc = pymupdf.open()
    try:
        page = doc.new_page()
        _write_text(page)
        if landscape:
            page.set_rotation(90)
        return page.get_pixmap(dpi=150).tobytes("png")
    finally:
        doc.close()


def _build(path: Path, kind: str) -> None:
    doc = pymupdf.open()

    if kind == "digital":
        _write_text(doc.new_page())
        _write_text(doc.new_page())
    elif kind == "scanned":
        page = doc.new_page()
        page.insert_image(page.rect, stream=_page_image_bytes())
    elif kind == "mixed":
        page = doc.new_page()
        _write_text(page, offset=36.0)
        # Bottom ~42% of the page is an image (landscape, wide rect, so the
        # aspect-fit doesn't shrink it below the 30% mixed threshold).
        page.insert_image(pymupdf.Rect(36, 430, 559, 842), stream=_page_image_bytes(landscape=True))
    elif kind == "blank":
        doc.new_page()
    else:
        raise ValueError(f"unknown fixture kind: {kind}")

    doc.save(path)
    doc.close()


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("pdfs")
    for kind in ("digital", "scanned", "mixed", "blank"):
        _build(out / f"{kind}.pdf", kind)
    return out


@pytest.fixture(scope="session")
def pdf_path(fixtures_dir: Path):
    return lambda name: fixtures_dir / f"{name}.pdf"
