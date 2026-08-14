"""VRM 1.0 structural validator (Phase 2.7-B base + 2.7-C consistency).

Zero-dependency check that a .vrm is a legal GLB carrying a structurally valid
VRMC_vrm extension, plus node/joint/IBM/JOINTS consistency. Bone names /
required fields follow the official VRM 1.0 schemas (see vrm_mapping.py).
Raises ValueError on any violation.
"""

from __future__ import annotations

import json
import struct

from .glb_builder import validate_glb
from .vrm_mapping import REQUIRED_HUMAN_BONES


def _bin_start(data: bytes, clen: int) -> int:
    return 20 + clen + 8


def _decode_uints(data: bytes, view: dict, accessor: dict) -> list[int]:
    """Decode a UNSIGNED_BYTE VEC4 accessor (JOINTS_0) into flat ints."""
    bin_start = _bin_start(data, struct.unpack("<I", data[12:16])[0])
    offset = view["byteOffset"]
    count = accessor["count"]
    raw = data[bin_start + offset : bin_start + offset + count * 4]
    return list(raw)


def validate_vrm(data: bytes) -> dict:
    """Validate VRM structure; returns the parsed VRMC_vrm dict."""
    validate_glb(data)
    clen, _ctype = struct.unpack("<I4s", data[12:20])
    gltf = json.loads(data[20 : 20 + clen])

    if "VRMC_vrm" not in gltf.get("extensionsUsed", []):
        raise ValueError("缺少 extensionsUsed: VRMC_vrm")
    vrm = (gltf.get("extensions") or {}).get("VRMC_vrm")
    if vrm is None:
        raise ValueError("缺少 extensions.VRMC_vrm")
    if vrm.get("specVersion") != "1.0":
        raise ValueError("specVersion 必须为 1.0")

    meta = vrm.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("缺少 meta")
    for field in ("name", "authors", "licenseUrl"):
        if field not in meta:
            raise ValueError(f"meta 缺少必填字段 {field}")

    humanoid = vrm.get("humanoid") or {}
    human_bones = humanoid.get("humanBones") or {}
    node_count = len(gltf.get("nodes", []))
    for bone in REQUIRED_HUMAN_BONES:
        entry = human_bones.get(bone)
        if entry is None:
            raise ValueError(f"humanBones 缺少 required 骨骼 {bone}")
        node = entry.get("node")
        if not isinstance(node, int) or not (0 <= node < node_count):
            raise ValueError(f"{bone}.node 越界或非法")

    # ---- Phase 2.7-C: skin consistency ----
    accessors = gltf.get("accessors") or []
    views = gltf.get("bufferViews") or []
    skins = gltf.get("skins") or []
    max_joint_allowed = -1
    for si, skin in enumerate(skins):
        joints = skin.get("joints") or []
        if not isinstance(joints, list):
            raise ValueError(f"skin[{si}].joints 非法")
        for j in joints:
            if not isinstance(j, int) or not (0 <= j < node_count):
                raise ValueError(f"skin[{si}].joints 越界")
        ibm_idx = skin.get("inverseBindMatrices")
        if not isinstance(ibm_idx, int) or not (0 <= ibm_idx < len(accessors)):
            raise ValueError(f"skin[{si}].inverseBindMatrices 非法")
        ibm = accessors[ibm_idx]
        if ibm.get("count") != len(joints):
            raise ValueError(f"skin[{si}] joints 数量与 inverseBindMatrices 不一致")
        max_joint_allowed = max(max_joint_allowed, len(joints) - 1)

    for mi, mesh in enumerate(gltf.get("meshes") or []):
        for pi, prim in enumerate(mesh.get("primitives") or []):
            attrs = prim.get("attributes") or {}
            if "JOINTS_0" in attrs:
                j_idx = attrs["JOINTS_0"]
                p_idx = attrs.get("POSITION")
                if not isinstance(j_idx, int) or not (0 <= j_idx < len(accessors)):
                    raise ValueError(f"mesh[{mi}].prim[{pi}] JOINTS_0 非法")
                jacc = accessors[j_idx]
                if jacc.get("componentType") != 5121 or jacc.get("type") != "VEC4":
                    raise ValueError(f"mesh[{mi}].prim[{pi}] JOINTS_0 应为 UNSIGNED_BYTE VEC4")
                if p_idx is not None and accessors[p_idx].get("count") != jacc.get("count"):
                    raise ValueError(f"mesh[{mi}].prim[{pi}] JOINTS_0 count 与 POSITION 不一致")
                view = views[jacc["bufferView"]]
                decoded = _decode_uints(data, view, jacc)
                if decoded and max(decoded) > max_joint_allowed:
                    raise ValueError(f"mesh[{mi}].prim[{pi}] JOINTS_0 索引越界")

    return vrm
