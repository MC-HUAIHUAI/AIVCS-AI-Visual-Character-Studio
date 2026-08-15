"""OfflineFakeVendorClient - fully offline fake vendor (Phase 2.4-C).

Simulates the Tripo-like lifecycle (create -> queued -> running -> done ->
download -> valid GLB) plus failure/rate-limit/invalid-response scenarios.
Deterministic, no network, no key required.

Scenarios: success / failed / timeout / cancelled / invalid / rate_limit
"""

from __future__ import annotations

import asyncio
import uuid

from ...schemas.character import CharacterSpec
from ...schemas.vision import VisionImageInput
from ...services.glb_builder import Primitive, build_glb
from ..base import CancellationToken
from .remote_base import IRemote3DClient, RemoteTaskError, RemoteTaskInfo

_FAKE_GLB = build_glb([Primitive("box", (0.6, 0.6, 0.6), color="#33CC88")])


class OfflineFakeVendorClient(IRemote3DClient):
    id = "tripo-fake"

    def __init__(
        self,
        scenario: str = "success",
        polls_to_finish: int = 2,
        poll_delay: float = 0.01,
        fail_on_create: bool = False,
        rate_limit_after_polls: int | None = None,
    ):
        self.scenario = scenario
        self.polls_to_finish = polls_to_finish
        self.poll_delay = poll_delay
        self.fail_on_create = fail_on_create
        self.rate_limit_after_polls = rate_limit_after_polls
        self._polls: dict[str, int] = {}
        self.cancel_calls: list[str] = []

    async def create_task(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        cancel_event: CancellationToken | None = None,
        runtime_id: str | None = None,
    ) -> RemoteTaskInfo:
        if self.fail_on_create:
            raise RemoteTaskError("create failed (fake vendor)")
        return RemoteTaskInfo(task_id=f"fake_{uuid.uuid4().hex[:8]}", status="queued", progress=0.0)

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

        if self.rate_limit_after_polls is not None and n >= self.rate_limit_after_polls:
            raise RemoteTaskError("429 rate limit (fake vendor)")

        if self.scenario == "failed" and n >= self.polls_to_finish:
            return RemoteTaskInfo(task_id=task_id, status="failed", error="fake vendor failure")
        if self.scenario == "timeout" and n >= self.polls_to_finish:
            return RemoteTaskInfo(task_id=task_id, status="timed_out", error="fake vendor timeout")
        if self.scenario == "cancelled" and n >= self.polls_to_finish:
            return RemoteTaskInfo(task_id=task_id, status="cancelled", message="fake vendor cancelled")
        if n >= self.polls_to_finish:
            return RemoteTaskInfo(
                task_id=task_id,
                status="done",
                progress=1.0,
                message="done",
                model_url=f"fake://models/{task_id}.glb",
            )
        return RemoteTaskInfo(task_id=task_id, status="running", progress=min(0.2 + n * 0.3, 0.9))

    async def cancel_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> None:
        self.cancel_calls.append(task_id)
        self._polls.pop(task_id, None)

    async def download_model(
        self,
        task_id: str,
        model_url: str,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        if self.scenario == "invalid":
            return b"<html>this is not a glb</html>"
        return _FAKE_GLB
