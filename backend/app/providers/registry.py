from .base import AIImage3DProvider
from .mock import MockImage3DProvider
from .real_placeholder import RealImage3DProviderPlaceholder
from .local_lowpower import LocalLowPower3DProvider

REGISTRY: dict[str, AIImage3DProvider] = {
    p.id: p
    for p in (
        MockImage3DProvider(),
        LocalLowPower3DProvider(),
        RealImage3DProviderPlaceholder(),
    )
}


def get_provider(provider_id: str) -> AIImage3DProvider:
    return REGISTRY.get(provider_id, REGISTRY["mock"])


def list_providers() -> list[str]:
    return list(REGISTRY.keys())
