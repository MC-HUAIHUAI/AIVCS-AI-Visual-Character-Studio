"""Paint Runtime output adaptation (Phase 3-H).

Turns a Paint Runtime's output GLB into the shape AIVCS accepts, and extracts
the texture metadata ModelStore stores:

    GLB (with embedded PBR textures)  ->  verify_textured_glb
                                        ->  {baseColor / normal / metallicRoughness maps}
                                        ->  ModelStore texture metadata (Phase 3-G field)

glTF 2.0 convention used here:
  - baseColorTexture      -> BaseColor map
  - normalTexture         -> Normal map
  - metallicRoughnessTexture -> Roughness + Metallic (single glTF PBR texture)

This is pure adaptation (parse + report). Paint inference itself NEVER runs in
the AIVCS backend - it happens in a separate local Paint Runtime process that
AIVCS talks to over the localhost EmbeddedClient protocol.

No network, no shell, no arbitrary paths. verify_textured_glb is fault tolerant
(returns None on any non-textured / malformed GLB) so it can be called on every
generated model without risking a done job.
"""

from __future__ import annotations

from .glb_analyzer import analyze_glb
from .glb_builder import parse_glb, validate_glb


class PaintOutputError(RuntimeError):
    """Raised when a Paint Runtime output is not an acceptable textured GLB."""


def verify_textured_glb(data: bytes) -> dict | None:
    """Return texture metadata for a textured GLB, or None when not textured.

    Fault tolerant: any structural failure, or a GLB without textures/UVs,
    yields None (never raises).
    """
    try:
        gltf, _buffer = parse_glb(data)
        textures = gltf.get("textures") or []
        if not textures:
            return None
        stats = analyze_glb(data)
        if not stats.hasUVs:
            return None
        materials = gltf.get("materials") or []
        maps = {"baseColor": False, "normal": False, "metallicRoughness": False}
        for mat in materials:
            pbr = mat.get("pbrMetallicRoughness") or {}
            if isinstance(pbr.get("baseColorTexture"), dict):
                maps["baseColor"] = True
            if isinstance(mat.get("normalTexture"), dict):
                maps["normal"] = True
            if isinstance(pbr.get("metallicRoughnessTexture"), dict):
                maps["metallicRoughness"] = True
        return {
            "supported": True,
            "kind": "paint",
            "maps": maps,
            "textureCount": len(textures),
            "hasUVs": True,
        }
    except Exception:  # noqa: BLE001 - never break a done job
        return None


def adapt_paint_output(glb_bytes: bytes) -> dict:
    """Validate + adapt a Paint Runtime GLB output.

    Raises PaintOutputError when the output is not a legal textured GLB.
    Returns {ok, textured, texture, format, mime, sizeBytes}.
    """
    validate_glb(glb_bytes)
    texture = verify_textured_glb(glb_bytes)
    if texture is None:
        raise PaintOutputError("Paint Runtime 输出未包含纹理（无 texture 或 UV），无法作为 textured GLB 接受")
    return {
        "ok": True,
        "textured": True,
        "texture": texture,
        "format": "glb",
        "mime": "model/gltf-binary",
        "sizeBytes": len(glb_bytes),
    }
