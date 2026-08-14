"""RigBuilder tests (Phase 2.6-A).

Assertions are "at least these key bones + hierarchy correct", NOT exact bone
counts - counts are not a contract.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.services.rig_builder import BoneNode, bone_tree_to_dicts, build_bone_tree  # noqa: E402


def make_spec(body_type="humanoid", height_cm=160, **anatomy):
    defaults = {
        "hasHead": True,
        "hasFace": True,
        "hasTorso": True,
        "hasLimbs": True,
        "tail": "none",
        "wings": False,
        "ears": True,
        "horns": False,
        "antlers": False,
        "snout": False,
        "muzzle": False,
        "beak": False,
        "paws": False,
        "claws": False,
        "hooves": False,
        "fins": False,
        "tentacles": False,
        "extraLimbs": False,
        "customAppendages": [],
    }
    defaults.update(anatomy)
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
        anatomy=defaults,
    )


def by_id(nodes, bone_id):
    return next(n for n in nodes if n.id == bone_id)


class RigBuilderTest(unittest.TestCase):
    def test_humanoid_key_bones_and_hierarchy(self):
        nodes = build_bone_tree(make_spec(body_type="humanoid"))
        required = ["hips", "spine", "chest", "neck", "head", "leftArm", "rightArm", "leftHand", "rightHand", "leftLeg", "rightLeg", "leftFoot", "rightFoot"]
        for bone in required:
            self.assertIn(bone, [n.id for n in nodes], f"missing key bone {bone}")
        self.assertIsNone(by_id(nodes, "hips").parent_id)
        self.assertEqual(by_id(nodes, "spine").parent_id, "hips")
        self.assertEqual(by_id(nodes, "chest").parent_id, "spine")
        self.assertEqual(by_id(nodes, "neck").parent_id, "chest")
        self.assertEqual(by_id(nodes, "head").parent_id, "neck")
        self.assertEqual(by_id(nodes, "leftHand").parent_id, "leftArm")
        self.assertEqual(by_id(nodes, "leftFoot").parent_id, "leftLeg")

    def test_anthropomorphic_has_tail_and_ears(self):
        nodes = build_bone_tree(make_spec(body_type="biped-anthro"))
        self.assertEqual(by_id(nodes, "tail").parent_id, "hips")
        self.assertEqual(by_id(nodes, "ears_L").parent_id, "head")
        self.assertEqual(by_id(nodes, "ears_R").parent_id, "head")

    def test_quadruped_hierarchy(self):
        nodes = build_bone_tree(make_spec(body_type="quadruped"))
        self.assertEqual(by_id(nodes, "frontLeg_L").parent_id, "chest")
        self.assertEqual(by_id(nodes, "rearLeg_L").parent_id, "hips")
        self.assertEqual(by_id(nodes, "tail").parent_id, "hips")
        self.assertEqual(by_id(nodes, "head").parent_id, "neck")

    def test_bird_hierarchy(self):
        nodes = build_bone_tree(make_spec(body_type="bird"))
        self.assertEqual(by_id(nodes, "wing_L").parent_id, "spine")
        self.assertEqual(by_id(nodes, "leg_L").parent_id, "hips")
        self.assertEqual(by_id(nodes, "tail").parent_id, "hips")

    def test_dragon_hierarchy(self):
        nodes = build_bone_tree(make_spec(body_type="dragon"))
        self.assertEqual(by_id(nodes, "horn_L").parent_id, "head")
        self.assertEqual(by_id(nodes, "wing_L").parent_id, "chest")
        self.assertEqual(by_id(nodes, "tail").parent_id, "hips")

    def test_custom_falls_back_to_humanoid(self):
        nodes = build_bone_tree(make_spec(body_type="custom"))
        self.assertIn("hips", [n.id for n in nodes])
        self.assertIn("head", [n.id for n in nodes])
        self.assertEqual(by_id(nodes, "head").parent_id, "neck")

    def test_anatomy_appendages_on_humanoid(self):
        nodes = build_bone_tree(make_spec(body_type="humanoid", tail="single", horns=True, wings=True))
        self.assertEqual(by_id(nodes, "horn_L").parent_id, "head")
        self.assertEqual(by_id(nodes, "wing_L").parent_id, "chest")
        self.assertEqual(by_id(nodes, "tail_01").parent_id, "hips")

    def test_multiple_tail_chains_segments(self):
        nodes = build_bone_tree(make_spec(body_type="humanoid", tail="multiple"))
        self.assertIn("tail_01", [n.id for n in nodes])
        self.assertIn("tail_02", [n.id for n in nodes])
        self.assertIn("tail_03", [n.id for n in nodes])
        self.assertEqual(by_id(nodes, "tail_02").parent_id, "tail_01")
        self.assertEqual(by_id(nodes, "tail_03").parent_id, "tail_02")

    def test_height_scaling(self):
        short = build_bone_tree(make_spec(body_type="humanoid", height_cm=160))
        tall = build_bone_tree(make_spec(body_type="humanoid", height_cm=200))
        ratio = by_id(tall, "head").position[1] / by_id(short, "head").position[1]
        self.assertAlmostEqual(ratio, 1.25, places=3)
        # feet stay near ground
        self.assertAlmostEqual(by_id(short, "leftFoot").position[1], 0.05, places=3)

    def test_deterministic(self):
        a = build_bone_tree(make_spec(body_type="dragon", tail="multiple", wings=True, horns=True))
        b = build_bone_tree(make_spec(body_type="dragon", tail="multiple", wings=True, horns=True))
        self.assertEqual(bone_tree_to_dicts(a), bone_tree_to_dicts(b))

    def test_no_anatomy_extra_bones_when_disabled(self):
        nodes = build_bone_tree(make_spec(body_type="humanoid", ears=False, tail="none", wings=False, horns=False))
        ids = [n.id for n in nodes]
        self.assertNotIn("ears_L", ids)
        self.assertNotIn("tail_01", ids)
        self.assertNotIn("wing_L", ids)
        self.assertNotIn("horn_L", ids)


if __name__ == "__main__":
    unittest.main()
