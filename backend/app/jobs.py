"""In-memory generation job + model stores.

Simple, single-process design for Phase 1: jobs run as asyncio tasks and the
resulting GLB bytes live in a dict keyed by model id. A real deployment would
swap these for a DB and object storage; the API surface stays the same.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Awaitable, Callable

from .providers.base import ProgressCallback
from .schemas.character import JobResult, JobStep, JobStatusResponse

Runner = Callable[[ProgressCallback], Awaitable[bytes]]


class JobRecord:
    def __init__(self, job_id: str, provider_name: str):
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

    def to_response(self) -> JobStatusResponse:
        return JobStatusResponse(
            jobId=self.job_id,
            status=self.status,
            progress=round(self.progress, 3),
            message=self.message,
            steps=self.steps,
            error=self.error,
            result=self.result,
        )


_JOBS: dict[str, JobRecord] = {}
_MODELS: dict[str, bytes] = {}


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


async def run_job(job: JobRecord, runner: Runner) -> None:
    job.status = "running"
    job.message = "开始生成…"
    try:
        result_bytes = await runner(lambda i, t, m: _apply_progress(job, i, t, m))
        model_id = str(uuid.uuid4())
        _MODELS[model_id] = result_bytes
        job.result = JobResult(modelId=model_id)
        job.status = "done"
        job.progress = 1.0
        job.message = "生成完成"
        for step in job.steps:
            step.status = "done"
    except Exception as exc:  # noqa: BLE001 - surface any failure to the client
        job.status = "failed"
        job.error = str(exc)
        job.message = str(exc)
    finally:
        job.finished_at = time.time()


def create_job(provider_name: str, runner: Runner) -> JobRecord:
    job = JobRecord(str(uuid.uuid4()), provider_name)
    _JOBS[job.job_id] = job
    asyncio.create_task(run_job(job, runner))
    return job


def get_job(job_id: str) -> JobRecord | None:
    return _JOBS.get(job_id)


def get_model(model_id: str) -> bytes | None:
    return _MODELS.get(model_id)
