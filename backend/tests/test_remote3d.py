"""RealAIImage3DProvider / MockRemote3DClient tests (Phase 2.4-A)."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import backend.app.jobs as jobs  # noqa: E402
from backend.app.providers.base import CancellationToken, ProviderCancelledError, ProviderError, ProviderTimeoutError  # noqa: E402
from backend.app.providers.remote.mock_client import MockRemote3DClient  # noqa: E402
from backend.app.providers.remote.mock_provider import MockRemote3DProvider  # noqa: E402
from backend.app.providers.remote.real_ai import RealAIImage3DProvider  # noqa: E402
from backend.app.providers.registry import REGISTRY  # noqa: E402
from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.services.glb_builder import validate_glb  # noqa: E402
from backend.app.services.model_store import ModelStore  # noqa: E402


def make_spec():
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
    )


async def wait_terminal(job_id, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get_job(job_id)
        if job.status in ("done", "failed", "timed_out", "cancelled"):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("not terminal")


class RemotePipelineTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._orig_store = jobs._store
        jobs._store = ModelStore(self.dir)

    def tearDown(self):
        jobs._store = self._orig_store

    def run_provider(self, client, spec=None, cancel=None, timeout=30):
        provider = RealAIImage3DProvider(client, default_timeout_seconds=timeout)
        return asyncio.run(provider.generate(spec or make_spec(), [], lambda _i, _t, _m: None, cancel))

    def test_success_returns_valid_glb(self):
        data = self.run_provider(MockRemote3DClient(scenario="success"))
        validate_glb(data)  # no raise

    def test_remote_failure_maps_to_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(MockRemote3DClient(scenario="remote_failure"))
        self.assertIn("远程任务失败", str(ctx.exception))

    def test_remote_timeout_maps_to_provider_timeout(self):
        with self.assertRaises(ProviderTimeoutError):
            self.run_provider(MockRemote3DClient(scenario="remote_timeout"))

    def test_remote_cancelled_maps_to_cancelled(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(ProviderCancelledError):
            self.run_provider(MockRemote3DClient(scenario="success"), cancel=token)

    def test_invalid_glb_rejected(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(MockRemote3DClient(scenario="invalid_glb"))
        self.assertIn("不是合法 GLB", str(ctx.exception))

    def test_create_error_maps_to_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(MockRemote3DClient(scenario="success", create_error=True))
        self.assertIn("创建远程任务失败", str(ctx.exception))

    def test_local_timeout(self):
        client = MockRemote3DClient(scenario="success", polls_to_finish=100, poll_delay=0.1)
        with self.assertRaises(ProviderTimeoutError):
            self.run_provider(client, timeout=0.05)

    def test_job_done_with_model_store(self):
        async def scenario():
            provider = MockRemote3DProvider(scenario="success")
            spec = make_spec()
            job = jobs.create_job("mock-remote", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "done")
            data = jobs.get_model(final.result.model_id)
            validate_glb(data)
            self.assertIsNotNone(jobs.get_model_record(final.result.model_id))
        asyncio.run(scenario())

    def test_job_remote_failure_failed(self):
        async def scenario():
            provider = MockRemote3DProvider(scenario="remote_failure")
            spec = make_spec()
            job = jobs.create_job("mock-remote", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "failed")
            self.assertTrue(final.retryable)
        asyncio.run(scenario())

    def test_job_remote_timeout_timed_out(self):
        async def scenario():
            provider = MockRemote3DProvider(scenario="remote_timeout")
            spec = make_spec()
            job = jobs.create_job("mock-remote", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "timed_out")
            self.assertTrue(final.timed_out)
            self.assertTrue(final.retryable)
        asyncio.run(scenario())

    def test_registry_has_mock_remote(self):
        self.assertIn("mock-remote", REGISTRY)
        self.assertEqual(REGISTRY["mock-remote"].id, "mock-remote")

    def test_mock_remote_provider_capabilities(self):
        provider = MockRemote3DProvider()
        self.assertFalse(provider.gpu_required)
        self.assertEqual(provider.max_references, 4)
        self.assertTrue(provider.supports_cancel)
        self.assertTrue(provider.supports_timeout)


if __name__ == "__main__":
    unittest.main()
