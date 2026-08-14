"""ModelStore <- GLB analyzer integration tests (Phase 2.5-B)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import backend.app.jobs as jobs  # noqa: E402
from backend.app import config  # noqa: E402
from backend.app.providers.local_lowpower import LocalLowPower3DProvider  # noqa: E402
from backend.app.providers.mock import MockImage3DProvider  # noqa: E402
from backend.app.schemas.asset import GlbStats  # noqa: E402
from backend.app.schemas.character import CharacterSpec, ModelMetaResponse  # noqa: E402
from backend.app.services.glb_analyzer import analyze_glb  # noqa: E402
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


class ModelAnalyzerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._orig_store = jobs._store
        jobs._store = ModelStore(self.dir)
        self._old_duration = config.MOCK3D_DURATION_SECONDS
        config.MOCK3D_DURATION_SECONDS = 0.02

    def tearDown(self):
        jobs._store = self._orig_store
        config.MOCK3D_DURATION_SECONDS = self._old_duration

    def run_mock_job(self, provider):
        async def scenario():
            spec = make_spec()
            job = jobs.create_job("mock", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            return final

        return asyncio.run(scenario())

    def test_mock_generation_writes_stats(self):
        final = self.run_mock_job(MockImage3DProvider())
        self.assertEqual(final.status, "done")
        data = jobs.get_model(final.result.model_id)
        record = jobs.get_model_record(final.result.model_id)
        self.assertIsNotNone(record.stats)
        # stats equal direct analyzer output
        self.assertEqual(record.stats, asdict(analyze_glb(data)))
        # JobResult carries stats
        self.assertIsNotNone(final.result.stats)

    def test_local_lowpower_writes_stats(self):
        final = self.run_mock_job(LocalLowPower3DProvider())
        self.assertEqual(final.status, "done")
        record = jobs.get_model_record(final.result.model_id)
        self.assertIsNotNone(record.stats)
        self.assertGreater(record.stats["meshCount"], 0)

    def test_old_sidecar_without_stats_still_readable(self):
        store = jobs._store
        rec = store.save(b"GLB", "mock", "j", "h")
        # strip stats from the sidecar to simulate an old record
        meta = store._meta_path(rec.id)
        data = json.loads(meta.read_text(encoding="utf-8"))
        data.pop("stats", None)
        data.pop("normalizations", None)
        meta.write_text(json.dumps(data), encoding="utf-8")
        loaded = store.get(rec.id)
        self.assertIsNone(loaded.stats)
        self.assertEqual(store.read_bytes(rec.id), b"GLB")

    def test_analyzer_failure_does_not_fail_job(self):
        async def scenario():
            provider = MockImage3DProvider()
            spec = make_spec()
            with mock.patch("backend.app.jobs.analyze_glb", side_effect=ValueError("boom")):
                job = jobs.create_job("mock", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
                final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "done")
            record = jobs.get_model_record(final.result.model_id)
            self.assertIsNone(record.stats)
            self.assertEqual(jobs.get_model(final.result.model_id), config.DEMO_MODEL_PATH.read_bytes())

        asyncio.run(scenario())

    def test_restart_reads_stats(self):
        final = self.run_mock_job(MockImage3DProvider())
        record = jobs.get_model_record(final.result.model_id)
        store2 = ModelStore(self.dir)  # simulates backend restart
        loaded = store2.get(record.id)
        self.assertEqual(loaded.stats, record.stats)
        self.assertEqual(store2.read_bytes(record.id), config.DEMO_MODEL_PATH.read_bytes())

    def test_model_meta_response_with_stats(self):
        final = self.run_mock_job(MockImage3DProvider())
        record = jobs.get_model_record(final.result.model_id)
        resp = ModelMetaResponse(
            modelId=record.id,
            format=record.format,
            mime=record.mime,
            sizeBytes=record.size_bytes,
            providerId=record.provider_id,
            sourceJobId=record.source_job_id,
            specHash=record.spec_hash,
            createdAt=record.created_at,
            stats=GlbStats.model_validate(record.stats) if record.stats else None,
        )
        self.assertIsNotNone(resp.stats)
        self.assertEqual(resp.stats.mesh_count, record.stats["meshCount"])

    def test_model_meta_response_without_stats(self):
        resp = ModelMetaResponse(
            modelId="x",
            format="glb",
            mime="model/gltf-binary",
            sizeBytes=1,
            providerId="mock",
            sourceJobId="j",
            specHash="h",
            createdAt=0.0,
        )
        self.assertIsNone(resp.stats)


if __name__ == "__main__":
    unittest.main()
