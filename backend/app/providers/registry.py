from .base import AIImage3DProvider
from .mock import MockImage3DProvider
from .real_placeholder import RealImage3DProviderPlaceholder
from .local_lowpower import LocalLowPower3DProvider
from .remote.mock_provider import MockRemote3DProvider


def _build_registry() -> dict[str, AIImage3DProvider]:
    providers: list[AIImage3DProvider] = [
        MockImage3DProvider(),
        LocalLowPower3DProvider(),
        MockRemote3DProvider(),
    ]

    # Real vendor adapter registration is environment-gated and is intentionally
    # NOT wired in Phase 2.4-B. A future vendor would:
    #   1. implement IRemote3DClient (backend/app/providers/remote/vendor.py);
    #   2. only register RealAIImage3DProvider(vendor_client) when its API key
    #      env var is set (never read/printed here);
    #   3. never default to a hardcoded endpoint, never touch the network unless
    #      the provider is explicitly selected.
    # `AIVCS_REAL3D_API_KEY` (see backend/.env.example) is reserved for that.

    providers.append(RealImage3DProviderPlaceholder())
    return {p.id: p for p in providers}


REGISTRY: dict[str, AIImage3DProvider] = _build_registry()


def get_provider(provider_id: str) -> AIImage3DProvider:
    return REGISTRY.get(provider_id, REGISTRY["mock"])


def list_providers() -> list[str]:
    return list(REGISTRY.keys())
