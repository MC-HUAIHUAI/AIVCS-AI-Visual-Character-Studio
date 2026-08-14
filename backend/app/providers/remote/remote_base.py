"""Vendor-agnostic remote image-to-3D client contract (Phase 2.4-A).

The real image-to-3d pipeline runs a remote task: create -> poll -> download.
`IRemote3DClient` is the ONLY seam a vendor needs to implement; `RealAIImage3DProvider`
drives it through the unified state mapping.

Unified remote status (the client must map vendor states to these):
    queued -> running -> done | failed | timed_out | cancelled
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ...schemas.character import CharacterSpec
from ...schemas.vision import VisionImageInput
from ..base import CancellationToken
from .contract import ProviderCapability

REMOTE_STATUSES = ("queued", "running", "done", "failed", "timed_out", "cancelled")


class RemoteTaskError(RuntimeError):
    """Raised by clients when the remote API call itself fails."""


@dataclass
class RemoteTaskInfo:
    task_id: str
    status: str  # one of REMOTE_STATUSES (canonical, already mapped)
    progress: float = 0.0  # 0..1
    message: str = ""
    error: str | None = None
    model_url: str | None = None
    metadata: dict = field(default_factory=dict)


class IRemote3DClient(ABC):
    """Adapter contract implemented by a vendor (or a mock)."""

    id: str = "base-remote"

    def capability(self) -> ProviderCapability:
        """Capability descriptor; default reports an unavailable skeleton."""
        return ProviderCapability(
            mode="cloud",
            gpu_required=False,
            max_references=4,
            output_format="glb",
            supports_cancel=True,
            supports_timeout=True,
            kind="skeleton",
        )

    @abstractmethod
    async def create_task(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        cancel_event: CancellationToken | None = None,
    ) -> RemoteTaskInfo:
        raise NotImplementedError

    @abstractmethod
    async def poll_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> RemoteTaskInfo:
        raise NotImplementedError

    @abstractmethod
    async def cancel_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def download_model(
        self,
        task_id: str,
        model_url: str,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        raise NotImplementedError
