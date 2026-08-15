"""Phase 3-F: Local 3D -> VRM Rigging Pipeline tests.

Covers the 12 required scenarios using TEST GLBs only (never a real Hunyuan GLB,
never real AI):
  1. valid humanoid test GLB -> rigs
  2. non-human GLB -> refused (no forced rig)
  3. malformed GLB -> explicit error
  4. skeleton hierarchy
  5. humanoid bone mapping
  6. bind pose
  7. skin weights
  8. VRM export
  9. VRM validation
  10. failure/no-fallback (explicit RigPipelineError, no mock)
  11. ModelStore round-trip (pipeline result persisted, re-readable)
  12. renderer loading (three.js GLTFLoader + @pixiv/three-vrm gates)
Plus: auto-rig of a static (unskinned) mesh with a humanoid hint.
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app import jobs  # noqa: E402
from backend.app.services.glb_builder import Primitive, build_glb, serialize_glb, validate_glb  # noqa: E402
from backend.app.services.local3d_rigger import (  # noqa: E402
    RigClassification,
    RigPipelineError,
    _skin_bone_ids,
    auto_rig_glb,
    build_bone_mapping,
    classify_glb,
    extract_skeleton,
    normalize_bone_name,
    normalize_skeleton_glb,
    rig_glb_to_vrm,
    verify_bind_pose,
    verify_skeleton_sanity,
    verify_skin_weights,
)
from backend.app.services.model_store import ModelStore  # noqa: E402
from backend.app.services.rig_builder import BoneNode, build_bone_tree  # noqa: E402
from backend.app.services.vrm_validator import validate_vrm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_spec(body_type="humanoid", character_type="human"):
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
        characterType=character_type,
    )


def humanoid_skinned_glb():
    bones = build_bone_tree(make_spec("humanoid"))
    prims = [
        Primitive("box", (0.3, 0.9, 0.3), center=(-0.15, 0.5, 0), color="#FF0000"),
        Primitive("box", (0.3, 0.9, 0.3), center=(0.15, 0.5, 0), color="#00AA00"),
        Primitive("box", (0.6, 0.6, 0.4), center=(0, 1.05, 0), color="#4466AA"),
        Primitive("sphere", radius=0.28, center=(0, 1.6, 0), color="#E8CDB3"),
    ]
    return build_glb(prims, scale=1.0, bones=bones)


def biped_anthro_skinned_glb():
    spec = make_spec("biped-anthro")
    spec.anatomy = spec.anatomy.model_copy(update={"tail": "single", "wings": True, "horns": True})
    bones = build_bone_tree(spec)
    prims = [
        Primitive("box", (0.4, 0.9, 0.4), center=(0, 0.9, 0), color="#FF0000"),
        Primitive("sphere", radius=0.26, center=(0, 1.5, 0), color="#E8CDB3"),
    ]
    return build_glb(prims, scale=1.0, bones=bones)


def quadruped_skinned_glb():
    bones = build_bone_tree(make_spec("quadruped"))
    prims = [Primitive("box", (0.5, 0.4, 0.8), center=(0, 0.55, 0), color="#888888")]
    return build_glb(prims, scale=1.0, bones=bones)


def unskinned_humanoidish_glb():
    """A static (unskinned) low-poly 'character-ish' mesh - like a dummy/test output."""
    prims = [
        Primitive("box", (0.6, 0.6, 0.4), center=(0, 1.05, 0), color="#4466AA"),
        Primitive("sphere", radius=0.28, center=(0, 1.6, 0), color="#E8CDB3"),
    ]
    return build_glb(prims)


def variant_named_skinned_glb():
    """Skinned humanoid whose bone node names use foreign conventions
    (LeftArm / Hips / _R suffixes) - must normalize before classification+export."""
    bones = [
        BoneNode("Hips", "骨盆", None, (0.0, 0.55, 0.0)),
        BoneNode("Spine", "脊椎", "Hips", (0.0, 0.85, 0.0)),
        BoneNode("Chest", "胸腔", "Spine", (0.0, 1.05, 0.0)),
        BoneNode("Neck", "颈部", "Chest", (0.0, 1.25, 0.0)),
        BoneNode("Head", "头部", "Neck", (0.0, 1.50, 0.0)),
        BoneNode("LeftArm", "左臂", "Chest", (-0.38, 1.05, 0.0)),
        BoneNode("LeftHand", "左手", "LeftArm", (-0.38, 0.78, 0.0)),
        BoneNode("Arm_R", "右臂", "Chest", (0.38, 1.05, 0.0)),
        BoneNode("Hand_R", "右手", "Arm_R", (0.38, 0.78, 0.0)),
        BoneNode("Leg_L", "左腿", "Hips", (-0.15, 0.28, 0.0)),
        BoneNode("Foot_L", "左脚", "Leg_L", (-0.15, 0.05, 0.0)),
        BoneNode("Leg_R", "右腿", "Hips", (0.15, 0.28, 0.0)),
        BoneNode("Foot_R", "右脚", "Leg_R", (0.15, 0.05, 0.0)),
    ]
    prims = [
        Primitive("box", (0.4, 0.9, 0.4), center=(0, 0.9, 0), color="#4466AA"),
        Primitive("sphere", radius=0.26, center=(0, 1.5, 0), color="#E8CDB3"),
    ]
    return build_glb(prims, scale=1.0, bones=bones)


def missing_left_leg_skinned_glb():
    """Humanoid rig missing a REQUIRED bone (leftLeg) - classification passes,
    skeleton sanity passes, but VRM export must fail clearly."""
    bones = [
        BoneNode("hips", "骨盆", None, (0.0, 0.55, 0.0)),
        BoneNode("spine", "脊椎", "hips", (0.0, 0.85, 0.0)),
        BoneNode("chest", "胸腔", "spine", (0.0, 1.05, 0.0)),
        BoneNode("neck", "颈部", "chest", (0.0, 1.25, 0.0)),
        BoneNode("head", "头部", "neck", (0.0, 1.50, 0.0)),
        BoneNode("leftArm", "左臂", "chest", (-0.38, 1.05, 0.0)),
        BoneNode("leftHand", "左手", "leftArm", (-0.38, 0.78, 0.0)),
        BoneNode("rightArm", "右臂", "chest", (0.38, 1.05, 0.0)),
        BoneNode("rightHand", "右手", "rightArm", (0.38, 0.78, 0.0)),
        BoneNode("rightLeg", "右腿", "hips", (0.15, 0.28, 0.0)),
        BoneNode("rightFoot", "右脚", "rightLeg", (0.15, 0.05, 0.0)),
        BoneNode("leftFoot", "左脚", "hips", (-0.15, 0.28, 0.0)),
    ]
    prims = [Primitive("box", (0.3, 0.9, 0.3), center=(0, 0.55, 0), color="#4466AA")]
    return build_glb(prims, scale=1.0, bones=bones)


def inverted_head_skinned_glb():
    """Humanoid rig with head BELOW hips (wrong direction) - sanity must fail."""
    base = [
        BoneNode("hips", "骨盆", None, (0.0, 0.55, 0.0)),
        BoneNode("spine", "脊椎", "hips", (0.0, 0.85, 0.0)),
        BoneNode("chest", "胸腔", "spine", (0.0, 1.05, 0.0)),
        BoneNode("neck", "颈部", "chest", (0.0, 1.25, 0.0)),
        BoneNode("head", "头部", "neck", (0.0, 0.30, 0.0)),
        BoneNode("leftArm", "左臂", "chest", (-0.38, 1.05, 0.0)),
        BoneNode("leftHand", "左手", "leftArm", (-0.38, 0.78, 0.0)),
        BoneNode("rightArm", "右臂", "chest", (0.38, 1.05, 0.0)),
        BoneNode("rightHand", "右手", "rightArm", (0.38, 0.78, 0.0)),
        BoneNode("leftLeg", "左腿", "hips", (-0.15, 0.28, 0.0)),
        BoneNode("leftFoot", "左脚", "leftLeg", (-0.15, 0.05, 0.0)),
        BoneNode("rightLeg", "右腿", "hips", (0.15, 0.28, 0.0)),
        BoneNode("rightFoot", "右脚", "rightLeg", (0.15, 0.05, 0.0)),
    ]
    prims = [Primitive("box", (0.4, 0.9, 0.4), center=(0, 0.9, 0), color="#4466AA")]
    return build_glb(prims, scale=1.0, bones=base)


def _patch_u8_attr(glb, attr_key, vertex_index, values):
    """Rewrite the first skinned primitive's U8 VEC4 accessor bytes (JOINTS_0)."""
    clen, _c = struct.unpack("<I4s", glb[12:20])
    gltf = json.loads(glb[20 : 20 + clen])
    bin_start = 20 + clen + 8
    buffer = bytearray(glb[bin_start:])
    views = gltf.get("bufferViews") or []
    accessors = gltf.get("accessors") or []
    for mesh in gltf.get("meshes") or []:
        for prim in mesh.get("primitives") or []:
            idx = (prim.get("attributes") or {}).get(attr_key)
            if idx is None:
                continue
            acc = accessors[idx]
            view = views[acc["bufferView"]]
            off = (view.get("byteOffset") or 0) + (acc.get("byteOffset") or 0) + vertex_index * 4
            buffer[off : off + 4] = bytes(values)
            return serialize_glb(gltf, bytes(buffer))
    raise AssertionError(f"no {attr_key} accessor")


def _patch_f32_attr(glb, attr_key, vertex_index, values):
    """Rewrite the first skinned primitive's FLOAT VEC4 accessor bytes (WEIGHTS_0)."""
    clen, _c = struct.unpack("<I4s", glb[12:20])
    gltf = json.loads(glb[20 : 20 + clen])
    bin_start = 20 + clen + 8
    buffer = bytearray(glb[bin_start:])
    views = gltf.get("bufferViews") or []
    accessors = gltf.get("accessors") or []
    for mesh in gltf.get("meshes") or []:
        for prim in mesh.get("primitives") or []:
            idx = (prim.get("attributes") or {}).get(attr_key)
            if idx is None:
                continue
            acc = accessors[idx]
            view = views[acc["bufferView"]]
            off = (view.get("byteOffset") or 0) + (acc.get("byteOffset") or 0) + vertex_index * 16
            buffer[off : off + 16] = struct.pack("<4f", *values)
            return serialize_glb(gltf, bytes(buffer))
    raise AssertionError(f"no {attr_key} accessor")


class ClassifyTest(unittest.TestCase):
    def test_humanoid_skinned_structural_no_hint(self):
        c = classify_glb(humanoid_skinned_glb())
        self.assertEqual(c.kind, "humanoid")
        self.assertTrue(c.skinned)
        self.assertEqual(c.body_type, "humanoid")

    def test_biped_anthro_structural_humanoid(self):
        c = classify_glb(biped_anthro_skinned_glb())
        self.assertEqual(c.kind, "humanoid")

    def test_quadruped_non_human_refused(self):
        c = classify_glb(quadruped_skinned_glb())
        self.assertEqual(c.kind, "non-human")

    def test_quadruped_hint_refuses_even_humanoid_glb(self):
        c = classify_glb(humanoid_skinned_glb(), body_type="quadruped")
        self.assertEqual(c.kind, "non-human")

    def test_humanoid_hint_on_unskinned(self):
        c = classify_glb(unskinned_humanoidish_glb(), body_type="humanoid")
        self.assertEqual(c.kind, "humanoid")

    def test_human_character_type_hint(self):
        c = classify_glb(unskinned_humanoidish_glb(), character_type="human")
        self.assertEqual(c.kind, "humanoid")

    def test_unskinned_no_hint_unclassified(self):
        c = classify_glb(unskinned_humanoidish_glb())
        self.assertEqual(c.kind, "unclassified")


class RigPipelineTest(unittest.TestCase):
    def test_valid_humanoid_glb_rigs(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="测试角色")
        self.assertTrue(r["ok"])
        self.assertEqual(r["classification"]["kind"], "humanoid")
        self.assertTrue(r["sourceSkinned"])
        self.assertFalse(r["autoRigged"])
        self.assertIsNotNone(r["vrmBytes"])

    def test_skeleton_hierarchy(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="x")
        sk = r["skeleton"]
        self.assertGreaterEqual(sk["boneCount"], 15)
        self.assertEqual(sk["root"], "hips")
        ids = [h["id"] for h in sk["hierarchy"]]
        for bone in ("hips", "spine", "head", "leftArm", "rightLeg"):
            self.assertIn(bone, ids)
        # parent/child links present and consistent
        by_id = {h["id"]: h for h in sk["hierarchy"]}
        self.assertEqual(by_id["spine"]["parentId"], "hips")
        self.assertEqual(by_id["head"]["parentId"], "neck")

    def test_bone_mapping(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="x")
        bm = r["boneMapping"]
        self.assertEqual(bm["requiredCovered"], bm["requiredTotal"])
        self.assertEqual(bm["requiredTotal"], 15)
        self.assertIn("hips", bm["mapped"])
        self.assertIn("leftUpperLeg", bm["mapped"])
        # lower limbs are synthesized at export (our rig has single limb bones)
        for synth in ("leftLowerArm", "rightLowerArm", "leftLowerLeg", "rightLowerLeg"):
            self.assertIn(synth, bm["synthesized"])

    def test_bind_pose(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="x")
        bp = r["bindPose"]
        self.assertTrue(bp["ibmPerJoint"])
        self.assertEqual(bp["jointCount"], bp["ibmCount"])

    def test_skin_weights(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="x")
        sw = r["skinWeights"]
        self.assertGreater(sw["skinnedMeshes"], 0)
        self.assertGreater(sw["skinnedVertexCount"], 0)
        self.assertEqual(sw["jointCount"], r["bindPose"]["jointCount"])
        # every skinned primitive verified (JOINTS/WEIGHTS present, bounds, sums)
        verify_skin_weights(r["vrmBytes"])  # VRM carries the same weights

    def test_vrm_export_and_validation(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="测试角色")
        vrm = r["vrmBytes"]
        validate_glb(vrm)
        meta = validate_vrm(vrm)
        self.assertEqual(meta["specVersion"], "1.0")
        self.assertEqual(meta["meta"]["name"], "测试角色")
        self.assertEqual(r["vrmMeta"]["specVersion"], "1.0")

    def test_non_human_never_rigged(self):
        with self.assertRaises(RigPipelineError) as ctx:
            rig_glb_to_vrm(quadruped_skinned_glb())
        self.assertIn("非人体", str(ctx.exception))

    def test_malformed_glb_explicit_error(self):
        with self.assertRaises(RigPipelineError) as ctx:
            rig_glb_to_vrm(b"<html>not a glb</html>")
        self.assertIn("GLB 结构无效", str(ctx.exception))

    def test_unskinned_without_hint_refused(self):
        with self.assertRaises(RigPipelineError) as ctx:
            rig_glb_to_vrm(unskinned_humanoidish_glb())
        self.assertIn("分类", str(ctx.exception))

    def test_auto_rig_unskinned_humanoid(self):
        r = rig_glb_to_vrm(unskinned_humanoidish_glb(), body_type="humanoid", model_name="auto")
        self.assertTrue(r["ok"])
        self.assertTrue(r["autoRigged"])
        self.assertFalse(r["sourceSkinned"])
        self.assertEqual(r["classification"]["kind"], "humanoid")
        # auto-rig produces a real skinned mesh + bind pose + weights
        self.assertGreater(r["skeleton"]["boneCount"], 0)
        self.assertTrue(r["bindPose"]["ibmPerJoint"])
        self.assertGreater(r["skinWeights"]["skinnedVertexCount"], 0)
        validate_vrm(r["vrmBytes"])

    def test_auto_rig_refuses_non_human_body_type(self):
        with self.assertRaises(RigPipelineError) as ctx:
            auto_rig_glb(unskinned_humanoidish_glb(), body_type="quadruped", model_name="x")
        self.assertIn("auto-rig", str(ctx.exception))

    def test_no_fallback_never_mock(self):
        # The pipeline only ever raises explicit errors; there is no mock path.
        for bad in (quadruped_skinned_glb(), unskinned_humanoidish_glb(), b"junk"):
            try:
                rig_glb_to_vrm(bad)
                self.fail("should have raised for non-riggable input")
            except RigPipelineError:
                pass

    def test_deterministic(self):
        a = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="n")
        b = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="n")
        self.assertEqual(a["vrmBytes"], b["vrmBytes"])

    def test_mesh_topology_reported(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="x")
        t = r["topology"]
        self.assertGreater(t["meshCount"], 0)
        self.assertGreater(t["triangleCount"], 0)
        self.assertTrue(t["skinned"])


class ModelStoreRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_store = jobs._store
        jobs._store = ModelStore(Path(self.tmp))
        self._orig_store_tmp = jobs._store

    def tearDown(self):
        jobs._store = self._orig_store

    def test_pipeline_result_persisted_and_readable(self):
        src = humanoid_skinned_glb()
        rec = jobs.save_model_bytes(src, provider_id="mock", source_job_id="job-1", spec_hash="h1")
        from backend.app.routers.local3d import rig_local3d

        result = asyncio.run(rig_local3d(rec.id, {"bodyType": "humanoid", "modelName": "管线测试"}))
        self.assertTrue(result["ok"])
        vrm_model_id = result["vrmModelId"]
        stored = jobs.get_model(vrm_model_id)
        self.assertIsNotNone(stored)
        validate_vrm(stored)  # the persisted VRM round-trips as valid
        meta = jobs.get_model_record(vrm_model_id)
        self.assertEqual(meta.provider_id, "local3d-rig")
        self.assertEqual(meta.source_job_id, "job-1")

    def test_router_refuses_non_human_with_400_reason(self):
        from backend.app.routers.local3d import rig_local3d
        from fastapi import HTTPException

        src = quadruped_skinned_glb()
        rec = jobs.save_model_bytes(src, provider_id="mock", source_job_id="job-q", spec_hash="hq")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(rig_local3d(rec.id, {"bodyType": "quadruped"}))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Rig 失败", ctx.exception.detail)

    def test_router_404_unknown_model(self):
        from backend.app.routers.local3d import rig_local3d
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(rig_local3d("no-such-id", None))
        self.assertEqual(ctx.exception.status_code, 404)


class RendererLoadTest(unittest.TestCase):
    """Renderer-side loading proof: the SAME three.js GLTFLoader + @pixiv/three-vrm
    stack the renderer uses (ViewportManager.loadGLB / check_vrm.cjs) parses the
    pipeline VRM output. Test GLBs only."""

    def _run_gate(self, script, payload, suffix=".vrm"):
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(payload)
            tmp = f.name
        try:
            res = subprocess.run(
                ["node", os.path.join(ROOT, "tools", script), tmp],
                capture_output=True,
                text=True,
                cwd=ROOT,
                timeout=120,
            )
            self.assertEqual(res.returncode, 0, msg=f"{script} failed: {res.stdout} {res.stderr}")
            return res.stdout
        finally:
            os.unlink(tmp)

    def test_skinned_humanoid_vrm_loads_in_renderer(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="x")
        out = self._run_gate("check_vrm.cjs", r["vrmBytes"])
        self.assertIn("VRM_OK", out)

    def test_auto_rigged_vrm_loads_in_renderer(self):
        r = rig_glb_to_vrm(unskinned_humanoidish_glb(), body_type="humanoid", model_name="auto")
        out = self._run_gate("check_vrm.cjs", r["vrmBytes"])
        self.assertIn("VRM_OK", out)

    def test_biped_anthro_vrm_loads_in_renderer(self):
        r = rig_glb_to_vrm(biped_anthro_skinned_glb(), model_name="兽人")
        out = self._run_gate("check_vrm.cjs", r["vrmBytes"])
        self.assertIn("VRM_OK", out)

    def test_auto_rigged_skinned_glb_loads_in_gltf_loader(self):
        skinned = auto_rig_glb(unskinned_humanoidish_glb(), "humanoid", "x")
        out = self._run_gate("check_skinned_glb.cjs", skinned, suffix=".glb")
        self.assertIn("SKINNED_OK", out)


class RigQualityUpgradeTest(unittest.TestCase):
    """Phase 3-G: richer skeleton, name normalization, sanity + weight checks."""

    def test_standard_humanoid_auto_rig_split_limb_mapping(self):
        r = rig_glb_to_vrm(unskinned_humanoidish_glb(), body_type="humanoid", model_name="x")
        self.assertTrue(r["ok"])
        bm = r["boneMapping"]
        self.assertEqual(bm["requiredCovered"], 15)
        self.assertEqual(bm["requiredTotal"], 15)
        # split-limb skeleton maps every required bone directly -> no synthesis
        self.assertEqual(bm["synthesized"], [])
        # richer hierarchy: upper AND lower limbs present
        ids = [h["id"] for h in r["skeleton"]["hierarchy"]]
        for bone in (
            "hips", "spine", "chest", "neck", "head",
            "leftUpperArm", "leftLowerArm", "leftHand",
            "rightUpperArm", "rightLowerArm", "rightHand",
            "leftUpperLeg", "leftLowerLeg", "leftFoot",
            "rightUpperLeg", "rightLowerLeg", "rightFoot",
        ):
            self.assertIn(bone, ids, f"missing {bone}")
        self.assertEqual(r["skeleton"]["root"], "hips")

    def test_bone_name_normalization_unit(self):
        cases = {
            "Hips": "hips", "Pelvis": "hips", "Spine": "spine", "Chest": "chest",
            "Head": "head", "LeftArm": "leftArm", "left_arm": "leftArm",
            "Arm_L": "leftArm", "l_Arm": "leftArm", "LeftUpperArm": "leftUpperArm",
            "LeftForearm": "leftLowerArm", "RightShin": "rightLowerLeg",
            "RightThigh": "rightUpperLeg", "LeftHand": "leftHand",
            "Foot_R": "rightFoot", "Leg_L": "leftLeg",
        }
        for raw, expect in cases.items():
            self.assertEqual(normalize_bone_name(raw), expect, raw)

    def test_name_variant_skinned_glb_normalizes_and_rigs(self):
        glb = variant_named_skinned_glb()
        c = classify_glb(glb)  # classification already normalizes names
        self.assertEqual(c.kind, "humanoid")
        norm = normalize_skeleton_glb(glb)
        self.assertNotEqual(norm, glb)  # rename happened
        r = rig_glb_to_vrm(glb, model_name="variant")  # full pipeline
        self.assertTrue(r["ok"])
        self.assertTrue(r["sourceSkinned"])
        self.assertTrue(r["nameNormalized"])
        self.assertEqual(r["boneMapping"]["requiredCovered"], 15)
        validate_vrm(r["vrmBytes"])

    def test_missing_required_bone_refused(self):
        glb = missing_left_leg_skinned_glb()
        self.assertEqual(classify_glb(glb).kind, "humanoid")  # still humanoid
        with self.assertRaises(RigPipelineError) as ctx:
            rig_glb_to_vrm(glb, model_name="x")
        self.assertTrue("无法为 required" in str(ctx.exception) or "导出失败" in str(ctx.exception))

    def test_wrong_bone_direction_refused(self):
        glb = inverted_head_skinned_glb()
        with self.assertRaises(RigPipelineError) as ctx:
            verify_skeleton_sanity(glb)
        self.assertIn("head", str(ctx.exception))
        with self.assertRaises(RigPipelineError):
            rig_glb_to_vrm(glb, model_name="x")

    def test_zero_length_bone_refused(self):
        bones = [
            BoneNode("hips", "骨盆", None, (0.0, 0.55, 0.0)),
            BoneNode("spine", "脊椎", "hips", (0.0, 0.55, 0.0)),  # zero-length child
            BoneNode("head", "头部", "spine", (0.0, 1.50, 0.0)),
        ]
        glb = build_glb([Primitive("box", (0.3, 0.3, 0.3), center=(0, 0.9, 0), color="#4466AA")], bones=bones)
        with self.assertRaises(RigPipelineError) as ctx:
            verify_skeleton_sanity(glb)
        self.assertIn("长度", str(ctx.exception))

    def test_weight_anomaly_refused(self):
        glb = _patch_f32_attr(humanoid_skinned_glb(), "WEIGHTS_0", 0, (0.0, 0.0, 0.0, 0.0))
        with self.assertRaises(RigPipelineError) as ctx:
            verify_skin_weights(glb)
        self.assertIn("权重和", str(ctx.exception))
        with self.assertRaises(RigPipelineError):
            rig_glb_to_vrm(glb, model_name="x")

    def test_weight_continuity_anomaly_refused(self):
        # Scramble joints so most adjacent vertices share no joint.
        glb = humanoid_skinned_glb()
        jcount = verify_skin_weights(glb)["jointCount"]
        scrambled = glb
        # patch a block of vertices in the first primitive with disjoint joints
        for v in range(0, 24):
            scrambled = _patch_u8_attr(scrambled, "JOINTS_0", v, [(v * 4 + k) % jcount for k in range(4)])
        with self.assertRaises(RigPipelineError) as ctx:
            verify_skin_weights(scrambled)
        self.assertIn("连续性", str(ctx.exception))

    def test_sanity_and_continuity_reported_on_valid(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="x")
        self.assertTrue(r["skeletonSanity"]["connected"])
        self.assertTrue(r["skeletonSanity"]["singleRoot"])
        self.assertGreater(r["skinWeights"]["weightContinuity"], 0.3)

    def test_already_skinned_never_re_auto_rigged(self):
        r = rig_glb_to_vrm(humanoid_skinned_glb(), model_name="x")
        self.assertTrue(r["sourceSkinned"])
        self.assertFalse(r["autoRigged"])
        # reuse keeps the source joint count (13 humanoid + 2 ears = 15);
        # no auto-rig expansion onto a richer skeleton.
        self.assertEqual(r["skeleton"]["boneCount"], len(_skin_bone_ids(humanoid_skinned_glb())))


if __name__ == "__main__":
    unittest.main()
