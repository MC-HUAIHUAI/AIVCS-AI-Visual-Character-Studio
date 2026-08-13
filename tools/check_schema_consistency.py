#!/usr/bin/env python3
"""AIVCS schema consistency check (TS <-> Python).

Verifies that the CharacterSpec family of models and the Phase 2.1 Vision
schemas agree between src/shared/types.ts (+ renderer provider types) and the
FastAPI Pydantic models. Pure standard library - no third-party deps.

Usage:
    python tools/check_schema_consistency.py
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TS_FILES = [
    os.path.join(ROOT, "src", "shared", "types.ts"),
    os.path.join(ROOT, "src", "renderer", "src", "core", "providers", "visionProvider.ts"),
]

# (ts model name, python import path, python model name)
MODEL_PAIRS = [
    ("CharacterSpec", "backend.app.schemas.character", "CharacterSpec"),
    ("SpeciesInfo", "backend.app.schemas.character", "SpeciesInfo"),
    ("FurProfile", "backend.app.schemas.character", "FurProfile"),
    ("AppearanceProfile", "backend.app.schemas.character", "AppearanceProfile"),
    ("AnatomyGraph", "backend.app.schemas.character", "AnatomyGraph"),
    ("VisionImageInput", "backend.app.schemas.vision", "VisionImageInput"),
    ("VisionAnalysisResult", "backend.app.schemas.vision", "VisionAnalysisResponse"),
    ("VisionAnalysisMeta", "backend.app.schemas.vision", "VisionAnalysisMeta"),
    ("VisionPerViewMeta", "backend.app.schemas.vision", "VisionPerViewMeta"),
    ("ViewAnalysis", "backend.app.schemas.vision", "ViewAnalysis"),
    ("ViewConflict", "backend.app.schemas.vision", "ViewConflict"),
]


def ts_fields(model: str) -> set[str]:
    for path in TS_FILES:
        text = open(path, encoding="utf-8").read()
        match = re.search(rf"export interface {model}\s*\{{(.*?)\n\}}", text, re.S)
        if match:
            body = match.group(1)
            fields = set(re.findall(r"\n\s*([A-Za-z_][A-Za-z0-9_]*)\s*[?:]", body))
            return fields
    return set()


def py_fields(import_path: str, model: str) -> set[str]:
    import importlib

    mod = importlib.import_module(import_path)
    cls = getattr(mod, model)
    return {field.alias or name for name, field in cls.model_fields.items()}


def main() -> int:
    failures = 0
    for ts_name, py_path, py_name in MODEL_PAIRS:
        ts = ts_fields(ts_name)
        py = py_fields(py_path, py_name)
        only_ts = ts - py
        only_py = py - ts
        status = "OK"
        if only_ts or only_py:
            failures += 1
            status = "MISMATCH"
        print(f"[{status}] {ts_name} <-> {py_name}")
        if only_ts:
            print(f"   only in TS: {sorted(only_ts)}")
        if only_py:
            print(f"   only in Python: {sorted(only_py)}")
    if failures:
        print(f"\nFAILED: {failures} model(s) out of sync")
        return 1
    print("\nAll models are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
