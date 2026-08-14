"""VRM 1.0 structural validator (Phase 2.7-B, base structure).

Zero-dependency check that a .vrm is a legal GLB carrying a structurally valid
VRMC_vrm extension. The bone names / required fields follow the official VRM 1.0
schemas (see vrm_mapping.py). Raises ValueError on any violation.
"""

from __future__ import annotations

import json
import struct

from .glb_builder import validate_glb
from .vrm_mapping import REQUIRED_HUMAN_BONES


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

    return vrm
