"""LocalLowPower3DProvider tests (Phase 2.3-D)."""

from __future__ import annotations

import asyncio
import base64
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import backend.app.jobs as jobs  # noqa: E402
from backend.app.providers.base import CancellationToken, ProviderCancelledError  # noqa: E402
from backend.app.providers.local_lowpower import LocalLowPower3DProvider, extract_palette  # noqa: E402
from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.schemas.vision import VisionImageInput  # noqa: E402
from backend.app.services.glb_builder import Primitive, build_glb  # noqa: E402
from backend.app.services.model_store import ModelStore  # noqa: E402


def make_spec(character_type="human", body_type="humanoid", height_cm=160, palette=None):
    kwargs = dict(
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
        characterType=character_type,
        bodyType=body_type,
    )
    if palette is not None:
        kwargs["appearance"] = {"palette": palette}
    return CharacterSpec(**kwargs)


def make_png(width, height, rgb):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(v for _ in range(width) for v in rgb) for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def png_ref(image_id="r1", rgb=(255, 0, 0)):
    b64 = base64.b64encode(make_png(16, 16, rgb)).decode("ascii")
    return VisionImageInput(imageId=image_id, dataUrl="data:image/png;base64," + b64, view="front")


async def wait_terminal(job_id, timeout=8):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get_job(job_id)
        if job.status in ("done", "failed", "timed_out", "cancelled"):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("not terminal")


class LocalLowPowerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._orig_store = jobs._store
        jobs._store = ModelStore(self.dir)
        self.provider = LocalLowPower3DProvider()

    def tearDown(self):
        jobs._store = self._orig_store

    def run_provider(self, spec, refs=None, cancel=None):
        return asyncio.run(self.provider.generate(spec, refs or [], lambda _i, _t, _m: None, cancel))

    def test_generates_valid_glb(self):
        data = self.run_provider(make_spec())
        self.assertGreater(len(data), 100)
        self.assertEqual(data[:4], b"glTF")
        # structural check via builder validation path
        gltf = _validate(data)
        self.assertGreater(len(gltf["meshes"]), 0)

    def test_deterministic(self):
        spec = make_spec(height_cm=160)
        self.assertEqual(self.run_provider(spec), self.run_provider(spec))

    def test_different_body_type_different_model(self):
        human = self.run_provider(make_spec(body_type="humanoid"))
        quad = self.run_provider(make_spec(character_type="animal", body_type="quadruped"))
        self.assertNotEqual(human, quad)

    def test_reference_palette_changes_output(self):
        ref = png_ref(rgb=(255, 0, 0))
        with_ref = self.run_provider(make_spec(), refs=[ref])
        no_ref = self.run_provider(make_spec())
        self.assertNotEqual(with_ref, no_ref)
        self.assertEqual(extract_palette([ref])[0], "#E00000")  # quantized red

    def test_cancelled_token_raises(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(ProviderCancelledError):
            self.run_provider(make_spec(), cancel=token)

    def test_job_integration_with_model_store(self):
        async def scenario():
            provider = LocalLowPower3DProvider()
            spec = make_spec()
            job = jobs.create_job("local-lowpower", lambda cb, cancel: provider.generate(spec, [], cb, cancel))
            final = await wait_terminal(job.job_id)
            self.assertEqual(final.status, "done")
            data = jobs.get_model(final.result.model_id)
            self.assertEqual(data[:4], b"glTF")
            self.assertIsNotNone(jobs.get_model_record(final.result.model_id))
        asyncio.run(scenario())

    def test_capabilities(self):
        self.assertFalse(self.provider.gpu_required)
        self.assertEqual(self.provider.max_references, 4)
        self.assertEqual(self.provider.output_format, "glb")
        self.assertTrue(self.provider.supports_cancel)
        self.assertTrue(self.provider.supports_timeout)


def _validate(data):
    import json as _json

    clen, _ctype = struct.unpack("<I4s", data[12:20])
    return _json.loads(data[20 : 20 + clen])


if __name__ == "__main__":
    unittest.main()
