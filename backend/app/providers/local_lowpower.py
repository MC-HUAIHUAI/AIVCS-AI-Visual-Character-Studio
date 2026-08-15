"""Local low-power 3D provider - deterministic CPU prototype (Phase 2.3-D).

Generates a legal low-poly GLB purely from the CharacterSpec plus dominant
colors sampled from the multi-view reference images. No cloud API, no GPU, no
large models, fully deterministic. Integrates with the existing JobManager
(cancel / timeout) and ModelStore through the standard AIImage3DProvider
contract.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import struct
import zlib
from dataclasses import dataclass

from .base import AIImage3DProvider, CancellationToken, ProgressCallback, ProviderCancelledError
from .. import config
from ..schemas.asset import CharacterAsset
from ..schemas.character import CharacterSpec
from ..schemas.vision import VisionImageInput
from ..services.glb_builder import Primitive, build_glb
from ..services.rig_builder import build_bone_tree

FALLBACK_PALETTE = ["#6C8CFF", "#3E4E8C", "#A55CFF", "#E6EAF2"]

_SKIN_FALLBACK = "#E8CDB3"
_DARK_FALLBACK = "#20242E"

# Body types that can carry the conditional minimal eye primitives.
_EYE_BODY_TYPES = ("humanoid", "biped-anthro")


# --------------------------------------------------------------------------- #
# Minimal PNG decoder (8-bit, non-interlaced, gray / RGB / RGBA)
# --------------------------------------------------------------------------- #

def decode_png(data: bytes) -> tuple[int, int, list]:
    """Return (width, height, rows) where rows[i] is a list of (r,g,b) tuples."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")
    pos = 8
    idat = b""
    width = height = bit_depth = color_type = interlace = 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        typ = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if typ == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
    if bit_depth != 8 or interlace != 0:
        raise ValueError("unsupported PNG encoding")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError("unsupported PNG color type")

    raw = zlib.decompress(idat)
    stride = width * channels
    prev = bytearray(stride)
    out = []
    p = 0
    for _ in range(height):
        f = raw[p]
        p += 1
        line = bytearray(raw[p : p + stride])
        p += stride
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                pr = a + b - c
                pa, pb, pc = abs(pr - a), abs(pr - b), abs(pr - c)
                line[i] = (line[i] + (a if (pa <= pb and pa <= pc) else (b if pb <= pc else c))) & 255
            elif f != 0:
                raise ValueError("bad PNG filter")
        prev = line
        if color_type == 2:
            out.append([(line[i], line[i + 1], line[i + 2]) for i in range(0, stride, 3)])
        elif color_type == 6:
            out.append([(line[i], line[i + 1], line[i + 2]) for i in range(0, stride, 4)])
        else:  # grayscale
            out.append([(line[i], line[i], line[i]) for i in range(stride)])
    return width, height, out


def _to_hex(rgb: tuple) -> str:
    return "#%02X%02X%02X" % (rgb[0], rgb[1], rgb[2])


def extract_palette(references: list[VisionImageInput], max_colors: int = 4) -> list[str]:
    """Sample dominant colors from the first decodable reference image."""
    for ref in references:
        try:
            b64 = ref.data_url.split(",", 1)[1]
            data = base64.b64decode(b64)
            _w, _h, rows = decode_png(data)
        except Exception:  # noqa: BLE001 - any decode failure falls through
            continue
        counts: dict = {}
        step = max(1, len(rows) // 48)
        for y in range(0, len(rows), step):
            row = rows[y]
            for x in range(0, len(row), step):
                r, g, b = row[x]
                q = (r // 32 * 32, g // 32 * 32, b // 32 * 32)
                counts[q] = counts.get(q, 0) + 1
        if not counts:
            continue
        ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return [_to_hex(c) for c, _ in ordered[:max_colors]]
    return []


# --------------------------------------------------------------------------- #
# Deterministic palette fallback
# --------------------------------------------------------------------------- #

def _spec_hash(spec: CharacterSpec) -> str:
    import json

    canonical = json.dumps(spec.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _deterministic_palette(spec: CharacterSpec) -> list[str]:
    digest = _spec_hash(spec)
    hues = [int(digest[i : i + 2], 16) for i in (0, 2, 4, 6)]
    return ["#%02X%02X%02X" % (hues[0] % 200 + 40, hues[1] % 200 + 40, hues[2] % 200 + 40), FALLBACK_PALETTE[1], FALLBACK_PALETTE[2], FALLBACK_PALETTE[3]]


def resolve_palette(spec: CharacterSpec, references: list[VisionImageInput]) -> list[str]:
    from_ref = extract_palette(references)
    if from_ref:
        return from_ref
    if spec.appearance.palette:
        return list(spec.appearance.palette[:4])
    if spec.fur.colors:
        return list(spec.fur.colors[:4])
    return _deterministic_palette(spec)


# --------------------------------------------------------------------------- #
# Render colors (Phase 3-3): CharacterAsset-driven semantic color roles.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RenderColors:
    primary: str
    secondary: str
    accent: str
    dark: str
    skin: str
    hair: str
    eye: str | None = None


def resolve_render_colors(
    spec: CharacterSpec,
    palette: list[str],
    asset: CharacterAsset | None = None,
) -> RenderColors:
    """Resolve the semantic render colors for the primitive topology.

    Deterministic. When no CharacterAsset is provided (old projects / demo) the
    result is byte-compatible with the pre-Phase-3 color resolution:

      primary   = palette[0] (fallback FALLBACK_PALETTE[0])
      secondary = palette[1] (fallback primary)
      accent    = palette[2] (fallback secondary)
      dark      = palette[3] (fallback _DARK_FALLBACK)
      skin      = _SKIN_FALLBACK
      hair      = dark
      eye       = None

    With a CharacterAsset:
      outfitColors[0] -> primary, [1] -> secondary, [2] -> accent
      (missing items fall back to the palette-derived values, one by one)
      skinColor -> skin, hairColor -> hair, eyeColor -> eye
    provenance (observed/derived) never affects geometry or determinism.
    """
    primary = palette[0] if palette else FALLBACK_PALETTE[0]
    secondary = palette[1] if len(palette) > 1 else primary
    accent = palette[2] if len(palette) > 2 else secondary
    dark = palette[3] if len(palette) > 3 else _DARK_FALLBACK
    skin = _SKIN_FALLBACK
    hair = dark
    eye = None

    if asset is not None:
        if asset.skin_color:
            skin = asset.skin_color
        if asset.hair_color:
            hair = asset.hair_color
        if asset.eye_color:
            eye = asset.eye_color
        outfit = asset.outfit_colors or []
        if outfit:
            primary = outfit[0]
        if len(outfit) > 1:
            secondary = outfit[1]
        if len(outfit) > 2:
            accent = outfit[2]

    return RenderColors(primary=primary, secondary=secondary, accent=accent, dark=dark, skin=skin, hair=hair, eye=eye)


# --------------------------------------------------------------------------- #
# Topology builder (deterministic)
# --------------------------------------------------------------------------- #

def build_primitives(
    spec: CharacterSpec,
    palette: list[str],
    render_colors: RenderColors | None = None,
) -> list[Primitive]:
    rc = render_colors or resolve_render_colors(spec, palette)
    primary = rc.primary
    secondary = rc.secondary
    accent = rc.accent
    dark = rc.dark
    skin = rc.skin
    hair = rc.hair
    eye = rc.eye

    anatomy = spec.anatomy
    parts: list[Primitive] = []

    body_type = spec.body_type or "humanoid"

    if body_type in ("quadruped", "animal"):
        # horizontal body
        parts.append(Primitive("box", (0.9, 0.5, 1.3), center=(0, 0.55, 0), color=primary))
        parts.append(Primitive("box", (0.3, 0.28, 0.32), center=(0.0, 0.4, 0.72), color=secondary))  # head
        parts.append(Primitive("box", (0.12, 0.3, 0.12), center=(-0.3, 0.22, 0.45), color=secondary))  # front L
        parts.append(Primitive("box", (0.12, 0.3, 0.12), center=(0.3, 0.22, 0.45), color=secondary))  # front R
        parts.append(Primitive("box", (0.14, 0.34, 0.14), center=(-0.3, 0.16, -0.45), color=secondary))  # rear L
        parts.append(Primitive("box", (0.14, 0.34, 0.14), center=(0.3, 0.16, -0.45), color=secondary))  # rear R
        if anatomy.tail != "none":
            parts.append(Primitive("box", (0.18, 0.18, 0.6), center=(0, 0.62, -0.95), color=accent, rotation=(0.5, 0, 0)))
        if anatomy.ears:
            parts.append(Primitive("box", (0.08, 0.16, 0.06), center=(-0.08, 0.58, 0.78), color=dark))
            parts.append(Primitive("box", (0.08, 0.16, 0.06), center=(0.08, 0.58, 0.78), color=dark))
        if anatomy.snout:
            parts.append(Primitive("box", (0.18, 0.12, 0.18), center=(0, 0.34, 0.9), color=secondary))
        return parts

    if body_type == "bird":
        parts.append(Primitive("box", (0.5, 0.5, 0.7), center=(0, 0.6, 0), color=primary))
        parts.append(Primitive("sphere", radius=0.24, center=(0, 0.95, 0.35), color=secondary))
        parts.append(Primitive("box", (0.1, 0.12, 0.16), center=(0, 0.94, 0.6), color=accent))  # beak
        parts.append(Primitive("box", (0.7, 0.16, 0.25), center=(-0.45, 0.62, 0), color=secondary, rotation=(0, 0, 0.6)))  # wing L
        parts.append(Primitive("box", (0.7, 0.16, 0.25), center=(0.45, 0.62, 0), color=secondary, rotation=(0, 0, -0.6)))  # wing R
        parts.append(Primitive("box", (0.1, 0.35, 0.1), center=(-0.12, 0.2, 0.05), color=dark))
        parts.append(Primitive("box", (0.1, 0.35, 0.1), center=(0.12, 0.2, 0.05), color=dark))
        parts.append(Primitive("box", (0.18, 0.2, 0.4), center=(0, 0.5, -0.5), color=accent, rotation=(0.4, 0, 0)))  # tail
        return parts

    # biped bodies (humanoid / biped-anthro / dragon / robot / default)
    if body_type == "dragon":
        parts.append(Primitive("box", (0.6, 0.5, 1.1), center=(0, 0.7, 0), color=primary))
        parts.append(Primitive("box", (0.4, 0.35, 0.5), center=(0, 1.2, 0.35), color=primary))  # neck
        parts.append(Primitive("sphere", radius=0.24, center=(0, 1.5, 0.5), color=primary))
        parts.append(Primitive("box", (0.16, 0.12, 0.3), center=(0, 1.45, 0.8), color=secondary))  # snout
        if anatomy.horns or anatomy.antlers:
            parts.append(Primitive("box", (0.05, 0.2, 0.05), center=(-0.12, 1.75, 0.5), color=accent, rotation=(0, 0, 0.3)))
            parts.append(Primitive("box", (0.05, 0.2, 0.05), center=(0.12, 1.75, 0.5), color=accent, rotation=(0, 0, -0.3)))
        if anatomy.wings:
            parts.append(Primitive("box", (0.6, 0.5, 0.06), center=(-0.6, 0.85, 0.2), color=accent, rotation=(0, 0, 0.5)))
            parts.append(Primitive("box", (0.6, 0.5, 0.06), center=(0.6, 0.85, 0.2), color=accent, rotation=(0, 0, -0.5)))
        parts.append(Primitive("box", (0.14, 0.55, 0.16), center=(-0.2, 0.32, -0.3), color=secondary))
        parts.append(Primitive("box", (0.14, 0.55, 0.16), center=(0.2, 0.32, -0.3), color=secondary))
        if anatomy.tail != "none":
            parts.append(Primitive("box", (0.2, 0.2, 0.7), center=(0, 0.8, -0.85), color=accent, rotation=(0.4, 0, 0)))
        return parts

    if body_type == "robot":
        parts.append(Primitive("box", (0.6, 0.6, 0.4), center=(0, 0.9, 0), color=primary))
        parts.append(Primitive("box", (0.4, 0.4, 0.3), center=(0, 1.45, 0), color=secondary))
        parts.append(Primitive("box", (0.1, 0.3, 0.1), center=(-0.38, 0.9, 0), color=secondary))
        parts.append(Primitive("box", (0.1, 0.3, 0.1), center=(0.38, 0.9, 0), color=secondary))
        parts.append(Primitive("box", (0.16, 0.45, 0.16), center=(-0.14, 0.25, 0), color=secondary))
        parts.append(Primitive("box", (0.16, 0.45, 0.16), center=(0.14, 0.25, 0), color=secondary))
        parts.append(Primitive("box", (0.06, 0.2, 0.06), center=(0, 1.7, 0), color=accent))  # antenna
        parts.append(Primitive("sphere", radius=0.05, center=(0, 1.82, 0), color=accent))
        return parts

    # humanoid / biped-anthro / default
    parts.append(Primitive("box", (0.16, 0.5, 0.18), center=(-0.15, 0.25, 0), color=dark))  # leg L
    parts.append(Primitive("box", (0.16, 0.5, 0.18), center=(0.15, 0.25, 0), color=dark))  # leg R
    parts.append(Primitive("box", (0.55, 0.55, 0.35), center=(0, 0.85, 0), color=primary))  # torso
    parts.append(Primitive("box", (0.14, 0.45, 0.14), center=(-0.38, 0.95, 0), color=secondary))  # arm L
    parts.append(Primitive("box", (0.14, 0.45, 0.14), center=(0.38, 0.95, 0), color=secondary))  # arm R
    parts.append(Primitive("sphere", radius=0.28, center=(0, 1.55, 0), color=skin))  # head
    parts.append(Primitive("box", (0.34, 0.08, 0.34), center=(0, 1.78, -0.05), color=hair))  # hair cap
    if anatomy.snout or body_type == "biped-anthro":
        parts.append(Primitive("box", (0.18, 0.12, 0.16), center=(0, 1.52, 0.28), color=skin))
        parts.append(Primitive("box", (0.05, 0.04, 0.03), center=(0, 1.52, 0.37), color=dark))
    if anatomy.ears:
        parts.append(Primitive("box", (0.08, 0.18, 0.05), center=(-0.26, 1.7, -0.05), color=secondary, rotation=(0, 0, 0.3)))
        parts.append(Primitive("box", (0.08, 0.18, 0.05), center=(0.26, 1.7, -0.05), color=secondary, rotation=(0, 0, -0.3)))
    if anatomy.horns or anatomy.antlers:
        parts.append(Primitive("box", (0.05, 0.16, 0.05), center=(-0.12, 1.85, 0), color=accent, rotation=(0, 0, 0.3)))
        parts.append(Primitive("box", (0.05, 0.16, 0.05), center=(0.12, 1.85, 0), color=accent, rotation=(0, 0, -0.3)))
    if anatomy.wings:
        parts.append(Primitive("box", (0.5, 0.35, 0.05), center=(-0.7, 1.0, 0.05), color=accent, rotation=(0, 0, 0.5)))
        parts.append(Primitive("box", (0.5, 0.35, 0.05), center=(0.7, 1.0, 0.05), color=accent, rotation=(0, 0, -0.5)))
    if anatomy.tail != "none":
        parts.append(Primitive("box", (0.18, 0.18, 0.5), center=(0, 0.6, -0.3), color=accent, rotation=(0.5, 0, 0)))
    # Phase 3-3: conditional minimal eyes - only humanoid/biped + eyeColor present.
    if body_type in _EYE_BODY_TYPES and eye:
        parts.append(Primitive("box", (0.05, 0.04, 0.02), center=(-0.11, 1.56, 0.24), color=eye))  # eye L
        parts.append(Primitive("box", (0.05, 0.04, 0.02), center=(0.11, 1.56, 0.24), color=eye))  # eye R
    return parts


# --------------------------------------------------------------------------- #
# Provider
# --------------------------------------------------------------------------- #

class LocalLowPower3DProvider(AIImage3DProvider):
    id = "local-lowpower"
    name = "Local Low-Power"
    description = "CPU 本地低功耗确定性原型：由 CharacterSpec + 参考图配色生成低模 GLB。无需 GPU 与云端 API。"
    gpu_required = False
    max_references = 4
    output_format = "glb"
    supports_cancel = True
    supports_timeout = True

    async def generate(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        on_progress: ProgressCallback,
        cancel_event: CancellationToken | None = None,
        character_asset: CharacterAsset | None = None,
        runtime_id: str | None = None,
    ) -> bytes:
        steps = ["解析角色规格", "提取参考图配色", "生成低模拓扑", "应用材质", "导出 GLB"]
        total = len(steps)
        for i, label in enumerate(steps):
            if cancel_event is not None and cancel_event.is_cancelled:
                raise ProviderCancelledError("生成已取消")
            on_progress(i, total, label)
            await asyncio.sleep(0.01)

        if cancel_event is not None and cancel_event.is_cancelled:
            raise ProviderCancelledError("生成已取消")

        palette = resolve_palette(spec, references)
        scale = max(0.5, min(2.0, (spec.height_cm or 160) / 160.0))
        render_colors = resolve_render_colors(spec, palette, character_asset)
        primitives = build_primitives(spec, palette, render_colors)

        # Phase 2.6-C: optional skinned output (default OFF keeps old behavior).
        # The bone tree is built in the same model space as the primitives, so
        # the nearest-bone binding (Phase 2.6-B) stays consistent.
        if config.LOCAL3D_RIG_ENABLED:
            bones = build_bone_tree(spec)
            data = build_glb(primitives, scale=scale, bones=bones)
        else:
            data = build_glb(primitives, scale=scale)

        on_progress(total, total, "生成完成")
        return data
