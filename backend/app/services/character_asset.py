"""CharacterAsset derivation (Phase 3-1).

Deterministic, network-free derivation of a renderable CharacterAsset from a
CharacterSpec - the mirror of the frontend pure logic in
src/renderer/src/core/spec/characterAssetLogic.ts. The CharacterSpec remains
the single semantic source; CharacterAsset is a derived appearance layer with
per-field provenance ('derived' | 'observed' | 'none'). Fields without a
reliable source stay absent - nothing is invented.

NOT wired to real 3D/2D output in this stage.
"""

from __future__ import annotations

import re

from ..schemas.asset import CharacterAsset

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _hex_list(value) -> list[str] | None:
    if not isinstance(value, list):
        return None
    out = [c for c in value if isinstance(c, str) and _HEX_RE.match(c)]
    return out or None


def _hex_or_null(value) -> str | None:
    if isinstance(value, str) and _HEX_RE.match(value):
        return value
    return None


def _str_or_null(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def derive_character_asset(spec) -> CharacterAsset:
    """Deterministically derive a CharacterAsset from a CharacterSpec."""
    asset = CharacterAsset()
    app = spec.appearance if spec.appearance is not None else None
    fur = spec.fur if spec.fur is not None else None

    app_palette = _hex_list(getattr(app, "palette", None) if app else None)
    if app_palette:
        asset.palette = app_palette
        asset.outfit_colors = app_palette[:4]
        asset.source["palette"] = "derived"
        asset.source["outfitColors"] = "derived"

    base = _hex_or_null(app.base_color if app else None)
    if base:
        asset.base_color = base
        asset.source["baseColor"] = "derived"

    secondary = _hex_list(getattr(app, "secondary_colors", None) if app else None)
    if secondary:
        asset.secondary_colors = secondary
        asset.source["secondaryColors"] = "derived"

    fur_colors = _hex_list(getattr(fur, "colors", None) if fur else None)
    if fur_colors:
        asset.fur_colors = fur_colors
        asset.source["furColors"] = "derived"

    fur_patterns = getattr(fur, "patterns", None) if fur else None
    if isinstance(fur_patterns, list):
        strings = [s for s in fur_patterns if isinstance(s, str)]
        if strings:
            asset.fur_patterns = strings[:8]
            asset.source["furPatterns"] = "derived"

    return asset


def apply_asset_patch(current: CharacterAsset, patch: dict) -> CharacterAsset:
    """Merge a user-confirmed assetPatch into a CharacterAsset.

    Every field present in the patch is clamped and marked source 'observed'.
    """
    next_asset = CharacterAsset(**current.model_dump())
    next_asset.source = dict(current.source)

    palette = _hex_list(patch.get("palette"))
    if palette:
        next_asset.palette = palette
        next_asset.source["palette"] = "observed"
    base = _hex_or_null(patch.get("baseColor"))
    if base:
        next_asset.base_color = base
        next_asset.source["baseColor"] = "observed"
    secondary = _hex_list(patch.get("secondaryColors"))
    if secondary:
        next_asset.secondary_colors = secondary
        next_asset.source["secondaryColors"] = "observed"
    fur_colors = _hex_list(patch.get("furColors"))
    if fur_colors:
        next_asset.fur_colors = fur_colors
        next_asset.source["furColors"] = "observed"
    fur_patterns = patch.get("furPatterns")
    if isinstance(fur_patterns, list):
        strings = [s for s in fur_patterns if isinstance(s, str)]
        if strings:
            next_asset.fur_patterns = strings[:8]
            next_asset.source["furPatterns"] = "observed"
    hair = _hex_or_null(patch.get("hairColor"))
    if hair:
        next_asset.hair_color = hair
        next_asset.source["hairColor"] = "observed"
    eye = _hex_or_null(patch.get("eyeColor"))
    if eye:
        next_asset.eye_color = eye
        next_asset.source["eyeColor"] = "observed"
    skin = _hex_or_null(patch.get("skinColor"))
    if skin:
        next_asset.skin_color = skin
        next_asset.source["skinColor"] = "observed"
    outfit = _hex_list(patch.get("outfitColors"))
    if outfit:
        next_asset.outfit_colors = outfit
        next_asset.source["outfitColors"] = "observed"
    back = _str_or_null(patch.get("backPattern"))
    if back:
        next_asset.back_pattern = back
        next_asset.source["backPattern"] = "observed"

    return next_asset
