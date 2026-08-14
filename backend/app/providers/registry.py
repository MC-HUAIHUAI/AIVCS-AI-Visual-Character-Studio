from .base import AIImage3DProvider
from .mock import MockImage3DProvider
from .real_placeholder import RealImage3DProviderPlaceholder
from .local_lowpower import LocalLowPower3DProvider
from .remote.mock_provider import MockRemote3DProvider
from .remote.contract import ProviderCapability

# Provider identity is registered ONCE and is independent of availability.
# `external3d_enabled` only controls whether the external-3d adapter may run
# real generation; mock/local providers are always available.
external3d_enabled: bool = False


def _build_registry() -> dict[str, AIImage3DProvider]:
    providers: list[AIImage3DProvider] = [
        MockImage3DProvider(),
        LocalLowPower3DProvider(),
        MockRemote3DProvider(),
    ]

    # Real vendor adapter registration is identity-only (Phase 2.4-B / 3-5B).
    # The provider id stays registered; availability is governed by
    # `external3d_enabled` (set via AppSettings, never by default). A future
    # vendor implements IRemote3DClient and is injected here without changing
    # the registry structure or the core state machine.
    providers.append(RealImage3DProviderPlaceholder())
    return {p.id: p for p in providers}


REGISTRY: dict[str, AIImage3DProvider] = _build_registry()


def get_provider(provider_id: str) -> AIImage3DProvider:
    return REGISTRY.get(provider_id, REGISTRY["mock"])


def list_providers() -> list[str]:
    return list(REGISTRY.keys())


def is_provider_available(provider_id: str) -> bool:
    """Availability: external-3d only runs when enabled; locals always available."""
    if provider_id == "real-placeholder":
        return external3d_enabled
    return True


def set_external3d_enabled(enabled: bool) -> None:
    """Runtime toggle (AppSettings -> backend). Does NOT unregister the id."""
    global external3d_enabled
    external3d_enabled = bool(enabled)


def capability_for(provider_id: str) -> ProviderCapability | None:
    """Capability descriptor for a provider id (None when unknown)."""
    provider = REGISTRY.get(provider_id)
    if provider is None:
        return None
    client = getattr(provider, "client", None)
    cap = client.capability() if client is not None and hasattr(client, "capability") else None
    if cap is not None:
        return cap
    # Fallback for local providers without a remote client.
    return ProviderCapability(
        mode="local",
        gpu_required=bool(provider.gpu_required),
        max_references=provider.max_references,
        output_format=provider.output_format,
        supports_cancel=bool(provider.supports_cancel),
        supports_timeout=bool(provider.supports_timeout),
        kind="local",
    )
