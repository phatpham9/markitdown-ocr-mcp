# markitdown-ocr-mcp — Implementation Plan

A thin MCP server exposing **MarkItDown + markitdown-ocr (LLM-vision) + oMLX/GLM-OCR** to Claude Code. Local, hybrid PDF → Markdown with page-level inspection, no custom OCR pipeline.

## 1. Goal

Claude Code gets OCR-capable PDF conversion through a minimal MCP wrapper:

```
Claude Code ──MCP──▶ markitdown-ocr-mcp ──▶ MarkItDown (+ markitdown-ocr plugin)
                                                  │
                                  OpenAI-compatible client
                                                  │
                                                  ▼
                                        oMLX :8080 (GLM-OCR-4bit)
```

**Success criteria**
1. `inspect_pdf` classifies pages (text/scanned/mixed/blank) without OCR.
2. `ocr_pdf` converts scanned + mixed PDFs to Markdown, OCR via oMLX-served GLM-OCR.
3. Registered globally in Claude Code; `claude mcp list` shows it; stdio probe works.
4. Unit tests green without oMLX (fake client); live smoke test green with oMLX.

## 2. Why this shape (verified 2026-09-07)

- **markitdown-ocr** (official plugin, PyPI 0.1.0) already implements the hybrid pipeline we had planned to build: automatic scanned-page detection (renders at 300 DPI, full page to LLM), inline OCR of embedded images interleaved in reading order, malformed-PDF recovery via PyMuPDF. It is LLM-vision — any OpenAI-compatible client — *not* PaddleOCR-the-library.
- Installed markitdown 0.1.7 supports the `markitdown.plugin` entry-point group and forwards `llm_client`/`llm_model`/`llm_prompt` kwargs to plugins (verified in installed source).
- The CLI has no `--llm-*` flags, and the official **markitdown-mcp never injects an `llm_client`** (verified in source) — so the plugin silently no-ops there. A thin custom MCP server is the only way to get OCR into Claude Code.
- oMLX 0.6.4 serves `mlx-community/GLM-OCR-4bit` through an OpenAI-compatible API.

## 3. Environment

| Component | State |
|---|---|
| oMLX | 0.6.4, loopback **:8080**, OpenAI-compatible (`/v1`), default API key `1234` |
| OCR model | `GLM-OCR-4bit` in `~/.omlx/models/mlx-community/` |
| markitdown / markitdown-ocr | 0.1.7 / 0.1.0 (both on PyPI) |
| Python / uv | 3.14.7 / 0.12.9 |

## 4. Design

### 4.1 Configuration (env vars, defaults in code)

| Var | Default |
|---|---|
| `OMLX_URL` | `http://127.0.0.1:8080/v1` |
| `OMLX_API_KEY` | env override; else auto-read from `~/.omlx/settings.json`; else oMLX's dev default |
| `OMLX_OCR_MODEL` | empty → auto-discover from `/v1/models` (prefer id containing `GLM-OCR`) |
| `OMLX_OCR_PROMPT` | `OCR:` (task prompt — the plugin's generic default is not what an OCR model expects) |
| `OCR_DPI` | `150` (direct-OCR render DPI) |
| `OCR_MAX_LONG_SIDE` | `1750` (pixel cap keeping the vision prefill inside oMLX's memory guard) |

### 4.2 Core convert path (`convert.py`) — hybrid, implemented 2026-09-07

Per page, after `inspect_pdf`-style classification:

- `text` pages → 1-page sub-PDF → MarkItDown (exact text-layer extraction, no vision calls)
- `scanned`/`mixed` pages → render at `OCR_DPI` (long side clamped to `OCR_MAX_LONG_SIDE` px) → direct `chat/completions` call to the vision model with `OMLX_OCR_PROMPT`
- `blank` pages → empty section

Pages are merged in order with `<!-- Page N -->` markers; per-page source/char stats are reported.

Why not the plugin's own scanned path: it hardcodes 300 DPI and swallows LLM errors. On this machine oMLX's memory guard rejects ~28 GB vision prefills for large pages, so 300 DPI scans fail silently. Direct OCR with a pixel-capped DPI (150 DPI / 1750 px long side, both env-tunable) fits the guard and measured 87.1% word recall vs. ground-truth text layers on real TOEIC scans.

### 4.3 Inspection (`inspect.py`, PyMuPDF, no OCR)

Per page: `text` / `scanned` / `mixed` / `blank` via text-layer char count + image coverage (thresholds as in the original plan: 100 chars, 60% coverage → scanned, 30% → mixed). Gives Claude Code page-level visibility the plugin lacks.

### 4.4 MCP tools (`server.py`, FastMCP, stdio)

```
inspect_pdf(path: str) -> dict
    { pages, kinds: {text, scanned, mixed, blank},
      pages: [{ page (1-based), kind, text_chars, image_count, image_coverage }] }

ocr_pdf(path: str, pages: str | None = None, out_path: str | None = None,
        dpi: int | None = None) -> str
    Hybrid conversion (§4.2). `pages` ("1-5,9") limits to a page subset.
    `out_path` writes result to file and returns a summary with per-page
    sources. `dpi` overrides OCR_DPI.

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
| GLM-OCR broken on an oMLX upgrade | fallback: Qwen-VL or any other vision model via oMLX (just a model id + prompt change) |
| OCR model load disables Qwen MTP (#1758) | Test in Phase 4; document reload-Qwen workaround |
| Generic prompt degrades OCR quality | `OMLX_OCR_PROMPT=OCR:` default (plugin's llm_prompt) |
| LLM errors silently swallowed by plugin | `omlx_models` tool + stats in ocr_pdf summary for diagnosis |
| markitdown 0.1.8 changes plugin kwargs | Deps pinned in pyproject (`markitdown>=0.1.7,<0.2`) |
| Python 3.14 wheel gaps (pandas/pdfminer/pdfplumber) | `uv python pin 3.13` fallback |

## 8. Plan B — triggered and implemented (2026-09-07)

The plugin path failed on real scanned PDFs (hardcoded 300 DPI → oMLX prefill
memory-guard rejection → silently empty pages), so the hybrid direct-OCR path
in §4.2 replaced it for scanned/mixed pages.

On real TOEIC scans: Listening = 87.1% word recall vs. ground-truth text
layers; Reading = 26/26 pages clean; Practice Test One (39 pages, 96-DPI
oversized scans) = good quality. GLM-OCR-4bit's CogViT encoder has a small
enough prefill footprint to fit oMLX's memory guard on this machine
(PaddleOCR-VL-8bit needed ~36 GB per page and was dropped). oMLX's guard tier
is set to `aggressive` in `~/.omlx/settings.json` (reversible).

Remaining future work: per-page prompt selection (Table/Formula/Chart),
PDF-image quality heuristics (upscaling/denoising for low-DPI scans),
concurrency/batching, and kernel `iogpu.wired_limit_mb` if a higher-res model
is ever needed.
