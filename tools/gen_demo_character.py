#!/usr/bin/env python3
"""AIVCS demo character generator.

Builds a stylized low-poly "chibi" humanoid and writes it as a binary glTF 2.0
(.glb) file. Pure standard library (no numpy / trimesh required) so it runs on
any Python 3.x.

Usage:
    python tools/gen_demo_character.py

Outputs:
    assets/demo_character.glb
    src/renderer/public/demo_character.glb   (bundled with the renderer)
"""

from __future__ import annotations

import json
import math
import os
import shutil
import struct
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #


@dataclass
class Mesh:
    name: str
    positions: list = field(default_factory=list)
    normals: list = field(default_factory=list)
    indices: list = field(default_factory=list)
    color: tuple = (0.8, 0.8, 0.8, 1.0)
    translation: tuple = (0.0, 0.0, 0.0)
    scale: tuple = (1.0, 1.0, 1.0)
    rotation: tuple = (0.0, 0.0, 0.0)  # euler radians, XYZ order


def euler_to_quaternion(rx, ry, rz):
    """XYZ euler -> (x, y, z, w) quaternion (matches three.js Euler XYZ)."""
    cr, sr = math.cos(rx / 2), math.sin(rx / 2)
    cp, sp = math.cos(ry / 2), math.sin(ry / 2)
    cy, sy = math.cos(rz / 2), math.sin(rz / 2)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _add_face(mesh: Mesh, corners, n):
    base = len(mesh.positions) // 3
    for c in corners:
        mesh.positions.extend(c)
        mesh.normals.extend(n)
    mesh.indices += [base, base + 1, base + 2, base, base + 2, base + 3]


def box_mesh(name, sx, sy, sz, color, translation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), rotation=(0.0, 0.0, 0.0)):
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    m = Mesh(name=name, color=color, translation=translation, scale=scale, rotation=rotation)
    _add_face(m, [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)], (0, 0, 1))
    _add_face(m, [(-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz)], (0, 0, -1))
    _add_face(m, [(hx, -hy, -hz), (hx, -hy, hz), (hx, hy, hz), (hx, hy, -hz)], (1, 0, 0))
    _add_face(m, [(-hx, -hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (-hx, -hy, hz)], (-1, 0, 0))
    _add_face(m, [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)], (0, 1, 0))
    _add_face(m, [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)], (0, -1, 0))
    return m


def uv_sphere_mesh(name, radius, color, lat=14, lon=22, translation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), rotation=(0.0, 0.0, 0.0)):
    m = Mesh(name=name, color=color, translation=translation, scale=scale, rotation=rotation)
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


# --------------------------------------------------------------------------- #
# GLB writer
# --------------------------------------------------------------------------- #


def _pad4(buf: bytearray) -> None:
    while len(buf) % 4 != 0:
        buf += b"\x00"


def build_glb(meshes: list) -> bytes:
    buffer = bytearray()
    buffer_views = []  # (byte_offset, byte_length, target)
    accessors = []
    mesh_index = 0
    material_map = {}
    materials = []
    mesh_defs = []
    nodes = []

    def add_view(byte_length, target):
        offset = len(buffer)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": byte_length}
        if target:
            view["target"] = target
        buffer_views.append((offset, byte_length, target))
        return offset, byte_length

    for mesh in meshes:
        # positions
        pos_bytes = struct.pack("<%df" % len(mesh.positions), *mesh.positions)
        _pad4(buffer)
        p_off, p_len = add_view(len(pos_bytes), 34962)
        buffer += pos_bytes
        minp = (min(mesh.positions[0::3]), min(mesh.positions[1::3]), min(mesh.positions[2::3]))
        maxp = (max(mesh.positions[0::3]), max(mesh.positions[1::3]), max(mesh.positions[2::3]))
        p_acc = {
            "bufferView": len(buffer_views) - 1,
            "componentType": 5126,
            "count": len(mesh.positions) // 3,
            "type": "VEC3",
            "min": list(minp),
            "max": list(maxp),
        }
        accessors.append(p_acc)

        # normals
        nrm_bytes = struct.pack("<%df" % len(mesh.normals), *mesh.normals)
        _pad4(buffer)
        add_view(len(nrm_bytes), 34962)
        buffer += nrm_bytes
        accessors.append(
            {
                "bufferView": len(buffer_views) - 1,
                "componentType": 5126,
                "count": len(mesh.normals) // 3,
                "type": "VEC3",
            }
        )

        # indices
        idx_bytes = struct.pack("<%dI" % len(mesh.indices), *mesh.indices)
        _pad4(buffer)
        add_view(len(idx_bytes), 34963)
        buffer += idx_bytes
        accessors.append(
            {
                "bufferView": len(buffer_views) - 1,
                "componentType": 5125,
                "count": len(mesh.indices),
                "type": "SCALAR",
            }
        )

        # material (shared by color)
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
                        "attributes": {
                            "POSITION": len(accessors) - 3,
                            "NORMAL": len(accessors) - 2,
                        },
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
            node["rotation"] = list(euler_to_quaternion(*mesh.rotation))
        nodes.append(node)
        mesh_index += 1

    gltf = {
        "asset": {"version": "2.0", "generator": "AIVCS demo character generator"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": mesh_defs,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": [
            {"buffer": 0, "byteOffset": o, "byteLength": n, **({"target": t} if t else {})}
            for o, n, t in buffer_views
        ],
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


# --------------------------------------------------------------------------- #
# Character assembly
# --------------------------------------------------------------------------- #


def build_demo_character() -> list:
    SKIN = (0.99, 0.84, 0.76, 1.0)
    HAIR = (0.16, 0.11, 0.14, 1.0)
    SHIRT = (0.33, 0.62, 0.92, 1.0)
    PANTS = (0.24, 0.27, 0.36, 1.0)
    SHOES = (0.12, 0.12, 0.14, 1.0)
    EYE = (0.07, 0.07, 0.10, 1.0)
    MOUTH = (0.55, 0.22, 0.26, 1.0)
    HAIR_LIGHT = (0.35, 0.28, 0.34, 1.0)

    meshes = []

    # Head
    meshes.append(uv_sphere_mesh("head", 0.34, SKIN, translation=(0.0, 1.32, 0.0)))
    # Hair (dome peeking above/behind the head)
    meshes.append(
        uv_sphere_mesh("hair", 0.37, HAIR, translation=(0.0, 1.46, -0.04), scale=(1.0, 0.85, 1.05))
    )
    # Bangs
    meshes.append(box_mesh("bangs", 0.55, 0.16, 0.10, HAIR_LIGHT))
    meshes[-1].translation = (0.0, 1.47, 0.12)
    # Eyes
    meshes.append(uv_sphere_mesh("eye_l", 0.055, EYE, translation=(-0.115, 1.36, 0.285)))
    meshes.append(uv_sphere_mesh("eye_r", 0.055, EYE, translation=(0.115, 1.36, 0.285)))
    # Mouth
    meshes.append(box_mesh("mouth", 0.11, 0.035, 0.02, MOUTH))
    meshes[-1].translation = (0.0, 1.22, 0.30)

    # Neck
    meshes.append(box_mesh("neck", 0.15, 0.14, 0.15, SKIN))
    meshes[-1].translation = (0.0, 1.00, 0.0)

    # Torso
    meshes.append(box_mesh("torso", 0.60, 0.52, 0.34, SHIRT))
    meshes[-1].translation = (0.0, 0.74, 0.0)
    # Collar
    meshes.append(box_mesh("collar", 0.34, 0.06, 0.30, (0.95, 0.95, 0.98, 1.0)))
    meshes[-1].translation = (0.0, 0.99, 0.0)

    # Arms
    meshes.append(box_mesh("arm_l", 0.15, 0.46, 0.15, SHIRT))
    meshes[-1].translation = (-0.38, 0.86, 0.0)
    meshes.append(box_mesh("arm_r", 0.15, 0.46, 0.15, SHIRT))
    meshes[-1].translation = (0.38, 0.86, 0.0)
    # Hands
    meshes.append(uv_sphere_mesh("hand_l", 0.09, SKIN, translation=(-0.38, 0.58, 0.0)))
    meshes.append(uv_sphere_mesh("hand_r", 0.09, SKIN, translation=(0.38, 0.58, 0.0)))

    # Legs
    meshes.append(box_mesh("leg_l", 0.19, 0.42, 0.19, PANTS))
    meshes[-1].translation = (-0.155, 0.24, 0.0)
    meshes.append(box_mesh("leg_r", 0.19, 0.42, 0.19, PANTS))
    meshes[-1].translation = (0.155, 0.24, 0.0)

    # Shoes
    meshes.append(box_mesh("shoe_l", 0.20, 0.07, 0.32, SHOES))
    meshes[-1].translation = (-0.155, 0.035, 0.03)
    meshes.append(box_mesh("shoe_r", 0.20, 0.07, 0.32, SHOES))
    meshes[-1].translation = (0.155, 0.035, 0.03)

    # Feet / floor offset - shift everything up so feet rest at y=0
    for m in meshes:
        m.translation = (m.translation[0], m.translation[1], m.translation[2])
    return meshes


def build_demo_fox() -> list:
    """Stylized biped anthro fox: snout, ears, digitigrade legs, curved tail.

    Demonstrates non-human anatomy end-to-end: the same GLB writer that builds
    the human chibi also builds a creature with a completely different graph.
    """
    FUR = (0.90, 0.53, 0.18, 1.0)
    FUR_LIGHT = (0.97, 0.93, 0.86, 1.0)
    FUR_DARK = (0.45, 0.30, 0.20, 1.0)
    EYE = (0.30, 0.55, 0.95, 1.0)
    NOSE = (0.12, 0.10, 0.12, 1.0)
    INNER = (0.95, 0.80, 0.85, 1.0)

    meshes = []

    # Digitigrade legs
    for side, sx in (("l", -0.15), ("r", 0.15)):
        meshes.append(box_mesh(f"thigh_{side}", 0.15, 0.22, 0.16, FUR, translation=(sx, 0.66, 0.02), rotation=(-0.25, 0.0, 0.0)))
        meshes.append(box_mesh(f"calf_{side}", 0.13, 0.20, 0.14, FUR, translation=(sx, 0.40, 0.06), rotation=(0.25, 0.0, 0.0)))
        meshes.append(box_mesh(f"paw_{side}", 0.17, 0.08, 0.30, FUR_DARK, translation=(sx, 0.06, 0.10)))

    # Pelvis + chest
    meshes.append(box_mesh("hips", 0.44, 0.28, 0.30, FUR, translation=(0.0, 0.80, 0.0)))
    meshes.append(box_mesh("torso", 0.52, 0.50, 0.30, FUR, translation=(0.0, 1.16, 0.0)))
    meshes.append(box_mesh("belly", 0.30, 0.36, 0.16, FUR_LIGHT, translation=(0.0, 1.14, 0.10)))
    meshes.append(box_mesh("chest_fluff", 0.24, 0.20, 0.12, FUR_LIGHT, translation=(0.0, 1.32, 0.13)))

    # Arms
    for side, sx in (("l", -0.33), ("r", 0.33)):
        meshes.append(box_mesh(f"arm_{side}", 0.13, 0.40, 0.13, FUR, translation=(sx, 1.10, 0.0)))
        meshes.append(uv_sphere_mesh(f"hand_{side}", 0.07, FUR_DARK, translation=(sx, 0.85, 0.0)))

    # Neck + head
    meshes.append(box_mesh("neck", 0.14, 0.14, 0.14, FUR, translation=(0.0, 1.44, 0.0)))
    meshes.append(uv_sphere_mesh("head", 0.21, FUR, translation=(0.0, 1.74, 0.0)))

    # Snout + muzzle + nose
    meshes.append(box_mesh("snout", 0.17, 0.10, 0.15, FUR, translation=(0.0, 1.70, 0.20)))
    meshes.append(box_mesh("muzzle", 0.14, 0.06, 0.10, FUR_LIGHT, translation=(0.0, 1.65, 0.22)))
    meshes.append(box_mesh("nose", 0.05, 0.035, 0.03, NOSE, translation=(0.0, 1.73, 0.30)))

    # Eyes
    meshes.append(uv_sphere_mesh("eye_l", 0.04, EYE, translation=(-0.10, 1.80, 0.17)))
    meshes.append(uv_sphere_mesh("eye_r", 0.04, EYE, translation=(0.10, 1.80, 0.17)))

    # Whiskers
    for side, sx, rotz in (("l", -0.10, 0.35), ("r", 0.10, -0.35)):
        meshes.append(box_mesh(f"whisker_{side}a", 0.03, 0.02, 0.11, FUR_LIGHT, translation=(sx, 1.70, 0.26), rotation=(0.0, 0.0, rotz)))
        meshes.append(box_mesh(f"whisker_{side}b", 0.03, 0.02, 0.11, FUR_LIGHT, translation=(sx, 1.66, 0.26), rotation=(0.0, 0.0, rotz)))

    # Ears (tilted outward) with inner ears
    for side, sx, rotz in (("l", -0.13, 0.30), ("r", 0.13, -0.30)):
        meshes.append(box_mesh(f"ear_{side}", 0.09, 0.20, 0.07, FUR, translation=(sx, 2.00, -0.03), rotation=(0.15, 0.0, rotz)))
        meshes.append(box_mesh(f"ear_inner_{side}", 0.05, 0.12, 0.04, INNER, translation=(sx, 2.00, -0.01), rotation=(0.15, 0.0, rotz)))

    # Curved tail (three segments, white tip)
    meshes.append(box_mesh("tail_1", 0.26, 0.26, 0.36, FUR, translation=(0.0, 0.84, -0.16), rotation=(0.35, 0.0, 0.0)))
    meshes.append(box_mesh("tail_2", 0.22, 0.22, 0.32, FUR, translation=(0.0, 0.98, -0.42), rotation=(0.70, 0.0, 0.0)))
    meshes.append(box_mesh("tail_3", 0.17, 0.17, 0.28, FUR_LIGHT, translation=(0.0, 1.14, -0.62), rotation=(1.05, 0.0, 0.0)))

    return meshes


def _write_glb(filename: str, meshes: list) -> str:
    glb = build_glb(meshes)
    out_assets = os.path.join(ROOT, "assets")
    out_public = os.path.join(ROOT, "src", "renderer", "public")
    os.makedirs(out_assets, exist_ok=True)
    os.makedirs(out_public, exist_ok=True)

    assets_path = os.path.join(out_assets, filename)
    with open(assets_path, "wb") as f:
        f.write(glb)

    public_path = os.path.join(out_public, filename)
    shutil.copyfile(assets_path, public_path)
    return f"{assets_path} ({len(glb)} bytes)"


def main() -> int:
    print("Wrote " + _write_glb("demo_character.glb", build_demo_character()))
    print("Wrote " + _write_glb("demo_fox.glb", build_demo_fox()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
