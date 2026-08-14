"""VRM 1.0 exporter tests (Phase 2.7-B)."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.services.glb_builder import Primitive, build_glb, validate_glb  # noqa: E402
from backend.app.services.rig_builder import build_bone_tree  # noqa: E402
from backend.app.services.vrm_exporter import VrmExportError, export_vrm  # noqa: E402
from backend.app.services.vrm_mapping import REQUIRED_HUMAN_BONES  # noqa: E402
from backend.app.services.vrm_validator import validate_vrm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_spec(body_type="humanoid"):
    return CharacterSpec(
        id="s",
        name="测试角色",
        style="stylized",
        gender="female",
        heightCm=160,
        description="",
        referenceImageIds=[],
        tags=[],
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:00Z",
        bodyType=body_type,
    )


def humanoid_skinned_glb():
    bones = build_bone_tree(make_spec(body_type="humanoid"))
    prims = [
        Primitive("box", (0.3, 0.9, 0.3), center=(-0.15, 0.5, 0), color="#FF0000"),
        Primitive("box", (0.3, 0.9, 0.3), center=(0.15, 0.5, 0), color="#00AA00"),
        Primitive("box", (0.6, 0.6, 0.4), center=(0, 1.05, 0), color="#4466AA"),
        Primitive("sphere", radius=0.28, center=(0, 1.6, 0), color="#E8CDB3"),
    ]
    return build_glb(prims, scale=1.0, bones=bones)


def bin_bytes(data):
    clen, _c = struct.unpack("<I4s", data[12:20])
    return data[20 + clen + 8 :]


class VrmExporterTest(unittest.TestCase):
    def test_exports_valid_vrm(self):
        vrm = export_vrm(humanoid_skinned_glb(), body_type="humanoid", model_name="测试角色")
        validate_glb(vrm)  # still a legal GLB
        v = validate_vrm(vrm)  # VRM structure OK
        self.assertEqual(v["specVersion"], "1.0")
        self.assertEqual(v["meta"]["name"], "测试角色")
        self.assertEqual(v["meta"]["authors"], ["AIVCS"])
        self.assertIn("licenseUrl", v["meta"])

    def test_humanoid_required_bones_present_and_valid(self):
        vrm = export_vrm(humanoid_skinned_glb(), body_type="humanoid", model_name="x")
        clen, _c = struct.unpack("<I4s", vrm[12:20])
        gltf = json.loads(vrm[20 : 20 + clen])
        hb = gltf["extensions"]["VRMC_vrm"]["humanoid"]["humanBones"]
        node_count = len(gltf["nodes"])
        for bone in REQUIRED_HUMAN_BONES:
            self.assertIn(bone, hb)
            node = hb[bone]["node"]
            self.assertIsInstance(node, int)
            self.assertTrue(0 <= node < node_count, f"{bone}.node 越界")

    def test_joints_match_ibm_count(self):
        src = humanoid_skinned_glb()
        vrm = export_vrm(src, body_type="humanoid", model_name="x")
        clen, _c = struct.unpack("<I4s", vrm[12:20])
        gltf = json.loads(vrm[20 : 20 + clen])
        skin = gltf["skins"][0]
        ibm_acc = gltf["accessors"][skin["inverseBindMatrices"]]
        self.assertEqual(len(skin["joints"]), ibm_acc["count"])

    def test_geometry_and_skin_unchanged(self):
        src = humanoid_skinned_glb()
        vrm = export_vrm(src, body_type="humanoid", model_name="x")
        # exporter only APPENDS IBM bytes to the BIN buffer -> original prefix intact
        in_bin = bin_bytes(src)
        out_bin = bin_bytes(vrm)
        self.assertGreater(len(out_bin), len(in_bin))
        self.assertEqual(out_bin[: len(in_bin)], in_bin)

    def test_deterministic(self):
        src = humanoid_skinned_glb()
        a = export_vrm(src, body_type="humanoid", model_name="n")
        b = export_vrm(src, body_type="humanoid", model_name="n")
        self.assertEqual(a, b)

    def test_no_bones_input_fails(self):
        prims = [Primitive("box", (1, 1, 1), color="#FF0000")]
        glb = build_glb(prims)
        with self.assertRaises(VrmExportError) as ctx:
            export_vrm(glb, body_type="humanoid", model_name="x")
        self.assertIn("skinned", str(ctx.exception))

    def test_unsupported_body_type_fails(self):
        for bt in ("quadruped", "bird", "dragon"):
            with self.assertRaises(VrmExportError) as ctx:
                export_vrm(humanoid_skinned_glb(), body_type=bt, model_name="x")
            self.assertIn("无法导出", str(ctx.exception))

    def test_malformed_glb_fails_safely(self):
        with self.assertRaises(ValueError):
            export_vrm(b"<html>not a glb</html>", body_type="humanoid", model_name="x")

    def test_skinned_mesh_still_loads_via_three(self):
        vrm = export_vrm(humanoid_skinned_glb(), body_type="humanoid", model_name="x")
        script = os.path.join(ROOT, "tools", "check_skinned_glb.cjs")
        with tempfile.NamedTemporaryFile(suffix=".vrm", delete=False) as f:
            f.write(vrm)
            tmp = f.name
        try:
            res = subprocess.run(["node", script, tmp], capture_output=True, text=True, cwd=ROOT, timeout=60)
            self.assertEqual(res.returncode, 0, msg=f"three gate failed: {res.stdout} {res.stderr}")
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
