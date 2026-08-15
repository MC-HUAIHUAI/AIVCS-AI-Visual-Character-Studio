"""Local 3D -> VRM Rigging Pipeline (Phase 3-F).

Takes a GLB that already lives in ModelStore (any local provider output: mock /
local-lowpower / dummy runtime / future local AI) and produces a validated VRM 1.0:

    AI 3D GLB
    -> GLB Analyzer (analyze_glb: structural gate + mesh topology)
    -> Human/Creature classification (hint + skeleton structure; never guessed)
    -> Human Rig Pipeline
        - skeleton generation  (existing rig_builder, skinned input) OR
          auto-rig of a static mesh (deterministic nearest-bone skinning)
        - skin weights verification (JOINTS_0/WEIGHTS_0)
        - bind pose verification (inverseBindMatrices)
    -> humanoid bone mapping (vrm_mapping RIG_TO_VRM + synthesis)
    -> VRM 1.0 export (existing vrm_exporter)
    -> validate (existing vrm_validator)
    -> ModelStore (via the caller/router)

Honesty guarantees:
  - a NON-human model is never forced into a humanoid rig (explicit error);
  - an unclassified / hint-less static mesh is refused (geometry alone cannot
    prove "human");
  - every failure raises RigPipelineError with a clear reason; no mock fallback;
  - auto-rig uses deterministic nearest-bone weights (shape-only; NOT a real
    auto-rigger). A real Hunyuan GLB is NOT required and is NOT claimed.

No network, no shell, no arbitrary file paths. All byte handling is pure stdlib.
"""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field

from .glb_analyzer import analyze_glb
from .glb_builder import parse_glb, serialize_glb, validate_glb
from .rig_builder import BoneNode
from .vrm_exporter import VrmExportError, export_vrm
from .vrm_mapping import (
    OPTIONAL_HUMAN_BONES,
    REQUIRED_HUMAN_BONES,
    RIG_TO_VRM,
    SYNTHESIZE,
    TERMINAL_SYNTHESIZE,
    VRM_SUPPORTED_BODY_TYPES,
)
from .vrm_validator import validate_vrm

# Body types that mean "creature" and are never humanoid-rigged.
NON_HUMAN_BODY_TYPES = frozenset({"quadruped", "bird", "dragon"})
# Body types that form a meaningful VRM Humanoid with our rigs.
HUMANOID_BODY_TYPES = frozenset({"humanoid", "biped-anthro", "custom"})
# Human-like character types (accepted as a humanoid hint when body type is absent).
HUMAN_CHARACTER_TYPES = frozenset({"human", "anime-human"})
# Minimum adjacent-vertex joint-overlap ratio for skin weights (Phase 3-G).
SKIN_WEIGHT_CONTINUITY_MIN = 0.3
# Sanity bounds for the skeleton (meters, Y-up). Lengths/directions outside
# these bounds are treated as invalid topology for a humanoid rig.
_MAX_BONE_LENGTH = 5.0
_MIN_BONE_LENGTH = 1e-4
# Left/right mirrored limb length ratio tolerance (0.5..2.0 = 2x asymmetry allowed).
_SYMMETRY_RATIO_LOW = 0.5
_SYMMETRY_RATIO_HIGH = 2.0
# Core humanoid bones that our rigs carry; structural evidence of humanoid-ness.
HUMANOID_CORE = frozenset({"hips", "spine", "head"})
# Humanoid limb signature - creatures (quadruped/bird/dragon) carry frontLeg_L /
# wing_L / arm_L instead, so this set stays humanoid-specific. Includes both
# single-limb (leftArm) and split-limb (leftUpperArm) rig conventions.
HUMANOID_LIMBS = frozenset(
    {
        "leftArm",
        "rightArm",
        "leftLeg",
        "rightLeg",
        "leftHand",
        "rightHand",
        "leftFoot",
        "rightFoot",
        "leftUpperArm",
        "rightUpperArm",
        "leftLowerArm",
        "rightLowerArm",
        "leftUpperLeg",
        "rightUpperLeg",
        "leftLowerLeg",
        "rightLowerLeg",
    }
)

# Bone-name synonym map (lowercase, alnum-only) -> canonical rig bone id.
_BONE_SYNONYMS: dict[str, str] = {
    "pelvis": "hips",
    "root": "hips",
    "hip": "hips",
    "spine": "spine",
    "chest": "chest",
    "thorax": "chest",
    "neck": "neck",
    "head": "head",
    "skull": "head",
    # single-limb arms/legs
    "arm": "Arm",
    "upperarm": "UpperArm",
    "forearm": "LowerArm",
    "lowerarm": "LowerArm",
    "hand": "Hand",
    "leg": "Leg",
    "thigh": "UpperLeg",
    "upperleg": "UpperLeg",
    "shin": "LowerLeg",
    "lowerleg": "LowerLeg",
    "foot": "Foot",
}

# Left/right markers recognized in bone names (checked in order).
_SIDE_MARKERS: tuple[tuple[str, str, bool], ...] = (
    ("left", "left", True),   # leftArm / leftUpperArm
    ("right", "right", True),
    ("_l", "left", False),    # arm_L
    ("_r", "right", False),
    ("l_", "left", True),     # l_Arm
    ("r_", "right", True),
)


def normalize_bone_name(name: str) -> str:
    """Normalize a bone name to a canonical rig id (left/right + synonyms).

    'LeftArm' / 'arm_L' / 'l_Arm' -> 'leftArm'; 'LeftUpperArm'/'LeftForearm'
    -> 'leftUpperArm'/'leftLowerArm'; 'Pelvis' -> 'hips'. Unrecognized names are
    returned lowercased (no side prefix) so they never accidentally match a
    humanoid bone.
    """
    s = (name or "").strip()
    if not s:
        return s
    low = s.lower()
    side: str | None = None
    rest = low
    for marker, side_val, prefix in _SIDE_MARKERS:
        if prefix and low.startswith(marker):
            side = side_val
            rest = low[len(marker):]
            break
        if not prefix and low.endswith(marker):
            side = side_val
            rest = low[: -len(marker)]
            break
    cleaned = "".join(ch for ch in rest if ch.isalnum())
    if cleaned == "":
        return low
    if cleaned in _BONE_SYNONYMS:
        canonical = _BONE_SYNONYMS[cleaned]
    elif cleaned in ("left", "right", "l", "r", "bone", "joint"):
        return low
    else:
        # unknown part: return lowercased original (never a humanoid match)
        return low
    if canonical in ("hips", "spine", "chest", "neck", "head"):
        return canonical
    if side is None:
        return canonical[0].lower() + canonical[1:] if canonical else low
    return f"{side}{canonical}"

_FLOAT = 5126
_U8 = 5121
_VEC3 = "VEC3"
_VEC4 = "VEC4"
_MAT4 = "MAT4"


class RigPipelineError(RuntimeError):
    """Raised when a GLB cannot be safely rigged to VRM (clear reason, no mock)."""


@dataclass
class RigClassification:
    kind: str  # "humanoid" | "non-human" | "unclassified"
    reason: str
    skinned: bool = False
    body_type: str | None = None
    character_type: str | None = None
    bone_ids: list[str] = field(default_factory=list)


_parse_glb = parse_glb  # shared GLB parser (Phase 3-K dedup)


def _skin_bone_ids(data: bytes) -> list[str]:
    """Canonical bone ids (joint node names, normalized) of the first skin.

    Phase 3-G: names are normalized (left/right + synonyms) so classification
    and bone mapping recognize foreign conventions ('LeftArm', 'arm_L', ...).
    """
    try:
        gltf, _buffer = _parse_glb(data)
    except ValueError:
        return []
    skins = gltf.get("skins") or []
    if not skins:
        return []
    nodes = gltf.get("nodes") or []
    joints = skins[0].get("joints") or []
    ids: list[str] = []
    for j in joints:
        name = ""
        if isinstance(j, int) and 0 <= j < len(nodes):
            name = normalize_bone_name(str((nodes[j] or {}).get("name", "")))
        ids.append(name)
    return ids


def normalize_skeleton_glb(data: bytes) -> bytes:
    """Return a copy of a skinned GLB whose joint node names are canonical.

    Only skin-joint node names are rewritten; node indices, geometry, JOINTS_0 /
    WEIGHTS_0 and inverseBindMatrices are untouched, so this is safe for the
    reuse path when a skinned GLB uses variant bone names. Identity when no
    rename is needed.
    """
    gltf, buffer = _parse_glb(data)
    skins = gltf.get("skins") or []
    if not skins:
        return data
    nodes = gltf.get("nodes") or []
    joints = skins[0].get("joints") or []
    changed = False
    for j in joints:
        if not (isinstance(j, int) and 0 <= j < len(nodes)):
            continue
        node = nodes[j]
        raw = str(node.get("name", ""))
        canon = normalize_bone_name(raw)
        if canon and canon != raw:
            node["name"] = canon
            changed = True
    if not changed:
        return data
    return serialize_glb(gltf, bytes(buffer))


def classify_glb(
    data: bytes,
    body_type: str | None = None,
    character_type: str | None = None,
) -> RigClassification:
    """Classify a GLB as humanoid / non-human / unclassified.

    Humanoid requires EITHER an explicit humanoid body-type (or human character
    type) hint, OR structural evidence: an existing skeleton carrying the core
    humanoid bones (hips/spine/head) plus a limb. A hint-less static mesh is
    classified unclassified and refused.
    """
    try:
        stats = analyze_glb(data)
    except ValueError as exc:
        raise RigPipelineError(f"GLB 结构无效，无法分类：{exc}") from exc

    skinned = bool(stats.skinned)
    bone_ids = _skin_bone_ids(data)
    bt = (body_type or "").strip().lower()
    ct = (character_type or "").strip().lower()

    if bt in NON_HUMAN_BODY_TYPES:
        return RigClassification(
            kind="non-human",
            reason=f"bodyType='{bt}' 属于非人体模型，不能强行映射为 VRM Humanoid",
            skinned=skinned,
            body_type=bt,
            character_type=ct or None,
            bone_ids=bone_ids,
        )
    if bt in HUMANOID_BODY_TYPES:
        return RigClassification(
            kind="humanoid",
            reason=f"bodyType='{bt}' 声明为人体/类人体，允许 humanoid rig",
            skinned=skinned,
            body_type=bt,
            character_type=ct or None,
            bone_ids=bone_ids,
        )
    if ct in HUMAN_CHARACTER_TYPES:
        return RigClassification(
            kind="humanoid",
            reason=f"characterType='{ct}' 为人类，允许 humanoid rig",
            skinned=skinned,
            body_type=bt or "humanoid",
            character_type=ct,
            bone_ids=bone_ids,
        )

    core = HUMANOID_CORE.intersection(bone_ids)
    limbs = HUMANOID_LIMBS.intersection(bone_ids)
    if skinned and len(core) == len(HUMANOID_CORE) and limbs:
        return RigClassification(
            kind="humanoid",
            reason="结构检测到人体核心骨骼（hips/spine/head + 人体四肢）",
            skinned=True,
            body_type="humanoid",
            character_type=ct or None,
            bone_ids=bone_ids,
        )
    if skinned and bone_ids:
        if len(core) < len(HUMANOID_CORE) or not limbs:
            return RigClassification(
                kind="non-human",
                reason=f"GLB 带骨骼但结构非人体（骨骼：{', '.join(bone_ids[:8])}），不能强行 Rig",
                skinned=True,
                body_type=bt or None,
                character_type=ct or None,
                bone_ids=bone_ids,
            )
    if skinned:
        return RigClassification(
            kind="unclassified",
            reason="GLB 带无法识别的骨骼，且未提供 bodyType/characterType 分类信息",
            skinned=True,
            body_type=bt or None,
            character_type=ct or None,
            bone_ids=bone_ids,
        )
    return RigClassification(
        kind="unclassified",
        reason="未提供分类信息（bodyType/characterType）且 GLB 无骨骼，几何无法推断是否人体",
        skinned=False,
        body_type=bt or None,
        character_type=ct or None,
        bone_ids=bone_ids,
    )


def verify_mesh_topology(data: bytes) -> dict:
    """Mesh topology check (GLB Analyzer based). Raises on empty geometry or a
    structurally invalid GLB (both surface as RigPipelineError with a reason)."""
    try:
        stats = analyze_glb(data)
    except ValueError as exc:
        raise RigPipelineError(f"GLB 结构无效：{exc}") from exc
    if stats.meshCount == 0 or stats.vertexCount == 0 or stats.triangleCount == 0:
        raise RigPipelineError(f"网格拓扑无效：mesh={stats.meshCount} vertex={stats.vertexCount} tri={stats.triangleCount}")
    return {
        "meshCount": stats.meshCount,
        "primitiveCount": stats.primitiveCount,
        "vertexCount": stats.vertexCount,
        "indexCount": stats.indexCount,
        "triangleCount": stats.triangleCount,
        "materialCount": stats.materialCount,
        "textureCount": stats.textureCount,
        "hasNormals": stats.hasNormals,
        "hasUVs": stats.hasUVs,
        "skinned": stats.skinned,
        "bounds": stats.bounds,
        "dimensions": stats.dimensions,
        "center": stats.center,
        "warnings": stats.warnings,
    }


def extract_skeleton(data: bytes) -> dict:
    """Extract the skeleton hierarchy (id/parent/root) from the first skin."""
    gltf, _buffer = _parse_glb(data)
    skins = gltf.get("skins") or []
    nodes = gltf.get("nodes") or []
    parent_of: dict[int, int] = {}
    for i, node in enumerate(nodes):
        p = node.get("parent")
        if isinstance(p, int):
            parent_of[i] = p
    skeleton_node = skins[0].get("skeleton") if skins else None
    joints = skins[0].get("joints") if skins else []
    hierarchy = []
    for j in joints:
        node = nodes[j] if isinstance(j, int) and 0 <= j < len(nodes) else {}
        idx = j if isinstance(j, int) else -1
        parent_idx = parent_of.get(idx)
        parent_id = str(nodes[parent_idx].get("name", "")) if parent_idx is not None else None
        hierarchy.append(
            {
                "id": str(node.get("name", "")),
                "nodeIndex": idx,
                "parentId": parent_id,
                "root": idx == skeleton_node,
            }
        )
    return {
        "boneCount": len(joints),
        "skeletonNode": skeleton_node,
        "hierarchy": hierarchy,
        "root": next((h["id"] for h in hierarchy if h["root"]), hierarchy[0]["id"] if hierarchy else None),
    }


def _decode_floats(buffer: bytearray, view: dict, accessor: dict) -> list[float]:
    """Decode a float accessor (honoring byteStride). Rejects sparse accessors."""
    if accessor.get("sparse"):
        raise RigPipelineError("不支持 sparse accessor")
    comp = accessor.get("componentType")
    typ = accessor.get("type")
    count = accessor.get("count") or 0
    if comp != _FLOAT:
        raise RigPipelineError(f"不支持 componentType={comp}")
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}.get(typ)
    if n is None:
        raise RigPipelineError(f"不支持 type={typ}")
    offset = (view.get("byteOffset") or 0) + (accessor.get("byteOffset") or 0)
    stride = view.get("byteStride") or (n * 4)
    out: list[float] = []
    for i in range(count):
        base = offset + i * stride
        vals = struct.unpack_from("<%df" % n, buffer, base)
        out.extend(vals)
    return out


def _decode_u8_vec4(buffer: bytearray, view: dict, accessor: dict) -> list[int]:
    if accessor.get("sparse"):
        raise RigPipelineError("不支持 sparse accessor")
    count = accessor.get("count") or 0
    offset = (view.get("byteOffset") or 0) + (accessor.get("byteOffset") or 0)
    stride = view.get("byteStride") or 4
    out: list[int] = []
    for i in range(count):
        vals = struct.unpack_from("<4B", buffer, offset + i * stride)
        out.extend(vals)
    return out


def verify_skin_weights(data: bytes) -> dict:
    """Verify JOINTS_0 / WEIGHTS_0 presence, counts, bounds and weight sums.

    Raises RigPipelineError on any violation (a GLB that claims to be skinned but
    has broken weights must never reach VRM export).
    """
    gltf, buffer = _parse_glb(data)
    skins = gltf.get("skins") or []
    if not skins:
        raise RigPipelineError("GLB 未携带 skin（需要 skinned 或先 auto-rig）")
    nodes = gltf.get("nodes") or []
    joints = skins[0].get("joints") or []
    joint_count = len(joints)
    accessors = gltf.get("accessors") or []
    views = gltf.get("bufferViews") or []
    mesh_count = 0
    vertex_total = 0
    issues: list[str] = []
    continuity_ratios: list[float] = []
    for mi, mesh in enumerate(gltf.get("meshes") or []):
        for pi, prim in enumerate(mesh.get("primitives") or []):
            attrs = prim.get("attributes") or {}
            ji = attrs.get("JOINTS_0")
            wi = attrs.get("WEIGHTS_0")
            pos_i = attrs.get("POSITION")
            if ji is None or wi is None:
                continue
            mesh_count += 1
            jacc = accessors[ji]
            wacc = accessors[wi]
            if jacc.get("componentType") != _U8 or jacc.get("type") != _VEC4:
                issues.append(f"mesh[{mi}].prim[{pi}] JOINTS_0 应为 UNSIGNED_BYTE VEC4")
            if wacc.get("componentType") != _FLOAT or wacc.get("type") != _VEC4:
                issues.append(f"mesh[{mi}].prim[{pi}] WEIGHTS_0 应为 FLOAT VEC4")
            pcount = accessors[pos_i].get("count") if pos_i is not None else None
            if pcount is not None and jacc.get("count") != pcount:
                issues.append(f"mesh[{mi}].prim[{pi}] JOINTS_0 count 与 POSITION 不一致")
            if pcount is not None and wacc.get("count") != pcount:
                issues.append(f"mesh[{mi}].prim[{pi}] WEIGHTS_0 count 与 POSITION 不一致")
            vertex_total += int(jacc.get("count") or 0)
            j_view_idx = jacc.get("bufferView")
            if isinstance(j_view_idx, int) and 0 <= j_view_idx < len(views) and (jacc.get("count") or 0) > 0:
                dec = _decode_u8_vec4(buffer, views[j_view_idx], jacc)
                if dec and max(dec) >= joint_count:
                    issues.append(f"mesh[{mi}].prim[{pi}] JOINTS_0 索引越界（>= {joint_count}）")
                # Phase 3-G: skin weight continuity - adjacent vertices (by
                # index) should share at least one joint. A very low ratio
                # means the weights were scrambled, not a real deformation.
                vcount = int(jacc.get("count") or 0)
                if vcount >= 2:
                    shared = 0
                    for v in range(vcount - 1):
                        a = set(dec[v * 4 : (v + 1) * 4])
                        b = set(dec[(v + 1) * 4 : (v + 2) * 4])
                        if a & b:
                            shared += 1
                    continuity_ratios.append(shared / (vcount - 1))
            w_view_idx = wacc.get("bufferView")
            if isinstance(w_view_idx, int) and 0 <= w_view_idx < len(views) and (wacc.get("count") or 0) > 0:
                dec = _decode_floats(buffer, views[w_view_idx], wacc)
                for k in range(0, len(dec), 4):
                    s = sum(dec[k : k + 4])
                    if abs(s - 1.0) > 0.02:
                        issues.append(f"mesh[{mi}].prim[{pi}] 顶点权重和 ≠ 1（{round(s, 4)}）")
                        break
    if mesh_count == 0:
        raise RigPipelineError("存在 skin 但没有任何 mesh 携带 JOINTS_0/WEIGHTS_0")
    if issues:
        raise RigPipelineError("skin weights 校验失败：" + " | ".join(issues[:6]))
    continuity = min(continuity_ratios) if continuity_ratios else 1.0
    if continuity < SKIN_WEIGHT_CONTINUITY_MIN:
        raise RigPipelineError(f"skin weights 连续性异常（相邻顶点共享关节比例 {round(continuity, 3)} < {SKIN_WEIGHT_CONTINUITY_MIN}）")
    return {
        "skinnedMeshes": mesh_count,
        "skinnedVertexCount": vertex_total,
        "jointCount": joint_count,
        "weightContinuity": round(continuity, 4),
    }


def verify_bind_pose(data: bytes) -> dict:
    """Verify inverseBindMatrices count matches the skin joints (bind pose)."""
    gltf, _buffer = _parse_glb(data)
    skins = gltf.get("skins") or []
    if not skins:
        raise RigPipelineError("GLB 未携带 skin")
    skin = skins[0]
    joints = skin.get("joints") or []
    ibm = skin.get("inverseBindMatrices")
    accessors = gltf.get("accessors") or []
    if not isinstance(ibm, int) or not (0 <= ibm < len(accessors)):
        raise RigPipelineError("inverseBindMatrices 非法")
    acc = accessors[ibm]
    if acc.get("componentType") != _FLOAT or acc.get("type") != _MAT4:
        raise RigPipelineError("inverseBindMatrices 应为 FLOAT MAT4")
    if acc.get("count") != len(joints):
        raise RigPipelineError(f"bind pose 不一致：joints={len(joints)} IBM={acc.get('count')}")
    return {"jointCount": len(joints), "ibmCount": acc.get("count"), "ibmPerJoint": True}


def _bone_world_positions(gltf: dict) -> tuple[dict[int, tuple], dict[int, int | None]]:
    """World positions (accumulated node translations) + parent map per node.

    Rotation is ignored (matches bind semantics); Y-up model space.
    """
    nodes = gltf.get("nodes") or []
    parent_of: dict[int, int | None] = {}
    for i, node in enumerate(nodes):
        p = node.get("parent")
        parent_of[i] = p if isinstance(p, int) else None
    world: dict[int, tuple] = {}

    def resolve(i: int) -> tuple:
        if i in world:
            return world[i]
        t = tuple(float(v) for v in nodes[i].get("translation", (0.0, 0.0, 0.0)))
        p = parent_of.get(i)
        pos = t if p is None else tuple(a + b for a, b in zip(resolve(p), t))
        world[i] = pos
        return pos

    for i in range(len(nodes)):
        resolve(i)
    return world, parent_of


def verify_skeleton_sanity(data: bytes) -> dict:
    """Skeleton quality gate (Phase 3-G): connectivity, bone lengths, direction.

    Checks (Y-up humanoid invariants, all lenient):
      - the hierarchy has a single root and no cycles;
      - every non-root bone has a positive, bounded length;
      - head sits above hips; feet sit at/below hips;
      - left/right mirrored limbs have comparable lengths.
    Raises RigPipelineError with a clear reason on any violation (a skeleton with
    broken topology must never be exported as VRM).
    """
    gltf, _buffer = _parse_glb(data)
    skins = gltf.get("skins") or []
    if not skins:
        raise RigPipelineError("GLB 未携带 skin（无法校验骨骼）")
    nodes = gltf.get("nodes") or []
    joints = skins[0].get("joints") or []
    joint_set = set(joints)
    if not joints:
        raise RigPipelineError("骨骼为空")

    world, parent_of = _bone_world_positions(gltf)

    # single root + no cycles (DFS from each joint)
    roots = [j for j in joints if parent_of.get(j) is None]
    if len(roots) != 1:
        raise RigPipelineError(f"骨骼层级应有且仅有 1 个根（实际 {len(roots)} 个）")
    root = roots[0]
    seen: set[int] = set()
    stack = [root]
    while stack:
        i = stack.pop()
        if i in seen:
            raise RigPipelineError("骨骼层级存在循环")
        seen.add(i)
        for j, p in parent_of.items():
            if p == i:
                stack.append(j)
    if len(seen) != len(joint_set):
        raise RigPipelineError("骨骼层级存在断链（部分骨骼不可达）")

    # per-bone world positions + lengths
    pos = {j: world[j] for j in joints}
    lengths: dict[int, float] = {}
    for j in joints:
        p = parent_of.get(j)
        if p is None:
            continue
        d = tuple(pos[j][k] - pos[p][k] for k in range(3))
        length = (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** 0.5
        lengths[j] = length
        if length < _MIN_BONE_LENGTH:
            raise RigPipelineError(f"骨骼 {nodes[j].get('name', j)} 长度为零或过短（{round(length, 5)}m）")
        if length > _MAX_BONE_LENGTH:
            raise RigPipelineError(f"骨骼 {nodes[j].get('name', j)} 长度异常（{round(length, 3)}m > {_MAX_BONE_LENGTH}m）")

    by_name = {normalize_bone_name(str(nodes[j].get("name", ""))): j for j in joints}

    # vertical invariants
    def _y(name: str) -> float | None:
        j = by_name.get(name)
        return pos[j][1] if j is not None else None

    hips_y = _y("hips")
    head_y = _y("head")
    if hips_y is not None and head_y is not None and head_y < hips_y - 0.1:
        raise RigPipelineError("骨骼方向异常：head 位于 hips 下方（倒置）")
    for foot in ("leftFoot", "rightFoot"):
        fy = _y(foot)
        if hips_y is not None and fy is not None and fy > hips_y + 0.1:
            raise RigPipelineError(f"骨骼方向异常：{foot} 位于 hips 上方")

    # left/right length symmetry (only for limbs that exist on both sides)
    pairs = (
        ("leftArm", "rightArm"),
        ("leftUpperArm", "rightUpperArm"),
        ("leftLowerArm", "rightLowerArm"),
        ("leftLeg", "rightLeg"),
        ("leftUpperLeg", "rightUpperLeg"),
        ("leftLowerLeg", "rightLowerLeg"),
        ("leftHand", "rightHand"),
        ("leftFoot", "rightFoot"),
    )
    for lname, rname in pairs:
        li = by_name.get(lname)
        ri = by_name.get(rname)
        if li is None or ri is None:
            continue
        if li not in lengths or ri not in lengths:
            continue
        ll, rl = lengths[li], lengths[ri]
        if ll <= 0 or rl <= 0:
            continue
        ratio = ll / rl
        if not (_SYMMETRY_RATIO_LOW <= ratio <= _SYMMETRY_RATIO_HIGH):
            raise RigPipelineError(f"左右骨骼长度不对称（{lname}/{rname} 比例 {round(ratio, 2)}）")

    return {
        "boneCount": len(joints),
        "root": normalize_bone_name(str(nodes[root].get("name", ""))),
        "maxBoneLength": round(max(lengths.values()) if lengths else 0.0, 4),
        "minBoneLength": round(min(lengths.values()) if lengths else 0.0, 4),
        "connected": True,
        "singleRoot": True,
    }


def build_bone_mapping(data: bytes) -> dict:
    """Humanoid bone mapping report (RIG_TO_VRM + VRM-required synthesis).

    RIG_TO_VRM is rig_id -> VRM human bone name; a present rig bone therefore
    maps its rig id onto the VRM bone name.
    """
    bone_ids = _skin_bone_ids(data)
    mapped: dict[str, str] = {}
    for rig, vrm_bone in RIG_TO_VRM.items():
        if rig in bone_ids:
            mapped[vrm_bone] = rig
    synthesized: list[str] = []
    for vrm_bone in REQUIRED_HUMAN_BONES:
        if vrm_bone in mapped:
            continue
        if vrm_bone in SYNTHESIZE or vrm_bone in TERMINAL_SYNTHESIZE:
            synthesized.append(vrm_bone)
    optional_present = [b for b in OPTIONAL_HUMAN_BONES if b in mapped]
    covered = [b for b in REQUIRED_HUMAN_BONES if b in mapped or b in synthesized]
    return {
        "mapped": mapped,
        "synthesized": sorted(synthesized),
        "optionalPresent": optional_present,
        "requiredCovered": len(covered),
        "requiredTotal": len(REQUIRED_HUMAN_BONES),
    }


# --------------------------------------------------------------------------- #
# Auto-rig: static (unskinned) low-poly mesh -> skinned humanoid GLB.
# Shape-only, deterministic nearest-bone skinning (NOT a production auto-rigger).
# --------------------------------------------------------------------------- #


def _bind_world_positions(world_positions: list[tuple[float, float, float]], bone_positions: list[tuple]) -> tuple[list[list[int]], list[list[float]]]:
    """Assign the 4 nearest bones per vertex (inverse-distance weights). Same
    deterministic semantics as glb_builder._bind_vertices (ties by bone index)."""
    joints: list[list[int]] = []
    weights: list[list[float]] = []
    for (wx, wy, wz) in world_positions:
        dists = []
        for bi, (bx, by, bz) in enumerate(bone_positions):
            dx = wx - bx
            dy = wy - by
            dz = wz - bz
            dists.append((dx * dx + dy * dy + dz * dz, bi))
        dists.sort(key=lambda t: (t[0], t[1]))
        top = dists[:4]
        if top[0][0] == 0.0:
            j = [top[0][1], 0, 0, 0]
            w = [1.0, 0.0, 0.0, 0.0]
        else:
            inv = [1.0 / (d + 1e-6) for d, _ in top]
            s = sum(inv)
            w = [v / s for v in inv]
            j = [bi for _, bi in top]
            while len(j) < 4:
                j.append(0)
            while len(w) < 4:
                w.append(0.0)
        joints.append(j[:4])
        weights.append(w[:4])
    return joints, weights


def _autorig_humanoid_bones() -> list[BoneNode]:
    """A more complete humanoid skeleton used ONLY by auto-rig (Phase 3-G).

    hips/spine/chest/neck/head + split upper/lower arms & hands + split
    upper/lower legs & feet (left/right). Deterministic T-pose model space
    (160cm). This is the auto-rig skeleton; the existing single-limb rig
    profiles (local-lowpower) stay unchanged.
    """
    def b(bid, parent, pos):
        return BoneNode(id=bid, label=bid, parent_id=parent, position=pos)

    return [
        b("hips", None, (0.0, 0.55, 0.0)),
        b("spine", "hips", (0.0, 0.85, 0.0)),
        b("chest", "spine", (0.0, 1.05, 0.0)),
        b("neck", "chest", (0.0, 1.25, 0.0)),
        b("head", "neck", (0.0, 1.50, 0.0)),
        b("leftUpperArm", "chest", (-0.38, 1.05, 0.0)),
        b("leftLowerArm", "leftUpperArm", (-0.38, 0.91, 0.0)),
        b("leftHand", "leftLowerArm", (-0.38, 0.78, 0.0)),
        b("rightUpperArm", "chest", (0.38, 1.05, 0.0)),
        b("rightLowerArm", "rightUpperArm", (0.38, 0.91, 0.0)),
        b("rightHand", "rightLowerArm", (0.38, 0.78, 0.0)),
        b("leftUpperLeg", "hips", (-0.15, 0.40, 0.0)),
        b("leftLowerLeg", "leftUpperLeg", (-0.15, 0.28, 0.0)),
        b("leftFoot", "leftLowerLeg", (-0.15, 0.05, 0.0)),
        b("rightUpperLeg", "hips", (0.15, 0.40, 0.0)),
        b("rightLowerLeg", "rightUpperLeg", (0.15, 0.28, 0.0)),
        b("rightFoot", "rightLowerLeg", (0.15, 0.05, 0.0)),
    ]


def _node_world_transform(gltf: dict) -> tuple[dict[int, list], dict[int, list]]:
    """world translation + world scale per node (accumulated along parents).

    Rotation is intentionally ignored for binding, matching the existing
    glb_builder._bind_vertices semantics (axis-aligned low-poly parts).
    """
    nodes = gltf.get("nodes") or []
    parent_of: dict[int, int] = {}
    for i, node in enumerate(nodes):
        p = node.get("parent")
        if isinstance(p, int):
            parent_of[i] = p
    world_t: dict[int, list] = {}
    world_s: dict[int, list] = {}

    def resolve(i: int) -> tuple[list, list]:
        if i in world_t:
            return world_t[i], world_s[i]
        node = nodes[i]
        t = list(float(v) for v in node.get("translation", (0.0, 0.0, 0.0)))
        s = list(float(v) for v in node.get("scale", (1.0, 1.0, 1.0)))
        p = parent_of.get(i)
        if p is not None:
            pt, ps = resolve(p)
            t = [t[k] + pt[k] for k in range(3)]
            s = [s[k] * ps[k] for k in range(3)]
        world_t[i] = t
        world_s[i] = s
        return t, s

    for i in range(len(nodes)):
        resolve(i)
    return world_t, world_s


def auto_rig_glb(data: bytes, body_type: str, model_name: str) -> bytes:
    """Attach a deterministic humanoid skeleton + skin weights to a static GLB.

    For each mesh vertex (model space = world translation + world scale * local
    POSITION), bind to the 4 nearest bones of the humanoid rig and write
    JOINTS_0 / WEIGHTS_0 + bind-pose IBM into the GLB. Shape-only.
    """
    if body_type not in VRM_SUPPORTED_BODY_TYPES:
        raise RigPipelineError(f"bodyType '{body_type}' 无法 auto-rig（仅 {', '.join(VRM_SUPPORTED_BODY_TYPES)}）")

    gltf, buffer = _parse_glb(data)
    if gltf.get("skins"):
        return data  # already skinned - nothing to do

    # Phase 3-G: richer split-limb humanoid skeleton for auto-rig (deterministic
    # procedural; NOT a production auto-rigger).
    bones = _autorig_humanoid_bones()
    by_id = {b.id: b for b in bones}
    bone_positions = [tuple(float(v) for v in b.position) for b in bones]
    bone_local: dict[str, tuple] = {}
    ibm: list[float] = []
    for b in bones:
        pos = tuple(float(v) for v in b.position)
        if b.parent_id and b.parent_id in by_id:
            pp = tuple(float(v) for v in by_id[b.parent_id].position)
            bone_local[b.id] = (pos[0] - pp[0], pos[1] - pp[1], pos[2] - pp[2])
        else:
            bone_local[b.id] = pos
        ibm.extend([1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -pos[0], -pos[1], -pos[2], 1.0])

    accessors = gltf.get("accessors") or []
    views = gltf.get("bufferViews") or []
    nodes = gltf.get("nodes") or []
    world_t, world_s = _node_world_transform(gltf)

    # ---- compute JOINTS/WEIGHTS per primitive ----
    per_prim: dict[tuple[int, int], tuple[bytes, bytes]] = {}
    for mi, mesh in enumerate(gltf.get("meshes") or []):
        for pi, prim in enumerate(mesh.get("primitives") or []):
            pos_i = (prim.get("attributes") or {}).get("POSITION")
            if pos_i is None:
                continue
            acc = accessors[pos_i]
            view = views[acc["bufferView"]]
            local = _decode_floats(buffer, view, acc)
            # find the mesh node that owns this mesh to apply its transform
            owner = next((i for i, n in enumerate(nodes) if n.get("mesh") == mi), None)
            t = world_t.get(owner, [0.0, 0.0, 0.0])
            s = world_s.get(owner, [1.0, 1.0, 1.0])
            world: list[tuple[float, float, float]] = []
            for k in range(0, len(local), 3):
                world.append((t[0] + s[0] * local[k], t[1] + s[1] * local[k + 1], t[2] + s[2] * local[k + 2]))
            joints, weights = _bind_world_positions(world, bone_positions)
            flat_j = [v for vert in joints for v in vert]
            flat_w = [round(v, 6) for vert in weights for v in vert]
            per_prim[(mi, pi)] = (
                struct.pack("<%dB" % len(flat_j), *flat_j),
                struct.pack("<%df" % len(flat_w), *flat_w),
            )

    def add_view(view_len: int, target: int) -> int:
        offset = len(buffer)
        while len(buffer) % 4:
            buffer.append(0)
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": view_len, "target": target})
        return len(views) - 1

    # ---- append bone nodes ----
    base = len(nodes)
    bone_node_index: dict[str, int] = {}
    for b in bones:
        bone_node_index[b.id] = len(nodes)
        node = {"name": b.id, "translation": list(bone_local[b.id])}
        nodes.append(node)
    for b in bones:
        if b.parent_id and b.parent_id in bone_node_index:
            nodes[bone_node_index[b.id]]["parent"] = bone_node_index[b.parent_id]

    # ---- JOINTS_0 / WEIGHTS_0 accessors ----
    new_accessor_indices: dict[tuple[int, int], tuple[int, int]] = {}
    for (mi, pi), (j_bytes, w_bytes) in per_prim.items():
        while len(buffer) % 4:
            buffer.append(0)
        views.append({"buffer": 0, "byteOffset": len(buffer), "byteLength": len(j_bytes), "target": 34962})
        j_view = len(views) - 1
        buffer += j_bytes
        accessors.append({"bufferView": j_view, "componentType": _U8, "count": len(j_bytes) // 4, "type": _VEC4})
        j_acc = len(accessors) - 1

        while len(buffer) % 4:
            buffer.append(0)
        views.append({"buffer": 0, "byteOffset": len(buffer), "byteLength": len(w_bytes), "target": 34962})
        w_view = len(views) - 1
        buffer += w_bytes
        accessors.append({"bufferView": w_view, "componentType": _FLOAT, "count": len(w_bytes) // 16, "type": _VEC4})
        w_acc = len(accessors) - 1
        new_accessor_indices[(mi, pi)] = (j_acc, w_acc)

    # ---- inverse bind matrices ----
    ibm_bytes = struct.pack("<%df" % len(ibm), *ibm)
    while len(buffer) % 4:
        buffer.append(0)
    views.append({"buffer": 0, "byteOffset": len(buffer), "byteLength": len(ibm_bytes), "target": 34962})
    ibm_view = len(views) - 1
    buffer += ibm_bytes
    accessors.append({"bufferView": ibm_view, "componentType": _FLOAT, "count": len(bones), "type": _MAT4})
    ibm_acc = len(accessors) - 1

    # ---- write attributes + skin + scene ----
    skin_joints = [bone_node_index[b.id] for b in bones]
    for (mi, pi), (j_acc, w_acc) in new_accessor_indices.items():
        prim = gltf["meshes"][mi]["primitives"][pi]
        attrs = prim.setdefault("attributes", {})
        attrs["JOINTS_0"] = j_acc
        attrs["WEIGHTS_0"] = w_acc

    for i, node in enumerate(nodes):
        if node.get("mesh") is not None:
            node["skin"] = 0

    root = next((i for i, b in enumerate(bones) if not b.parent_id), 0)
    gltf.setdefault("skins", []).append(
        {
            "joints": skin_joints,
            "inverseBindMatrices": ibm_acc,
            "skeleton": skin_joints[root],
        }
    )

    scene = gltf.get("scenes") or [{"nodes": []}]
    scene_nodes = list(scene[0].get("nodes", []))
    for b in bones:
        if not b.parent_id:
            scene_nodes.append(bone_node_index[b.id])
    scene[0]["nodes"] = scene_nodes
    gltf["scenes"] = scene
    gltf.setdefault("buffers", [{}])[0]["byteLength"] = len(buffer)

    return serialize_glb(gltf, bytes(buffer))


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def rig_glb_to_vrm(
    data: bytes,
    body_type: str | None = None,
    character_type: str | None = None,
    model_name: str = "AIVCS Character",
) -> dict:
    """Run the full Local 3D -> VRM pipeline. Returns a result dict (see below).

    Raises RigPipelineError / VrmExportError / ValueError with a clear reason.
    Never falls back to mock and never forces a non-human rig.
    """
    # 1) GLB Analyzer + mesh topology gate.
    topology = verify_mesh_topology(data)
    stats = analyze_glb(data)

    # 2) Human/Creature classification.
    cls = classify_glb(data, body_type, character_type)
    if cls.kind != "humanoid":
        raise RigPipelineError(cls.reason)
    effective_bt = cls.body_type or "humanoid"
    if effective_bt not in VRM_SUPPORTED_BODY_TYPES:
        raise RigPipelineError(f"bodyType '{effective_bt}' 不支持导出 VRM Humanoid")

    # 3) Rig: reuse the existing skeleton (name-normalized), or auto-rig a
    #    static mesh. Never re-auto-rigs an already-skinned GLB.
    source_skinned = bool(stats.skinned)
    name_normalized = False
    if source_skinned:
        normalized = normalize_skeleton_glb(data)
        name_normalized = normalized != data
        rigged = normalized
    else:
        rigged = auto_rig_glb(data, effective_bt, model_name)

    # 4) Skeleton hierarchy / sanity (length+direction) / bind pose /
    #    skin weights (incl. continuity) verification.
    skeleton = extract_skeleton(rigged)
    sanity = verify_skeleton_sanity(rigged)
    bind_pose = verify_bind_pose(rigged)
    skin_weights = verify_skin_weights(rigged)
    bone_mapping = build_bone_mapping(rigged)

    # 5) VRM 1.0 export + validate.
    try:
        vrm = export_vrm(rigged, body_type=effective_bt, model_name=model_name)
    except VrmExportError as exc:
        raise RigPipelineError(f"VRM 导出失败：{exc}") from exc
    vrm_meta = validate_vrm(vrm)

    return {
        "ok": True,
        "classification": asdict(cls),
        "topology": topology,
        "skeleton": skeleton,
        "skeletonSanity": sanity,
        "boneMapping": bone_mapping,
        "bindPose": bind_pose,
        "skinWeights": skin_weights,
        "sourceSkinned": source_skinned,
        "nameNormalized": name_normalized,
        "autoRigged": not source_skinned,
        "vrmMeta": {
            "specVersion": vrm_meta.get("specVersion"),
            "name": vrm_meta.get("meta", {}).get("name"),
            "authors": vrm_meta.get("meta", {}).get("authors"),
            "licenseUrl": vrm_meta.get("meta", {}).get("licenseUrl"),
        },
        "stats": asdict(stats),
        "vrmBytes": vrm,
    }
