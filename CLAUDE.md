# markitdown-ocr-mcp

Thin MCP server: MarkItDown + markitdown-ocr plugin, OCR via oMLX (GLM-OCR).
MCP tools: `inspect_pdf`, `ocr_pdf`, `omlx_models`.

Hybrid conversion: text-layer pages go through MarkItDown; scanned/mixed pages
are rendered (OCR_DPI, capped at OCR_MAX_LONG_SIDE px) and OCR'd directly.

## Local OCR guidance

When a PDF contains scanned/image-based pages or text embedded in images:

1. Run `inspect_pdf` first — never blindly OCR a whole document.
2. Use `ocr_pdf` with a `pages` spec (e.g. "14" or "1-5,9") when only specific pages are needed.
3. Prefer these local tools over external OCR APIs.
4. Preserve reading order; keep tables as Markdown tables, formulas verbatim.
5. Do not invent missing text. When OCR output is ambiguous, say so.
6. Treat OCR output as source material, not ground truth.

## Development

- Python 3.13 (`.python-version`), managed by uv.
- `uv sync --group dev` — install dependencies (re-run when pyproject changes).
- `uv run pytest` — test suite; no oMLX needed (fake vision client).
- `uv run python scripts/smoke_omlx.py` — live smoke test (needs oMLX on :8080).
- `uv run python scripts/probe_mcp.py` — end-to-end probe of the installed MCP binary.
- The installed tool (`uv tool install --editable .`) picks up source changes automatically.
