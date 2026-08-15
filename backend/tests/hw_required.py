"""Hardware-required test marker (Phase 3-I).

Real NVIDIA CUDA tests must be explicitly marked with `@requires_real_gpu` and
are SKIPPED by default on this build machine (no NVIDIA GPU, Device Guard, no
CUDA). They only run when the operator explicitly opts in via
`AIVCS_ALLOW_REAL_GPU=1` on a real NVIDIA Windows machine.

This is the honest convention: a real-GPU test is never "faked through" - it is
either genuinely skipped or genuinely run on capable hardware.
"""

from __future__ import annotations

import os
import unittest

REAL_GPU_ALLOWED = os.environ.get("AIVCS_ALLOW_REAL_GPU", "").strip().lower() in ("1", "true", "yes")

requires_real_gpu = unittest.skipUnless(
    REAL_GPU_ALLOWED,
    "需要 NVIDIA CUDA Windows 真机（设置 AIVCS_ALLOW_REAL_GPU=1 才运行）",
)
