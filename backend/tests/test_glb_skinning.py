"""Skinned GLB tests + Three.js SkinnedMesh hard gate (Phase 2.6-B)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.services.glb_builder import Primitive, build_glb, validate_glb  # noqa: E402
from backend.app.services.rig_builder import build_bone_tree  # noqa: E402
from backend.app.services.rig_profiles import get_rig_profile  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GATE_SCRIPT = os.path.join(ROOT, "tools", "check_skinned_glb.cjs")

# Byte-level backward compatibility golden (pre-2.6-B build_glb output).
GOLDEN_NO_BONES_SHA256 = "2236f634e7205a5660dbe97f935406e41f1097308ff0e4f8a5f926ab0a62bb05"


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


def parse_glb(data: bytes) -> dict:
    clen, _ctype = struct.unpack("<I4s", data[12:20])
    return json.loads(data[20 : 20 + clen])


def demo_primitives():
    return [
        Primitive("box", (0.3, 0.9, 0.3), center=(-0.15, 0.5, 0), color="#FF0000"),
        Primitive("box", (0.3, 0.9, 0.3), center=(0.15, 0.5, 0), color="#00AA00"),
        Primitive("box", (0.6, 0.6, 0.4), center=(0, 1.05, 0), color="#4466AA"),
        Primitive("sphere", radius=0.28, center=(0, 1.6, 0), color="#E8CDB3"),
    ]


class SkinnedGlbTest(unittest.TestCase):
    def test_no_bones_byte_compat(self):
        prims = [
            Primitive("box", (0.5, 0.5, 0.5), center=(0, 0.5, 0), color="#FF0000"),
            Primitive("sphere", radius=0.25, center=(0, 1.0, 0), color="#00FF00"),
        ]
        data = build_glb(prims)
        self.assertEqual(hashlib.sha256(data).hexdigest(), GOLDEN_NO_BONES_SHA256)

    def test_skinned_glb_structure(self):
        bones = build_bone_tree(make_spec(body_type="humanoid"))
        data = build_glb(demo_primitives(), scale=1.0, bones=bones)
        validate_glb(data)  # structural gate
        gltf = parse_glb(data)

        self.assertIn("skins", gltf)
        self.assertEqual(len(gltf["skins"]), 1)
        skin = gltf["skins"][0]
        self.assertEqual(len(skin["joints"]), len(bones))

        # every mesh primitive carries JOINTS_0 / WEIGHTS_0
        for mesh in gltf["meshes"]:
            attrs = mesh["primitives"][0]["attributes"]
            self.assertIn("JOINTS_0", attrs)
            self.assertIn("WEIGHTS_0", attrs)

        # JOINTS accessor is VEC4 / UNSIGNED_BYTE; WEIGHTS is VEC4 float
        jacc = next(a for a in gltf["accessors"] if a["type"] == "VEC4" and a["componentType"] == 5121)
        self.assertGreater(jacc["count"], 0)

        # all bufferViews are 4-byte aligned
        for view in gltf["bufferViews"]:
            self.assertEqual(view["byteOffset"] % 4, 0)

        # inverseBindMatrices is MAT4
        ibm = next(a for a in gltf["accessors"] if a["type"] == "MAT4")
        self.assertEqual(ibm["count"], len(bones))

    def test_joints_indices_within_range(self):
        bones = build_bone_tree(make_spec(body_type="humanoid"))
        data = build_glb(demo_primitives(), scale=1.0, bones=bones)
        gltf = parse_glb(data)
        # decode JOINTS_0 for one primitive and verify indices < len(joints)
        accessors = gltf["accessors"]
        views = gltf["bufferViews"]
        buffer_start = 20 + struct.unpack("<I", data[12:16])[0] + 8  # end of JSON chunk
        # find the first JOINTS accessor
        jacc = next(a for a in accessors if a["type"] == "VEC4" and a["componentType"] == 5121)
        view = views[jacc["bufferView"]]
        offset = view["byteOffset"]
        # data layout: [header 12][json chunk 8+clen][bin chunk 8] -> bin data starts after bin chunk header
        clen = struct.unpack("<I", data[12:16])[0]
        bin_data_offset = 20 + clen + 8
        raw = data[bin_data_offset + offset : bin_data_offset + offset + jacc["count"] * 4]
        max_joint = max(raw)
        self.assertLess(max_joint, len(gltf["skins"][0]["joints"]))

    def test_three_js_skinned_gate(self):
        bones = build_bone_tree(make_spec(body_type="humanoid"))
        data = build_glb(demo_primitives(), scale=1.0, bones=bones)
        with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
            f.write(data)
            tmp = f.name
        try:
            res = subprocess.run(
                ["node", GATE_SCRIPT, tmp], capture_output=True, text=True, cwd=ROOT, timeout=60
            )
            self.assertEqual(res.returncode, 0, msg=f"three.js gate failed: {res.stdout} {res.stderr}")
            m = re.search(r"bones=(\d+)", res.stdout)
            self.assertIsNotNone(m)
            bones_loaded = int(m.group(1))
            gltf = parse_glb(data)
            self.assertEqual(bones_loaded, len(gltf["skins"][0]["joints"]))
        finally:
            os.unlink(tmp)

    def test_three_js_gate_quadruped(self):
        bones = build_bone_tree(make_spec(body_type="quadruped"))
        prims = [
            Primitive("box", (0.9, 0.5, 1.3), center=(0, 0.55, 0), color="#AA7700"),
            Primitive("box", (0.3, 0.3, 0.3), center=(0, 0.7, 0.9), color="#CCCCCC"),
        ]
        data = build_glb(prims, scale=1.0, bones=bones)
        with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
            f.write(data)
            tmp = f.name
        try:
            res = subprocess.run(["node", GATE_SCRIPT, tmp], capture_output=True, text=True, cwd=ROOT, timeout=60)
            self.assertEqual(res.returncode, 0, msg=f"quadruped gate failed: {res.stdout} {res.stderr}")
        finally:
            os.unlink(tmp)

    def test_skinned_differs_from_unskinned(self):
        bones = build_bone_tree(make_spec(body_type="humanoid"))
        prims = demo_primitives()
        self.assertNotEqual(build_glb(prims, bones=bones), build_glb(prims))


if __name__ == "__main__":
    unittest.main()
