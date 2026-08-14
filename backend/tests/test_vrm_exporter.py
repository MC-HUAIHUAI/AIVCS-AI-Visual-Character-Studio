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

from backend.app.schemas.character import AnatomyGraph, CharacterSpec  # noqa: E402
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


def biped_anthro_skinned_glb():
    spec = make_spec(body_type="biped-anthro")
    spec.anatomy = AnatomyGraph(tail="single", wings=True, horns=True)
    bones = build_bone_tree(spec)
    prims = [
        Primitive("box", (0.4, 0.9, 0.4), center=(0, 0.9, 0), color="#FF0000"),
        Primitive("sphere", radius=0.26, center=(0, 1.5, 0), color="#E8CDB3"),
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

    # ---- Phase 2.7-C: biped-anthro (appendages + terminal synthesis) ----

    def _parse_gltf(self, vrm):
        clen, _c = struct.unpack("<I4s", vrm[12:20])
        return json.loads(vrm[20 : 20 + clen])

    def test_biped_anthro_exports_valid_vrm(self):
        vrm = export_vrm(biped_anthro_skinned_glb(), body_type="biped-anthro", model_name="兽人")
        validate_glb(vrm)
        v = validate_vrm(vrm)
        self.assertEqual(v["specVersion"], "1.0")
        self.assertEqual(v["meta"]["name"], "兽人")

    def test_biped_anthro_required_bones_present_and_valid(self):
        vrm = export_vrm(biped_anthro_skinned_glb(), body_type="biped-anthro", model_name="兽人")
        gltf = self._parse_gltf(vrm)
        hb = gltf["extensions"]["VRMC_vrm"]["humanoid"]["humanBones"]
        node_count = len(gltf["nodes"])
        for bone in REQUIRED_HUMAN_BONES:
            self.assertIn(bone, hb)
            node = hb[bone]["node"]
            self.assertIsInstance(node, int)
            self.assertTrue(0 <= node < node_count, f"{bone}.node 越界")

    def test_biped_anthro_synthesized_terminals(self):
        vrm = export_vrm(biped_anthro_skinned_glb(), body_type="biped-anthro", model_name="兽人")
        gltf = self._parse_gltf(vrm)
        hb = gltf["extensions"]["VRMC_vrm"]["humanoid"]["humanBones"]
        names = {n.get("name") for n in gltf["nodes"]}
        # hands/feet + lower limbs synthesized at export
        for bone in ("leftHand", "rightHand", "leftFoot", "rightFoot",
                     "leftLowerArm", "rightLowerArm", "leftLowerLeg", "rightLowerLeg"):
            self.assertIn(bone, hb)
            self.assertIn(bone, names)
            self.assertEqual(gltf["nodes"][hb[bone]["node"]].get("name"), bone)

    def test_biped_anthro_joints_match_ibm_count(self):
        vrm = export_vrm(biped_anthro_skinned_glb(), body_type="biped-anthro", model_name="兽人")
        gltf = self._parse_gltf(vrm)
        skin = gltf["skins"][0]
        ibm_acc = gltf["accessors"][skin["inverseBindMatrices"]]
        self.assertEqual(len(skin["joints"]), ibm_acc["count"])

    def test_biped_anthro_geometry_and_skin_unchanged(self):
        src = biped_anthro_skinned_glb()
        vrm = export_vrm(src, body_type="biped-anthro", model_name="兽人")
        in_bin = bin_bytes(src)
        out_bin = bin_bytes(vrm)
        self.assertGreater(len(out_bin), len(in_bin))
        self.assertEqual(out_bin[: len(in_bin)], in_bin)

    def test_biped_anthro_deterministic(self):
        src = biped_anthro_skinned_glb()
        a = export_vrm(src, body_type="biped-anthro", model_name="n")
        b = export_vrm(src, body_type="biped-anthro", model_name="n")
        self.assertEqual(a, b)

    def test_biped_anthro_appendages_preserved_and_not_humanoid(self):
        vrm = export_vrm(biped_anthro_skinned_glb(), body_type="biped-anthro", model_name="兽人")
        gltf = self._parse_gltf(vrm)
        names = {n.get("name") for n in gltf["nodes"]}
        hb = gltf["extensions"]["VRMC_vrm"]["humanoid"]["humanBones"]
        # tail / ears / wings / horns are ordinary nodes/joints ...
        for bone in ("tail", "ears_L", "ears_R", "wing_L", "wing_R", "horn_L", "horn_R"):
            self.assertIn(bone, names)
        # ... and are NOT mapped into VRM Humanoid humanBones.
        for bone in ("tail", "ears_L", "ears_R", "wing_L", "wing_R", "horn_L", "horn_R"):
            self.assertNotIn(bone, hb, f"appendage {bone} 不应出现在 humanBones")

    def test_biped_anthro_skinned_mesh_loads_via_three(self):
        vrm = export_vrm(biped_anthro_skinned_glb(), body_type="biped-anthro", model_name="兽人")
        script = os.path.join(ROOT, "tools", "check_skinned_glb.cjs")
        with tempfile.NamedTemporaryFile(suffix=".vrm", delete=False) as f:
            f.write(vrm)
            tmp = f.name
        try:
            res = subprocess.run(["node", script, tmp], capture_output=True, text=True, cwd=ROOT, timeout=60)
            self.assertEqual(res.returncode, 0, msg=f"three gate failed: {res.stdout} {res.stderr}")
        finally:
            os.unlink(tmp)

    def _run_loader_gate(self, vrm):
        script = os.path.join(ROOT, "tools", "check_vrm.cjs")
        with tempfile.NamedTemporaryFile(suffix=".vrm", delete=False) as f:
            f.write(vrm)
            tmp = f.name
        try:
            res = subprocess.run(["node", script, tmp], capture_output=True, text=True, cwd=ROOT, timeout=60)
            self.assertEqual(res.returncode, 0, msg=f"@pixiv/three-vrm gate failed: {res.stdout} {res.stderr}")
            return res.stdout
        finally:
            os.unlink(tmp)

    def test_humanoid_loads_via_three_vrm_loader(self):
        out = self._run_loader_gate(export_vrm(humanoid_skinned_glb(), body_type="humanoid", model_name="x"))
        self.assertIn("VRM_OK", out)

    def test_biped_anthro_loads_via_three_vrm_loader(self):
        out = self._run_loader_gate(export_vrm(biped_anthro_skinned_glb(), body_type="biped-anthro", model_name="兽人"))
        self.assertIn("VRM_OK", out)

    # ---- Phase 2.7-C: vrm_validator negative cases ----

    def _vrm_without(self, bone):
        vrm = export_vrm(humanoid_skinned_glb(), body_type="humanoid", model_name="x")
        clen, _c = struct.unpack("<I4s", vrm[12:20])
        gltf = json.loads(vrm[20 : 20 + clen])
        del gltf["extensions"]["VRMC_vrm"]["humanoid"]["humanBones"][bone]
        import backend.app.services.glb_builder as gb

        buffer = vrm[20 + clen + 8 :]
        return gb.serialize_glb(gltf, buffer)

    def test_validator_missing_required_bone_fails(self):
        bad = self._vrm_without("leftLowerArm")
        with self.assertRaises(ValueError) as ctx:
            validate_vrm(bad)
        self.assertIn("leftLowerArm", str(ctx.exception))

    def test_validator_bad_node_index_fails(self):
        vrm = export_vrm(humanoid_skinned_glb(), body_type="humanoid", model_name="x")
        clen, _c = struct.unpack("<I4s", vrm[12:20])
        gltf = json.loads(vrm[20 : 20 + clen])
        gltf["extensions"]["VRMC_vrm"]["humanoid"]["humanBones"]["hips"]["node"] = 99999
        import backend.app.services.glb_builder as gb

        buffer = vrm[20 + clen + 8 :]
        bad = gb.serialize_glb(gltf, buffer)
        with self.assertRaises(ValueError) as ctx:
            validate_vrm(bad)
        self.assertIn("hips", str(ctx.exception))

    def test_validator_joints_ibm_mismatch_fails(self):
        vrm = export_vrm(humanoid_skinned_glb(), body_type="humanoid", model_name="x")
        clen, _c = struct.unpack("<I4s", vrm[12:20])
        gltf = json.loads(vrm[20 : 20 + clen])
        gltf["skins"][0]["joints"] = gltf["skins"][0]["joints"][:-1]
        import backend.app.services.glb_builder as gb

        buffer = vrm[20 + clen + 8 :]
        bad = gb.serialize_glb(gltf, buffer)
        with self.assertRaises(ValueError) as ctx:
            validate_vrm(bad)
        self.assertIn("inverseBindMatrices", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
