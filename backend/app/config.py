"""Application configuration.

No API keys are hardcoded. Real providers read their keys from the environment
through provider-specific settings (see providers/real_placeholder.py).
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

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

BACKEND_NAME = "aivcs-backend"
BACKEND_VERSION = "0.1.0"
