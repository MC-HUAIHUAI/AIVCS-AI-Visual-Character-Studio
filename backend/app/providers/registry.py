import os

from .base import AIImage3DProvider
from .mock import MockImage3DProvider
from .real_placeholder import RealImage3DProviderPlaceholder
from .local_lowpower import LocalLowPower3DProvider
from .remote.mock_provider import MockRemote3DProvider
from .remote.real_ai import RealAIImage3DProvider


def _build_registry() -> dict[str, AIImage3DProvider]:
    providers: list[AIImage3DProvider] = [
        MockImage3DProvider(),
        LocalLowPower3DProvider(),
        MockRemote3DProvider(),
    ]

    # Real vendor adapter registration is environment-gated. Phase 2.4-A has no
    # vendor client factory yet, so the real adapter is not auto-registered; a
    # future vendor would be wired here behind `IRemote3DClient` and enabled via
    # AIVCS_REAL3D_PROVIDER. No API key is ever read/printed here.
    if os.environ.get("AIVCS_REAL3D_PROVIDER"):
        # e.g. providers.append(RealAIImage3DProvider(vendor_client))
        pass

    providers.append(RealImage3DProviderPlaceholder())
    return {p.id: p for p in providers}


REGISTRY: dict[str, AIImage3DProvider] = _build_registry()


def get_provider(provider_id: str) -> AIImage3DProvider:
    return REGISTRY.get(provider_id, REGISTRY["mock"])


def list_providers() -> list[str]:
    return list(REGISTRY.keys())
