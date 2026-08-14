"""RigBuilder - CharacterSpec -> BoneNode[] (Phase 2.6-A).

Instantiates a rig profile into a deterministic bone tree in MODEL SPACE:

  - RigProfile bone templates -> BoneNode (id / label / parent / position);
  - positions are T-pose model-space coordinates (same space the LocalLowPower
    primitives live in - Phase 2.6-B binding happens in this space);
  - height scaling via heightCm / 160;
  - non-human anatomy appendages (ears / horns / antlers / wings / tail) become
    extra bones rooted at head / chest / hips.

This stage produces ONLY the bone tree (no GLB, no skinning). Bone counts are
NOT a contract - tests assert "at least these key bones + correct hierarchy".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas.character import CharacterSpec
from .rig_profiles import RigBoneDef, get_rig_profile

BASE_HEIGHT_CM = 160.0

# CharacterSpec.body_type -> rig profile id (biped-anthro -> anthropomorphic).
RIG_FOR_BODY_TYPE = {
    "humanoid": "humanoid",
    "biped-anthro": "anthropomorphic",
    "quadruped": "quadruped",
    "bird": "bird",
    "dragon": "dragon",
    "custom": "custom",
}


@dataclass
class BoneNode:
    id: str
    label: str
    parent_id: str | None
    position: tuple[float, float, float]  # model-space T-pose

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "parent_id": self.parent_id, "position": list(self.position)}


# Base T-pose model-space positions (heightCm = 160). Values are deliberately
# plain; the builder scales them by heightCm / 160.
_BASE_POSITIONS: dict[str, dict[str, tuple[float, float, float]]] = {
    "humanoid": {
        "hips": (0.0, 0.55, 0.0),
        "spine": (0.0, 0.85, 0.0),
        "chest": (0.0, 1.05, 0.0),
        "neck": (0.0, 1.25, 0.0),
        "head": (0.0, 1.50, 0.0),
        "leftArm": (-0.38, 1.05, 0.0),
        "rightArm": (0.38, 1.05, 0.0),
        "leftHand": (-0.38, 0.78, 0.0),
        "rightHand": (0.38, 0.78, 0.0),
        "leftLeg": (-0.15, 0.28, 0.0),
        "rightLeg": (0.15, 0.28, 0.0),
        "leftFoot": (-0.15, 0.05, 0.0),
        "rightFoot": (0.15, 0.05, 0.0),
    },
    "anthropomorphic": {
        "hips": (0.0, 0.55, 0.0),
        "spine": (0.0, 0.85, 0.0),
        "chest": (0.0, 1.05, 0.0),
        "neck": (0.0, 1.25, 0.0),
        "head": (0.0, 1.50, 0.0),
        "leftArm": (-0.38, 1.05, 0.0),
        "rightArm": (0.38, 1.05, 0.0),
        "leftLeg": (-0.15, 0.28, 0.0),
        "rightLeg": (0.15, 0.28, 0.0),
        "tail": (0.0, 0.55, -0.30),
        "ears_L": (-0.14, 1.60, 0.0),
        "ears_R": (0.14, 1.60, 0.0),
    },
    "quadruped": {
        "hips": (0.0, 0.45, -0.20),
        "spine": (0.0, 0.55, 0.10),
        "chest": (0.0, 0.60, 0.45),
        "neck": (0.0, 0.65, 0.75),
        "head": (0.0, 0.70, 0.90),
        "frontLeg_L": (-0.25, 0.30, 0.45),
        "frontLeg_R": (0.25, 0.30, 0.45),
        "rearLeg_L": (-0.25, 0.25, -0.20),
        "rearLeg_R": (0.25, 0.25, -0.20),
        "tail": (0.0, 0.60, -0.55),
    },
    "bird": {
        "hips": (0.0, 0.35, 0.0),
        "spine": (0.0, 0.60, 0.0),
        "neck": (0.0, 0.80, 0.15),
        "head": (0.0, 0.95, 0.30),
        "wing_L": (-0.40, 0.60, 0.0),
        "wing_R": (0.40, 0.60, 0.0),
        "leg_L": (-0.12, 0.18, 0.0),
        "leg_R": (0.12, 0.18, 0.0),
        "tail": (0.0, 0.50, -0.35),
    },
    "dragon": {
        "hips": (0.0, 0.50, -0.20),
        "spine": (0.0, 0.75, 0.10),
        "chest": (0.0, 0.95, 0.40),
        "neck": (0.0, 1.20, 0.60),
        "head": (0.0, 1.45, 0.75),
        "arm_L": (-0.35, 0.95, 0.35),
        "arm_R": (0.35, 0.95, 0.35),
        "leg_L": (-0.20, 0.30, -0.20),
        "leg_R": (0.20, 0.30, -0.20),
        "wing_L": (-0.60, 0.90, 0.30),
        "wing_R": (0.60, 0.90, 0.30),
        "tail": (0.0, 0.55, -0.75),
        "horn_L": (-0.12, 1.65, 0.70),
        "horn_R": (0.12, 1.65, 0.70),
    },
}


def _scale(pos: tuple[float, float, float], factor: float) -> tuple[float, float, float]:
    return (round(pos[0] * factor, 6), round(pos[1] * factor, 6), round(pos[2] * factor, 6))


def _offset(pos: tuple[float, float, float], dx: float, dy: float, dz: float) -> tuple[float, float, float]:
    return (pos[0] + dx, pos[1] + dy, pos[2] + dz)


def _has_bone(nodes: list[BoneNode], prefix: str) -> bool:
    return any(n.id.startswith(prefix) for n in nodes)


def _appendage_bones(spec: CharacterSpec, nodes: list[BoneNode], scale: float) -> None:
    anatomy = spec.anatomy
    head = next((n for n in nodes if n.id == "head"), None)
    chest = next((n for n in nodes if n.id == "chest"), None) or next((n for n in nodes if n.id == "spine"), None)
    hips = next((n for n in nodes if n.id == "hips"), None)

    if anatomy.ears and head is not None and not _has_bone(nodes, "ears"):
        nodes.append(BoneNode("ears_L", "左耳", "head", _scale(_offset(head.position, -0.13, 0.10, 0.0), scale)))
        nodes.append(BoneNode("ears_R", "右耳", "head", _scale(_offset(head.position, 0.13, 0.10, 0.0), scale)))

    if (anatomy.horns or anatomy.antlers) and head is not None and not _has_bone(nodes, "horn") and not _has_bone(nodes, "antler"):
        prefix = "antler" if anatomy.antlers and not anatomy.horns else "horn"
        label = "鹿角" if prefix == "antler" else "角"
        nodes.append(BoneNode(f"{prefix}_L", f"{label}（左）", "head", _scale(_offset(head.position, -0.12, 0.16, 0.0), scale)))
        nodes.append(BoneNode(f"{prefix}_R", f"{label}（右）", "head", _scale(_offset(head.position, 0.12, 0.16, 0.0), scale)))

    if anatomy.wings and chest is not None and not _has_bone(nodes, "wing"):
        nodes.append(BoneNode("wing_L", "左翼", chest.id, _scale(_offset(chest.position, -0.55, 0.05, 0.0), scale)))
        nodes.append(BoneNode("wing_R", "右翼", chest.id, _scale(_offset(chest.position, 0.55, 0.05, 0.0), scale)))

    if anatomy.tail in ("single", "multiple") and hips is not None:
        if not _has_bone(nodes, "tail"):
            nodes.append(BoneNode("tail_01", "尾巴 1", "hips", _scale(_offset(hips.position, 0.0, 0.05, -0.30), scale)))
        if anatomy.tail == "multiple":
            count = len([n for n in nodes if n.id.startswith("tail_")])
            for i in range(count + 1, count + 3):  # append 2 more segments
                nodes.append(BoneNode(f"tail_{i:02d}", f"尾巴 {i}", f"tail_{i - 1:02d}", _scale(_offset(hips.position, 0.0, 0.05 + 0.15 * i, -0.30 - 0.25 * i), scale)))


def build_bone_tree(spec: CharacterSpec) -> list[BoneNode]:
    """Build the deterministic MODEL-SPACE bone tree for a CharacterSpec.

    body_type maps to a rig profile (custom -> humanoid). The output is a flat
    list of BoneNode with parent_id links; positions are T-pose model space
    (scaled by heightCm / 160), the same space Phase 2.6-B will bind meshes in.
    """
    profile_id = RIG_FOR_BODY_TYPE.get(spec.body_type or "humanoid", "humanoid")
    profile = get_rig_profile(profile_id)
    base = _BASE_POSITIONS.get(profile_id, _BASE_POSITIONS["humanoid"])

    scale = max(0.5, min(2.0, (spec.height_cm or BASE_HEIGHT_CM) / BASE_HEIGHT_CM))

    nodes: list[BoneNode] = []
    for bone_def in profile:
        pos = base.get(bone_def.id, (0.0, 0.0, 0.0))
        nodes.append(BoneNode(bone_def.id, bone_def.label, bone_def.parent, _scale(pos, scale)))

    _appendage_bones(spec, nodes, scale)
    return nodes


def bone_tree_to_dicts(nodes: list[BoneNode]) -> list[dict]:
    return [n.to_dict() for n in nodes]
