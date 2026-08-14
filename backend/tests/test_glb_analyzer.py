"""GLB Asset Analyzer tests (Phase 2.5-A)."""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app import config  # noqa: E402
from backend.app.providers.local_lowpower import LocalLowPower3DProvider  # noqa: E402
from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.services.glb_analyzer import analyze_glb  # noqa: E402
from backend.app.services.glb_builder import Primitive, build_glb  # noqa: E402


def make_glb(gltf_dict: dict) -> bytes:
    body = json.dumps(gltf_dict, separators=(",", ":")).encode()
    clen = len(body)
    total = 20 + clen
    return struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", clen, b"JSON") + body


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


class GlbAnalyzerTest(unittest.TestCase):
    def test_demo_character_stats(self):
        data = config.DEMO_MODEL_PATH.read_bytes()
        stats = analyze_glb(data)
        self.assertEqual(stats.format, "glb")
        self.assertEqual(stats.version, 2)
        self.assertEqual(stats.sizeBytes, len(data))
        self.assertEqual(stats.meshCount, 17)
        self.assertEqual(stats.primitiveCount, 17)
        self.assertGreater(stats.vertexCount, 0)
        self.assertGreater(stats.indexCount, 0)
        self.assertEqual(stats.triangleCount, stats.indexCount // 3)
        self.assertGreater(stats.materialCount, 0)
        self.assertEqual(stats.textureCount, 0)
        self.assertTrue(stats.hasNormals)
        self.assertFalse(stats.hasUVs)
        self.assertIsNotNone(stats.bounds)
        d = stats.dimensions
        self.assertGreater(d["x"], 0)
        self.assertGreater(d["y"], 0)
        self.assertGreater(d["z"], 0)
        self.assertEqual(len(stats.meshStats), 17)

    def test_demo_fox_stats(self):
        stats = analyze_glb(config.DEMO_FOX_MODEL_PATH.read_bytes())
        self.assertEqual(stats.meshCount, 32)
        self.assertEqual(stats.primitiveCount, 32)

    def test_local_lowpower_glb_stats(self):
        provider = LocalLowPower3DProvider()
        data = asyncio.run(provider.generate(make_spec(), [], lambda _i, _t, _m: None, None))
        stats = analyze_glb(data)
        self.assertGreater(stats.meshCount, 0)
        self.assertGreater(stats.vertexCount, 0)
        self.assertTrue(stats.hasNormals)
        self.assertIsNotNone(stats.bounds)

    def test_box_counts(self):
        data = build_glb([Primitive("box", (1, 1, 1), center=(0, 1, 0), color="#FF0000")])
        stats = analyze_glb(data)
        self.assertEqual(stats.meshCount, 1)
        self.assertEqual(stats.primitiveCount, 1)
        self.assertEqual(stats.vertexCount, 24)
        self.assertEqual(stats.indexCount, 36)
        self.assertEqual(stats.triangleCount, 12)
        self.assertEqual(stats.materialCount, 1)
        self.assertTrue(stats.hasNormals)
        self.assertFalse(stats.hasUVs)
        # bounds are in LOCAL mesh space (node transform not applied - 2.5-B)
        self.assertEqual(stats.bounds["min"], [-0.5, -0.5, -0.5])
        self.assertEqual(stats.bounds["max"], [0.5, 0.5, 0.5])
        self.assertEqual(stats.dimensions, {"x": 1.0, "y": 1.0, "z": 1.0})
        self.assertEqual(stats.center, {"x": 0.0, "y": 0.0, "z": 0.0})

    def test_uvs_normals_texture_materials(self):
        gltf = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 0}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 0, "target": 34962}],
            "accessors": [
                {"bufferView": 0, "componentType": 5126, "count": 0, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]},
                {"bufferView": 0, "componentType": 5126, "count": 0, "type": "VEC3"},
                {"bufferView": 0, "componentType": 5122, "count": 0, "type": "VEC2"},
            ],
            "materials": [{"name": "m", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
            "textures": [{"source": 0}],
            "meshes": [
                {"name": "m0", "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "material": 0, "mode": 4}]}
            ],
            "nodes": [{"mesh": 0}],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
        }
        stats = analyze_glb(make_glb(gltf))
        self.assertEqual(stats.materialCount, 1)
        self.assertEqual(stats.textureCount, 1)
        self.assertTrue(stats.hasNormals)
        self.assertTrue(stats.hasUVs)
        self.assertEqual(stats.bounds["min"], [0.0, 0.0, 0.0])
        self.assertEqual(stats.bounds["max"], [1.0, 1.0, 1.0])

    def test_non_indexed_primitive(self):
        gltf = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 0}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 0, "target": 34962}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]}],
            "meshes": [{"name": "tri", "primitives": [{"attributes": {"POSITION": 0}, "mode": 4}]}],
            "nodes": [{"mesh": 0}],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
        }
        stats = analyze_glb(make_glb(gltf))
        self.assertEqual(stats.indexCount, 0)
        self.assertEqual(stats.triangleCount, 1)
        self.assertTrue(any("非索引" in w for w in stats.warnings))

    def test_skinned_flag(self):
        unskinned = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 0}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 0, "target": 34962}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]}],
            "meshes": [{"name": "m", "primitives": [{"attributes": {"POSITION": 0}, "mode": 4}]}],
            "nodes": [{"mesh": 0}],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
        }
        self.assertFalse(analyze_glb(make_glb(unskinned)).skinned)

        skinned = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 0}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 0, "target": 34962}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]}],
            "meshes": [{"name": "m", "primitives": [{"attributes": {"POSITION": 0}, "mode": 4}]}],
            "nodes": [{"mesh": 0, "skin": 0}],
            "skins": [{"joints": [0], "inverseBindMatrices": 0}],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
        }
        self.assertTrue(analyze_glb(make_glb(skinned)).skinned)

    def test_empty_invalid_raises_valueerror(self):
        with self.assertRaises(ValueError):
            analyze_glb(b"")
        with self.assertRaises(ValueError):
            analyze_glb(b"<html>not a glb</html>")

    def test_partial_anomaly_is_tolerant(self):
        # POSITION accessor index out of range -> that primitive is skipped
        gltf = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 0}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 0, "target": 34962}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]}],
            "meshes": [{"name": "bad", "primitives": [{"attributes": {"POSITION": 9}, "mode": 4}]}],
            "nodes": [{"mesh": 0}],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
        }
        stats = analyze_glb(make_glb(gltf))  # must not crash
        self.assertEqual(stats.meshCount, 1)
        self.assertEqual(stats.primitiveCount, 1)
        self.assertEqual(len(stats.meshStats), 0)
        self.assertTrue(any("分析失败" in w for w in stats.warnings))

    def test_deterministic(self):
        data = config.DEMO_MODEL_PATH.read_bytes()
        self.assertEqual(analyze_glb(data), analyze_glb(data))


if __name__ == "__main__":
    unittest.main()
