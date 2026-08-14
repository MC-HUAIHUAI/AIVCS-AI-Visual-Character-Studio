"""Deterministic low-poly GLB builder (backend service, Phase 2.3-D).

Pure stdlib (struct/zlib) - no three.js, no numpy. Builds a binary glTF 2.0
(.glb) from a list of axis-aligned primitives (box / sphere) with hex colors and
optional per-part rotation. Deterministic: identical input always produces
identical bytes, so tests can assert byte-level equality.

The writer logic is the same proven approach used by tools/gen_demo_character.py
(whose output loads correctly in three.js).
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from dataclasses import dataclass, field


@dataclass
class Primitive:
    kind: str  # 'box' | 'sphere'
    size: tuple = (1.0, 1.0, 1.0)  # box half-ish extents (full width)
    radius: float = 1.0
    center: tuple = (0.0, 0.0, 0.0)
    color: str = "#CCCCCC"  # #RRGGBB
    rotation: tuple = (0.0, 0.0, 0.0)  # euler radians, XYZ order


@dataclass
class _Mesh:
    name: str
    positions: list = field(default_factory=list)
    normals: list = field(default_factory=list)
    indices: list = field(default_factory=list)
    color: tuple = (0.8, 0.8, 0.8, 1.0)
    translation: tuple = (0.0, 0.0, 0.0)
    scale: tuple = (1.0, 1.0, 1.0)
    rotation: tuple = (0.0, 0.0, 0.0)


def _hex_to_rgba(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    try:
        if len(h) != 6:
            raise ValueError
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
    except ValueError:
        return (0.8, 0.8, 0.8, 1.0)
    return (r, g, b, 1.0)


def _euler_to_quaternion(rx: float, ry: float, rz: float):
    cr, sr = math.cos(rx / 2), math.sin(rx / 2)
    cp, sp = math.cos(ry / 2), math.sin(ry / 2)
    cy, sy = math.cos(rz / 2), math.sin(rz / 2)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _add_face(mesh: _Mesh, corners, n):
    base = len(mesh.positions) // 3
    for c in corners:
        mesh.positions.extend(c)
        mesh.normals.extend(n)
    mesh.indices += [base, base + 1, base + 2, base, base + 2, base + 3]


def _box_mesh(name: str, sx: float, sy: float, sz: float, color: tuple) -> _Mesh:
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    m = _Mesh(name=name, color=color)
    _add_face(m, [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)], (0, 0, 1))
    _add_face(m, [(-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz)], (0, 0, -1))
    _add_face(m, [(hx, -hy, -hz), (hx, -hy, hz), (hx, hy, hz), (hx, hy, -hz)], (1, 0, 0))
    _add_face(m, [(-hx, -hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (-hx, -hy, hz)], (-1, 0, 0))
    _add_face(m, [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)], (0, 1, 0))
    _add_face(m, [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)], (0, -1, 0))
    return m


def _sphere_mesh(name: str, radius: float, color: tuple, lat: int = 10, lon: int = 14) -> _Mesh:
    m = _Mesh(name=name, color=color)
    for i in range(lat + 1):
        phi = i * math.pi / lat
        for j in range(lon):
            theta = j * 2.0 * math.pi / lon
            x = math.sin(phi) * math.cos(theta)
            y = math.cos(phi)
            z = math.sin(phi) * math.sin(theta)
            m.positions.extend([x * radius, y * radius, z * radius])
            m.normals.extend([x, y, z])
    for i in range(lat):
        for j in range(lon):
            a = i * lon + j
            b = (i + 1) * lon + j
            a2 = a + 1 if j < lon - 1 else a - (lon - 1)
            b2 = b + 1 if j < lon - 1 else b - (lon - 1)
            m.indices += [a, b, b2, a, b2, a2]
    return m


def _pad4(buf: bytearray) -> None:
    while len(buf) % 4 != 0:
        buf += b"\x00"


def validate_glb(data: bytes) -> None:
    """Validate a GLB is structurally legal. Raises ValueError on failure.

    Any structural anomaly (including index/KeyError inside the JSON) is
    normalized to ValueError so callers can rely on one exception type.
    """
    try:
        _validate_glb_inner(data)
    except ValueError:
        raise
    except (IndexError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("malformed GLB structure") from exc


def _validate_glb_inner(data: bytes) -> None:
    if len(data) < 20:
        raise ValueError("too short")
    if data[:4] != b"glTF":
        raise ValueError("bad magic")
    _magic, version, total = struct.unpack("<4sII", data[:12])
    if version != 2:
        raise ValueError(f"unsupported version {version}")
    if total != len(data):
        raise ValueError("length mismatch")
    clen, ctype = struct.unpack("<I4s", data[12:20])
    if ctype != b"JSON":
        raise ValueError("missing JSON chunk")
    if 20 + clen > len(data):
        raise ValueError("JSON chunk out of bounds")
    try:
        gltf = json.loads(data[20 : 20 + clen])
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid JSON chunk") from exc
    if gltf.get("asset", {}).get("version") != "2.0":
        raise ValueError("invalid asset version")
    if "buffers" not in gltf or not gltf["buffers"]:
        raise ValueError("no buffers")
    if not isinstance(gltf.get("meshes"), list):
        raise ValueError("no meshes")
    buf_len = gltf["buffers"][0].get("byteLength", 0)
    for acc in gltf.get("accessors", []):
        view = gltf["bufferViews"][acc["bufferView"]]
        if view["byteOffset"] + view["byteLength"] > buf_len:
            raise ValueError("accessor out of buffer bounds")


def build_glb(primitives: list[Primitive], scale: float = 1.0) -> bytes:
    """Serialize primitives (scaled by `scale`) into a binary glTF 2.0 .glb."""
    meshes: list[_Mesh] = []
    for idx, p in enumerate(primitives):
        color = _hex_to_rgba(p.color)
        if p.kind == "sphere":
            m = _sphere_mesh(f"part_{idx}", p.radius, color)
        else:
            m = _box_mesh(f"part_{idx}", p.size[0], p.size[1], p.size[2], color)
        m.translation = (p.center[0] * scale, p.center[1] * scale, p.center[2] * scale)
        m.scale = (scale, scale, scale)
        m.rotation = p.rotation
        meshes.append(m)

    buffer = bytearray()
    buffer_views = []
    accessors = []
    mesh_defs = []
    nodes = []
    material_map: dict = {}
    materials: list[dict] = []
    mesh_index = 0

    def add_view(byte_length: int, target: int):
        offset = len(buffer)
        buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": byte_length, "target": target})
        return offset, byte_length

    for mesh in meshes:
        pos_bytes = struct.pack("<%df" % len(mesh.positions), *mesh.positions)
        _pad4(buffer)
        add_view(len(pos_bytes), 34962)
        buffer += pos_bytes
        minp = (min(mesh.positions[0::3]), min(mesh.positions[1::3]), min(mesh.positions[2::3]))
        maxp = (max(mesh.positions[0::3]), max(mesh.positions[1::3]), max(mesh.positions[2::3]))
        accessors.append(
            {
                "bufferView": len(buffer_views) - 1,
                "componentType": 5126,
                "count": len(mesh.positions) // 3,
                "type": "VEC3",
                "min": list(minp),
                "max": list(maxp),
            }
        )

        nrm_bytes = struct.pack("<%df" % len(mesh.normals), *mesh.normals)
        _pad4(buffer)
        add_view(len(nrm_bytes), 34962)
        buffer += nrm_bytes
        accessors.append(
            {"bufferView": len(buffer_views) - 1, "componentType": 5126, "count": len(mesh.normals) // 3, "type": "VEC3"}
        )

        idx_bytes = struct.pack("<%dI" % len(mesh.indices), *mesh.indices)
        _pad4(buffer)
        add_view(len(idx_bytes), 34963)
        buffer += idx_bytes
        accessors.append(
            {"bufferView": len(buffer_views) - 1, "componentType": 5125, "count": len(mesh.indices), "type": "SCALAR"}
        )

        if mesh.color not in material_map:
            material_map[mesh.color] = len(materials)
            r, g, b, a = mesh.color
            materials.append(
                {
                    "name": "mat_%d" % len(materials),
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [r, g, b, a],
                        "metallicFactor": 0.0,
                        "roughnessFactor": 0.85,
                    },
                    "doubleSided": True,
                }
            )
        mat_idx = material_map[mesh.color]

        mesh_defs.append(
            {
                "name": mesh.name,
                "primitives": [
                    {
                        "attributes": {"POSITION": len(accessors) - 3, "NORMAL": len(accessors) - 2},
                        "indices": len(accessors) - 1,
                        "material": mat_idx,
                        "mode": 4,
                    }
                ],
            }
        )

        node = {"name": mesh.name, "mesh": mesh_index}
        if mesh.translation != (0.0, 0.0, 0.0):
            node["translation"] = list(mesh.translation)
        if mesh.scale != (1.0, 1.0, 1.0):
            node["scale"] = list(mesh.scale)
        if mesh.rotation != (0.0, 0.0, 0.0):
            node["rotation"] = list(_euler_to_quaternion(*mesh.rotation))
        nodes.append(node)
        mesh_index += 1

    gltf = {
        "asset": {"version": "2.0", "generator": "AIVCS local low-power 3D provider"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": mesh_defs,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(buffer)}],
    }

    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    _pad4(json_bytes)
    _pad4(buffer)
    total = 12 + 8 + len(json_bytes) + 8 + len(buffer)
    header = struct.pack("<4sII", b"glTF", 2, total)
    json_chunk = struct.pack("<I4s", len(json_bytes), b"JSON") + json_bytes
    bin_chunk = struct.pack("<I4s", len(buffer), b"BIN\x00") + buffer
    return header + json_chunk + bin_chunk
