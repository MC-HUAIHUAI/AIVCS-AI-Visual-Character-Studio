"""Real NVIDIA GPU gate (Phase 3-I).

These tests are the Phase 4 REAL GPU POC placeholders: they assert actual CUDA
inference works. They are SKIPPED by default on this build machine (no NVIDIA
GPU / no CUDA / no weights / Device Guard) and only run with
AIVCS_ALLOW_REAL_GPU=1 on a real NVIDIA Windows machine. They never fake a pass.
"""

from __future__ import annotations

import sys
import unittest

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))))

from backend.app.services import ai3d_runtime_manager as rm  # noqa: E402
from backend.tests.hw_required import requires_real_gpu  # noqa: E402


@requires_real_gpu
class RealGpuInferenceTest(unittest.TestCase):
    def test_real_gpu_present(self):
        hw = rm.detect_hardware()
        self.assertEqual(hw.gpu_vendor, "nvidia")
        self.assertIsNotNone(hw.vram_mb)
        self.assertIn("cuda", hw.available_backends)

    def test_real_gpu_meets_hunyuan_vram(self):
        hw = rm.detect_hardware()
        self.assertGreaterEqual(hw.vram_mb or 0, 6144, "Hunyuan3D-2mini shape 需要 >=6GB VRAM")

    def test_real_gpu_meets_hunyuan_paint_vram(self):
        hw = rm.detect_hardware()
        self.assertGreaterEqual(hw.vram_mb or 0, 16384, "Hunyuan3D-2 Paint 官方 shape+texture 需 16GB")


if __name__ == "__main__":
    unittest.main()
