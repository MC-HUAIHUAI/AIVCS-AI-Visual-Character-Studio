from .base import AIVisionProvider
from .mock import MockVisionProvider
from ... import config
from .kimi import KimiVisionProvider


def _build_registry() -> dict[str, AIVisionProvider]:
    providers: list[AIVisionProvider] = [MockVisionProvider()]
    # Kimi is only registered when a key is available. A missing key must never
    # prevent the backend from starting. Env vars win; runtime override (set by
    # the main process via the local config endpoint) is the fallback.
    if config.effective_kimi_config()["api_key"]:
        providers.append(KimiVisionProvider())
    return {p.id: p for p in providers}


REGISTRY: dict[str, AIVisionProvider] = _build_registry()


def rebuild_registry() -> None:
    """Rebuild the registry to reflect the current effective provider config."""
    global REGISTRY
    REGISTRY = _build_registry()


def select_vision_provider(provider_id: str) -> AIVisionProvider | None:
    """Resolve a requested provider id.

    'auto'/'default' prefer the real provider (Kimi) when configured, otherwise
    fall back to Mock. Explicit ids return None when the provider is unavailable
    so the router can report "not configured".
    """
    if provider_id in ("auto", "default"):
        return REGISTRY.get("kimi") or REGISTRY.get("mock")
    return REGISTRY.get(provider_id)


def list_vision_providers() -> list[str]:
    return list(REGISTRY.keys())
