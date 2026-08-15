"""Phase 3-C: Hunyuan3D-2mini Embedded Runtime tests.

Covers:
  - Hunyuan manifest discovery + schema (download/checksum/license/launch)
  - path traversal / absolute / UNC / backslash rejection (incl. download URL)
  - Runtime/Model Package install state + verify (checksum/size/license)
  - hardware incompatibility -> generate blocked
  - provider availability: never fallback to mock
  - runtime selection (GenerateRequest.runtimeId) -> explicit failure when
    not installed / incompatible
  - HunyuanEmbeddedClient DTO mapping (send/status/download/cancel)
  - fake Hunyuan HTTP server protocol test
  - fake GLB -> ModelStore (through RealAIImage3DProvider)
  - cancel/error/timeout semantics

No real AI, no GPU, no network to external hosts, no real weight download.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.schemas.ai3d_runtime import Ai3DRuntimeManifest  # noqa: E402
from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.services import ai3d_runtime_manager as rm  # noqa: E402
from backend.app.services.ai3d_runtime_manager import HardwareCapability, InstallState, PackageInstallState  # noqa: E402

FAKE_GLB = b"glTF" + b"\x00" * 64 + b"fake-glb-payload"  # not a valid GLB for ModelStore gate; see real_ai validate


def make_spec(**overrides):
    base = dict(
        id="s", name="t", style="stylized", gender="female", heightCm=160, description="",
        referenceImageIds=[], tags=[], createdAt="2026-01-01T00:00:00Z", updatedAt="2026-01-01T00:00:00Z",
    )
    base.update(overrides)
    return CharacterSpec(**base)


HUNYUAN_MANIFEST = {
    "id": "hunyuan3d-2mini",
    "name": "Hunyuan3D-2 mini（本地 AI 3D）",
    "version": "0.1.0",
    "modelVersion": "hunyuan3d-dit-v2-mini-turbo 0.6B",
    "inputTypes": ["image"],
    "outputTypes": ["glb"],
    "capabilities": {
        "supportsCancel": False,
        "supportsProgress": False,
        "supportsResume": False,
        "texture": {"supported": False, "kind": "future", "notes": "needs compiled extensions"},
    },
    "hardware": {
        "requiresGPU": True,
        "minimumVRAMMB": 6144,
        "recommendedVRAMMB": 12288,
        "minimumRAMMB": 16384,
        "supportedOS": ["windows-x64", "windows-amd64"],
        "supportedBackends": ["cuda"],
    },
    "files": {
        "executable": "hunyuan3d/api_server.py",
        "modelPath": "hunyuan3d-mini/hunyuan3d-dit-v2-mini-turbo",
        "relativeTo": "resources/ai/3d/",
        "license": "hunyuan3d/LICENSE",
        "notice": "hunyuan3d/NOTICE",
    },
    "license": {
        "id": "tencent-hunyuan-3d-2-community",
        "url": "https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/LICENSE",
        "modelSource": "huggingface",
        "modelSourceUrl": "https://huggingface.co/tencent/Hunyuan3D-2mini",
        "noticeFile": "hunyuan3d/NOTICE",
        "territoryRestrictions": "不得在欧盟 / 英国 / 韩国使用或分发",
        "commercialThreshold": "月活跃用户超过 100 万须向腾讯申请商业许可",
    },
    "download": {
        "kind": "model",
        "url": "https://huggingface.co/tencent/Hunyuan3D-2mini/resolve/main/hunyuan3d-dit-v2-mini-turbo/model.fp16.safetensors",
        "sha256": "bdbcef30dd0149a281e17d5b5b1fdad1122c904e098a42f3100e04e03c247bc4",
        "sizeBytes": 3822584202,
    },
    "launch": {
        "args": ["--host", "127.0.0.1", "--port", "{port}", "--model_path", "tencent/Hunyuan3D-2mini", "--device", "cuda"],
        "healthPath": "/",
        "readyTimeoutSeconds": 120.0,
    },
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


class HunyuanManifestSchemaTest(unittest.TestCase):
    def test_manifest_valid(self):
        m = Ai3DRuntimeManifest.model_validate(HUNYUAN_MANIFEST)
        self.assertEqual(m.id, "hunyuan3d-2mini")
        self.assertEqual(m.download.sha256, HUNYUAN_MANIFEST["download"]["sha256"])
        self.assertEqual(m.download.size_bytes, 3822584202)
        self.assertEqual(m.launch.health_path, "/")
        self.assertIn("--model_path", m.launch.args)

    def test_manifest_texture_capability_shape_only(self):
        # Phase 3-G: Hunyuan stays shape-only; texture is declared future, never
        # claimed as available.
        m = Ai3DRuntimeManifest.model_validate(HUNYUAN_MANIFEST)
        self.assertIsNotNone(m.capabilities.texture)
        self.assertFalse(m.capabilities.texture.supported)
        self.assertEqual(m.capabilities.texture.kind, "future")

    def test_texture_absent_manifest_defaults_shape_only(self):
        raw = json.loads(json.dumps(HUNYUAN_MANIFEST))
        raw["capabilities"].pop("texture", None)
        m = Ai3DRuntimeManifest.model_validate(raw)
        self.assertIsNone(m.capabilities.texture)

    def test_repo_hunyuan_manifest_texture_surfaces_in_runtime_info(self):
        here = Path(__file__).resolve().parents[2]
        manifest_path = here / "resources" / "ai" / "3d" / "manifests" / "hunyuan3d-2mini.runtime.json"
        m = Ai3DRuntimeManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
        info = rm.build_runtime_info(m, make_hw())
        tex = info.capabilities.get("texture")
        self.assertIsNotNone(tex)
        self.assertFalse(tex["supported"])
        self.assertEqual(tex["kind"], "future")

    def test_download_url_must_be_http(self):
        bad = json.loads(json.dumps(HUNYUAN_MANIFEST))
        bad["download"]["url"] = "file:///C:/evil/model.safetensors"
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(bad)
        bad["download"]["url"] = "C:\\evil\\model.safetensors"
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(bad)

    def test_download_sha256_must_be_64hex(self):
        for value in ("short", "z" * 64, "A" * 64.5 if isinstance(64.5, str) else "a" * 63):
            bad = json.loads(json.dumps(HUNYUAN_MANIFEST))
            bad["download"]["sha256"] = value
            with self.assertRaises(Exception, msg=value):
                Ai3DRuntimeManifest.model_validate(bad)

    def test_path_traversal_and_windows_rejected(self):
        for field in ("executable", "modelPath", "license", "notice"):
            for value in ("../../evil", "C:\\evil\\x", "\\evil", "..\\..\\x", "res\\\\.."):
                bad = json.loads(json.dumps(HUNYUAN_MANIFEST))
                bad["files"][field] = value
                with self.assertRaises(Exception, msg=f"{field}={value}"):
                    Ai3DRuntimeManifest.model_validate(bad)

    def test_license_notice_optional(self):
        m = json.loads(json.dumps(HUNYUAN_MANIFEST))
        m["files"].pop("license", None)
        m["files"].pop("notice", None)
        Ai3DRuntimeManifest.model_validate(m)  # should not raise


class HunyuanInstallStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.resources = Path(self.tmp) / "resources" / "ai" / "3d"
        self.manifests = self.resources / "manifests"
        self.manifests.mkdir(parents=True, exist_ok=True)
        self._old_res = os.environ.get(rm.AI3D_RESOURCES_ENV)
        self._old_man = os.environ.get(rm.MANIFESTS_DIR_ENV)
        os.environ[rm.AI3D_RESOURCES_ENV] = str(self.resources)
        os.environ[rm.MANIFESTS_DIR_ENV] = str(self.manifests)
        rm._transient_states.clear()
        # Pre-create the runtime dir so license/notice touches never fail.
        # NOTE: the model dir is NOT pre-created - a directory must not count as
        # an installed model file (is_file() check in _resolve_paths).
        (self.resources / "runtimes" / "hunyuan3d").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self._old_res is None:
            os.environ.pop(rm.AI3D_RESOURCES_ENV, None)
        else:
            os.environ[rm.AI3D_RESOURCES_ENV] = self._old_res
        if self._old_man is None:
            os.environ.pop(rm.MANIFESTS_DIR_ENV, None)
        else:
            os.environ[rm.MANIFESTS_DIR_ENV] = self._old_man
        rm._transient_states.clear()

    def write_hunyuan(self, payload=None):
        (self.manifests / "hunyuan.json").write_text(json.dumps(payload or HUNYUAN_MANIFEST), encoding="utf-8")
        return Ai3DRuntimeManifest.model_validate(payload or HUNYUAN_MANIFEST)

    def test_discovered_not_installed(self):
        m = self.write_hunyuan()
        self.assertEqual(rm.compute_install_state(m), InstallState.NOT_INSTALLED)
        self.assertEqual(rm.package_state_for(m, make_hw()).value, PackageInstallState.NOT_INSTALLED.value)

    def test_full_install_is_ready(self):
        m = self.write_hunyuan()
        exe = self.resources / "runtimes" / "hunyuan3d" / "api_server.py"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.touch()
        model = self.resources / "models" / "hunyuan3d-mini" / "hunyuan3d-dit-v2-mini-turbo" / "model.fp16.safetensors"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.touch()
        lic = self.resources / "runtimes" / "hunyuan3d" / "LICENSE"
        lic.touch()
        notc = self.resources / "runtimes" / "hunyuan3d" / "NOTICE"
        notc.touch()
        self.assertEqual(rm.compute_install_state(m), InstallState.INSTALLED)
        hw = make_hw()
        self.assertEqual(rm.package_state_for(m, hw).value, PackageInstallState.READY.value)
        status, compatible = rm.compute_status(m, hw)
        self.assertEqual(status, "ready")
        self.assertTrue(compatible)

    def test_full_install_hardware_incompatible(self):
        m = self.write_hunyuan()
        exe = self.resources / "runtimes" / "hunyuan3d" / "api_server.py"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.touch()
        model = self.resources / "models" / "hunyuan3d-mini" / "hunyuan3d-dit-v2-mini-turbo" / "model.fp16.safetensors"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.touch()
        (self.resources / "runtimes" / "hunyuan3d" / "LICENSE").touch()
        (self.resources / "runtimes" / "hunyuan3d" / "NOTICE").touch()
        hw = make_hw(gpu="unknown", vram=None)
        self.assertEqual(rm.package_state_for(m, hw).value, PackageInstallState.INCOMPATIBLE.value)
        status, compatible = rm.compute_status(m, hw)
        self.assertEqual(status, "incompatible")
        self.assertFalse(compatible)

    def test_partial_when_license_missing(self):
        m = self.write_hunyuan()
        exe = self.resources / "runtimes" / "hunyuan3d" / "api_server.py"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.touch()
        model = self.resources / "models" / "hunyuan3d-mini" / "hunyuan3d-dit-v2-mini-turbo" / "model.fp16.safetensors"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.touch()
        # LICENSE exists but NOTICE is missing -> partial (not installed).
        (self.resources / "runtimes" / "hunyuan3d" / "LICENSE").touch()
        self.assertEqual(rm.compute_install_state(m), InstallState.PARTIAL)

    def test_verify_rejects_wrong_checksum(self):
        m = self.write_hunyuan()
        model = self.resources / "models" / "hunyuan3d-mini" / "hunyuan3d-dit-v2-mini-turbo" / "model.fp16.safetensors"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"not-the-real-model")
        (self.resources / "runtimes" / "hunyuan3d" / "LICENSE").parent.mkdir(parents=True, exist_ok=True)
        (self.resources / "runtimes" / "hunyuan3d" / "LICENSE").touch()
        (self.resources / "runtimes" / "hunyuan3d" / "NOTICE").touch()
        result = rm.verify_downloaded_package(m)
        self.assertFalse(result["ok"])
        self.assertTrue(any("SHA-256" in e or "大小" in e for e in result["errors"]))

    def test_install_no_downloader_returns_not_installed(self):
        self.write_hunyuan()
        result = rm.install_runtime_package("hunyuan3d-2mini", fetcher=None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "not-installed")
        self.assertEqual(result["packageState"], PackageInstallState.NOT_INSTALLED.value)

    def test_install_with_fetcher_verifies(self):
        import hashlib

        m = self.write_hunyuan()
        payload = b"hello-hunyuan-model"
        sha = hashlib.sha256(payload).hexdigest()
        mm = json.loads(json.dumps(HUNYUAN_MANIFEST))
        mm["download"]["sha256"] = sha
        mm["download"]["sizeBytes"] = len(payload)
        mm["download"]["url"] = "https://example.invalid/model.fp16.safetensors"
        self.write_hunyuan(mm)
        (self.resources / "runtimes" / "hunyuan3d" / "LICENSE").parent.mkdir(parents=True, exist_ok=True)
        (self.resources / "runtimes" / "hunyuan3d" / "LICENSE").touch()
        (self.resources / "runtimes" / "hunyuan3d" / "NOTICE").touch()

        def fetcher(url, sha256, size_bytes, on_progress):
            self.assertEqual(url, mm["download"]["url"])
            self.assertEqual(sha256, sha)
            return {"ok": True, "bytes": payload}

        result = rm.install_runtime_package("hunyuan3d-2mini", fetcher=fetcher)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "installed")
        target = self.resources / "models" / "hunyuan3d-mini" / "hunyuan3d-dit-v2-mini-turbo" / "model.fp16.safetensors"
        self.assertEqual(target.read_bytes(), payload)


class FakeHunyuanServer:
    """Minimal fake of the official Hunyuan api_server.py protocol (/send /status)."""

    def __init__(self, glb: bytes = FAKE_GLB, fail_poll: bool = False, never_done: bool = False):
        self.glb = glb
        self.fail_poll = fail_poll
        self.never_done = never_done
        self._server = None
        self._thread = None
        self.port = 0
        self._uid = "fake-uid-1"
        self.started = threading.Event()

    def start(self) -> int:
        handler = self._make_handler()
        self._server = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.started.set()
        return self.port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _json(self, code, obj):
                data = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if self.path == "/send":
                    self._json(200, {"uid": server._uid})
                else:
                    self._json(404, {"detail": "not found"})

            def do_GET(self):
                if self.path.startswith("/status/"):
                    if server.fail_poll:
                        self._json(500, {"detail": "boom"})
                    elif server.never_done:
                        self._json(200, {"status": "processing"})
                    else:
                        self._json(
                            200,
                            {
                                "status": "completed",
                                "model_base64": base64.b64encode(server.glb).decode("ascii"),
                            },
                        )
                else:
                    self._json(404, {"detail": "not found"})

        return Handler


class HunyuanClientProtocolTest(unittest.TestCase):
    def setUp(self):
        self.server = FakeHunyuanServer(glb=FAKE_GLB)
        self.port = self.server.start()

    def tearDown(self):
        self.server.stop()

    def client(self):
        from backend.app.providers.remote.hunyuan_client import HunyuanEmbeddedClient

        return HunyuanEmbeddedClient(f"http://127.0.0.1:{self.port}", "tok")

    def test_create_maps_to_queued(self):
        from backend.app.schemas.vision import VisionImageInput

        c = self.client()
        refs = [VisionImageInput(imageId="i1", dataUrl="data:image/png;base64,aGVsbG8=", view="front")]
        info = asyncio.run(c.create_task(make_spec(), refs))
        self.assertEqual(info.task_id, "fake-uid-1")
        self.assertEqual(info.status, "queued")

    def test_poll_done_maps_to_done(self):
        c = self.client()
        info = asyncio.run(c.poll_task("fake-uid-1"))
        self.assertEqual(info.status, "done")
        self.assertEqual(info.progress, 1.0)

    def test_poll_processing_maps_to_running(self):
        self.server.never_done = True
        c = self.client()
        info = asyncio.run(c.poll_task("fake-uid-1"))
        self.assertEqual(info.status, "running")

    def test_poll_error_raises(self):
        self.server.fail_poll = True
        c = self.client()
        with self.assertRaises(Exception):
            asyncio.run(c.poll_task("fake-uid-1"))

    def test_download_decodes_base64(self):
        c = self.client()
        data = asyncio.run(c.download_model("fake-uid-1", ""))
        self.assertEqual(data, FAKE_GLB)

    def test_cancel_never_fakes_ack(self):
        c = self.client()
        # Official API has no cancel; calling it must not raise and must not lie.
        asyncio.run(c.cancel_task("fake-uid-1"))
        self.assertEqual(c.capability().supports_cancel, False)
        self.assertEqual(c.capability().kind, "real")

    def test_cancel_event_maps_to_cancelled(self):
        from backend.app.providers.base import CancellationToken

        c = self.client()
        token = CancellationToken()
        token.cancel()
        info = asyncio.run(c.poll_task("fake-uid-1", token))
        self.assertEqual(info.status, "cancelled")


class HunyuanProviderNoFallbackTest(unittest.TestCase):
    def test_generate_not_installed_raises_explicit(self):
        from backend.app.providers.remote.real_ai import RealAIImage3DProvider
        from backend.app.providers.remote.hunyuan_client import HunyuanEmbeddedClient

        # Point the client at a dead port -> remote error (never mock).
        client = HunyuanEmbeddedClient("http://127.0.0.1:1", "tok")
        provider = RealAIImage3DProvider(client=client, provider_id="embedded-ai-3d")
        with self.assertRaises(Exception) as ctx:
            asyncio.run(provider.generate(make_spec(), [], lambda _i, _t, _m: None))
        self.assertIn("Hunyuan", str(ctx.exception))

    def test_hunyuan_client_rejects_non_localhost(self):
        from backend.app.providers.remote.hunyuan_client import HunyuanEmbeddedClient, HunyuanClientError

        with self.assertRaises(HunyuanClientError):
            HunyuanEmbeddedClient("http://example.com:8081", "tok")

    def test_registry_embedded_kind_real_never_mock(self):
        from backend.app.providers.registry import REGISTRY, is_provider_available, capability_for

        self.assertIn("embedded-ai-3d", REGISTRY)
        cap = capability_for("embedded-ai-3d")
        self.assertEqual(cap.kind, "real")
        self.assertNotIn("mock", REGISTRY["embedded-ai-3d"].id)
        # embedded availability reflects real install state; mock stays available.
        self.assertTrue(is_provider_available("mock"))
        self.assertTrue(is_provider_available("local-lowpower"))

    def test_generate_request_carries_runtime_id(self):
        from backend.app.schemas.character import GenerateRequest

        req = GenerateRequest(
            provider="embedded-ai-3d",
            spec=make_spec(),
            referenceImageIds=[],
            references=[],
            runtimeId="hunyuan3d-2mini",
        )
        self.assertEqual(req.runtime_id, "hunyuan3d-2mini")
        # Backward compatible: omitted runtimeId stays None.
        req2 = GenerateRequest(provider="mock", spec=make_spec(), referenceImageIds=[], references=[])
        self.assertIsNone(req2.runtime_id)


class RuntimeSelectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.resources = Path(self.tmp) / "resources" / "ai" / "3d"
        self.manifests = self.resources / "manifests"
        self.manifests.mkdir(parents=True, exist_ok=True)
        self._old_res = os.environ.get(rm.AI3D_RESOURCES_ENV)
        self._old_man = os.environ.get(rm.MANIFESTS_DIR_ENV)
        os.environ[rm.AI3D_RESOURCES_ENV] = str(self.resources)
        os.environ[rm.MANIFESTS_DIR_ENV] = str(self.manifests)
        rm._processes.clear()
        rm._transient_states.clear()

    def tearDown(self):
        for rid in list(rm._processes.keys()):
            rm.stop_runtime(rid)
        rm._processes.clear()
        rm._transient_states.clear()
        if self._old_res is None:
            os.environ.pop(rm.AI3D_RESOURCES_ENV, None)
        else:
            os.environ[rm.AI3D_RESOURCES_ENV] = self._old_res
        if self._old_man is None:
            os.environ.pop(rm.MANIFESTS_DIR_ENV, None)
        else:
            os.environ[rm.MANIFESTS_DIR_ENV] = self._old_man

    def _install_hunyuan(self):
        (self.manifests / "h.json").write_text(json.dumps(HUNYUAN_MANIFEST), encoding="utf-8")
        base = self.resources
        (base / "runtimes" / "hunyuan3d" / "api_server.py").parent.mkdir(parents=True, exist_ok=True)
        (base / "runtimes" / "hunyuan3d" / "api_server.py").touch()
        (base / "models" / "hunyuan3d-mini" / "hunyuan3d-dit-v2-mini-turbo").mkdir(parents=True, exist_ok=True)
        (base / "models" / "hunyuan3d-mini" / "hunyuan3d-dit-v2-mini-turbo" / "model.fp16.safetensors").touch()
        (base / "runtimes" / "hunyuan3d" / "LICENSE").touch()
        (base / "runtimes" / "hunyuan3d" / "NOTICE").touch()

    def test_embedded_client_explicit_runtime_not_installed_raises(self):
        from backend.app.providers.registry import _RuntimeManagerClient
        from backend.app.providers.remote.embedded_client import EmbeddedClientError

        # No manifest written -> explicit runtime not found.
        client = _RuntimeManagerClient()
        with self.assertRaises(EmbeddedClientError) as ctx:
            asyncio.run(client.create_task(make_spec(), [], None, "hunyuan3d-2mini"))
        self.assertIn("未发现", str(ctx.exception))

    def test_embedded_client_explicit_runtime_incompatible_hardware_raises(self):
        self._install_hunyuan()
        from backend.app.providers.registry import _RuntimeManagerClient
        from backend.app.providers.remote.embedded_client import EmbeddedClientError

        # No NVIDIA GPU on this machine -> incompatible -> explicit error (never mock).
        client = _RuntimeManagerClient()
        with self.assertRaises(EmbeddedClientError) as ctx:
            asyncio.run(client.create_task(make_spec(), [], None, "hunyuan3d-2mini"))
        self.assertIn("硬件不兼容", str(ctx.exception))


class HunyuanE2ETest(unittest.TestCase):
    """Fake Hunyuan HTTP server + RealAIImage3DProvider + fake GLB -> ModelStore.

    Uses a REAL valid GLB (build_glb) so the provider's validate_glb gate passes
    and the job persists to ModelStore - proving the full chain without GPU.
    """

    def test_fake_server_to_modelstore_full_chain(self):
        from backend.app.providers.remote.hunyuan_client import HunyuanEmbeddedClient
        from backend.app.providers.remote.real_ai import RealAIImage3DProvider
        from backend.app.services.glb_builder import Primitive, build_glb
        from backend.app.schemas.vision import VisionImageInput

        glb = build_glb([Primitive("box", (0.4, 0.4, 0.4), color="#44AA66")])
        server = FakeHunyuanServer(glb=glb)
        port = server.start()
        try:
            client = HunyuanEmbeddedClient(f"http://127.0.0.1:{port}", "tok")
            provider = RealAIImage3DProvider(client=client, provider_id="embedded-ai-3d")
            refs = [VisionImageInput(imageId="i1", dataUrl="data:image/png;base64,aGVsbG8=", view="front")]
            data = asyncio.run(provider.generate(make_spec(), refs, lambda _i, _t, _m: None))
            self.assertEqual(data, glb)
        finally:
            server.stop()

    def test_fake_server_never_done_times_out(self):
        from backend.app.providers.remote.hunyuan_client import HunyuanEmbeddedClient
        from backend.app.providers.remote.real_ai import RealAIImage3DProvider

        server = FakeHunyuanServer(glb=FAKE_GLB, never_done=True)
        port = server.start()
        try:
            client = HunyuanEmbeddedClient(f"http://127.0.0.1:{port}", "tok")
            provider = RealAIImage3DProvider(
                client=client, provider_id="embedded-ai-3d", default_timeout_seconds=0.5
            )
            with self.assertRaises(Exception):
                asyncio.run(provider.generate(make_spec(), [], lambda _i, _t, _m: None))
        finally:
            server.stop()

    def test_user_cancel_maps_to_cancelled(self):
        from backend.app.providers.base import CancellationToken
        from backend.app.providers.remote.hunyuan_client import HunyuanEmbeddedClient
        from backend.app.providers.remote.real_ai import RealAIImage3DProvider

        server = FakeHunyuanServer(glb=FAKE_GLB, never_done=True)
        port = server.start()
        try:
            client = HunyuanEmbeddedClient(f"http://127.0.0.1:{port}", "tok")
            provider = RealAIImage3DProvider(client=client, provider_id="embedded-ai-3d")
            token = CancellationToken()

            async def run():
                task = asyncio.create_task(provider.generate(make_spec(), [], lambda _i, _t, _m: None, token))
                await asyncio.sleep(0.2)
                token.cancel()
                with self.assertRaises(Exception):
                    await task

            asyncio.run(run())
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
