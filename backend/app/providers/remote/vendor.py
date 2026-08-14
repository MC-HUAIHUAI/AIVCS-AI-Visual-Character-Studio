"""Vendor adapter - offline skeleton (Phase 2.4-B).

This is NOT a real vendor implementation and performs NO network requests.

It readies the seam a future vendor (e.g. Meshy / Tripo / etc.) will fill in:
  - the API key is read from the environment only;
  - the provider is never registered when the key is missing;
  - there is NO default real API endpoint hardcoded here;
  - every method raises NotImplementedError once a dummy key is present,
    proving the offline stub never touches the network.

A future vendor replaces this class (or adds a sibling implementing
IRemote3DClient); JobManager, ModelStore, generationStore and
RealAIImage3DProvider stay unchanged.
"""

from __future__ import annotations

import os

from ...schemas.character import CharacterSpec
from ...schemas.vision import VisionImageInput
from ..base import CancellationToken
from .remote_base import IRemote3DClient, RemoteTaskError, RemoteTaskInfo

VENDOR_API_KEY_ENV = "AIVCS_REAL3D_API_KEY"


class VendorRemoteClient(IRemote3DClient):
    id = "vendor"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key if api_key is not None else os.environ.get(VENDOR_API_KEY_ENV, "")

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def require_configured(self) -> None:
        if not self.configured:
            raise RemoteTaskError(f"未配置 {VENDOR_API_KEY_ENV}")

    async def create_task(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        cancel_event: CancellationToken | None = None,
    ) -> RemoteTaskInfo:
        self.require_configured()
        raise NotImplementedError("vendor client 尚未实现（离线骨架，不发起任何网络请求）")

    async def poll_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> RemoteTaskInfo:
        self.require_configured()
        raise NotImplementedError("vendor client 尚未实现（离线骨架，不发起任何网络请求）")

    async def cancel_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> None:
        self.require_configured()
        raise NotImplementedError("vendor client 尚未实现（离线骨架，不发起任何网络请求）")

    async def download_model(
        self,
        task_id: str,
        model_url: str,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        self.require_configured()
        raise NotImplementedError("vendor client 尚未实现（离线骨架，不发起任何网络请求）")
