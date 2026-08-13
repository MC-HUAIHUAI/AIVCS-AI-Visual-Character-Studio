"""Generation job manager (Phase 2.3-A).

In-memory, single-process design. Job state machine:

    queued -> running -> done | failed | timed_out | cancelled
    queued -> cancelled | timed_out

Rules:
- No auto-retry and no retry loop; "retry" means creating a new job.
- `timed_out` and `failed` are distinct terminal states; `cancelled` and
  `timed_out` are distinct terminal states.
- Provider errors are surfaced to the client through user-safe messages only.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Awaitable, Callable

from .providers.base import CancellationToken, ProgressCallback, ProviderCancelledError, ProviderError, ProviderTimeoutError
from .schemas.character import JobResult, JobStep, JobStatusResponse
from .services.model_store import ModelRecord, ModelStore

Runner = Callable[[ProgressCallback, CancellationToken], Awaitable[bytes]]


class JobRecord:
    def __init__(
        self,
        job_id: str,
        provider_name: str,
        deadline_at: float | None = None,
        attempt: int = 1,
        spec_hash: str = "",
    ):
        self.job_id = job_id
        self.provider_name = provider_name
        self.status = "queued"
        self.progress = 0.0
        self.message = "排队中"
        self.steps: list[JobStep] = []
        self.error: str | None = None
        self.result: JobResult | None = None
        self.created_at = time.time()
        self.finished_at: float | None = None
        self.deadline_at: float | None = deadline_at
        self.duration_ms: int | None = None
        self.retryable = False
        self.cancelled_by_user = False
        self.timed_out = False
        self.attempt = attempt
        self.spec_hash = spec_hash
        self.cancel_token = CancellationToken()

    def to_response(self) -> JobStatusResponse:
        return JobStatusResponse(
            jobId=self.job_id,
            status=self.status,
            progress=round(self.progress, 3),
            message=self.message,
            steps=self.steps,
            error=self.error,
            result=self.result,
            deadlineAt=self.deadline_at,
            durationMs=self.duration_ms,
            retryable=self.retryable,
            cancelledByUser=self.cancelled_by_user,
            timedOut=self.timed_out,
            attempt=self.attempt,
        )


_JOBS: dict[str, JobRecord] = {}
_TASKS: dict[str, asyncio.Task] = {}
_store: ModelStore = ModelStore()


def _apply_progress(job: JobRecord, index: int, total: int, message: str) -> None:
    job.progress = min(max(index / total if total else 0, 0.0), 1.0)
    job.message = message
    if total != len(job.steps):
        job.steps = [JobStep(index=i, label=f"步骤 {i + 1}", status="pending") for i in range(total)]
    for i, step in enumerate(job.steps):
        if index >= total:
            step.status = "done"
        elif i < index:
            step.status = "done"
        elif i == index:
            step.status = "running"
            step.label = message
        else:
            step.status = "pending"


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, ProviderError):
        return str(exc)
    return "生成失败，请稍后重试"


async def run_job(job: JobRecord, runner: Runner) -> None:
    if job.status == "cancelled" or job.cancel_token.is_cancelled:
        job.status = "cancelled"
        job.cancelled_by_user = True
        job.message = "已取消"
        job.finished_at = time.time()
        job.duration_ms = 0
        return

    job.status = "running"
    job.message = "开始生成…"
    started = time.time()
    try:
        coro = runner(lambda i, t, m: _apply_progress(job, i, t, m), job.cancel_token)
        if job.deadline_at is not None:
            remaining = max(job.deadline_at - time.time(), 0.001)
            result_bytes = await asyncio.wait_for(coro, timeout=remaining)
        else:
            result_bytes = await coro
    except TimeoutError:
        job.status = "timed_out"
        job.timed_out = True
        job.retryable = True
        job.error = "生成超时"
        job.message = "生成超时"
    except ProviderTimeoutError:
        job.status = "timed_out"
        job.timed_out = True
        job.retryable = True
        job.error = "生成超时"
        job.message = "生成超时"
    except asyncio.CancelledError:
        job.status = "cancelled"
        job.cancelled_by_user = True
        job.message = "已取消"
    except ProviderCancelledError:
        job.status = "cancelled"
        job.cancelled_by_user = True
        job.message = "已取消"
    except Exception as exc:  # noqa: BLE001 - surface any failure safely
        job.status = "failed"
        job.retryable = True
        job.error = _safe_error(exc)
        job.message = job.error
    else:
        record = _store.save(
            result_bytes,
            provider_id=job.provider_name,
            source_job_id=job.job_id,
            spec_hash=job.spec_hash,
        )
        job.result = JobResult(
            modelId=record.id,
            format=record.format,
            mime=record.mime,
            sizeBytes=record.size_bytes,
            providerId=record.provider_id,
            sourceJobId=record.source_job_id,
        )
        job.status = "done"
        job.progress = 1.0
        job.message = "生成完成"
        for step in job.steps:
            step.status = "done"
    finally:
        job.finished_at = time.time()
        job.duration_ms = int((job.finished_at - started) * 1000)
        _TASKS.pop(job.job_id, None)


def create_job(
    provider_name: str,
    runner: Runner,
    timeout_seconds: float | None = None,
    attempt: int = 1,
    spec_hash: str = "",
) -> JobRecord:
    deadline = time.time() + timeout_seconds if timeout_seconds else None
    job = JobRecord(str(uuid.uuid4()), provider_name, deadline_at=deadline, attempt=attempt, spec_hash=spec_hash)
    _JOBS[job.job_id] = job
    _TASKS[job.job_id] = asyncio.create_task(run_job(job, runner))
    return job


def cancel_job(job_id: str) -> bool | None:
    """Request cancellation. Returns None if the job is unknown, False if it is
    already terminal, True when the cancellation was requested."""
    job = _JOBS.get(job_id)
    if job is None:
        return None
    if job.status not in ("queued", "running"):
        return False
    job.cancel_token.cancel()
    job.cancelled_by_user = True
    if job.status == "queued":
        # Not started yet - transition directly; a late-starting task will see
        # the cancelled token/status in run_job and stay cancelled.
        job.status = "cancelled"
        job.message = "已取消"
        job.finished_at = time.time()
        job.duration_ms = 0
        task = _TASKS.pop(job_id, None)
        if task is not None:
            task.cancel()
        return True
    task = _TASKS.get(job_id)
    if task is not None:
        task.cancel()
    return True


def get_job(job_id: str) -> JobRecord | None:
    return _JOBS.get(job_id)


def get_model(model_id: str) -> bytes | None:
    return _store.read_bytes(model_id)


def get_model_record(model_id: str) -> ModelRecord | None:
    return _store.get(model_id)
