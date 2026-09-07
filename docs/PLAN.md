# markitdown-ocr-mcp — Implementation Plan

A thin MCP server exposing **MarkItDown + markitdown-ocr (LLM-vision) + oMLX/PaddleOCR-VL** to Claude Code. Local, hybrid PDF → Markdown with page-level inspection, no custom OCR pipeline.

## 1. Goal

Claude Code gets OCR-capable PDF conversion through a minimal MCP wrapper:

```
Claude Code ──MCP──▶ markitdown-ocr-mcp ──▶ MarkItDown (+ markitdown-ocr plugin)
                                                  │
                                  OpenAI-compatible client
                                                  │
                                                  ▼
                                        oMLX :8000 (PaddleOCR-VL-1.6-MLX-8bit)
```

**Success criteria**
1. `inspect_pdf` classifies pages (text/scanned/mixed/blank) without OCR.
2. `ocr_pdf` converts scanned + mixed PDFs to Markdown, OCR via oMLX-served PaddleOCR-VL.
3. Registered globally in Claude Code; `claude mcp list` shows it; stdio probe works.
4. Unit tests green without oMLX (fake client); live smoke test green with oMLX.

## 2. Why this shape (verified 2026-09-07)

- **markitdown-ocr** (official plugin, PyPI 0.1.0) already implements the hybrid pipeline we had planned to build: automatic scanned-page detection (renders at 300 DPI, full page to LLM), inline OCR of embedded images interleaved in reading order, malformed-PDF recovery via PyMuPDF. It is LLM-vision — any OpenAI-compatible client — *not* PaddleOCR-the-library.
- Installed markitdown 0.1.7 supports the `markitdown.plugin` entry-point group and forwards `llm_client`/`llm_model`/`llm_prompt` kwargs to plugins (verified in installed source).
- The CLI has no `--llm-*` flags, and the official **markitdown-mcp never injects an `llm_client`** (verified in source) — so the plugin silently no-ops there. A thin custom MCP server is the only way to get OCR into Claude Code.
- oMLX 0.6.4 already has `OpenGryd/PaddleOCR-VL-1.6-MLX-8bit` downloaded; it serves it through an OpenAI-compatible API.

## 3. Environment

| Component | State |
|---|---|
| oMLX | 0.6.4, loopback **:8080**, OpenAI-compatible (`/v1`), default API key `1234` |
| OCR model | `PaddleOCR-VL-1.6-MLX-8bit` in `~/.omlx/models/OpenGryd/` |
| markitdown / markitdown-ocr | 0.1.7 / 0.1.0 (both on PyPI) |
| Python / uv | 3.14.7 / 0.12.9 |

## 4. Design

### 4.1 Configuration (env vars, defaults in code)

| Var | Default |
|---|---|
| `OMLX_URL` | `http://127.0.0.1:8080/v1` |
| `OMLX_API_KEY` | env override; else auto-read from `~/.omlx/settings.json`; else oMLX's dev default |
| `OMLX_OCR_MODEL` | empty → auto-discover from `/v1/models` (prefer id containing `PaddleOCR`); fallback `PaddleOCR-VL-1.6-MLX-8bit` |
| `OMLX_OCR_PROMPT` | `OCR:` (PaddleOCR-VL task prompt — the plugin's generic default is not what this model expects) |

### 4.2 Core convert path (`convert.py`)

```python
md = MarkItDown(
    enable_plugins=True,
    llm_client=OpenAI(base_url=OMLX_URL, api_key=OMLX_API_KEY),
    llm_model=resolved_model,
    llm_prompt=OMLX_OCR_PROMPT,
)
return md.convert(path).text_content
```

Notes:
- Plugin behavior: scanned pages auto-rendered at 300 DPI → full-page LLM call; embedded images OCR'd inline; LLM errors swallowed per image (conversion continues).
- `llm_prompt` is global — per-image table/formula prompts require patching the plugin (Plan B territory).
- Model id resolved once per server lifetime via `/v1/models` and cached.

### 4.3 Inspection (`inspect.py`, PyMuPDF, no OCR)

Per page: `text` / `scanned` / `mixed` / `blank` via text-layer char count + image coverage (thresholds as in the original plan: 100 chars, 60% coverage → scanned, 30% → mixed). Gives Claude Code page-level visibility the plugin lacks.

### 4.4 MCP tools (`server.py`, FastMCP, stdio)

```
inspect_pdf(path: str) -> dict
    { pages, kinds: {text, scanned, mixed, blank},
      pages: [{ page (1-based), kind, text_chars, image_count, image_coverage }] }

ocr_pdf(path: str, pages: str | None = None, out_path: str | None = None) -> str
    Full markitdown-ocr conversion. `pages` ("1-5,9") extracts a page-range
    sub-PDF via PyMuPDF first (targeted OCR without converting whole docs).
    `out_path` writes result to file and returns a summary instead of the full text.

omlx_models() -> dict
    GET /v1/models passthrough + the resolved OCR model — for diagnosing
    "OCR silently skipped" and verifying oMLX is up.
```

### 4.5 Distribution & registration

- `uv tool install --editable .` → `markitdown-ocr-mcp` on PATH (fast stdio startup, fixed venv).
- `claude mcp add markitdown-ocr-mcp --scope user -- ~/.local/bin/markitdown-ocr-mcp`
- Env overrides (if ever needed): `claude mcp add ... --env OMLX_URL=...` — defaults work out of the box.

## 5. Project structure

```
markitdown-ocr/
├── pyproject.toml              # name markitdown-ocr-mcp; deps: mcp, markitdown, markitdown-ocr, openai, pymupdf
├── README.md
├── CLAUDE.md                   # when Claude Code should use inspect_pdf / ocr_pdf
├── PLAN.md                     # this file
├── src/markitdown_ocr_mcp/
│   ├── __init__.py
│   ├── config.py               # env-driven settings + model resolution/caching
│   ├── inspect.py              # page classification
│   ├── convert.py              # MarkItDown + plugin + OpenAI client
│   └── server.py               # FastMCP: inspect_pdf, ocr_pdf, omlx_models
├── tests/
│   ├── conftest.py             # fixtures: digital.pdf, scanned.pdf, mixed.pdf (PyMuPDF-generated)
│   ├── fake_llm.py             # mock OpenAI client (canned vision responses)
│   ├── test_inspect.py
│   └── test_convert.py         # ocr_pdf wiring with fake client — no oMLX needed
└── scripts/
    └── smoke_omlx.py           # live: model discovery + real OCR of scanned.pdf
```

## 6. Phases

| # | Step | Verify |
|---|---|---|
| 0 | Scaffold: pyproject, uv sync, git init, .gitignore | `uv run python -c "import fitz, mcp, markitdown, markitdown_ocr, openai"` |
| 1 | config.py + inspect.py + fixtures | pytest: classification matches fixture kinds |
| 2 | convert.py (plugin wiring, model discovery) + fake-client test | pytest: scanned fixture output contains canned OCR text; digital fixture conversion works |
| 3 | server.py (3 tools) + stdio probe script | probe returns inspect_pdf JSON |
| 4 | Live smoke: start oMLX, discover model, real OCR on scanned fixture | `scripts/smoke_omlx.py` exits 0, OCR text extracted |
| 5 | Install as uv tool, register globally (`claude mcp add --scope user`) | `claude mcp list` shows it; registered server answers a stdio probe |
| 6 | README + CLAUDE.md | docs complete; user restarts session → `ocr_pdf` visible to Claude Code |

## 7. Risks

| Risk | Mitigation |
|---|---|
| PaddleOCR-VL broken on oMLX 0.6.4 (history: 0.4.0 Metal regression) | Phase 4 gates; fallback: GLM-OCR or Qwen-VL via oMLX (just a model id + prompt change) |
| OCR model load disables Qwen MTP (#1758) | Test in Phase 4; document reload-Qwen workaround |
| Generic prompt degrades PaddleOCR-VL | `OMLX_OCR_PROMPT=OCR:` default (plugin's llm_prompt) |
| LLM errors silently swallowed by plugin | `omlx_models` tool + stats in ocr_pdf summary for diagnosis |
| markitdown 0.1.8 changes plugin kwargs | Deps pinned in pyproject (`markitdown>=0.1.7,<0.2`) |
| Python 3.14 wheel gaps (pandas/pdfminer/pdfplumber) | `uv python pin 3.13` fallback |

## 8. Plan B (fallback, only if plugin output quality disappoints)

Full custom pipeline from the original plan: per-page PyMuPDF classification + per-page MarkItDown + direct oMLX calls with per-page prompts (`OCR:` / `Table Recognition:` / `Formula Recognition:`), page-range/DPI/stats control. The `inspect.py` module here is its first building block. Trigger: benchmark markitdown-ocr vs. direct per-page OCR on real PDFs (tables, formulas, multi-column); escalate where the plugin loses fidelity.
