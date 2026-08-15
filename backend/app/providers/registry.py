from .base import AIImage3DProvider
from .mock import MockImage3DProvider
from .real_placeholder import RealImage3DProviderPlaceholder
from .local_lowpower import LocalLowPower3DProvider
from .remote.mock_provider import MockRemote3DProvider
from .remote.embedded_client import EmbeddedClient, EmbeddedClientError
from .remote.contract import ProviderCapability
from .remote.remote_base import IRemote3DClient

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

    # Embedded local AI 3D runtime (Phase 1: infrastructure only). Registered as
    # a REAL AI provider. It MUST NOT silently fall back to mock: when no
    # runtime is installed/ready the generate path raises an explicit error.
    providers.append(_build_embedded_provider())

    return {p.id: p for p in providers}


def _build_embedded_provider():
    """Build the embedded-ai-3d provider from EmbeddedClient (runtime started on demand)."""
    from .remote.real_ai import RealAIImage3DProvider

    client = _RuntimeManagerClient()
    return RealAIImage3DProvider(
        client=client,
        provider_id="embedded-ai-3d",
        provider_name="Embedded AI 3D（本地）",
        description="本地 AI 3D Runtime（多 Runtime 管理）。未安装/未就绪时不可用，绝不回退 Mock。",
        default_timeout_seconds=900.0,
    )


class _RuntimeManagerClient(EmbeddedClient):
    """EmbeddedClient that starts the requested (or first installed) runtime on
    demand via the Runtime Manager, then binds to its localhost endpoint + token.

    The protocol used for generation is selected by the runtime's client kind:
    the dummy runtime speaks the AIVCS /task protocol; the Hunyuan runtime speaks
    the official /send + /status protocol. Never falls back to Mock: when no
    runtime is installed / compatible / ready an explicit EmbeddedClientError is
    raised (the provider turns it into a ProviderError -> job failed, never mock).
    """

    _protocol_clients: dict[str, IRemote3DClient] = {}

    def capability(self) -> ProviderCapability:
        # If the selected runtime speaks the Hunyuan protocol, report its true
        # capability (no cancel, no real progress). Otherwise fall back to the
        # AIVCS protocol (cancel + coarse progress supported by wrapper).
        proto = self._protocol_clients.get(next(iter(self._protocol_clients.keys()), ""))
        if isinstance(proto, IRemote3DClient) and proto.id == "hunyuan-embedded":
            return proto.capability()
        return ProviderCapability(
            mode="local",
            gpu_required=True,
            max_references=4,
            output_format="glb",
            supports_cancel=True,
            supports_timeout=True,
            kind="real",
        )

    @classmethod
    def _client_for(cls, runtime_id: str, base_url: str, token: str) -> IRemote3DClient:
        from ..services import ai3d_runtime_manager as rm

        manifest = next((m for m in rm.load_manifests() if m.id == runtime_id), None)
        # The Hunyuan runtime launches the official api_server.py (launch.args
        # carries `--model_path`); it speaks the /send + /status protocol.
        is_hunyuan = manifest is not None and any(
            a.startswith("--model_path") for a in manifest.launch.args
        )
        if is_hunyuan:
            # Phase 3-H: `--enable_tex` marks the PAINT runtime (official
            # `--tex_model_path tencent/Hunyuan3D-2 --enable_tex`) -> textured GLB.
            is_paint = any(a.startswith("--enable_tex") for a in manifest.launch.args)
            if is_paint:
                from .remote.hunyuan_paint_client import HunyuanPaintClient

                return HunyuanPaintClient(base_url, token)
            from .hunyuan_client import HunyuanEmbeddedClient

            return HunyuanEmbeddedClient(base_url, token)
        return EmbeddedClient(base_url, token)

    def _ensure_runtime(self, runtime_id: str | None = None) -> None:
        from ..services import ai3d_runtime_manager as rm

        # Explicit runtime selection wins. If a specific runtime was requested it
        # MUST be installed + compatible, otherwise this is an explicit failure.
        if runtime_id:
            manifest = next((m for m in rm.load_manifests() if m.id == runtime_id), None)
            if manifest is None:
                raise EmbeddedClientError(f"embedded-ai-3d：Runtime '{runtime_id}' 未发现")
            hw = rm.detect_hardware()
            install = rm.compute_install_state(manifest)
            if install != rm.InstallState.INSTALLED:
                raise EmbeddedClientError(
                    f"embedded-ai-3d：Runtime '{runtime_id}' 未安装（{install.value}），无法生成"
                )
            if not rm.hardware_compatible(manifest, hw):
                raise EmbeddedClientError(
                    f"embedded-ai-3d：Runtime '{runtime_id}' 与当前硬件不兼容（需要 "
                    f"{manifest.hardware.minimum_vram_mb}MB VRAM / "
                    f"{'/'.join(manifest.hardware.supported_backends)}），无法生成"
                )
            candidates = [manifest]
        else:
            candidates = [m for m in rm.load_manifests() if rm.compute_install_state(m) == rm.InstallState.INSTALLED]
        if not candidates:
            raise EmbeddedClientError("embedded-ai-3d：无已安装的 AI 3D Runtime，无法生成")
        picked = candidates[0].id
        result = rm.start_runtime(picked)
        if not result["ok"]:
            raise EmbeddedClientError(f"embedded-ai-3d：Runtime 启动失败：{result.get('error')}")
        rp = rm.get_runtime_process(picked)
        if rp is None:
            raise EmbeddedClientError("embedded-ai-3d：Runtime 进程状态异常")
        base_url = f"http://127.0.0.1:{rp.port}"
        proto = self._client_for(picked, base_url, rp.token)
        self._protocol_clients[picked] = proto
        if isinstance(proto, EmbeddedClient):
            self.set_runtime_endpoint(base_url, rp.token)

    def _protocol(self, runtime_id: str | None) -> IRemote3DClient:
        if not runtime_id:
            runtime_id = next(iter(self._protocol_clients.keys()), None)
        proto = self._protocol_clients.get(runtime_id or "")
        if proto is None:
            self._ensure_runtime(runtime_id)
            proto = self._protocol_clients.get(runtime_id or "")
        if proto is None:
            raise EmbeddedClientError("embedded-ai-3d：未绑定 Runtime 协议")
        return proto

    async def create_task(self, spec, references, cancel_event=None, runtime_id=None):
        proto = self._protocol(runtime_id)
        return await proto.create_task(spec, references, cancel_event, runtime_id)

    async def poll_task(self, task_id, cancel_event=None):
        proto = self._protocol(None)
        return await proto.poll_task(task_id, cancel_event)

    async def cancel_task(self, task_id, cancel_event=None):
        proto = self._protocol(None)
        return await proto.cancel_task(task_id, cancel_event)

    async def download_model(self, task_id, model_url, cancel_event=None):
        proto = self._protocol(None)
        return await proto.download_model(task_id, model_url, cancel_event)


REGISTRY: dict[str, AIImage3DProvider] = _build_registry()


def get_provider(provider_id: str) -> AIImage3DProvider:
    return REGISTRY.get(provider_id, REGISTRY["mock"])


def list_providers() -> list[str]:
    return list(REGISTRY.keys())


def is_provider_available(provider_id: str) -> bool:
    """Availability: external-3d only runs when enabled; locals always available;
    embedded-ai-3d only when a runtime is installed AND startable (Phase 2:
    runtime manager can start it). Never silently falls back to mock."""
    if provider_id == "real-placeholder":
        return external3d_enabled
    if provider_id == "embedded-ai-3d":
        from ..services import ai3d_runtime_manager as rm

        # A runtime is "available" when at least one manifest is installed and
        # compatible (startable). If none, explicit unavailable.
        return rm.any_installed_runtime()
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
