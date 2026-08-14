"""RealAI image-to-3d provider - vendor-agnostic adapter (Phase 2.4-A/B).

Implements the AIImage3DProvider contract by driving any IRemote3DClient
through a unified remote-task flow:

    create task -> poll (canonical state mapping + local deadline) -> download
    GLB -> validate -> return bytes (the JobManager persists via ModelStore).

Remote state mapping to job outcomes:
    done       -> download + validate
    failed     -> ProviderError            -> job failed
    timed_out  -> ProviderTimeoutError     -> job timed_out
    cancelled  -> ProviderCancelledError   -> job cancelled
    queued/running -> keep polling
    user cancel (cancel_event) -> best-effort client.cancel_task THEN
                                  ProviderCancelledError -> job cancelled
    local deadline exceeded -> best-effort cancel + ProviderTimeoutError
                               -> job timed_out

No auto-retry; cancel_task is invoked at most once per run; a failing
cancel_task never masks the user's cancel intent.
"""

from __future__ import annotations

import asyncio
import time

from ..base import (
    AIImage3DProvider,
    CancellationToken,
    ProgressCallback,
    ProviderCancelledError,
    ProviderError,
    ProviderTimeoutError,
)
from ...schemas.character import CharacterSpec
from ...schemas.vision import VisionImageInput
from ...services.glb_builder import validate_glb
from .remote_base import IRemote3DClient, RemoteTaskError

STEPS = ["创建远程任务", "等待远程任务", "下载 GLB", "校验 GLB", "完成"]

# Upper bound for a single remote poll (the overall job deadline still applies
# via the JobManager; this guards a single hung poll call).
POLL_ATTEMPT_TIMEOUT_SECONDS = 60.0


class RealAIImage3DProvider(AIImage3DProvider):
    id = "real-ai"
    name = "Real AI (adapter)"
    description = "通用云端 Image-to-3D 适配器（未绑定厂商；注入 IRemote3DClient 使用）。"

    gpu_required = False
    max_references = 4
    output_format = "glb"
    supports_cancel = True
    supports_timeout = True

    def __init__(
        self,
        client: IRemote3DClient,
        provider_id: str | None = None,
        provider_name: str | None = None,
        description: str | None = None,
        default_timeout_seconds: float = 600.0,
    ):
        self.client = client
        self._default_timeout_seconds = default_timeout_seconds
        if provider_id:
            self.id = provider_id
        if provider_name:
            self.name = provider_name
        if description:
            self.description = description

    async def generate(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        on_progress: ProgressCallback,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        total = len(STEPS)
        notified = False

        async def notify_cancel_remote(task_id: str | None) -> None:
            """Best-effort remote cancel; called at most once per run. Never
            raises - the caller's cancellation semantics always win."""
            nonlocal notified
            if notified or task_id is None:
                return
            notified = True
            try:
                await self.client.cancel_task(task_id, cancel_event)
            except Exception:  # noqa: BLE001 - do not mask user cancel intent
                pass

        async def check_cancel(task_id: str | None = None) -> None:
            if cancel_event is not None and cancel_event.is_cancelled:
                await notify_cancel_remote(task_id)
                raise ProviderCancelledError("已取消")

        # 1) create task
        await check_cancel()
        try:
            info = await self.client.create_task(spec, references, cancel_event)
        except RemoteTaskError as exc:
            raise ProviderError(f"创建远程任务失败：{exc}") from exc
        on_progress(1, total, f"已创建远程任务 {info.task_id}")

        # 2) poll with unified mapping + local deadline + per-poll timeout
        deadline = time.monotonic() + self._default_timeout_seconds
        while info.status in ("queued", "running"):
            await check_cancel(info.task_id)

            if time.monotonic() > deadline:
                await notify_cancel_remote(info.task_id)
                raise ProviderTimeoutError("生成超时")

            poll_timeout = min(max(deadline - time.monotonic(), 0.1), POLL_ATTEMPT_TIMEOUT_SECONDS)
            try:
                info = await asyncio.wait_for(
                    self.client.poll_task(info.task_id, cancel_event), timeout=poll_timeout
                )
            except TimeoutError:
                await notify_cancel_remote(info.task_id)
                raise ProviderTimeoutError("生成超时") from None
            except RemoteTaskError as exc:
                raise ProviderError(f"轮询远程任务失败：{exc}") from exc

            on_progress(1, total, f"远程任务 {info.status}：{info.message or info.status}")

        if info.status == "failed":
            raise ProviderError(info.error or "远程任务失败")
        if info.status == "timed_out":
            raise ProviderTimeoutError(info.error or "远程任务超时")
        if info.status == "cancelled":
            raise ProviderCancelledError(info.error or "远程任务已取消")
        if info.status != "done":
            raise ProviderError(f"未知远程状态：{info.status}")

        # 3) download GLB
        on_progress(2, total, "下载 GLB")
        try:
            data = await self.client.download_model(info.task_id, info.model_url or "", cancel_event)
        except RemoteTaskError as exc:
            raise ProviderError(f"下载模型失败：{exc}") from exc

        # 4) validate GLB
        on_progress(3, total, "校验 GLB")
        try:
            validate_glb(data)
        except ValueError as exc:
            raise ProviderError(f"远程模型不是合法 GLB：{exc}") from exc

        # 5) hand back bytes (JobManager persists via ModelStore)
        on_progress(total, total, "生成完成")
        return data
