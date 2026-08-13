"""Vision result normalization.

Safety boundary between "whatever a vision provider returns" and the
CharacterSpec patch the client is allowed to see. Unknown / illegal values are
clamped to the canonical enums or dropped - never guessed. This keeps the
boundary: raw AI output -> parse/validate -> mapper -> CrossViewResolver ->
spec patch. Per-view observations (perView[]) are normalized through the exact
same path as the unified patch - there is no second validation system.
"""

from __future__ import annotations

import re

from ..schemas.vision import ViewAnalysis, VisionAnalysisResponse, VisionSpecPatch

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

VIEWS = ("front", "side", "back", "custom")

CHARACTER_TYPES = {"human", "anime-human", "anthro", "animal", "fantasy-creature", "robot", "alien", "custom"}
CHARACTER_STYLES = {"stylized", "realistic", "anime", "pixel"}
CHARACTER_GENDERS = {"female", "male", "neutral"}
BODY_TYPES = {"humanoid", "biped-anthro", "quadruped", "bird", "dragon", "custom"}
SPECIES_KINDS = {"wolf", "fox", "cat", "dog", "bear", "rabbit", "deer", "dragon", "bird", "reptile", "aquatic", "insect", "custom"}
FUR_STYLES = {"none", "toon", "anime", "stylized", "realistic"}
FUR_LENGTHS = {"short", "medium", "long"}
TAIL_MODES = {"none", "single", "multiple"}
ANATOMY_BOOLS = {
    "hasHead",
    "hasFace",
    "hasTorso",
    "hasLimbs",
    "wings",
    "ears",
    "horns",
    "antlers",
    "snout",
    "muzzle",
    "beak",
    "paws",
    "claws",
    "hooves",
    "fins",
    "tentacles",
    "extraLimbs",
}


def _clamp(value, allowed):
    if isinstance(value, str) and value in allowed:
        return value
    return None


def _clamp_float(value, lo: float, hi: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return min(hi, max(lo, float(value)))
    return 0.0


def _clamp_int(value, lo: int, hi: int):
    if isinstance(value, int) and not isinstance(value, bool):
        return min(hi, max(lo, value))
    return None


def _str_list(value) -> list[str] | None:
    if isinstance(value, list):
        items = [s for s in value if isinstance(s, str)]
        return items or None
    return None


def _hex_list(value) -> list[str] | None:
    if isinstance(value, list):
        items = [s for s in value if isinstance(s, str) and _HEX_RE.match(s)]
        return items or None
    return None


def _bool_or_none(value):
    if isinstance(value, bool):
        return value
    return None


def _to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def _convert_keys(value):
    """Recursively convert provider-internal snake_case keys to camelCase."""
    if isinstance(value, dict):
        return {_to_camel(k): _convert_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_convert_keys(v) for v in value]
    return value


def normalize_spec_patch(raw_patch) -> dict:
    """Clamp/validate a raw spec patch into a safe camelCase dict.

    Reused for both the unified patch and every per-view patch.
    """
    patch = _convert_keys(raw_patch if isinstance(raw_patch, dict) else {})
    spec: dict = {}

    for key in ("name", "description", "userNotes"):
        value = patch.get(key)
        if isinstance(value, str) and value:
            spec[key] = value

    style = _clamp(patch.get("style"), CHARACTER_STYLES)
    if style:
        spec["style"] = style

    gender = _clamp(patch.get("gender"), CHARACTER_GENDERS)
    if gender:
        spec["gender"] = gender

    character_type = _clamp(patch.get("characterType"), CHARACTER_TYPES)
    if character_type:
        spec["characterType"] = character_type

    body_type = _clamp(patch.get("bodyType"), BODY_TYPES)
    if body_type:
        spec["bodyType"] = body_type

    height_cm = _clamp_int(patch.get("heightCm"), 50, 300)
    if height_cm is not None:
        spec["heightCm"] = height_cm

    species = patch.get("species")
    if isinstance(species, dict):
        species_patch = {}
        primary = _clamp(species.get("primary"), SPECIES_KINDS)
        if primary:
            species_patch["primary"] = primary
        secondary = _clamp(species.get("secondary"), SPECIES_KINDS)
        if secondary:
            species_patch["secondary"] = secondary
        label = species.get("label")
        if isinstance(label, str) and label:
            species_patch["label"] = label
        conf = species.get("confidence")
        if isinstance(conf, (int, float)) and not isinstance(conf, bool):
            species_patch["confidence"] = min(1.0, max(0.0, float(conf)))
        if species_patch:
            spec["species"] = species_patch

    anatomy = patch.get("anatomy")
    if isinstance(anatomy, dict):
        anatomy_patch = {}
        for key in ANATOMY_BOOLS:
            value = _bool_or_none(anatomy.get(key))
            if value is not None:
                anatomy_patch[key] = value
        tail = _clamp(anatomy.get("tail"), TAIL_MODES)
        if tail:
            anatomy_patch["tail"] = tail
        appendages = _str_list(anatomy.get("customAppendages"))
        if appendages is not None:
            anatomy_patch["customAppendages"] = appendages
        if anatomy_patch:
            spec["anatomy"] = anatomy_patch

    fur = patch.get("fur")
    if isinstance(fur, dict):
        fur_patch = {}
        enabled = _bool_or_none(fur.get("enabled"))
        if enabled is not None:
            fur_patch["enabled"] = enabled
        fur_style = _clamp(fur.get("style"), FUR_STYLES)
        if fur_style:
            fur_patch["style"] = fur_style
        fur_length = _clamp(fur.get("length"), FUR_LENGTHS)
        if fur_length:
            fur_patch["length"] = fur_length
        colors = _str_list(fur.get("colors"))
        if colors is not None:
            fur_patch["colors"] = colors
        patterns = _str_list(fur.get("patterns"))
        if patterns is not None:
            fur_patch["patterns"] = patterns
        if fur_patch:
            spec["fur"] = fur_patch

    appearance = patch.get("appearance")
    if isinstance(appearance, dict):
        appearance_patch = {}
        base_color = appearance.get("baseColor")
        if isinstance(base_color, str) and _HEX_RE.match(base_color):
            appearance_patch["baseColor"] = base_color
        for key in ("secondaryColors", "patterns", "markings"):
            items = _str_list(appearance.get(key))
            if items is not None:
                appearance_patch[key] = items
        palette = _hex_list(appearance.get("palette"))
        if palette is not None:
            appearance_patch["palette"] = palette
        if appearance_patch:
            spec["appearance"] = appearance_patch

    vision_analysis = patch.get("visionAnalysis")
    if isinstance(vision_analysis, dict):
        va_provider = vision_analysis.get("providerId")
        va_source = _str_list(vision_analysis.get("sourceImageIds"))
        if isinstance(va_provider, str) and va_source is not None:
            spec["visionAnalysis"] = {
                "providerId": va_provider,
                "analyzedAt": vision_analysis.get("analyzedAt") if isinstance(vision_analysis.get("analyzedAt"), str) else None,
                "sourceImageIds": va_source,
                "confidence": _clamp_float(vision_analysis.get("confidence"), 0.0, 1.0),
            }

    return spec


def normalize_view(item) -> ViewAnalysis | None:
    """Normalize a single per-view observation into a validated ViewAnalysis.

    Returns None for non-dict entries, unknown views, or missing source ids so
    the caller can safely drop illegal items.
    """
    if not isinstance(item, dict):
        return None
    view = item.get("view")
    if view not in VIEWS:
        return None
    source = item.get("source_image_id") or item.get("sourceImageId")
    if not isinstance(source, str) or not source:
        return None
    patch = normalize_spec_patch(item.get("spec_patch") or item.get("specPatch") or {})
    confidence = _clamp_float(item.get("confidence"), 0.0, 1.0)
    notes = _str_list(item.get("notes")) or []
    warnings = _str_list(item.get("warnings")) or []
    return ViewAnalysis(
        view=view,
        sourceImageId=source,
        specPatch=patch,
        confidence=confidence,
        notes=notes,
        warnings=warnings,
    )


def validate_spec_patch_dict(unified: dict) -> VisionSpecPatch:
    """Re-validate a CrossViewResolver unified patch into the response model."""
    return VisionSpecPatch.model_validate(unified)


def normalize(provider_result: dict) -> VisionAnalysisResponse:
    raw = provider_result or {}
    spec_patch = normalize_spec_patch(raw.get("spec_patch") or {})
    notes = _str_list(raw.get("notes")) or []
    warnings = _str_list(raw.get("warnings")) or []
    confidence = _clamp_float(raw.get("confidence"), 0.0, 1.0)
    source_ids = _str_list(raw.get("source_image_ids")) or []
    provider_id = raw.get("provider_id") if isinstance(raw.get("provider_id"), str) else "mock"

    per_view = None
    raw_per_view = raw.get("per_view")
    if isinstance(raw_per_view, list):
        items = [normalize_view(item) for item in raw_per_view]
        items = [item for item in items if item is not None]
        if items:
            per_view = items

    return VisionAnalysisResponse(
        specPatch=spec_patch,
        confidence=confidence,
        notes=notes,
        warnings=warnings,
        sourceImageIds=source_ids,
        providerId=provider_id,
        perView=per_view,
    )
