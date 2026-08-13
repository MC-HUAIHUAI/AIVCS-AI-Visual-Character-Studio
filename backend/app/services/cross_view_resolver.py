"""Cross-view consistency resolver (Phase 2.2-A).

Deterministic, LLM-free, network-free merge of per-view vision observations
into a single unified CharacterSpec patch plus a conflict report.

Ownership rule: vision providers only produce per-view observations
(perView[]). This resolver is the ONLY place that decides final unified values
and detects conflicts. Any conflicts[] the model claims are ignored/recomputed
here. Inputs must already be normalized ViewAnalysis objects.

Rules:
  A. Field absent in all views     -> not present in unifiedPatch.
  B. Field present in one view     -> taken as-is, no conflict.
  C. Same value from >=2 views     -> taken, source = highest-confidence view.
  D. Different values from >=2 views -> conflict; unified value defaults to the
                                       highest-confidence candidate (but the
                                       conflict is still reported).

Missing field semantics: a field absent from a view means "not observed", NOT
"false". Only an explicit boolean value counts as true/false.
"""

from __future__ import annotations

from typing import Any

from ..schemas.vision import ViewAnalysis, ViewConflict, ViewConflictCandidate

_MISSING = object()

# Explicit numeric tolerance (kept as a constant on purpose - tested).
HEIGHT_TOLERANCE_CM = 10

TOP_ENUMS = ("characterType", "style", "gender", "bodyType")

ANATOMY_BOOLS = (
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
)

# Field path (tuple) -> conflict kind.
MANAGED_FIELDS: dict[tuple[str, ...], str] = {
    ("characterType",): "enum",
    ("style",): "enum",
    ("gender",): "enum",
    ("bodyType",): "enum",
    ("species", "primary"): "enum",
    ("heightCm",): "number",
    ("anatomy", "tail"): "enum",
    ("fur", "enabled"): "bool",
    ("fur", "style"): "enum",
    ("fur", "length"): "enum",
    ("appearance", "baseColor"): "enum",
}
for _key in ANATOMY_BOOLS:
    MANAGED_FIELDS[("anatomy", _key)] = "bool"

# Pass-through paths copied from whichever view provides them (single-source).
PASS_THROUGH_TOP = (("name",), ("description",), ("userNotes",))
PASS_THROUGH_PATHS = (
    ("species", "secondary"),
    ("species", "label"),
    ("species", "confidence"),
    ("fur", "colors"),
    ("fur", "patterns"),
    ("appearance", "secondaryColors"),
    ("appearance", "patterns"),
    ("appearance", "markings"),
    ("appearance", "palette"),
)

FIELD_LABELS: dict[str, str] = {
    "characterType": "角色类型",
    "style": "风格",
    "gender": "性别",
    "bodyType": "体型",
    "species.primary": "物种",
    "heightCm": "身高",
    "anatomy.tail": "尾巴",
    "fur.enabled": "毛发（启用）",
    "fur.style": "毛发风格",
    "fur.length": "毛发长度",
    "appearance.baseColor": "主色",
    "anatomy.hasHead": "头部",
    "anatomy.hasFace": "面部",
    "anatomy.hasTorso": "躯干",
    "anatomy.hasLimbs": "四肢",
    "anatomy.wings": "翼",
    "anatomy.ears": "耳",
    "anatomy.horns": "角",
    "anatomy.antlers": "鹿角",
    "anatomy.snout": "口鼻",
    "anatomy.muzzle": "吻部",
    "anatomy.beak": "喙",
    "anatomy.paws": "爪掌",
    "anatomy.claws": "利爪",
    "anatomy.hooves": "蹄",
    "anatomy.fins": "鳍",
    "anatomy.tentacles": "触手",
    "anatomy.extraLimbs": "额外肢体",
}


def _dot(path: tuple[str, ...]) -> str:
    return ".".join(path)


def _get(patch: dict, path: tuple[str, ...]) -> Any:
    cur = patch
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return _MISSING
        cur = cur[key]
    return cur


def _set(target: dict, path: tuple[str, ...], value: Any) -> None:
    cur = target
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


def _distinct(values: list) -> set:
    out: set = set()
    for v in values:
        if isinstance(v, (str, bool, int)):
            out.add(v)
    return out


def _winner(cands):
    """Deterministic winner: highest confidence, then earliest view index."""
    return max(cands, key=lambda c: (c[2], -c[3]))


def resolve_cross_view(per_views: list[ViewAnalysis]) -> dict:
    """Merge normalized per-view analyses into {unifiedPatch, conflicts}.

    Deterministic: identical input always yields identical output. Never
    mutates the inputs, never calls LLMs, never touches the network, and never
    modifies the CharacterSpec itself.
    """
    unified: dict = {}
    conflicts: list[ViewConflict] = []

    if not per_views:
        return {"unifiedPatch": unified, "conflicts": conflicts}

    entries = []
    for idx, va in enumerate(per_views):
        patch = va.spec_patch if isinstance(va.spec_patch, dict) else {}
        entries.append((va, idx, patch))

    # 1) Managed fields (conflict detection).
    for path, kind in MANAGED_FIELDS.items():
        cands = []
        for va, idx, patch in entries:
            value = _get(patch, path)
            if value is _MISSING:
                continue
            cands.append((value, va.view, float(va.confidence), idx))
        if not cands:
            continue

        best = _winner(cands)

        conflicted = False
        if kind == "number":
            values = [c[0] for c in cands if isinstance(c[0], (int, float)) and not isinstance(c[0], bool)]
            if len(set(values)) > 1 and (max(values) - min(values)) > HEIGHT_TOLERANCE_CM:
                conflicted = True
        elif len(_distinct([c[0] for c in cands])) >= 2:
            conflicted = True

        _set(unified, path, best[0])

        if conflicted:
            ordered = sorted(cands, key=lambda c: (-c[2], c[3]))
            candidates = [
                ViewConflictCandidate(value=c[0], view=c[1], confidence=c[2]) for c in ordered
            ]
            conflicts.append(
                ViewConflict(
                    field=_dot(path),
                    fieldLabel=FIELD_LABELS.get(_dot(path), _dot(path)),
                    candidates=candidates,
                    resolvedTo=ViewConflictCandidate(value=best[0], view=best[1], confidence=best[2]),
                )
            )

    # 2) Pass-through fields (single-source, no conflict).
    for path in PASS_THROUGH_TOP + PASS_THROUGH_PATHS:
        providers = [(va, idx, patch) for va, idx, patch in entries if _get(patch, path) is not _MISSING]
        if not providers:
            continue
        va, _idx, patch = max(providers, key=lambda p: (float(p[0].confidence), -p[1]))
        _set(unified, path, _get(patch, path))

    return {"unifiedPatch": unified, "conflicts": conflicts}
