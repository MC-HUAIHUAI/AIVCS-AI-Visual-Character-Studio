"""VRM 1.0 Humanoid mapping (Phase 2.7-B).

Bone names / required / optional sets and required fields are taken from the
OFFICIAL VRM 1.0 JSON schemas:

  - VRMC_vrm.schema.json
      required: ["specVersion", "meta", "humanoid"]
  - VRMC_vrm.meta.schema.json
      required: ["name", "authors", "licenseUrl"]
  - VRMC_vrm.humanoid.humanBones.schema.json
      required (15): hips, spine, head, leftUpperLeg, leftLowerLeg, leftFoot,
      rightUpperLeg, rightLowerLeg, rightFoot, leftUpperArm, leftLowerArm,
      leftHand, rightUpperArm, rightLowerArm, rightHand
      (chest / upperChest / neck / eyes / jaw / toes / shoulders / fingers are
       optional)
  - VRMC_vrm.humanoid.humanBones.humanBone.schema.json
      required: ["node"]

Source (retrieved 2026-08-14):
  https://raw.githubusercontent.com/vrm-c/vrm-specification/master/specification/VRMC_vrm-1.0/schema/...
"""

from __future__ import annotations

REQUIRED_HUMAN_BONES: tuple[str, ...] = (
    "hips",
    "spine",
    "head",
    "leftUpperLeg",
    "leftLowerLeg",
    "leftFoot",
    "rightUpperLeg",
    "rightLowerLeg",
    "rightFoot",
    "leftUpperArm",
    "leftLowerArm",
    "leftHand",
    "rightUpperArm",
    "rightLowerArm",
    "rightHand",
)

OPTIONAL_HUMAN_BONES: tuple[str, ...] = (
    "chest",
    "upperChest",
    "neck",
    "leftEye",
    "rightEye",
    "jaw",
    "leftToes",
    "rightToes",
    "leftShoulder",
    "rightShoulder",
    "leftThumbMetacarpal",
    "leftThumbProximal",
    "leftThumbDistal",
    "rightThumbMetacarpal",
    "rightThumbProximal",
    "rightThumbDistal",
)

# Body types that form a meaningful VRM 1.0 Humanoid with our rig. Others
# (quadruped / bird / dragon) are rejected with a safe error rather than being
# forced into a misleading humanoid mapping.
VRM_SUPPORTED_BODY_TYPES: tuple[str, ...] = ("humanoid", "biped-anthro", "custom")

# Map our rig bone id -> VRM human bone name (for humanoid-like rigs).
RIG_TO_VRM: dict[str, str] = {
    "hips": "hips",
    "spine": "spine",
    "chest": "chest",
    "neck": "neck",
    "head": "head",
    "leftArm": "leftUpperArm",
    "leftHand": "leftHand",
    "rightArm": "rightUpperArm",
    "rightHand": "rightHand",
    "leftLeg": "leftUpperLeg",
    "leftFoot": "leftFoot",
    "rightLeg": "rightUpperLeg",
    "rightFoot": "rightFoot",
}

# Required VRM bones that must be SYNTHESIZED (export-time only) because our rig
# models each limb as a single bone. For each: the parent rig bone and the
# reference (end) rig bone used to interpolate its world position.
SYNTHESIZE: dict[str, tuple[str, str]] = {
    "leftLowerArm": ("leftArm", "leftHand"),
    "rightLowerArm": ("rightArm", "rightHand"),
    "leftLowerLeg": ("leftLeg", "leftFoot"),
    "rightLowerLeg": ("rightLeg", "rightFoot"),
}

# Terminal hand/foot bones. Rigs that lack a distinct hand/foot bone
# (biped-anthro) synthesize them at export time, rooted at the corresponding
# limb bone. Deterministic order: hands first, then feet.
TERMINAL_SYNTHESIZE: dict[str, str] = {
    "leftHand": "leftArm",
    "rightHand": "rightArm",
    "leftFoot": "leftLeg",
    "rightFoot": "rightLeg",
}
