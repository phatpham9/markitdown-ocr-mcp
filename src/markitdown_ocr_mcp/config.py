"""Environment-driven settings.

Defaults target a local oMLX server on loopback with its dev API key.
All values are read once at import time — restart the MCP server after
changing them (or pass them via `claude mcp add --env`).
"""

import json
import os
from pathlib import Path

# Fallback when no env override and /v1/models discovery fails.
DEFAULT_OMLX_MODEL = "PaddleOCR-VL-1.6-MLX-8bit"


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
    # PaddleOCR-VL expects its task prompt, not the plugin's generic one.
    omlx_prompt: str = os.getenv("OMLX_OCR_PROMPT", "OCR:")


settings = Settings()
