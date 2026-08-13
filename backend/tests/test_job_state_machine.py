"""Job state machine tests (Phase 2.3-A).

Covers: queued->done, queued->running->done, queued cancel, running cancel,
timeout->timed_out, provider error->failed+retryable, safe error mapping,
and successful generation still returning the demo GLB via the Mock provider.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import backend.app.jobs as jobs  # noqa: E402
from backend.app import config  # noqa: E402
from backend.app.providers.base import ProviderCancelledError, ProviderError  # noqa: E402
from backend.app.providers.mock import MockImage3DProvider  # noqa: E402
from backend.app.schemas.character import CharacterSpec  # noqa: E402


async def wait_terminal(job_id: str, timeout: float = 8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get_job(job_id)
        if job.status in ("done", "failed", "timed_out", "cancelled"):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("job did not reach a terminal state")


async def ok_runner(cb, cancel):
    for i in range(3):
        cb(i, 3, f"step{i}")
        await asyncio.sleep(0.02)
    cb(3, 3, "done")
    return b"GLB_OK"


async def slow_runner(cb, cancel):
    for i in range(200):
        cb(i, 200, f"s{i}")
        if cancel.is_cancelled:
            raise ProviderCancelledError("cancelled")
        await asyncio.sleep(0.05)
    return b"GLB"


async def boom_runner(cb, cancel):
    cb(0, 1, "start")
    await asyncio.sleep(0.01)
    raise ProviderError("boom")


def make_spec(character_type="human", user_notes=""):
    return CharacterSpec(
        id="s",
        name="t",
        style="stylized",
        gender="female",
        heightCm=160,
        description="",
        referenceImageIds=[],
        tags=[],
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:00Z",
        characterType=character_type,
        userNotes=user_notes,
    )


class JobStateMachineTest(unittest.TestCase):
    def test_queued_to_done(self):
        async def scenario():
            job = jobs.create_job("mock", ok_runner)
            self.assertEqual(job.status, "queued")
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "done")
            self.assertIsNotNone(final.result)
            self.assertEqual(jobs.get_model(final.result.model_id), b"GLB_OK")
            self.assertFalse(final.retryable)
            self.assertFalse(final.timed_out)
            self.assertFalse(final.cancelled_by_user)
            self.assertIsNotNone(final.duration_ms)
        asyncio.run(scenario())

    def test_queued_running_done(self):
        async def scenario():
            job = jobs.create_job("mock", ok_runner)
            seen_running = False
            for _ in range(500):
                if job.status == "running":
                    seen_running = True
                if job.status == "done":
                    break
                if job.status in ("failed", "timed_out", "cancelled"):
                    break
                await asyncio.sleep(0.01)
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "done")
            self.assertTrue(seen_running)
        asyncio.run(scenario())

    def test_queued_cancel(self):
        async def scenario():
            job = jobs.create_job("mock", slow_runner)
            self.assertTrue(jobs.cancel_job(job.job_id))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "cancelled")
            self.assertTrue(final.cancelled_by_user)
            self.assertFalse(final.timed_out)
        asyncio.run(scenario())

    def test_running_cancel(self):
        async def scenario():
            job = jobs.create_job("mock", slow_runner)
            for _ in range(500):
                if job.status == "running":
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(job.status, "running")
            self.assertTrue(jobs.cancel_job(job.job_id))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "cancelled")
            self.assertTrue(final.cancelled_by_user)
        asyncio.run(scenario())

    def test_cancel_after_terminal_returns_false(self):
        async def scenario():
            job = jobs.create_job("mock", ok_runner)
            await wait_terminal(job.job_id)
            self.assertFalse(jobs.cancel_job(job.job_id))
            self.assertIsNone(jobs.cancel_job("does-not-exist"))
        asyncio.run(scenario())

    def test_timeout_timed_out(self):
        async def scenario():
            job = jobs.create_job("mock", slow_runner, timeout_seconds=0.1)
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "timed_out")
            self.assertTrue(final.timed_out)
            self.assertTrue(final.retryable)
            self.assertFalse(final.cancelled_by_user)
        asyncio.run(scenario())

    def test_provider_error_failed_retryable(self):
        async def scenario():
            job = jobs.create_job("mock", boom_runner)
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "failed")
            self.assertTrue(final.retryable)
            self.assertEqual(final.error, "boom")
            self.assertFalse(final.timed_out)
        asyncio.run(scenario())

    def test_generic_error_is_sanitized(self):
        async def scenario():
            async def bad_runner(cb, cancel):
                raise RuntimeError("sensitive internal detail")
            job = jobs.create_job("mock", bad_runner)
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "failed")
            self.assertNotIn("sensitive", final.error)
        asyncio.run(scenario())

    def test_mock_success_returns_demo_glb(self):
        async def scenario():
            old = config.MOCK3D_DURATION_SECONDS
            config.MOCK3D_DURATION_SECONDS = 0.02
            try:
                provider = MockImage3DProvider()
                spec = make_spec()
                job = jobs.create_job(
                    "mock",
                    lambda cb, cancel: provider.generate(spec, [], cb, cancel),
                )
                final = await wait_terminal(job.job_id)
                self.assertEqual(final.status, "done")
                data = jobs.get_model(final.result.model_id)
                self.assertEqual(data, config.DEMO_MODEL_PATH.read_bytes())
                self.assertEqual(len(data), 111857)
            finally:
                config.MOCK3D_DURATION_SECONDS = old
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
