"""Conversion tests using the fake vision client — no oMLX required."""

import pytest
from fake_llm import FakeVisionClient
from markitdown import MarkItDown

from markitdown_ocr_mcp.convert import OcrConverter, _parse_page_spec


def make_converter(client: FakeVisionClient) -> OcrConverter:
    """Build an OcrConverter with an injected fake vision backend.

    Skips __init__ (which contacts oMLX for model discovery) and wires the
    client + markitdown instance directly — the production path
    `get_converter()` does exactly this construction with a real OpenAI client.
    """
    converter = object.__new__(OcrConverter)
    converter.client = client
    converter.model = "fake-vision-model"
    converter.markitdown = MarkItDown(
        enable_plugins=True,
        llm_client=client,
        llm_model="fake-vision-model",
        llm_prompt="OCR:",
    )
    return converter


def test_scanned_pdf_is_ocrd(pdf_path) -> None:
    client = FakeVisionClient(reply="QUARTERLY REVENUE GREW")
    text = make_converter(client).convert_pdf(str(pdf_path("scanned")))

    assert "QUARTERLY REVENUE GREW" in text
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["model"] == "fake-vision-model"
    content = call["messages"][0]["content"]
    assert any(part["type"] == "image_url" for part in content)


def test_digital_pdf_needs_no_ocr(pdf_path) -> None:
    client = FakeVisionClient()
    text = make_converter(client).convert_pdf(str(pdf_path("digital")))

    assert "Quarterly Report Summary" in text
    assert client.calls == []
    assert "<!-- Page 1 -->" in text and "<!-- Page 2 -->" in text


def test_mixed_pdf_is_ocrd_full_page(pdf_path) -> None:
    client = FakeVisionClient(reply="IMAGE CAPTION TEXT")
    text = make_converter(client).convert_pdf(str(pdf_path("mixed")))

    # Mixed pages go through full-page OCR (not the text layer), so only the
    # OCR reply appears.
    assert "IMAGE CAPTION TEXT" in text
    assert len(client.calls) == 1


def test_blank_pdf_produces_marker_without_ocr(pdf_path) -> None:
    client = FakeVisionClient()
    text = make_converter(client).convert_pdf(str(pdf_path("blank")))

    assert "<!-- Page 1 -->" in text
    assert client.calls == []


def test_empty_ocr_reply_is_not_fatal(pdf_path) -> None:
    client = FakeVisionClient(reply="")
    text = make_converter(client).convert_pdf(str(pdf_path("scanned")))

    assert "<!-- Page 1 -->" in text
    assert len(client.calls) == 1


def test_page_subset_limits_ocr(pdf_path) -> None:
    client = FakeVisionClient()
    text = make_converter(client).convert_pdf(str(pdf_path("scanned")), pages="1")

    assert "FAKE_OCR_TEXT" in text
    assert len(client.calls) == 1


def test_out_path_writes_file_and_returns_summary(pdf_path, tmp_path) -> None:
    out = tmp_path / "nested" / "result.md"
    client = FakeVisionClient()
    summary = make_converter(client).convert_pdf(str(pdf_path("scanned")), out_path=str(out))

    assert "Wrote" in summary and "fake-vision-model" in summary
    assert "'source': 'ocr'" in summary
    assert "FAKE_OCR_TEXT" in out.read_text()


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        make_converter(FakeVisionClient()).convert_pdf("/nonexistent/nope.pdf")


class TestParsePageSpec:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("1-5,9", [0, 1, 2, 3, 4, 8]),
            ("3", [2]),
            ("2,1", [1, 0]),  # spec order preserved
            ("1-2,2-3", [0, 1, 2]),  # duplicates dropped
            (" 1 , 2-4 ", [0, 1, 2, 3]),  # whitespace tolerated
        ],
    )
    def test_valid(self, spec, expected) -> None:
        assert _parse_page_spec(spec, page_count=10) == expected

    @pytest.mark.parametrize("spec", ["0", "11", "1-11", "5-2", "a-b", "1,2,x", "", ","])
    def test_invalid(self, spec) -> None:
        with pytest.raises(ValueError):
            _parse_page_spec(spec, page_count=10)
