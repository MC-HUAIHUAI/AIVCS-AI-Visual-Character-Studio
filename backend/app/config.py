"""Application configuration.

No API keys are hardcoded. Real providers read their keys from the environment
through provider-specific settings (see providers/vision/kimi.py). An optional
backend/.env file (git-ignored) can hold these vars via python-dotenv.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / ".env")
except ImportError:
    pass

# Path to the bundled demo character, used by the mock provider.
DEMO_MODEL_PATH = Path(
    os.environ.get("AIVCS_DEMO_MODEL", ROOT / "assets" / "demo_character.glb")
)

# Demo non-human model (anthro fox) returned for creature characters.
DEMO_FOX_MODEL_PATH = Path(
    os.environ.get("AIVCS_DEMO_FOX_MODEL", ROOT / "assets" / "demo_fox.glb")
)

# The provider selected on the backend when a client omits it.
DEFAULT_PROVIDER = os.environ.get("AIVCS_DEFAULT_PROVIDER", "mock")

# CORS origins allowed to talk to this backend (the Electron renderer).
CORS_ORIGINS = [origin.strip() for origin in os.environ.get("AIVCS_CORS_ORIGINS", "*").split(",")]

# --------------------------------------------------------------------------- #
# Moonshot Kimi vision (Phase 2.1 Stage 2B)
# --------------------------------------------------------------------------- #

# Backend-only. Never exposed to the frontend, never logged, never returned.
KIMI_API_KEY = os.environ.get("AIVCS_KIMI_API_KEY", "")
KIMI_BASE_URL = os.environ.get("AIVCS_KIMI_BASE_URL", "https://api.moonshot.cn/v1")
KIMI_MODEL = os.environ.get("AIVCS_KIMI_MODEL", "kimi-k2.6")
KIMI_TIMEOUT_SECONDS = float(os.environ.get("AIVCS_KIMI_TIMEOUT_SECONDS", "240"))

BACKEND_NAME = "aivcs-backend"
BACKEND_VERSION = "0.1.0"
