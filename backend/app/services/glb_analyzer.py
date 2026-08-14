"""Deterministic GLB Asset Analyzer (Phase 2.5-A).

Pure stdlib (struct/json/zlib) - no third-party deps. Produces structural
statistics for a GLB:

  format/version/sizeBytes
  meshCount / primitiveCount / vertexCount / indexCount / triangleCount
  materialCount / textureCount / hasNormals / hasUVs
  bounds / dimensions / center
  per-mesh meshStats + warnings

Behavior:
  - validate_glb is used as the structural gate (its semantics are unchanged);
  - counts come from accessor metadata (no geometry decode needed);
  - bounds come from POSITION accessor min/max, which are in LOCAL mesh space
    (node transforms are NOT applied - that is Phase 2.5-B normalization);
  - the analyzer is fault tolerant: a single bad mesh/field never crashes the
    whole run; unanalyzable fields get safe defaults plus a warning.

NOT implemented here: GLB rewriting, coordinate transforms, unit conversion,
Rig / Skinning / VRM.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field

from .glb_builder import validate_glb

_TEXTURE_REF_KEYS = ("baseColorTexture", "metallicRoughnessTexture", "normalTexture", "occlusionTexture", "emissiveTexture")


@dataclass
class MeshStat:
    name: str
    index: int
    vertexCount: int
    indexCount: int
    triangleCount: int
    materialIndex: int | None
    hasNormals: bool
    hasUVs: bool
    mode: int = 4


@dataclass
class GlbStats:
    format: str = "glb"
    version: int = 2
    sizeBytes: int = 0
    meshCount: int = 0
    primitiveCount: int = 0
    vertexCount: int = 0
    indexCount: int = 0
    triangleCount: int = 0
    materialCount: int = 0
    textureCount: int = 0
    hasNormals: bool = False
    hasUVs: bool = False
    bounds: dict | None = None
    dimensions: dict | None = None
    center: dict | None = None
    meshStats: list[MeshStat] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Phase 2.7-D: whether the GLB carries a `skins` entry (skinned mesh).
    # Optional field; old stats without it stay valid/backward compatible.
    skinned: bool = False


def _accessor_at(prim: dict, accessors: list, key: str):
    """Return the accessor dict for a primitive attribute key, or None."""
    attrs = prim.get("attributes") or {}
    idx = attrs.get(key)
    if idx is None:
        return None
    if not isinstance(idx, int) or not (0 <= idx < len(accessors)):
        raise ValueError(f"accessor {idx} 越界")
    return accessors[idx]


def _accessor_by_index(idx, accessors: list):
    if not isinstance(idx, int) or not (0 <= idx < len(accessors)):
        raise ValueError(f"indices accessor {idx} 越界")
    return accessors[idx]


def _count_referenced_textures(materials: list) -> int:
    refs: set[int] = set()
    for mat in materials:
        pbr = mat.get("pbrMetallicRoughness") or {}
        for key in _TEXTURE_REF_KEYS:
            slot = pbr.get(key) or mat.get(key)
            if isinstance(slot, dict) and isinstance(slot.get("index"), int):
                refs.add(slot["index"])
    return len(refs)


def _analyze_primitive(prim: dict, accessors: list, mesh_name: str, m_index: int, p_index: int, stats: GlbStats) -> MeshStat:
    pos = _accessor_at(prim, accessors, "POSITION")
    if pos is None:
        raise ValueError("缺少 POSITION accessor")
    vcount = int(pos.get("count", 0) or 0)

    attrs = prim.get("attributes") or {}
    mode = int(prim.get("mode", 4))
    ms = MeshStat(
        name=mesh_name,
        index=m_index,
        vertexCount=vcount,
        indexCount=0,
        triangleCount=0,
        materialIndex=prim.get("material"),
        hasNormals="NORMAL" in attrs,
        hasUVs="TEXCOORD_0" in attrs,
        mode=mode,
    )

    if "indices" in prim:
        idx_acc = _accessor_by_index(prim["indices"], accessors)
        icount = int(idx_acc.get("count", 0) or 0)
        ms.indexCount = icount
        ms.triangleCount = icount // 3 if mode == 4 else 0
    elif mode == 4:
        ms.triangleCount = vcount // 3
        stats.warnings.append(f"mesh[{m_index}].primitives[{p_index}] 为非索引 primitive，三角形数按 POSITION/3 估算")
    return ms


def _merge_bounds(lo: list, hi: list, minv: list, maxv: list) -> None:
    for i in range(3):
        vmin = float(minv[i]) if len(minv) > i else 0.0
        vmax = float(maxv[i]) if len(maxv) > i else 0.0
        lo[i] = vmin if lo[i] is None else min(lo[i], vmin)
        hi[i] = vmax if hi[i] is None else max(hi[i], vmax)


def _fin(values: list) -> list:
    return [round(float(v), 6) for v in values]


def analyze_glb(data: bytes) -> GlbStats:
    """Analyze a GLB into GlbStats. Raises ValueError on structurally invalid GLB."""
    validate_glb(data)  # structural gate - semantics unchanged

    _magic, version, total = struct.unpack("<4sII", data[:12])
    clen, _ctype = struct.unpack("<I4s", data[12:20])
    gltf = json.loads(data[20 : 20 + clen])

    stats = GlbStats(version=version, sizeBytes=len(data))
    accessors = gltf.get("accessors") or []
    materials = gltf.get("materials") or []
    textures = gltf.get("textures") or []
    stats.materialCount = len(materials)
    stats.textureCount = _count_referenced_textures(materials) or len(textures)
    stats.skinned = bool(gltf.get("skins"))

    meshes = gltf.get("meshes") or []
    stats.meshCount = len(meshes)

    lo = [None, None, None]
    hi = [None, None, None]
    has_pos_minmax = False
    warned_minmax = False

    for m_index, mesh in enumerate(meshes):
        mesh_name = mesh.get("name") or f"mesh_{m_index}"
        for p_index, prim in enumerate(mesh.get("primitives") or []):
            stats.primitiveCount += 1
            try:
                ms = _analyze_primitive(prim, accessors, mesh_name, m_index, p_index, stats)
                stats.meshStats.append(ms)
                stats.vertexCount += ms.vertexCount
                stats.indexCount += ms.indexCount
                stats.triangleCount += ms.triangleCount
                stats.hasNormals = stats.hasNormals or ms.hasNormals
                stats.hasUVs = stats.hasUVs or ms.hasUVs

                pos_acc = _accessor_at(prim, accessors, "POSITION")
                if pos_acc is not None and "min" in pos_acc and "max" in pos_acc:
                    has_pos_minmax = True
                    _merge_bounds(lo, hi, pos_acc["min"], pos_acc["max"])
                elif pos_acc is not None and not warned_minmax:
                    stats.warnings.append("部分 POSITION accessor 缺少 min/max，bounds 可能不完整")
                    warned_minmax = True
            except Exception as exc:  # noqa: BLE001 - one bad primitive never aborts analysis
                stats.warnings.append(f"mesh[{m_index}].primitives[{p_index}] 分析失败：{exc}")

    if has_pos_minmax:
        bmin = _fin(lo)
        bmax = _fin(hi)
        stats.bounds = {"min": bmin, "max": bmax}
        stats.dimensions = {
            "x": round(bmax[0] - bmin[0], 6),
            "y": round(bmax[1] - bmin[1], 6),
            "z": round(bmax[2] - bmin[2], 6),
        }
        stats.center = {
            "x": round((bmin[0] + bmax[0]) / 2, 6),
            "y": round((bmin[1] + bmax[1]) / 2, 6),
            "z": round((bmin[2] + bmax[2]) / 2, 6),
        }
        stats.warnings.append("bounds 基于 accessor 局部坐标（未应用节点变换），世界坐标需 Phase 2.5-B")
    else:
        stats.warnings.append("无法统计 bounds：所有 POSITION accessor 均缺 min/max")

    return stats
