"""Tripo adapter scaffold + OfflineFakeVendorClient tests (Phase 2.4-C)."""

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
from backend.app.providers.remote.offline_fake_client import OfflineFakeVendorClient  # noqa: E402
from backend.app.providers.remote.remote_base import RemoteTaskError, RemoteTaskInfo  # noqa: E402
from backend.app.providers.remote.real_ai import RealAIImage3DProvider  # noqa: E402
from backend.app.providers.remote.tripo_client import (  # noqa: E402
    TRIPO_API_KEY_ENV,
    TripoClient,
    TripoTaskDto,
    map_tripo_status,
    multiview_suitability,
    refs_to_tripo_input,
    tripo_error_to_provider_error,
    tripo_task_to_remote_task,
)
from backend.app.providers.registry import REGISTRY  # noqa: E402
from backend.app.providers.remote.remote_base import RemoteTaskError, RemoteTaskInfo  # noqa: E402
from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.schemas.vision import VisionImageInput  # noqa: E402
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


class TripoScaffoldTest(unittest.TestCase):
    def test_without_key_not_configured(self):
        client = TripoClient(api_key="")
        self.assertFalse(client.configured)
        with self.assertRaises(RemoteTaskError) as ctx:
            asyncio.run(client.create_task(make_spec(), []))
        self.assertIn(TRIPO_API_KEY_ENV, str(ctx.exception))

    def test_with_key_raises_not_implemented_without_network(self):
        client = TripoClient(api_key="dummy-key-not-real")
        self.assertTrue(client.configured)
        for call in (
            client.create_task(make_spec(), []),
            client.poll_task("t"),
            client.cancel_task("t"),
            client.download_model("t", "mock://x"),
        ):
            with self.assertRaises(NotImplementedError):
                asyncio.run(call)

    def test_real_tripo_not_registered_without_key(self):
        self.assertNotIn("tripo", REGISTRY)

    def test_status_mapping(self):
        self.assertEqual(map_tripo_status("queued"), "queued")
        self.assertEqual(map_tripo_status("processing"), "running")
        self.assertEqual(map_tripo_status("succeeded"), "done")
        self.assertEqual(map_tripo_status("error"), "failed")
        self.assertEqual(map_tripo_status("timeout"), "timed_out")
        self.assertEqual(map_tripo_status("canceled"), "cancelled")
        self.assertEqual(map_tripo_status("weird"), "unknown")

    def test_task_dto_to_remote_task(self):
        dto = TripoTaskDto(task_id="t1", status="processing", progress=0.6, message="working")
        info = tripo_task_to_remote_task(dto)
        self.assertIsInstance(info, RemoteTaskInfo)
        self.assertEqual(info.task_id, "t1")
        self.assertEqual(info.status, "running")
        self.assertEqual(info.progress, 0.6)

    def test_error_mapping(self):
        class E(Exception):
            def __init__(self, status, msg="x"):
                self.status_code = status
                super().__init__(msg)

        self.assertIsInstance(tripo_error_to_provider_error(E(401)), ProviderError)
        self.assertIn("Key", str(tripo_error_to_provider_error(E(401))))
        self.assertIn("过于频繁", str(tripo_error_to_provider_error(E(429))))
        self.assertIsInstance(tripo_error_to_provider_error(TimeoutError()), ProviderTimeoutError)
        self.assertIsInstance(tripo_error_to_provider_error(E(500)), ProviderError)
        self.assertIn("服务异常", str(tripo_error_to_provider_error(E(500))))


class TripoRefsMappingTest(unittest.TestCase):
    def ref(self, image_id, view):
        return VisionImageInput(imageId=image_id, dataUrl="data:image/png;base64,AA", view=view)

    def test_single_image_maps_to_image_to_model(self):
        payload = refs_to_tripo_input([self.ref("a", "front")])
        self.assertEqual(payload["type"], "image_to_model")
        self.assertEqual(len(payload["images"]), 1)
        self.assertEqual(payload["images"][0]["view"], "front")

    def test_multiview_images_map_to_multiview_to_model(self):
        payload = refs_to_tripo_input([self.ref("a", "front"), self.ref("b", "side"), self.ref("c", "back")])
        self.assertEqual(payload["type"], "multiview_to_model")
        self.assertEqual(len(payload["images"]), 3)
        views = {img["view"] for img in payload["images"]}
        self.assertEqual(views, {"front", "side", "back"})

    def test_multiview_suitability(self):
        self.assertTrue(multiview_suitability(["front", "side", "back"])["usable"])
        self.assertEqual(multiview_suitability(["front", "side", "back"])["task_type"], "multiview_to_model")
        self.assertFalse(multiview_suitability(["front"])["usable"])
        self.assertEqual(multiview_suitability(["front"])["task_type"], "image_to_model")
        self.assertTrue(multiview_suitability(["side", "back"])["usable"])

    def test_custom_does_not_count_as_primary_view(self):
        # front + custom -> only 1 non-custom view -> not Multiview-usable
        r = multiview_suitability(["front", "custom"])
        self.assertFalse(r["usable"])
        self.assertEqual(r["multiview_candidates"], ["front"])

    def test_none_view_defaults_to_front(self):
        r = multiview_suitability([None, "side"])
        self.assertEqual(r["distinct_views"], ["front", "side"])
        self.assertTrue(r["usable"])


class OfflineFakeVendorTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._orig_store = jobs._store
        jobs._store = ModelStore(self.dir)

    def tearDown(self):
        jobs._store = self._orig_store

    def run_provider(self, client, cancel=None, timeout=30):
        provider = RealAIImage3DProvider(client, default_timeout_seconds=timeout)
        return asyncio.run(provider.generate(make_spec(), [], lambda _i, _t, _m: None, cancel))

    def test_success_returns_valid_glb(self):
        data = self.run_provider(OfflineFakeVendorClient(scenario="success"))
        validate_glb(data)

    def test_failed_maps_to_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(OfflineFakeVendorClient(scenario="failed"))
        self.assertIn("fake vendor failure", str(ctx.exception))

    def test_timeout_maps_to_provider_timeout(self):
        with self.assertRaises(ProviderTimeoutError):
            self.run_provider(OfflineFakeVendorClient(scenario="timeout"))

    def test_cancelled_maps_to_provider_cancelled(self):
        with self.assertRaises(ProviderCancelledError):
            self.run_provider(OfflineFakeVendorClient(scenario="cancelled"))

    def test_invalid_response_rejected(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(OfflineFakeVendorClient(scenario="invalid"))
        self.assertIn("不是合法 GLB", str(ctx.exception))

    def test_rate_limit_maps_to_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_provider(OfflineFakeVendorClient(scenario="success", rate_limit_after_polls=1))
        self.assertIn("轮询远程任务失败", str(ctx.exception))

    def test_user_cancel_calls_cancel_task_and_cancelled(self):
        client = OfflineFakeVendorClient(scenario="success", poll_delay=0.5)
        provider = RealAIImage3DProvider(client, default_timeout_seconds=30)
        token = CancellationToken()

        async def scenario():
            task = asyncio.create_task(provider.generate(make_spec(), [], lambda _i, _t, _m: None, token))
            await asyncio.sleep(0.1)
            token.cancel()
            with self.assertRaises(ProviderCancelledError):
                await task

        asyncio.run(scenario())
        self.assertTrue(client.cancel_calls)

    def test_job_done_with_model_store(self):
        async def scenario():
            provider = RealAIImage3DProvider(OfflineFakeVendorClient(scenario="success"))
            spec = make_spec()
            job = jobs.create_job("tripo-fake", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "done")
            validate_glb(jobs.get_model(final.result.model_id))
        asyncio.run(scenario())

    def test_job_failed_with_model_store_empty(self):
        async def scenario():
            provider = RealAIImage3DProvider(OfflineFakeVendorClient(scenario="failed"))
            spec = make_spec()
            job = jobs.create_job("tripo-fake", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "failed")
            self.assertTrue(final.retryable)
            self.assertIsNone(final.result)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
