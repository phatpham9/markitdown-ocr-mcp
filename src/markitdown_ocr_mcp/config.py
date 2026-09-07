"""Environment-driven settings.

Defaults target a local oMLX server on loopback with its dev API key.
All values are read once at import time — restart the MCP server after
changing them (or pass them via `claude mcp add --env`).
"""

import json
import os
from pathlib import Path


def _omlx_api_key() -> str:
    """API key from env, else from oMLX's own settings file, else its default."""
    env_key = os.getenv("OMLX_API_KEY")
    if env_key:
        return env_key
    try:
        settings_path = Path.home() / ".omlx" / "settings.json"
        if settings_path.exists():
            data = json.loads(settings_path.read_text())
            key = data.get("auth", {}).get("api_key")
            if key:
                return key
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    return "1234"


class Settings:
    omlx_url: str = os.getenv("OMLX_URL", "http://127.0.0.1:8080/v1")
    omlx_api_key: str = _omlx_api_key()
    # Empty string -> discover from GET /v1/models at first use.
    omlx_model: str = os.getenv("OMLX_OCR_MODEL", "")
    # GLM-OCR works well with a plain task prompt; the plugin's generic
    # description prompt is not what an OCR model expects.
    omlx_prompt: str = os.getenv("OMLX_OCR_PROMPT", "OCR:")
    # Direct-OCR rendering: DPI for normal pages, and the hard pixel cap on
    # the long side that keeps oMLX's prefill within its memory guard
    # (1750px needs ~28 GB of prefill; 1300px stays well inside the guard
    # even when other models/apps are loaded, with no measurable quality loss).
    ocr_dpi: int = int(os.getenv("OCR_DPI", "150"))
    ocr_max_long_side: int = int(os.getenv("OCR_MAX_LONG_SIDE", "1300"))


settings = Settings()
