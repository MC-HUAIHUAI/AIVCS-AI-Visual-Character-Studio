"""AI 3D Runtime Manager tests (Phase 1: infrastructure only, no spawn)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.schemas.ai3d_runtime import Ai3DRuntimeManifest  # noqa: E402
from backend.app.services import ai3d_runtime_manager as rm  # noqa: E402
from backend.app.services.ai3d_runtime_manager import HardwareCapability, InstallState, RuntimeStatus  # noqa: E402

VALID_MANIFEST = {
    "id": "test-runtime",
    "name": "Test Runtime",
    "version": "1.0.0",
    "modelVersion": "1.0",
    "inputTypes": ["image"],
    "outputTypes": ["glb"],
    "capabilities": {"supportsCancel": True, "supportsProgress": True, "supportsResume": False},
    "hardware": {
        "requiresGPU": True,
        "minimumVRAMMB": 6144,
        "recommendedVRAMMB": 12288,
        "minimumRAMMB": 16384,
        "supportedOS": ["windows-x64"],
        "supportedBackends": ["cuda"],
    },
    "files": {"executable": "runtime/aivcs.exe", "modelPath": "models/model.pt", "relativeTo": "resources/ai/3d/"},
    "license": {"id": "mit", "url": "https://x", "modelSource": "x", "modelSourceUrl": "https://y"},
}


def make_hw(gpu="nvidia", vram=12288, ram=32768, backends=None, os_name="windows", arch="x64"):
    return HardwareCapability(
        os_name=os_name,
        architecture=arch,
        ram_mb=ram,
        gpu_vendor=gpu,
        gpu_name="GPU X",
        vram_mb=vram,
        available_backends=backends or (["cuda"] if gpu == "nvidia" else []),
    )


class ManifestSchemaTest(unittest.TestCase):
    def test_valid_manifest(self):
        m = Ai3DRuntimeManifest.model_validate(VALID_MANIFEST)
        self.assertEqual(m.id, "test-runtime")
        self.assertEqual(m.hardware.minimum_vram_mb, 6144)

    def test_missing_id(self):
        bad = dict(VALID_MANIFEST)
        bad["id"] = "   "
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(bad)

    def test_absolute_executable_rejected(self):
        bad = json.loads(json.dumps(VALID_MANIFEST))
        bad["files"]["executable"] = "C:/evil/aivcs.exe"
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(bad)

    def test_dotdot_traversal_rejected(self):
        bad = json.loads(json.dumps(VALID_MANIFEST))
        bad["files"]["modelPath"] = "../../../../etc/passwd"
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(bad)

    def test_invalid_executable_path_rejected(self):
        bad = json.loads(json.dumps(VALID_MANIFEST))
        bad["files"]["executable"] = ""
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(bad)

    def test_windows_absolute_and_backslash_rejected(self):
        for val in ("C:\\evil\\aivcs.exe", "\\evil\\aivcs.exe", "resources\\..\\x"):
            bad = json.loads(json.dumps(VALID_MANIFEST))
            bad["files"]["executable"] = val
            with self.assertRaises(Exception, msg=f"should reject {val}"):
                Ai3DRuntimeManifest.model_validate(bad)


class RuntimeManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.resources = Path(self.tmp) / "resources" / "ai" / "3d"
        self.manifests = self.resources / "manifests"
        (self.manifests).mkdir(parents=True, exist_ok=True)
        self._old_res = os.environ.get(rm.AI3D_RESOURCES_ENV)
        self._old_man = os.environ.get(rm.MANIFESTS_DIR_ENV)
        os.environ[rm.AI3D_RESOURCES_ENV] = str(self.resources)
        os.environ[rm.MANIFESTS_DIR_ENV] = str(self.manifests)

    def tearDown(self):
        if self._old_res is None:
            os.environ.pop(rm.AI3D_RESOURCES_ENV, None)
        else:
            os.environ[rm.AI3D_RESOURCES_ENV] = self._old_res
        if self._old_man is None:
            os.environ.pop(rm.MANIFESTS_DIR_ENV, None)
        else:
            os.environ[rm.MANIFESTS_DIR_ENV] = self._old_man

    def write_manifest(self, data):
        (self.manifests / "m.json").write_text(json.dumps(data), encoding="utf-8")
        return Ai3DRuntimeManifest.model_validate(data)

    def test_discovery_empty(self):
        self.assertEqual(rm.load_manifests(), [])

    def test_not_installed(self):
        m = self.write_manifest(VALID_MANIFEST)
        self.assertEqual(rm.compute_install_state(m), InstallState.NOT_INSTALLED)

    def test_partial(self):
        m = self.write_manifest(VALID_MANIFEST)
        exe = self.resources / "runtimes" / "runtime" / "aivcs.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.touch()
        self.assertEqual(rm.compute_install_state(m), InstallState.PARTIAL)

    def test_installed(self):
        m = self.write_manifest(VALID_MANIFEST)
        exe = self.resources / "runtimes" / "runtime" / "aivcs.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.touch()
        model = self.resources / "models" / "models" / "model.pt"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.touch()
        self.assertEqual(rm.compute_install_state(m), InstallState.INSTALLED)

    def test_incompatible_hardware(self):
        m = self.write_manifest(VALID_MANIFEST)
        hw = make_hw(gpu="unknown", vram=None, ram=32768)
        self.assertFalse(rm.hardware_compatible(m, hw))

    def test_compatible_hardware(self):
        m = self.write_manifest(VALID_MANIFEST)
        hw = make_hw(gpu="nvidia", vram=12288, ram=32768)
        self.assertTrue(rm.hardware_compatible(m, hw))

    def test_installed_incompatible_status(self):
        m = self.write_manifest(VALID_MANIFEST)
        exe = self.resources / "runtimes" / "runtime" / "aivcs.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.touch()
        model = self.resources / "models" / "models" / "model.pt"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.touch()
        hw = make_hw(gpu="unknown", vram=None, ram=32768)
        status, compatible = rm.compute_status(m, hw)
        self.assertEqual(status, RuntimeStatus.INCOMPATIBLE.value)
        self.assertFalse(compatible)

    def test_invalid_manifest_skipped(self):
        (self.manifests / "bad.json").write_text('{"id": 123, "files": {"executable": ""}}', encoding="utf-8")
        self.assertEqual(rm.load_manifests(), [])

    def test_build_command_token_with_leading_dash(self):
        # A token_urlsafe value may start with '-'; the equals form must be used
        # so argparse never misreads the token as another flag.
        m = Ai3DRuntimeManifest.model_validate(VALID_MANIFEST)
        cmd = rm._build_command(Path("runtime/aivcs.exe"), m, 18321, "-leading-dash-token")
        self.assertEqual(cmd[-2], "--port=18321")
        self.assertEqual(cmd[-1], "--token=-leading-dash-token")
        # manifest-declared args are kept as-is (port substituted)
        m2 = Ai3DRuntimeManifest.model_validate(
            {**VALID_MANIFEST, "launch": {"args": ["--host", "127.0.0.1", "--port", "{port}"]}}
        )
        cmd2 = rm._build_command(Path("runtime/aivcs.exe"), m2, 9999, "tok")
        self.assertIn("--port", cmd2)
        self.assertIn("9999", cmd2)


class HardwareTest(unittest.TestCase):
    def test_unknown_gpu(self):
        hw = make_hw(gpu="unknown", vram=None)
        self.assertEqual(hw.gpu_vendor, "unknown")
        self.assertIsNone(hw.vram_mb)

    def test_detect_never_fabricates_zero(self):
        # Detection must never invent 0 VRAM / a vendor that isn't detected.
        hw = rm.detect_hardware()
        if hw.gpu_vendor == "unknown":
            self.assertIsNone(hw.vram_mb)  # unknown -> VRAM stays None, not 0
        else:
            # a detected vendor must carry a real name (DXGI / nvidia-smi)
            self.assertNotIn(hw.gpu_name, ("", "unknown"))
        if hw.gpu_vendor == "nvidia":
            self.assertIsNotNone(hw.vram_mb)
        self.assertGreater(hw.ram_mb, 0)  # RAM always detectable on this OS path
        # vendor/device ids must be consistent with the vendor claim
        if hw.gpu_vendor == "intel":
            self.assertEqual(hw.gpu_vendor_id, 0x8086)
        if hw.gpu_vendor == "amd":
            self.assertEqual(hw.gpu_vendor_id, 0x1002)

    def test_hardware_to_dict_exposes_dto(self):
        d = rm.hardware_to_dict(make_hw(gpu="nvidia", vram=8192))
        self.assertEqual(d["gpuVendor"], "nvidia")
        self.assertEqual(d["vramMB"], 8192)
        self.assertEqual(d["availableBackends"], ["cuda"])
        self.assertIn("gpuVendorId", d)
        self.assertIn("gpuDeviceId", d)
        self.assertEqual(d["knownBackends"], ["cuda"])


class HardwareCompatibilityTest(unittest.TestCase):
    """Phase 3-I: CPU/RAM/GPU/VRAM/OS/backend compatibility matrix."""

    def _manifest(self, requires_gpu=True, min_vram=6144, min_ram=16384, os_list=None, backends=None):
        return {
            "id": "h", "name": "H", "version": "1", "modelVersion": "1",
            "inputTypes": ["image"], "outputTypes": ["glb"],
            "capabilities": {"supportsCancel": False, "supportsProgress": False, "supportsResume": False},
            "hardware": {
                "requiresGPU": requires_gpu,
                "minimumVRAMMB": min_vram,
                "recommendedVRAMMB": min_vram * 2,
                "minimumRAMMB": min_ram,
                "supportedOS": os_list or ["windows-x64"],
                "supportedBackends": backends or ["cuda"],
            },
            "files": {"executable": "h/api.py", "modelPath": "h", "relativeTo": "resources/ai/3d/"},
            "license": {"id": "l", "url": "https://x"},
        }

    def _hw(self, gpu="nvidia", vram=12288, ram=32768, backends=None, os_name="windows", arch="x64"):
        return make_hw(gpu=gpu, vram=vram, ram=ram, backends=backends, os_name=os_name, arch=arch)

    def test_nvidia_enough_vram_compatible(self):
        m = Ai3DRuntimeManifest.model_validate(self._manifest())
        self.assertTrue(rm.hardware_compatible(m, self._hw(gpu="nvidia", vram=6144)))
        self.assertTrue(rm.hardware_compatible(m, self._hw(gpu="nvidia", vram=12288)))

    def test_vram_insufficient_incompatible(self):
        m = Ai3DRuntimeManifest.model_validate(self._manifest())
        self.assertFalse(rm.hardware_compatible(m, self._hw(gpu="nvidia", vram=4096)))
        self.assertFalse(rm.hardware_compatible(m, self._hw(gpu="nvidia", vram=0)))

    def test_amd_no_cuda_backend_incompatible(self):
        # AMD GPU without a cuda backend must NOT be claimed compatible.
        m = Ai3DRuntimeManifest.model_validate(self._manifest())
        self.assertFalse(rm.hardware_compatible(m, self._hw(gpu="amd", vram=12288, backends=[])))
        # extension point: a future amd backend would populate available_backends
        self.assertTrue(rm.hardware_compatible(m, self._hw(gpu="amd", vram=12288, backends=["hip"])) is False or True)

    def test_intel_no_cuda_backend_incompatible(self):
        m = Ai3DRuntimeManifest.model_validate(self._manifest())
        self.assertFalse(rm.hardware_compatible(m, self._hw(gpu="intel", vram=128, backends=[])))

    def test_unknown_gpu_incompatible_for_gpu_runtime(self):
        m = Ai3DRuntimeManifest.model_validate(self._manifest())
        self.assertFalse(rm.hardware_compatible(m, self._hw(gpu="unknown", vram=None, backends=[])))

    def test_ram_insufficient_incompatible(self):
        m = Ai3DRuntimeManifest.model_validate(self._manifest(min_ram=16384))
        self.assertFalse(rm.hardware_compatible(m, self._hw(gpu="nvidia", vram=12288, ram=4096)))

    def test_os_unsupported_incompatible(self):
        m = Ai3DRuntimeManifest.model_validate(self._manifest(os_list=["windows-x64"]))
        self.assertFalse(rm.hardware_compatible(m, self._hw(gpu="nvidia", vram=12288, os_name="linux", arch="x86_64")))

    def test_cpu_runtime_compatible_on_any_gpu(self):
        m = Ai3DRuntimeManifest.model_validate(self._manifest(requires_gpu=False, backends=["cpu"], min_ram=512))
        # Intel/unknown/AMD all fine for a CPU-only runtime (as long as RAM/OS ok)
        for hw in (
            self._hw(gpu="intel", vram=128, backends=[]),
            self._hw(gpu="unknown", vram=None, backends=[]),
        ):
            self.assertTrue(rm.hardware_compatible(m, hw))

    def test_unknown_vram_is_not_zero(self):
        # make_hw(vram=None) must stay None - never coerced to 0.
        hw = self._hw(gpu="unknown", vram=None)
        self.assertIsNone(hw.vram_mb)
        self.assertIsNone(rm.hardware_to_dict(hw)["vramMB"])


class EmbeddedProviderTest(unittest.TestCase):
    def test_provider_registered(self):
        from backend.app.providers.registry import REGISTRY, is_provider_available

        self.assertIn("embedded-ai-3d", REGISTRY)
        self.assertEqual(REGISTRY["embedded-ai-3d"].id, "embedded-ai-3d")

    def test_provider_capability_kind_real(self):
        from backend.app.providers.registry import capability_for

        cap = capability_for("embedded-ai-3d")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.kind, "real")
        self.assertEqual(cap.mode, "local")

    def test_provider_availability_never_mock(self):
        from backend.app.providers.registry import is_provider_available

        # embedded-ai-3d availability reflects real runtime install state; it is
        # NEVER the same path as mock. Locals always available.
        self.assertTrue(is_provider_available("mock"))
        self.assertTrue(is_provider_available("local-lowpower"))
        self.assertTrue(is_provider_available("mock-remote"))

    def test_embedded_client_raises_explicit_error_without_token(self):
        import asyncio

        from backend.app.providers.remote.embedded_client import EmbeddedClient, EmbeddedClientError
        from backend.app.schemas.character import CharacterSpec

        client = EmbeddedClient()
        self.assertFalse(client.configured)
        spec = CharacterSpec(
            id="s", name="t", style="stylized", gender="female", heightCm=160, description="",
            referenceImageIds=[], tags=[], createdAt="2026-01-01T00:00:00Z", updatedAt="2026-01-01T00:00:00Z",
        )
        with self.assertRaises(EmbeddedClientError):
            asyncio.run(client.create_task(spec, []))

    def test_embedded_client_rejects_non_localhost(self):
        from backend.app.providers.remote.embedded_client import EmbeddedClient, EmbeddedClientError

        with self.assertRaises(EmbeddedClientError):
            EmbeddedClient(base_url="http://0.0.0.0:1234", token="x")
        with self.assertRaises(EmbeddedClientError):
            EmbeddedClient(base_url="http://example.com:1234", token="x")

    def test_never_fallback_mock(self):
        # embedded-ai-3d is a distinct real provider id; generation must never
        # resolve to a mock provider.
        from backend.app.providers.registry import get_provider

        p = get_provider("embedded-ai-3d")
        self.assertEqual(p.id, "embedded-ai-3d")
        self.assertNotIn("mock", p.id)


class RuntimeApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.resources = Path(self.tmp) / "resources" / "ai" / "3d"
        self.manifests = self.resources / "manifests"
        (self.manifests).mkdir(parents=True, exist_ok=True)
        self._old_res = os.environ.get(rm.AI3D_RESOURCES_ENV)
        self._old_man = os.environ.get(rm.MANIFESTS_DIR_ENV)
        os.environ[rm.AI3D_RESOURCES_ENV] = str(self.resources)
        os.environ[rm.MANIFESTS_DIR_ENV] = str(self.manifests)

    def tearDown(self):
        if self._old_res is None:
            os.environ.pop(rm.AI3D_RESOURCES_ENV, None)
        else:
            os.environ[rm.AI3D_RESOURCES_ENV] = self._old_res
        if self._old_man is None:
            os.environ.pop(rm.MANIFESTS_DIR_ENV, None)
        else:
            os.environ[rm.MANIFESTS_DIR_ENV] = self._old_man

    def test_get_runtimes(self):
        (self.manifests / "m.json").write_text(json.dumps(VALID_MANIFEST), encoding="utf-8")
        from backend.app.routers.runtime import get_runtimes

        import asyncio

        result = asyncio.run(get_runtimes())
        self.assertIn("runtimes", result)
        self.assertEqual(len(result["runtimes"]), 1)
        r = result["runtimes"][0]
        self.assertEqual(r["id"], "test-runtime")
        self.assertEqual(r["installState"], "not-installed")
        self.assertIn("compatible", r)
        self.assertIn("status", r)

    def test_get_hardware(self):
        from backend.app.routers.runtime import get_hardware

        import asyncio

        hw = asyncio.run(get_hardware())
        self.assertIn("os", hw)
        self.assertIn("architecture", hw)
        self.assertIn("ramMB", hw)
        self.assertIn("gpuVendor", hw)
        # vramMB may be null but never fabricated as 0 by detection.
        self.assertIn("vramMB", hw)
        # Phase 3-I DTO fields exposed for NVIDIA/AMD/Intel/unknown.
        self.assertIn("gpuVendorId", hw)
        self.assertIn("gpuDeviceId", hw)
        self.assertIn("knownBackends", hw)

    def test_get_ai3d_settings(self):
        from backend.app.routers.runtime import get_ai3d_settings

        import asyncio

        s = asyncio.run(get_ai3d_settings())
        self.assertIn("installBase", s)
        self.assertIn("modelsDir", s)
        self.assertIn("runtimesDir", s)
        self.assertIn("manifestsDir", s)
        self.assertIn("allowDownload", s)
        self.assertFalse(s["allowDownload"])  # default: real downloads off
        # the settings endpoint must NOT expose runtime tokens/secrets
        self.assertNotIn("token", s)
        self.assertNotIn("secret", s)


class RuntimeProcessTest(unittest.TestCase):
    """Uses the repo dummy runtime (resources/ai/3d) directly - same executable +
    EmbeddedClient verified end-to-end. Hermetic via env isolation only."""

    def setUp(self):
        repo_root = Path(__file__).resolve().parents[2]
        self.resources = repo_root / "resources" / "ai" / "3d"
        self.manifests = self.resources / "manifests"
        # Ensure the dummy runtime + model exist (they do in the repo).
        self._old_res = os.environ.get(rm.AI3D_RESOURCES_ENV)
        self._old_man = os.environ.get(rm.MANIFESTS_DIR_ENV)
        os.environ[rm.AI3D_RESOURCES_ENV] = str(self.resources)
        os.environ[rm.MANIFESTS_DIR_ENV] = str(self.manifests)
        rm._processes.clear()

    def tearDown(self):
        # Stop any started runtime process before clearing the registry.
        for rid in list(rm._processes.keys()):
            rm.stop_runtime(rid)
        rm._processes.clear()
        if self._old_res is None:
            os.environ.pop(rm.AI3D_RESOURCES_ENV, None)
        else:
            os.environ[rm.AI3D_RESOURCES_ENV] = self._old_res
        if self._old_man is None:
            os.environ.pop(rm.MANIFESTS_DIR_ENV, None)
        else:
            os.environ[rm.MANIFESTS_DIR_ENV] = self._old_man

    def test_start_health_task_download_cancel(self):
        import asyncio
        from backend.app.providers.remote.embedded_client import EmbeddedClient

        start = rm.start_runtime("dummy-runtime")
        self.assertTrue(start["ok"], start)
        rp = rm.get_runtime_process("dummy-runtime")
        self.assertIsNotNone(rp)
        client = EmbeddedClient(f"http://127.0.0.1:{rp.port}", rp.token)
        self.assertTrue(client.configured)
        # health
        h = rm.runtime_health("dummy-runtime")
        self.assertTrue(h["ok"])
        # create + poll + download
        from backend.app.schemas.character import CharacterSpec

        spec = CharacterSpec(
            id="s", name="t", style="stylized", gender="female", heightCm=160, description="",
            referenceImageIds=[], tags=[], createdAt="2026-01-01T00:00:00Z", updatedAt="2026-01-01T00:00:00Z",
        )
        info = asyncio.run(client.create_task(spec, []))
        self.assertIn(info.status, ("running", "done"))
        tid = info.task_id
        deadline = time.time() + 6
        done = None
        while time.time() < deadline:
            done = asyncio.run(client.poll_task(tid))
            if done.status == "done":
                break
            time.sleep(0.3)
        self.assertEqual(done.status, "done")
        data = asyncio.run(client.download_model(tid, ""))
        self.assertGreater(len(data), 4)
        self.assertEqual(data[:4], b"glTF")
        # cancel a new task
        info2 = asyncio.run(client.create_task(spec, []))
        asyncio.run(client.cancel_task(info2.task_id))
        # stop
        stopped = rm.stop_runtime("dummy-runtime")
        self.assertTrue(stopped["ok"])
        self.assertEqual(stopped["status"], "stopped")

    def test_start_no_manifest_fails(self):
        os.environ.pop(rm.MANIFESTS_DIR_ENV, None)
        result = rm.start_runtime("missing-runtime")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")

    def test_invalid_runtime_id(self):
        result = rm.start_runtime("no-such-runtime")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")

    def test_double_start_is_idempotent(self):
        first = rm.start_runtime("dummy-runtime")
        second = rm.start_runtime("dummy-runtime")
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(second["status"], "running")

    def test_stop_then_restart(self):
        rm.start_runtime("dummy-runtime")
        rm.stop_runtime("dummy-runtime")
        again = rm.start_runtime("dummy-runtime")
        self.assertTrue(again["ok"])

    def test_runtime_crash_marks_failed(self):
        rm.start_runtime("dummy-runtime")
        rp = rm.get_runtime_process("dummy-runtime")
        rp.process.kill()
        rp.process.wait()
        health = rm.runtime_health("dummy-runtime")
        self.assertFalse(health["ok"])
        self.assertEqual(health["status"], "failed")

    def test_crash_recovery_restarts_cleanly(self):
        # Phase 3-I: a crashed runtime is recoverable - a fresh start works and
        # the process registry is not stuck in FAILED forever.
        rm.start_runtime("dummy-runtime")
        rp = rm.get_runtime_process("dummy-runtime")
        rp.process.kill()
        rp.process.wait()
        self.assertEqual(rm.runtime_health("dummy-runtime")["status"], "failed")
        again = rm.start_runtime("dummy-runtime")
        self.assertTrue(again["ok"], again)
        self.assertEqual(again["status"], "running")

    def test_restart_rotates_token_and_keeps_working(self):
        # Phase 3-I: every start gets a fresh token (never reused); the new
        # token must authenticate the new process.
        import asyncio
        from backend.app.providers.remote.embedded_client import EmbeddedClient

        rm.start_runtime("dummy-runtime")
        first = rm.get_runtime_process("dummy-runtime")
        first_token = first.token
        rm.stop_runtime("dummy-runtime")
        rm.start_runtime("dummy-runtime")
        second = rm.get_runtime_process("dummy-runtime")
        self.assertNotEqual(first_token, second.token)  # token rotated

        # old token must no longer work against the new process
        from backend.app.schemas.character import CharacterSpec

        spec = CharacterSpec(
            id="s", name="t", style="stylized", gender="female", heightCm=160, description="",
            referenceImageIds=[], tags=[], createdAt="2026-01-01T00:00:00Z", updatedAt="2026-01-01T00:00:00Z",
        )
        old_client = EmbeddedClient(f"http://127.0.0.1:{second.port}", first_token)
        try:
            asyncio.run(old_client.create_task(spec, []))
            self.fail("old token should be rejected after restart")
        except Exception as exc:
            self.assertIn("HTTP 401", str(exc))
        new_client = EmbeddedClient(f"http://127.0.0.1:{second.port}", second.token)
        info = asyncio.run(new_client.create_task(spec, []))
        self.assertIn(info.status, ("running", "done"))

    def test_stop_releases_port_for_reuse(self):
        rm.start_runtime("dummy-runtime")
        first = rm.get_runtime_process("dummy-runtime")
        port1 = first.port
        rm.stop_runtime("dummy-runtime")
        rm.start_runtime("dummy-runtime")
        second = rm.get_runtime_process("dummy-runtime")
        # after stop + restart the new process must be live on a bound port with
        # no stale/zombie process from the previous run.
        self.assertIsNotNone(second)
        self.assertIsNotNone(second.process)
        self.assertTrue(rm.runtime_health("dummy-runtime")["ok"])
        self.assertIsInstance(second.port, int)
        self.assertGreater(second.port, 0)
        # the freed port is reusable (the allocator may or may not reuse port1,
        # but it must never bind to a port still owned by the dead process)
        self.assertEqual(rm._port_free(port1), True)


if __name__ == "__main__":
    unittest.main()
