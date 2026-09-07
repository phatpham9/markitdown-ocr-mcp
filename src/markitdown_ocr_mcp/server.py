"""MCP server exposing OCR-enabled PDF conversion to Claude Code."""

from mcp.server.mcpserver import MCPServer

from . import inspect as _inspect
from .convert import get_converter, list_models

mcp = MCPServer("markitdown-ocr-mcp")


@mcp.tool()
def inspect_pdf(path: str) -> dict:
    """Classify each page of a PDF as text / scanned / mixed / blank.

    Uses the PDF text layer and image geometry only — no OCR is run.
    Use this first to decide whether (and which pages need) OCR.
    """
    return _inspect.inspect_pdf(path)


@mcp.tool()
def ocr_pdf(
    path: str,
    pages: str | None = None,
    out_path: str | None = None,
    dpi: int | None = None,
) -> str:
    """Convert a PDF to Markdown, OCR-ing scanned/image pages via oMLX.

    Text-layer pages go through MarkItDown directly; scanned/mixed pages are
    rendered and OCR'd by the vision model. If `pages` is given (e.g.
    "1-5,9"), only those pages are converted. If `out_path` is given the
    Markdown is written there and a summary with per-page sources is returned.
    `dpi` overrides OCR_DPI (default 150); the render is clamped so the long
    side stays within OCR_MAX_LONG_SIDE pixels (oMLX memory guard).
    """
    return get_converter().convert_pdf(path, pages=pages, out_path=out_path, dpi=dpi)


@mcp.tool()
def omlx_models() -> dict:
    """Check oMLX health: available models and the resolved OCR model."""
    return list_models()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
