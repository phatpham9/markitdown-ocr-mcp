"""Classification tests against the synthetic fixtures."""

from markitdown_ocr_mcp.inspect import inspect_pdf


def _kinds(result: dict) -> dict:
    return result["kinds"]


def _page(result: dict, number: int) -> dict:
    return result["pages"][number - 1]


def test_digital_pdf_is_all_text(pdf_path) -> None:
    result = inspect_pdf(str(pdf_path("digital")))
    assert result["page_count"] == 2
    assert _kinds(result) == {"text": 2, "scanned": 0, "mixed": 0, "blank": 0}
    assert _page(result, 1)["text_chars"] > 100


def test_scanned_pdf_detected(pdf_path) -> None:
    result = inspect_pdf(str(pdf_path("scanned")))
    assert _kinds(result)["scanned"] == 1
    page = _page(result, 1)
    assert page["text_chars"] == 0
    assert page["image_count"] == 1
    assert page["image_coverage"] > 0.9


def test_mixed_pdf_detected(pdf_path) -> None:
    result = inspect_pdf(str(pdf_path("mixed")))
    assert _kinds(result)["mixed"] == 1
    page = _page(result, 1)
    assert page["text_chars"] > 100
    assert 0.3 <= page["image_coverage"] < 0.6


def test_blank_pdf_detected(pdf_path) -> None:
    result = inspect_pdf(str(pdf_path("blank")))
    assert _kinds(result)["blank"] == 1


def test_missing_file_raises() -> None:
    import pytest

    with pytest.raises(FileNotFoundError):
        inspect_pdf("/nonexistent/nope.pdf")
