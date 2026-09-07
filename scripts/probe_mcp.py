"""Functional probe of the registered markitdown-ocr-mcp server over stdio.

Launches the installed binary and exercises all three tools, including a
live OCR conversion (requires oMLX). Usage:

    uv run python scripts/probe_mcp.py

Exit code 0 only if every check passes.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pymupdf
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BINARY = str(Path.home() / ".local" / "bin" / "markitdown-ocr-mcp")

EXPECTED_PHRASE = "the quick brown fox"


def build_scanned_pdf() -> Path:
    out = Path(tempfile.mkdtemp()) / "probe.pdf"
    src = pymupdf.open()
    try:
        page = src.new_page()
        y = 72
        for line in ("PROBE DOCUMENT", "", EXPECTED_PHRASE, "second line here"):
            page.insert_text((72, y), line, fontsize=14)
            y += 28
        png = page.get_pixmap(dpi=200).tobytes("png")
    finally:
        src.close()

    target = pymupdf.open()
    try:
        page = target.new_page()
        page.insert_image(page.rect, stream=png)
        target.save(out)
    finally:
        target.close()
    return out


async def probe() -> int:
    pdf = build_scanned_pdf()
    failures: list[str] = []

    params = StdioServerParameters(command=BINARY, args=[])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            print(f"tools: {sorted(names)}")
            for expected in ("inspect_pdf", "ocr_pdf", "omlx_models"):
                if expected not in names:
                    failures.append(f"tool missing: {expected}")

            result = await session.call_tool("omlx_models", {})
            status = json.loads(result.content[0].text)
            print(f"omlx_models: ok={status['ok']} model={status.get('resolved_ocr_model')}")
            if not status["ok"]:
                failures.append(f"omlx_models not ok: {status}")

            result = await session.call_tool("inspect_pdf", {"path": str(pdf)})
            inspection = json.loads(result.content[0].text)
            print(f"inspect_pdf: {inspection['kinds']}")
            if inspection["kinds"].get("scanned") != 1:
                failures.append(f"expected scanned=1, got {inspection['kinds']}")

            result = await session.call_tool("ocr_pdf", {"path": str(pdf)})
            text = result.content[0].text
            print(f"ocr_pdf: {len(text)} chars, phrase found: {EXPECTED_PHRASE in text.lower()}")
            if EXPECTED_PHRASE not in text.lower():
                failures.append("OCR output missing expected phrase")

    if failures:
        print("PROBE FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PROBE PASS: all three tools work end-to-end over stdio")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(probe()))
