"""LocalLowPower + RigBuilder integration tests (Phase 2.6-C)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import backend.app.jobs as jobs  # noqa: E402
from backend.app import config  # noqa: E402
from backend.app.providers.local_lowpower import LocalLowPower3DProvider  # noqa: E402
from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.services.glb_analyzer import analyze_glb  # noqa: E402
from backend.app.services.glb_builder import validate_glb  # noqa: E402
from backend.app.services.model_store import ModelStore  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE_SCRIPT = os.path.join(ROOT, "tools", "check_skinned_glb.cjs")


def make_spec(body_type="humanoid", height_cm=160):
    return CharacterSpec(
        id="s",
        name="t",
        style="stylized",
        gender="female",
        heightCm=height_cm,
        description="",
        referenceImageIds=[],
        tags=[],
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:00Z",
        bodyType=body_type,
    )


def parse_glb(data):
    clen, _ctype = struct.unpack("<I4s", data[12:20])
    return json.loads(data[20 : 20 + clen])


def run_three_gate(data):
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        res = subprocess.run(["node", GATE_SCRIPT, tmp], capture_output=True, text=True, cwd=ROOT, timeout=60)
        return res
    finally:
        os.unlink(tmp)


class RigIntegrationTest(unittest.TestCase):
    def setUp(self):
        self._rig = config.LOCAL3D_RIG_ENABLED
        self.dir = tempfile.mkdtemp()
        self._orig_store = jobs._store
        jobs._store = ModelStore(self.dir)

    def tearDown(self):
        config.LOCAL3D_RIG_ENABLED = self._rig
        jobs._store = self._orig_store

    def run_provider(self, spec):
        provider = LocalLowPower3DProvider()
        return asyncio.run(provider.generate(spec, [], lambda _i, _t, _m: None, None))

    def test_default_rig_disabled_unskinned(self):
        # env not set -> default false
        config.LOCAL3D_RIG_ENABLED = False
        data = self.run_provider(make_spec())
        validate_glb(data)
        gltf = parse_glb(data)
        self.assertNotIn("skins", gltf)
        self.assertNotIn("JOINTS_0", gltf["meshes"][0]["primitives"][0]["attributes"])

    def test_rig_enabled_skinned_and_three_gate(self):
        config.LOCAL3D_RIG_ENABLED = True
        data = self.run_provider(make_spec(body_type="humanoid"))
        validate_glb(data)
        gltf = parse_glb(data)
        self.assertIn("skins", gltf)
        self.assertIn("JOINTS_0", gltf["meshes"][0]["primitives"][0]["attributes"])
        self.assertIn("WEIGHTS_0", gltf["meshes"][0]["primitives"][0]["attributes"])
        res = run_three_gate(data)
        self.assertEqual(res.returncode, 0, msg=f"three gate failed: {res.stdout} {res.stderr}")

    def test_rig_enabled_quadruped_three_gate(self):
        config.LOCAL3D_RIG_ENABLED = True
        data = self.run_provider(make_spec(body_type="quadruped"))
        res = run_three_gate(data)
        self.assertEqual(res.returncode, 0, msg=f"quadruped gate failed: {res.stdout} {res.stderr}")

    def test_rig_disabled_matches_old_behavior(self):
        # Both disabled runs produce the identical (unskinned) GLB.
        config.LOCAL3D_RIG_ENABLED = False
        a = self.run_provider(make_spec())
        b = self.run_provider(make_spec())
        self.assertEqual(a, b)
        self.assertNotIn("skins", parse_glb(a))

    def test_analyzer_works_on_skinned_glb(self):
        config.LOCAL3D_RIG_ENABLED = True
        data = self.run_provider(make_spec())
        stats = analyze_glb(data)
        self.assertGreater(stats.meshCount, 0)
        self.assertGreater(stats.vertexCount, 0)

    def test_job_pipeline_with_rig_enabled(self):
        async def scenario():
            config.LOCAL3D_RIG_ENABLED = True
            provider = LocalLowPower3DProvider()
            spec = make_spec()
            job = jobs.create_job("local-lowpower", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            deadline = time.time() + 8
            while time.time() < deadline and job.status in ("queued", "running"):
                await asyncio.sleep(0.02)
            self.assertEqual(job.status, "done")
            data = jobs.get_model(job.result.model_id)
            self.assertIn("skins", parse_glb(data))
            res = run_three_gate(data)
            self.assertEqual(res.returncode, 0, msg=f"job gate failed: {res.stdout} {res.stderr}")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
