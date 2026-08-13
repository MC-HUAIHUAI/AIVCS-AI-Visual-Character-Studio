"""GLB builder tests (Phase 2.3-D)."""

from __future__ import annotations

import json
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.services.glb_builder import Primitive, build_glb  # noqa: E402


def validate_glb(data: bytes) -> dict:
    assert data[:4] == b"glTF", "bad magic"
    _magic, version, total = struct.unpack("<4sII", data[:12])
    assert version == 2
    assert total == len(data)
    clen, ctype = struct.unpack("<I4s", data[12:20])
    assert ctype == b"JSON"
    gltf = json.loads(data[20 : 20 + clen])
    assert gltf["asset"]["version"] == "2.0"
    # accessors must fit inside the buffer
    buf_len = gltf["buffers"][0]["byteLength"]
    views = gltf["bufferViews"]
    for acc in gltf["accessors"]:
        view = views[acc["bufferView"]]
        assert view["byteOffset"] + view["byteLength"] <= buf_len
    return gltf


class GlbBuilderTest(unittest.TestCase):
    def test_builds_valid_glb(self):
        prims = [
            Primitive("box", (1, 1, 1), center=(0, 0.5, 0), color="#FF0000"),
            Primitive("sphere", radius=0.5, center=(0, 1.5, 0), color="#00FF00"),
        ]
        data = build_glb(prims)
        gltf = validate_glb(data)
        self.assertGreater(len(gltf["meshes"]), 0)
        self.assertGreater(len(gltf["accessors"]), 0)

    def test_deterministic(self):
        prims = [Primitive("box", (0.5, 0.5, 0.5), color="#123456"), Primitive("sphere", radius=0.3)]
        self.assertEqual(build_glb(prims), build_glb(prims))

    def test_different_input_different_bytes(self):
        a = build_glb([Primitive("box", (1, 1, 1), color="#FF0000")])
        b = build_glb([Primitive("box", (1, 1, 1), color="#00FF00")])
        self.assertNotEqual(a, b)

    def test_scale_applied(self):
        small = build_glb([Primitive("box", (1, 1, 1), center=(0, 1, 0))], scale=1.0)
        big = build_glb([Primitive("box", (1, 1, 1), center=(0, 1, 0))], scale=2.0)
        self.assertNotEqual(small, big)

    def test_empty_primitives(self):
        data = build_glb([])
        gltf = validate_glb(data)
        self.assertEqual(len(gltf["meshes"]), 0)


if __name__ == "__main__":
    unittest.main()
