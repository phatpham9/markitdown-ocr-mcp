"""PDF page inspection — classification without OCR, using PyMuPDF."""

from pathlib import Path

import pymupdf

# Classification thresholds (env-overridable for tuning against real documents).
MIN_TEXT_CHARS = 100
SCANNED_IMAGE_COVERAGE = 0.60
MIXED_IMAGE_COVERAGE = 0.30

KINDS = ("text", "scanned", "mixed", "blank")


def classify_page(page: pymupdf.Page) -> dict:
    """Classify one page as text / scanned / mixed / blank.

    Heuristic: text-layer character count vs. how much of the page is
    covered by images. A scanned page has little or no text layer and a
    large image; a mixed page has both a text layer and substantial images.
    """
    chars = len(page.get_text("text").strip())

    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    image_area = 0.0
    image_count = 0
    for info in page.get_image_info():
        image_count += 1
        bbox = pymupdf.Rect(info["bbox"]) & page_rect
        if not bbox.is_empty:
            image_area += bbox.width * bbox.height
    coverage = image_area / page_area if page_area > 0 else 0.0

    if chars == 0 and image_count == 0:
        kind = "blank"
    elif chars < MIN_TEXT_CHARS and coverage >= SCANNED_IMAGE_COVERAGE:
        kind = "scanned"
    elif chars >= MIN_TEXT_CHARS and coverage >= MIXED_IMAGE_COVERAGE:
        kind = "mixed"
    else:
        kind = "text"

    return {
        "kind": kind,
        "text_chars": chars,
        "image_count": image_count,
        "image_coverage": round(coverage, 4),
        "width_pt": round(page_rect.width, 1),
        "height_pt": round(page_rect.height, 1),
    }


def inspect_pdf(path: str) -> dict:
    """Return per-page classification of a PDF. No OCR is performed."""
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise ValueError(f"PDF is password-protected: {path}")

        pages = []
        kinds = {kind: 0 for kind in KINDS}
        for number, page in enumerate(doc):
            info = classify_page(page)
            kinds[info["kind"]] += 1
            pages.append({"page": number + 1, **info})

    return {
        "page_count": len(pages),
        "kinds": kinds,
        "pages": pages,
    }
