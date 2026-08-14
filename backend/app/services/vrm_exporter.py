"""VRM 1.0 exporter (Phase 2.7-B).

Takes a Phase 2.6 SKINNED GLB (bones= output) and emits a VRM 1.0 GLB:

  - keeps nodes / POSITION / skin / JOINTS_0 / WEIGHTS_0 / inverseBindMatrices
    of the input unchanged;
  - synthesizes the required split limb bones (leftLowerArm/... /leftLowerLeg)
    as additional joints (appended), with bind-pose world-inverse IBM entries;
  - injects the VRMC_vrm extension (specVersion / meta / humanoid) per the
    official VRM 1.0 schema;
  - re-serializes the same BIN buffer (extended only by the new IBM matrices).

Deterministic. No hips re-root (only added later if the spec/validation proves
it is required). Non-humanoid body types are rejected with a clear error.

NOT implemented: SpringBone / Animation / MToon / VRM 0.x / UI.
"""

from __future__ import annotations

import json
import struct

from .glb_builder import serialize_glb, validate_glb
from .vrm_mapping import (
    OPTIONAL_HUMAN_BONES,
    REQUIRED_HUMAN_BONES,
    RIG_TO_VRM,
    SYNTHESIZE,
    VRM_SUPPORTED_BODY_TYPES,
)

SPEC_VERSION = "1.0"
AUTHOR = "AIVCS"
DEFAULT_LICENSE_URL = "https://vrm.dev/"
EXTENSION_NAME = "VRMC_vrm"

_VRM_TO_RIG: dict[str, str] = {v: k for k, v in RIG_TO_VRM.items()}


class VrmExportError(RuntimeError):
    """Raised when a GLB cannot be exported to VRM."""


def _parse(data: bytes) -> tuple[dict, bytearray]:
    validate_glb(data)
    clen, _ctype = struct.unpack("<I4s", data[12:20])
    gltf = json.loads(data[20 : 20 + clen])
    bin_start = 20 + clen + 8
    buffer = bytearray(data[bin_start:])
    return gltf, buffer


def _world_positions(nodes: list, parent_of: dict) -> dict[int, tuple[float, float, float]]:
    world: dict[int, tuple[float, float, float]] = {}

    def resolve(i: int) -> tuple[float, float, float]:
        if i in world:
            return world[i]
        t = tuple(float(v) for v in nodes[i].get("translation", (0.0, 0.0, 0.0)))
        p = parent_of.get(i)
        pos = t if p is None else tuple(a + b for a, b in zip(resolve(p), t))
        world[i] = pos
        return pos

    for i in range(len(nodes)):
        resolve(i)
    return world


def _lerp(a: tuple, b: tuple, t: float) -> tuple[float, float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def export_vrm(glb_bytes: bytes, body_type: str, model_name: str) -> bytes:
    """Export a Phase 2.6 skinned GLB to a VRM 1.0 GLB.

    Raises VrmExportError on unsupported body types or missing skin.
    """
    if body_type not in VRM_SUPPORTED_BODY_TYPES:
        raise VrmExportError(
            f"bodyType '{body_type}' 无法导出合法的 VRM Humanoid；仅支持 {' / '.join(VRM_SUPPORTED_BODY_TYPES)}"
        )

    gltf, buffer = _parse(glb_bytes)

    skins = gltf.get("skins")
    if not skins:
        raise VrmExportError("需要 skinned GLB（AIVCS_LOCAL3D_RIG_ENABLED=true 生成）才能导出 VRM")

    nodes = gltf["nodes"]
    skin = skins[0]
    joints = list(skin["joints"])
    ibm_acc_idx = skin["inverseBindMatrices"]
    accessors = gltf["accessors"]
    views = gltf["bufferViews"]
    ibm_view = views[accessors[ibm_acc_idx]["bufferView"]]

    parent_of: dict[int, int] = {}
    for i, node in enumerate(nodes):
        if "parent" in node:
            parent_of[i] = node["parent"]

    # bone node index -> rig bone id (bone nodes are named by their rig id)
    bone_to_node: dict[str, int] = {}
    for idx in joints:
        name = nodes[idx].get("name", "")
        if name:
            bone_to_node[name] = idx

    world = _world_positions(nodes, parent_of)

    def node_pos(bone_id: str) -> tuple[float, float, float]:
        idx = bone_to_node.get(bone_id)
        if idx is None:
            raise VrmExportError(f"缺少骨骼 {bone_id}")
        return world[idx]

    human_bones: dict[str, dict] = {}
    to_synthesize: list[tuple[str, int, tuple[float, float, float]]] = []

    # Required bones.
    for vrm_bone in REQUIRED_HUMAN_BONES:
        rig = _VRM_TO_RIG.get(vrm_bone)
        if rig is not None and rig in bone_to_node:
            human_bones[vrm_bone] = {"node": bone_to_node[rig]}
        elif vrm_bone in SYNTHESIZE:
            parent_rig, end_rig = SYNTHESIZE[vrm_bone]
            parent_idx = bone_to_node[parent_rig]
            parent_pos = world[parent_idx]
            end_pos = node_pos(end_rig)
            to_synthesize.append((vrm_bone, parent_idx, _lerp(parent_pos, end_pos, 0.5)))
        else:
            raise VrmExportError(f"无法为 required 骨骼 {vrm_bone} 建立映射")

    # Optional bones that exist in our rig.
    for vrm_bone in OPTIONAL_HUMAN_BONES:
        rig = _VRM_TO_RIG.get(vrm_bone)
        if rig is not None and rig in bone_to_node:
            human_bones.setdefault(vrm_bone, {"node": bone_to_node[rig]})

    # Append synthesized nodes + joints + IBM entries.
    if to_synthesize:
        for vrm_bone, parent_idx, world_pos in to_synthesize:
            parent_world = world[parent_idx]
            node_idx = len(nodes)
            nodes.append(
                {
                    "name": vrm_bone,
                    "parent": parent_idx,
                    "translation": [
                        round(world_pos[0] - parent_world[0], 6),
                        round(world_pos[1] - parent_world[1], 6),
                        round(world_pos[2] - parent_world[2], 6),
                    ],
                }
            )
            joints.append(node_idx)
            human_bones[vrm_bone] = {"node": node_idx}

        extra = struct.pack(
            "<%df" % (16 * len(to_synthesize)),
            *[
                v
                for _name, _pidx, p in to_synthesize
                for v in (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -p[0], -p[1], -p[2], 1.0)
            ],
        )
        while len(buffer) % 4:
            buffer.append(0)
        ibm_view["byteLength"] += len(extra)
        buffer += extra
        accessors[ibm_acc_idx]["count"] += len(to_synthesize)
        gltf["buffers"][0]["byteLength"] += len(extra)

    skin["joints"] = joints

    meta = {
        "name": model_name or "AIVCS Character",
        "version": "1.0",
        "authors": [AUTHOR],
        "licenseUrl": DEFAULT_LICENSE_URL,
    }
    gltf.setdefault("extensionsUsed", []).append(EXTENSION_NAME)
    gltf["extensions"] = {
        EXTENSION_NAME: {
            "specVersion": SPEC_VERSION,
            "meta": meta,
            "humanoid": {"humanBones": human_bones},
        }
    }

    return serialize_glb(gltf, bytes(buffer))
