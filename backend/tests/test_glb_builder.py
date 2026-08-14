"""GLB builder tests (Phase 2.3-D)."""

from __future__ import annotations

import json
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.services.glb_builder import Primitive, build_glb, validate_glb  # noqa: E402


def parse_glb(data: bytes) -> dict:
    """Structural parser used to inspect generated GLBs (not the validator)."""
    assert data[:4] == b"glTF", "bad magic"
    _magic, version, total = struct.unpack("<4sII", data[:12])
    assert version == 2
    assert total == len(data)
    clen, ctype = struct.unpack("<I4s", data[12:20])
    assert ctype == b"JSON"
    gltf = json.loads(data[20 : 20 + clen])
    assert gltf["asset"]["version"] == "2.0"
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
        gltf = parse_glb(data)
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
        gltf = parse_glb(data)
        self.assertEqual(len(gltf["meshes"]), 0)

    def test_validate_rejects_garbage(self):
        for bad in (b"", b"short", b"not a glb at all", b"<html>error</html>", b"glTF\x02\x00\x00\x00garbage"):
            with self.assertRaises(ValueError):
                validate_glb(bad)

    def test_validate_rejects_wrong_version(self):
        # patch version bytes to 1
        data = bytearray(build_glb([Primitive("box", (1, 1, 1))]))
        data[4:8] = struct.pack("<I", 1)
        with self.assertRaises(ValueError):
            validate_glb(bytes(data))

    def test_validate_normalizes_malformed_accessor_to_valueerror(self):
        # craft JSON whose accessor references a missing bufferView index
        body = json.dumps(
            {
                "asset": {"version": "2.0"},
                "buffers": [{"byteLength": 0}],
                "bufferViews": [],
                "meshes": [],
                "accessors": [{"bufferView": 5, "byteOffset": 0, "byteLength": 10}],
            },
            separators=(",", ":"),
        ).encode()
        clen = len(body)
        total = 20 + clen
        glb = struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", clen, b"JSON") + body
        with self.assertRaises(ValueError) as ctx:
            validate_glb(glb)
        self.assertIn("GLB", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
