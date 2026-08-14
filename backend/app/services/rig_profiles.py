"""Rig profiles - Python mirror of src/shared/types.ts RIG_PROFILES (Phase 2.6).

Bone templates per rig profile. These are the canonical skeleton definitions
the RigBuilder instantiates into BoneNode trees. Phase 2.7 (VRM) will map these
bones onto VRM Humanoid + ExtraBones.
"""

from __future__ import annotations

from dataclasses import dataclass

RIG_PROFILE_IDS = ("humanoid", "quadruped", "anthropomorphic", "bird", "dragon", "custom")


@dataclass(frozen=True)
class RigBoneDef:
    id: str
    label: str
    parent: str | None = None


# Mirrors src/shared/types.ts RIG_PROFILES (bone ids/labels/parents).
RIG_PROFILES: dict[str, tuple[RigBoneDef, ...]] = {
    "humanoid": (
        RigBoneDef("hips", "骨盆"),
        RigBoneDef("spine", "脊椎", "hips"),
        RigBoneDef("chest", "胸腔", "spine"),
        RigBoneDef("neck", "颈部", "chest"),
        RigBoneDef("head", "头部", "neck"),
        RigBoneDef("leftArm", "左臂", "chest"),
        RigBoneDef("leftHand", "左手", "leftArm"),
        RigBoneDef("rightArm", "右臂", "chest"),
        RigBoneDef("rightHand", "右手", "rightArm"),
        RigBoneDef("leftLeg", "左腿", "hips"),
        RigBoneDef("leftFoot", "左脚", "leftLeg"),
        RigBoneDef("rightLeg", "右腿", "hips"),
        RigBoneDef("rightFoot", "右脚", "rightLeg"),
    ),
    "quadruped": (
        RigBoneDef("hips", "骨盆"),
        RigBoneDef("spine", "脊椎", "hips"),
        RigBoneDef("chest", "胸腔", "spine"),
        RigBoneDef("neck", "颈部", "chest"),
        RigBoneDef("head", "头部", "neck"),
        RigBoneDef("frontLeg_L", "前腿（左）", "chest"),
        RigBoneDef("frontLeg_R", "前腿（右）", "chest"),
        RigBoneDef("rearLeg_L", "后腿（左）", "hips"),
        RigBoneDef("rearLeg_R", "后腿（右）", "hips"),
        RigBoneDef("tail", "尾巴", "hips"),
    ),
    "anthropomorphic": (
        RigBoneDef("hips", "骨盆"),
        RigBoneDef("spine", "脊椎", "hips"),
        RigBoneDef("chest", "胸腔", "spine"),
        RigBoneDef("neck", "颈部", "chest"),
        RigBoneDef("head", "头部", "neck"),
        RigBoneDef("leftArm", "左臂", "chest"),
        RigBoneDef("rightArm", "右臂", "chest"),
        RigBoneDef("leftLeg", "左腿", "hips"),
        RigBoneDef("rightLeg", "右腿", "hips"),
        RigBoneDef("tail", "尾巴", "hips"),
        RigBoneDef("ears_L", "左耳", "head"),
        RigBoneDef("ears_R", "右耳", "head"),
    ),
    "bird": (
        RigBoneDef("hips", "骨盆"),
        RigBoneDef("spine", "脊椎", "hips"),
        RigBoneDef("neck", "颈部", "spine"),
        RigBoneDef("head", "头部", "neck"),
        RigBoneDef("wing_L", "左翅", "spine"),
        RigBoneDef("wing_R", "右翅", "spine"),
        RigBoneDef("leg_L", "左腿", "hips"),
        RigBoneDef("leg_R", "右腿", "hips"),
        RigBoneDef("tail", "尾羽", "hips"),
    ),
    "dragon": (
        RigBoneDef("hips", "骨盆"),
        RigBoneDef("spine", "脊椎", "hips"),
        RigBoneDef("chest", "胸腔", "spine"),
        RigBoneDef("neck", "颈部", "chest"),
        RigBoneDef("head", "头部", "neck"),
        RigBoneDef("arm_L", "左臂", "chest"),
        RigBoneDef("arm_R", "右臂", "chest"),
        RigBoneDef("leg_L", "左腿", "hips"),
        RigBoneDef("leg_R", "右腿", "hips"),
        RigBoneDef("wing_L", "左翼", "chest"),
        RigBoneDef("wing_R", "右翼", "chest"),
        RigBoneDef("tail", "尾巴", "hips"),
        RigBoneDef("horn_L", "左角", "head"),
        RigBoneDef("horn_R", "右角", "head"),
    ),
    "custom": (),
}


def get_rig_profile(profile_id: str) -> tuple[RigBoneDef, ...]:
    """Return a rig profile's bone template; unknown/custom fall back to humanoid."""
    if profile_id not in RIG_PROFILES or profile_id == "custom":
        return RIG_PROFILES["humanoid"]
    return RIG_PROFILES[profile_id]
