"""Application configuration.

No API keys are hardcoded. Real providers read their keys from the environment
through provider-specific settings (see providers/vision/kimi.py). An optional
backend/.env file (git-ignored) can hold these vars via python-dotenv.
"""

import os
import secrets
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

# Simulated duration of a Mock image-to-3D generation (seconds).
MOCK3D_DURATION_SECONDS = float(os.environ.get("AIVCS_MOCK3D_DURATION_SECONDS", "5"))


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name, "true" if default else "false").strip().lower()
    return value in ("1", "true", "yes", "on")


# LocalLowPower skinned output. Default OFF keeps the existing unskinned GLB
# behavior byte-stable; enable for SkinnedMesh output (RigBuilder + skinning).
LOCAL3D_RIG_ENABLED = _env_bool("AIVCS_LOCAL3D_RIG_ENABLED", False)

# Persistent model output store.
MODEL_DIR = Path(os.environ.get("AIVCS_MODEL_DIR", ROOT / "backend" / "data" / "models"))
# Models older than this are deleted by cleanup (hours).
MODEL_TTL_HOURS = float(os.environ.get("AIVCS_MODEL_TTL_HOURS", "24"))

# Safe default job timeout when a request omits timeoutSeconds (seconds), so a
# remote provider can never wait forever. User-supplied timeouts still win.
GENERATION_DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("AIVCS_GENERATION_DEFAULT_TIMEOUT_SECONDS", "600"))

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


# --------------------------------------------------------------------------- #
# Phase 3-5A: runtime provider config bridge (AppSettings -> backend).
# --------------------------------------------------------------------------- #
#
# The renderer persists App Settings (Vision / External 3D) via the Electron
# main process (safeStorage). The effective provider config on the backend is:
#   - USER AppSettings (runtime override) takes priority - a user who enters
#     their own key in Settings must NEVER silently fall back to a developer's
#     .env key;
#   - env vars (AIVCS_KIMI_*) act only as a developer/local fallback when no
#     user runtime config is set;
#   - otherwise the provider is not configured (mock).
# The `source` is exposed (never the key) so UI/debug can confirm the origin.
# Only the main process may set runtime config; it authenticates with a random
# per-process token written to a local runtime file (never over GET, never
# logged, never in responses, no external proxy).

# In-memory runtime overrides (empty = not set by the main process).
_RUNTIME_VISION: dict[str, str] = {"base_url": "", "model": "", "api_key": ""}

# Random per-process token used to guard the local config endpoint.
LOCAL_CONFIG_TOKEN = secrets.token_urlsafe(32)

# Where the token is exposed for the Electron main process to read (127.0.0.1
# only). Never logged, never returned in API responses.
RUNTIME_TOKEN_FILE = Path(
    os.environ.get("AIVCS_RUNTIME_TOKEN_FILE", ROOT / "backend" / "data" / "runtime_config_token")
)


def write_runtime_token_file() -> None:
    try:
        RUNTIME_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_TOKEN_FILE.write_text(LOCAL_CONFIG_TOKEN, encoding="utf-8")
    except OSError:
        # Best effort: if the token file cannot be written, runtime config
        # override is disabled (env-only mode), which is still safe.
        pass


def set_runtime_vision(base_url: str = "", model: str = "", api_key: str = "") -> None:
    """Set runtime overrides (called by the main process only)."""
    _RUNTIME_VISION["base_url"] = base_url or ""
    _RUNTIME_VISION["model"] = model or ""
    _RUNTIME_VISION["api_key"] = api_key or ""
    # Rebuild the vision provider registry so the new effective config applies
    # without a backend restart.
    from .providers.vision import registry as _vision_registry

    _vision_registry.rebuild_registry()


def effective_kimi_config() -> dict[str, str]:
    """Return the effective Kimi config.

    Priority (hard rule):
        1. user AppSettings (runtime) - wins whenever it has a key;
        2. env vars (AIVCS_KIMI_*) - developer/local fallback only;
        3. otherwise mock (api_key empty).

    `source` reports the origin ("runtime" | "env" | "mock"). The apiKey is
    never logged, never returned in API responses, never part of project data.
    """
    runtime_key = _RUNTIME_VISION.get("api_key", "")
    if runtime_key:
        return {
            "api_key": runtime_key,
            "base_url": _RUNTIME_VISION.get("base_url") or KIMI_BASE_URL,
            "model": _RUNTIME_VISION.get("model") or KIMI_MODEL,
            "source": "runtime",
        }
    if KIMI_API_KEY:
        return {
            "api_key": KIMI_API_KEY,
            "base_url": KIMI_BASE_URL,
            "model": KIMI_MODEL,
            "source": "env",
        }
    return {
        "api_key": "",
        "base_url": KIMI_BASE_URL,
        "model": KIMI_MODEL,
        "source": "mock",
    }


# Runtime external-3d availability toggle (Phase 3-5B). Provider identity stays
# registered regardless; this only gates real generation. Default False.
_runtime_external3d_enabled: bool = False


def set_runtime_external3d(enabled: bool) -> None:
    """Set external-3d availability (main process only). Does NOT unregister."""
    global _runtime_external3d_enabled
    _runtime_external3d_enabled = bool(enabled)
    from .providers import registry as _3d_registry

    _3d_registry.set_external3d_enabled(_runtime_external3d_enabled)


def is_external3d_enabled() -> bool:
    return _runtime_external3d_enabled

BACKEND_NAME = "aivcs-backend"
BACKEND_VERSION = "0.1.0"
