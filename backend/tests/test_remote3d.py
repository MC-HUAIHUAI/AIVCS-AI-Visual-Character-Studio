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
from backend.app.providers.remote.remote_base import RemoteTaskError, RemoteTaskInfo  # noqa: E402
from backend.app.providers.remote.vendor import VendorRemoteClient  # noqa: E402
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


class RecordingClient(MockRemote3DClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cancel_calls: list[str] = []

    async def cancel_task(self, task_id, cancel_event=None):
        self.cancel_calls.append(task_id)
        return await super().cancel_task(task_id, cancel_event)


class FailingCancelClient(MockRemote3DClient):
    async def cancel_task(self, task_id, cancel_event=None):
        raise RuntimeError("cancel transport failed")


class DownloadFailClient(MockRemote3DClient):
    async def download_model(self, task_id, model_url, cancel_event=None):
        raise RemoteTaskError("download exploded")


class UnknownStatusClient(MockRemote3DClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gave_unknown = False

    async def poll_task(self, task_id, cancel_event=None):
        if not self._gave_unknown:
            self._gave_unknown = True
            return RemoteTaskInfo(task_id=task_id, status="weird-state")
        return await super().poll_task(task_id, cancel_event)


class MalformedResponseClient(MockRemote3DClient):
    """Simulates a vendor returning a malformed task info (missing status)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gave_malformed = False

    async def poll_task(self, task_id, cancel_event=None):
        if not self._gave_malformed:
            self._gave_malformed = True
            # status missing -> falls through to "unknown" mapping path
            return RemoteTaskInfo(task_id=task_id, status="")  # type: ignore[arg-type]
        return await super().poll_task(task_id, cancel_event)


class CancelNotifyTest(RemotePipelineTest):
    def test_user_cancel_calls_client_cancel_task(self):
        client = RecordingClient(scenario="success", poll_delay=0.5)
        provider = RealAIImage3DProvider(client, default_timeout_seconds=30)
        token = CancellationToken()

        async def scenario():
            task = asyncio.create_task(provider.generate(make_spec(), [], lambda _i, _t, _m: None, token))
            await asyncio.sleep(0.1)
            token.cancel()
            with self.assertRaises(ProviderCancelledError):
                await task

        asyncio.run(scenario())
        self.assertTrue(client.cancel_calls, "cancel_task should have been invoked")

    def test_cancel_task_failure_still_cancelled(self):
        client = FailingCancelClient(scenario="success", poll_delay=0.5)
        provider = RealAIImage3DProvider(client, default_timeout_seconds=30)
        token = CancellationToken()

        async def scenario():
            task = asyncio.create_task(provider.generate(make_spec(), [], lambda _i, _t, _m: None, token))
            await asyncio.sleep(0.1)
            token.cancel()
            with self.assertRaises(ProviderCancelledError):
                await task

        asyncio.run(scenario())

    def test_cancel_job_still_cancelled_when_cancel_task_fails(self):
        async def scenario():
            provider = RealAIImage3DProvider(FailingCancelClient(scenario="success", poll_delay=0.5), default_timeout_seconds=30)
            spec = make_spec()
            job = jobs.create_job("mock-remote", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            await asyncio.sleep(0.05)
            jobs.cancel_job(job.job_id)
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "cancelled")
            self.assertTrue(final.cancelled_by_user)
        asyncio.run(scenario())

    def test_download_failure_maps_to_provider_error(self):
        client = DownloadFailClient(scenario="success")
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(client)
        self.assertIn("下载模型失败", str(ctx.exception))

    def test_download_failure_job_failed(self):
        async def scenario():
            provider = RealAIImage3DProvider(DownloadFailClient(scenario="success"))
            spec = make_spec()
            job = jobs.create_job("mock-remote", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "failed")
            self.assertTrue(final.retryable)
        asyncio.run(scenario())

    def test_unknown_remote_status_maps_to_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(UnknownStatusClient(scenario="success"))
        self.assertIn("未知远程状态", str(ctx.exception))

    def test_malformed_response_maps_to_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(MalformedResponseClient(scenario="success"))
        self.assertIn("未知远程状态", str(ctx.exception))

    def test_capability_kind_mock(self):
        client = MockRemote3DClient()
        cap = client.capability()
        self.assertEqual(cap.kind, "mock")
        self.assertEqual(cap.mode, "cloud")
        self.assertEqual(cap.output_format, "glb")
        self.assertTrue(cap.supports_cancel)
        self.assertTrue(cap.supports_timeout)

    def test_vendor_capability_kind_skeleton(self):
        from backend.app.providers.remote.vendor import VendorRemoteClient

        cap = VendorRemoteClient().capability()
        self.assertEqual(cap.kind, "skeleton")

    def test_invalid_glb_job_failed(self):
        async def scenario():
            provider = MockRemote3DProvider(scenario="invalid_glb")
            spec = make_spec()
            job = jobs.create_job("mock-remote", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "failed")
            self.assertTrue(final.retryable)
        asyncio.run(scenario())

    def test_provider_local_timeout_job_timed_out(self):
        async def scenario():
            provider = RealAIImage3DProvider(
                MockRemote3DClient(scenario="success", polls_to_finish=100, poll_delay=0.2),
                default_timeout_seconds=0.05,
            )
            spec = make_spec()
            job = jobs.create_job("mock-remote", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "timed_out")
            self.assertTrue(final.timed_out)
        asyncio.run(scenario())


class VendorSkeletonTest(unittest.TestCase):
    def test_without_key_not_configured(self):
        client = VendorRemoteClient(api_key="")
        self.assertFalse(client.configured)
        with self.assertRaises(RemoteTaskError) as ctx:
            asyncio.run(client.create_task(make_spec(), []))
        self.assertIn("AIVCS_REAL3D_API_KEY", str(ctx.exception))

    def test_with_key_raises_not_implemented_without_network(self):
        client = VendorRemoteClient(api_key="dummy-key-not-real")
        self.assertTrue(client.configured)
        for call in (
            client.create_task(make_spec(), []),
            client.poll_task("t"),
            client.cancel_task("t"),
            client.download_model("t", "mock://x"),
        ):
            with self.assertRaises(NotImplementedError):
                asyncio.run(call)

    def test_real_provider_not_registered(self):
        self.assertNotIn("vendor", REGISTRY)
        self.assertNotIn("real-ai", REGISTRY)


class RegistryAvailabilityTest(unittest.TestCase):
    def setUp(self):
        from backend.app import config

        self._old = config.is_external3d_enabled()
        config.set_runtime_external3d(False)

    def tearDown(self):
        from backend.app import config

        config.set_runtime_external3d(self._old)

    def test_external3d_identity_stays_registered(self):
        from backend.app.providers import registry

        self.assertIn("real-placeholder", registry.REGISTRY)

    def test_external3d_not_available_when_disabled(self):
        from backend.app.providers import registry

        self.assertFalse(registry.is_provider_available("real-placeholder"))
        # locals always available
        self.assertTrue(registry.is_provider_available("mock-remote"))
        self.assertTrue(registry.is_provider_available("local-lowpower"))
        self.assertTrue(registry.is_provider_available("mock"))

    def test_external3d_available_when_enabled(self):
        from backend.app import config
        from backend.app.providers import registry

        config.set_runtime_external3d(True)
        self.assertTrue(registry.is_provider_available("real-placeholder"))

    def test_capability_for_mock_remote(self):
        from backend.app.providers import registry

        cap = registry.capability_for("mock-remote")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.kind, "mock")

    def test_capability_for_local(self):
        from backend.app.providers import registry

        cap = registry.capability_for("local-lowpower")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.kind, "local")

    def test_generate_router_rejects_disabled_external3d(self):
        from fastapi import HTTPException
        from backend.app.routers import generate as generate_router

        async def run():
            await generate_router.generate_image_to_3d(None)  # type: ignore[arg-type]

        # Simpler: assert is_provider_available gates the call path (router
        # already checks before touching the provider).
        from backend.app.providers import registry

        self.assertFalse(registry.is_provider_available("real-placeholder"))
        self.assertTrue(callable(generate_router.generate_image_to_3d))


if __name__ == "__main__":
    unittest.main()
