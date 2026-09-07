# markitdown-ocr-mcp

MCP server exposing OCR-enabled PDF → Markdown conversion to Claude Code.

MarkItDown + the official `markitdown-ocr` LLM-vision plugin, backed by a local
oMLX server running PaddleOCR-VL (or any OpenAI-compatible vision endpoint).

## Setup

```bash
uv sync --group dev
uv tool install --editable .
claude mcp add markitdown-ocr-mcp --scope user -- ~/.local/bin/markitdown-ocr-mcp
```

oMLX must be running (`omlx start`) with a vision model loaded.

## Tools

- `inspect_pdf(path)` — per-page classification (text / scanned / mixed / blank), no OCR
- `ocr_pdf(path, pages?, out_path?)` — full hybrid conversion to Markdown; `pages` ("1-5,9") extracts only a page subset; `out_path` writes to file
- `omlx_models()` — oMLX health check + available models + resolved OCR model

## Testing

```bash
uv run pytest                        # unit + integration, no oMLX needed
uv run python scripts/smoke_omlx.py  # live OCR smoke test (needs oMLX)
uv run python scripts/probe_mcp.py   # end-to-end probe of the installed binary
```

## Config (env vars)

| Var | Default |
|---|---|
| `OMLX_URL` | `http://127.0.0.1:8080/v1` |
| `OMLX_API_KEY` | auto-read from `~/.omlx/settings.json` |
| `OMLX_OCR_MODEL` | auto-discovered from `/v1/models` |
| `OMLX_OCR_PROMPT` | `OCR:` |
