from .base import AIVisionProvider
from .mock import MockVisionProvider

# Phase 2.1 registers only the Mock provider. Real providers (e.g. DeepSeek)
# will be added here in a later stage.
REGISTRY: dict[str, AIVisionProvider] = {
    p.id: p
    for p in (
        MockVisionProvider(),
    )
}


def get_vision_provider(provider_id: str) -> AIVisionProvider:
    return REGISTRY.get(provider_id, REGISTRY["mock"])


def list_vision_providers() -> list[str]:
    return list(REGISTRY.keys())
