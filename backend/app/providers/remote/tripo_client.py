"""Tripo adapter - OFFLINE SCAFFOLD (Phase 2.4-C / 2.4-D-pre).

STATUS: **UNVERIFIED**. As of 2026-08-14 the official Tripo API documentation
(platform.tripo3d.ai / api-docs.tripo3d.ai / docs.tripo3d.ai) could NOT be
reached from the build environment, so no endpoint / DTO / status string below
is claimed as confirmed. Everything vendor-specific is a STRUCTURAL PLACEHOLDER
that must be verified against the official docs before any real call.

Tripo (tripo3d.ai) is selected as the first concrete vendor target. This module
implements the vendor seam ONLY - it performs NO network requests:

  - API key is read from the environment (AIVCS_TRIPO_API_KEY);
  - the client is never registered when the key is missing;
  - there is NO default endpoint auto-called anywhere;
  - create/poll/cancel/download raise NotImplementedError once a dummy key is
    present, proving the scaffold never touches the network.

All behavior is exercised offline through OfflineFakeVendorClient and the pure
mapping/design functions below (which are testable without any vendor contract).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ...schemas.character import CharacterSpec
from ...schemas.vision import VisionImageInput
from ..base import CancellationToken, ProviderCancelledError, ProviderError, ProviderTimeoutError
from .remote_base import IRemote3DClient, RemoteTaskError, RemoteTaskInfo

TRIPO_API_KEY_ENV = "AIVCS_TRIPO_API_KEY"


# --------------------------------------------------------------------------- #
# DTOs (structural placeholders - verify against official docs before use)
# --------------------------------------------------------------------------- #

@dataclass
class TripoCreateRequest:
    """What we intend to send when creating a Tripo task. Pending doc check."""
    spec_summary: str
    references: list[VisionImageInput] = field(default_factory=list)
    mode: str = "trellis"


@dataclass
class TripoTaskDto:
    """A Tripo task response. Pending doc check."""
    task_id: str
    status: str
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    model_url: str | None = None


@dataclass
class TripoModelDto:
    """Tripo model download payload. Pending doc check."""
    data: bytes


# --------------------------------------------------------------------------- #
# Pure status / error mapping (offline-testable)
# --------------------------------------------------------------------------- #

# Vendor status -> canonical IRemote3DClient status. Pending doc confirmation.
TRIPO_STATUS_MAP = {
    "queued": "queued",
    "queueing": "queued",
    "running": "running",
    "processing": "running",
    "succeeded": "done",
    "success": "done",
    "done": "done",
    "failed": "failed",
    "error": "failed",
    "timed_out": "timed_out",
    "timeout": "timed_out",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


def map_tripo_status(vendor_status: str) -> str:
    """Map a vendor status string to the canonical remote status."""
    return TRIPO_STATUS_MAP.get(vendor_status, "unknown")


def tripo_task_to_remote_task(dto: TripoTaskDto) -> RemoteTaskInfo:
    """Map a vendor task DTO into the canonical RemoteTaskInfo."""
    status = map_tripo_status(dto.status)
    return RemoteTaskInfo(
        task_id=dto.task_id,
        status=status,
        progress=max(0.0, min(1.0, dto.progress)),
        message=dto.message or dto.status,
        error=dto.error,
        model_url=dto.model_url,
    )


def tripo_error_to_provider_error(err: Exception) -> ProviderError:
    """Map a vendor/transport error to the provider error family.

    The scaffold supports the error classes a Tripo client would raise; it is
    never invoked by this module (no network)."""
    status = getattr(err, "status_code", None)
    message = str(err)
    if isinstance(err, TimeoutError) or status == 408:
        return ProviderTimeoutError("Tripo 请求超时")
    if status in (401, 403):
        return ProviderError(f"Tripo API Key 无效或未授权（{message}）")
    if status == 429:
        return ProviderError("Tripo 请求过于频繁，请稍后重试")
    if status is not None and status >= 500:
        return ProviderError(f"Tripo 服务异常（{message}）")
    return ProviderError(f"Tripo 请求失败：{message}")


# --------------------------------------------------------------------------- #
# CharacterSpec.references[] -> Tripo input (DESIGN DRAFT - unverified)
# --------------------------------------------------------------------------- #

# Phase 2.2 reference views that map directly onto a Tripo Multiview image set.
MULTIVIEW_VIEWS = ("front", "side", "back")


def refs_to_tripo_input(references: list[VisionImageInput]) -> dict:
    """DESIGN DRAFT (UNVERIFIED): map AIVCS references to a Tripo task payload.

    The exact request field names are NOT confirmed and must be checked against
    the official Tripo docs. This function only establishes the intended shape:
    one image per reference (data URL), each tagged with its view, and a task
    type chosen by how many non-custom views are present."""
    images = []
    for ref in references:
        view = ref.view or "front"
        images.append({"image": ref.data_url, "view": view})
    return {
        "type": "multiview_to_model" if len(images) >= 2 else "image_to_model",
        "images": images,
    }


def multiview_suitability(views: list[str | None]) -> dict:
    """Pure design check: can the given views drive Tripo Multiview?

    - front/side/back are the direct Multiview inputs (Phase 2.2 views map 1:1);
    - custom is treated as an extra view, NOT a primary Multiview axis;
    - a single usable view is only suitable for image_to_model.

    This does not depend on any vendor contract and is fully testable offline."""
    present = [v or "front" for v in views]
    non_custom = [v for v in present if v in MULTIVIEW_VIEWS]
    usable = len(non_custom) >= 2
    return {
        "usable": usable,
        "distinct_views": sorted(set(present)),
        "multiview_candidates": sorted(set(non_custom)),
        "task_type": "multiview_to_model" if usable else "image_to_model",
        "notes": [] if usable else ["仅 1 个有效视角（front/side/back），无法构成 Multiview，将回退 image_to_model"],
    }


# --------------------------------------------------------------------------- #
# Offline client scaffold
# --------------------------------------------------------------------------- #

class TripoClient(IRemote3DClient):
    id = "tripo"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key if api_key is not None else os.environ.get(TRIPO_API_KEY_ENV, "")

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def require_configured(self) -> None:
        if not self.configured:
            raise RemoteTaskError(f"未配置 {TRIPO_API_KEY_ENV}")

    async def create_task(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        cancel_event: CancellationToken | None = None,
    ) -> RemoteTaskInfo:
        self.require_configured()
        raise NotImplementedError(
            "Tripo client 尚未实现（离线骨架）。需按官方 API 文档确认 DTO 后再启用，且必须先获得人工授权。"
        )

    async def poll_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> RemoteTaskInfo:
        self.require_configured()
        raise NotImplementedError("Tripo client 尚未实现（离线骨架，不发起任何网络请求）")

    async def cancel_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> None:
        self.require_configured()
        raise NotImplementedError("Tripo client 尚未实现（离线骨架，不发起任何网络请求）")

    async def download_model(
        self,
        task_id: str,
        model_url: str,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        self.require_configured()
        raise NotImplementedError("Tripo client 尚未实现（离线骨架，不发起任何网络请求）")
