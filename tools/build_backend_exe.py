#!/usr/bin/env python
"""Build the packaged backend executable (Phase 3-5C).

Usage (from repo root):
    python tools/build_backend_exe.py

Requires PyInstaller (build tool only, not a runtime dependency):
    python -m pip install pyinstaller

Produces:
    dist/backend/backend.exe   (PyInstaller onefile)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "tools" / "backend_entry.py"
WORKDIR = ROOT / "dist" / "_pyinstaller"
DIST = ROOT / "dist" / "backend"

HIDDEN = [
    # uvicorn picks up protocol/loop implementations dynamically.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--name",
        "backend",
        "--distpath",
        str(DIST),
        "--workpath",
        str(WORKDIR),
        "--specpath",
        str(WORKDIR),
    ]
    for h in HIDDEN:
        cmd += ["--hidden-import", h]
    cmd.append(str(ENTRY))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    sys.exit(main())
