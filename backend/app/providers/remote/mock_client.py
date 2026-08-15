"""Mock remote 3D client - deterministic vendor simulation (Phase 2.4-A).

Simulates the "create task -> poll -> download GLB" lifecycle of a real cloud
image-to-3d vendor. Scenarios cover every remote path:

    success / remote_failure / remote_timeout / invalid_glb / cancelled
"""

from __future__ import annotations

import asyncio
import json
import uuid

from ...schemas.character import CharacterSpec
from ...schemas.vision import VisionImageInput
from ...services.glb_builder import Primitive, build_glb
from ..base import CancellationToken
from .contract import ProviderCapability
from .remote_base import IRemote3DClient, RemoteTaskError, RemoteTaskInfo

_MOCK_GLB = build_glb([Primitive("box", (0.5, 0.5, 0.5), color="#4466AA")])


class MockRemote3DClient(IRemote3DClient):
    id = "mock-remote"

    def __init__(
        self,
        scenario: str = "success",
        polls_to_finish: int = 3,
        poll_delay: float = 0.01,
        create_error: bool = False,
    ):
        self.scenario = scenario
        self.polls_to_finish = polls_to_finish
        self.poll_delay = poll_delay
        self.create_error = create_error
        self._polls: dict[str, int] = {}

    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            mode="cloud",
            gpu_required=False,
            max_references=4,
            output_format="glb",
            supports_cancel=True,
            supports_timeout=True,
            kind="mock",
        )

    async def create_task(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        cancel_event: CancellationToken | None = None,
        runtime_id: str | None = None,
    ) -> RemoteTaskInfo:
        if self.create_error:
            raise RemoteTaskError("create failed (mock)")
        return RemoteTaskInfo(task_id=f"task_{uuid.uuid4().hex[:8]}", status="queued", progress=0.0)

    async def poll_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> RemoteTaskInfo:
        if cancel_event is not None and cancel_event.is_cancelled:
            return RemoteTaskInfo(task_id=task_id, status="cancelled", message="cancelled by user")
        await asyncio.sleep(self.poll_delay)
        n = self._polls.get(task_id, 0)
        self._polls[task_id] = n + 1

        if self.scenario == "remote_failure" and n >= self.polls_to_finish:
            return RemoteTaskInfo(task_id=task_id, status="failed", progress=0.5, error="远程任务失败（模拟）")
        if self.scenario == "remote_timeout" and n >= self.polls_to_finish:
            return RemoteTaskInfo(task_id=task_id, status="timed_out", progress=0.6, error="远程任务超时（模拟）")
        if n >= self.polls_to_finish:
            return RemoteTaskInfo(
                task_id=task_id,
                status="done",
                progress=1.0,
                message="done",
                model_url=f"mock://models/{task_id}.glb",
            )
        return RemoteTaskInfo(task_id=task_id, status="running", progress=min(0.2 + n * 0.2, 0.9))

    async def cancel_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> None:
        self._polls.pop(task_id, None)

    async def download_model(
        self,
        task_id: str,
        model_url: str,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        if self.scenario == "invalid_glb":
            return b"this is not a glb at all"
        return _MOCK_GLB
