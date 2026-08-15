"""Phase 3-D: Hunyuan3D-2mini Runtime/Model Package Installer tests.

Covers:
  - secure downloader: success / cancel / checksum failure / size mismatch /
    interrupted connection / atomic rename / redirect-host refusal / http gate
  - Runtime Package + Model Package as INDEPENDENT install units (partial states)
  - install state machine: NOT_INSTALLED -> DOWNLOADING -> VERIFYING -> INSTALLED
    with explicit FAILED / cancelled (never faked INSTALLED)
  - license acceptance gating (start blocked before acceptance)
  - hardware gating (start blocked on incompatible hardware / no NVIDIA)
  - manifest URL / artifact path / executable path validation (no arbitrary URL,
    no arbitrary executable)
  - start_runtime blocked before installation / before license / incompatible hw
  - no real download by default (AIVCS_AI3D_ALLOW_DOWNLOAD off)

No real AI, no GPU, no network to external hosts, no real weight download.
All downloads use a local 127.0.0.1 fake HTTP server or an injected fake fetcher.
"""

from __future__ import annotations

import hashlib
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
from backend.app.services import ai3d_downloader as dl  # noqa: E402
from backend.app.services import ai3d_runtime_manager as rm  # noqa: E402
from backend.app.services.ai3d_runtime_manager import HardwareCapability, InstallState, PackageInstallState, RuntimeStatus  # noqa: E402


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


class FakeArtifactServer:
    """Local fake HTTP server serving manifest artifact bytes (127.0.0.1 only)."""

    def __init__(self):
        self.routes: dict[str, tuple[bytes, dict]] = {}
        self._server = None
        self._thread = None
        self.port = 0

    def add(self, path, data=b"", **opts):
        self.routes[path] = (data, opts)

    def start(self) -> int:
        handler = self._make_handler()
        self._server = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _json(self, code, obj):
                body = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                route = server.routes.get(self.path)
                if route is None:
                    self._json(404, {"error": "not found"})
                    return
                data, opts = route
                if opts.get("redirect"):
                    self.send_response(302)
                    self.send_header("Location", opts["redirect"])
                    self.end_headers()
                    return
                if opts.get("status"):
                    self._json(opts["status"], {"error": "boom"})
                    return
                if opts.get("abort"):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    try:
                        self.wfile.write(data[: max(1, len(data) // 2)])
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    self.close_connection = True
                    return
                if opts.get("chunk_delay"):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    chunk_size = opts.get("chunk_size", 16)
                    try:
                        self.wfile.write(data[:chunk_size])
                        self.wfile.flush()
                        time.sleep(opts["chunk_delay"])
                        self.wfile.write(data[chunk_size:])
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler


def artifact(server, path, data, http_allowed=True, url_path=None, **opts):
    """Build an artifact dict, registering its bytes on the fake server."""
    sha = hashlib.sha256(data).hexdigest()
    up = url_path or f"/{path}"
    server.add(up, data, **opts)
    return {
        "path": path,
        "url": server.url(up),
        "sha256": sha,
        "sizeBytes": len(data),
        "httpAllowed": http_allowed,
    }


RUNTIME_CONTENT = b"#!/usr/bin/env python\nprint('fake api_server')\n"
LICENSE_CONTENT = b"Tencent Hunyuan 3D Community License (test fixture)\n"
NOTICE_CONTENT = b"NOTICE (test fixture)\n"
MODEL_CONTENT = b"fake-model-safetensors-bytes"


def build_manifest(server, requires_acceptance=True, runtime_artifacts=None, model_artifacts=None, **over):
    m = {
        "id": "h3d",
        "name": "H3D (test)",
        "version": "0.1.0",
        "modelVersion": "hunyuan3d-dit-v2-mini-turbo 0.6B",
        "inputTypes": ["image"],
        "outputTypes": ["glb"],
        "capabilities": {"supportsCancel": False, "supportsProgress": False, "supportsResume": False},
        "hardware": {
            "requiresGPU": True,
            "minimumVRAMMB": 6144,
            "recommendedVRAMMB": 12288,
            "minimumRAMMB": 16384,
            "supportedOS": ["windows-x64"],
            "supportedBackends": ["cuda"],
        },
        "files": {
            "executable": "h3d/api_server.py",
            "modelPath": "h3d",
            "relativeTo": "resources/ai/3d/",
            "license": "h3d/LICENSE",
            "notice": "h3d/NOTICE",
        },
        "license": {
            "id": "tencent-hunyuan-3d-2-community",
            "url": "https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/LICENSE",
            "modelSource": "huggingface",
            "modelSourceUrl": "https://huggingface.co/tencent/Hunyuan3D-2mini",
            "territoryRestrictions": "不得在欧盟 / 英国 / 韩国使用或分发",
            "commercialThreshold": "月活跃用户超过 100 万须向腾讯申请商业许可",
            "requiresAcceptance": requires_acceptance,
        },
        "packages": [
            {
                "id": "h3d-runtime",
                "kind": "runtime",
                "version": "0.1.0",
                "source": "github",
                "sourceUrl": "https://github.com/Tencent-Hunyuan/Hunyuan3D-2",
                "license": "tencent-hunyuan-3d-2-community",
                "notice": "h3d/NOTICE",
                "installDir": "h3d",
                "artifacts": runtime_artifacts or [],
            },
            {
                "id": "h3d-model",
                "kind": "model",
                "version": "mini",
                "source": "huggingface",
                "sourceUrl": "https://huggingface.co/tencent/Hunyuan3D-2mini",
                "license": "tencent-hunyuan-3d-2-community",
                "notice": "h3d/NOTICE",
                "installDir": "h3d",
                "artifacts": model_artifacts or [],
            },
        ],
    }
    m.update(over)
    return m


class IsolatedEnvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.resources = Path(self.tmp) / "resources" / "ai" / "3d"
        self.manifests = self.resources / "manifests"
        self.manifests.mkdir(parents=True, exist_ok=True)
        self._old_res = os.environ.get(rm.AI3D_RESOURCES_ENV)
        self._old_man = os.environ.get(rm.MANIFESTS_DIR_ENV)
        self._old_userdata = os.environ.get(rm.USERDATA_ENV)
        self._old_allow = os.environ.get(rm.ALLOW_DOWNLOAD_ENV)
        os.environ[rm.AI3D_RESOURCES_ENV] = str(self.resources)
        os.environ[rm.MANIFESTS_DIR_ENV] = str(self.manifests)
        os.environ.pop(rm.ALLOW_DOWNLOAD_ENV, None)
        rm._transient_states.clear()
        with rm._install_lock:
            rm._progress.clear()
            rm._cancel_events.clear()
        rm._processes.clear()
        self.server = FakeArtifactServer()
        self.server.start()
        self.base = rm.install_base()

    def tearDown(self):
        self.server.stop()
        for rid in list(rm._processes.keys()):
            rm.stop_runtime(rid)
        rm._transient_states.clear()
        with rm._install_lock:
            rm._progress.clear()
            rm._cancel_events.clear()
        rm._processes.clear()
        for env, old in (
            (rm.AI3D_RESOURCES_ENV, self._old_res),
            (rm.MANIFESTS_DIR_ENV, self._old_man),
            (rm.USERDATA_ENV, self._old_userdata),
            (rm.ALLOW_DOWNLOAD_ENV, self._old_allow),
        ):
            if old is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = old

    def write_manifest(self, payload) -> Ai3DRuntimeManifest:
        (self.manifests / "h3d.json").write_text(json.dumps(payload), encoding="utf-8")
        return Ai3DRuntimeManifest.model_validate(payload)

    def default_payload(self, **over):
        return build_manifest(self.server, **over)


class DownloaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = FakeArtifactServer()
        self.server.start()

    def tearDown(self):
        self.server.stop()

    def test_success_verifies_and_commits_atomically(self):
        data = b"hello-artifact"
        self.server.add("/a.bin", data)
        dest = Path(self.tmp) / "out"
        final = dl.download_artifact(
            self.server.url("/a.bin"), dest, hashlib.sha256(data).hexdigest(), len(data), http_allowed=True
        )
        self.assertEqual(final.read_bytes(), data)
        self.assertFalse(list(dest.glob("*.part")))

    def test_checksum_failure_no_final_file(self):
        data = b"actual-bytes"
        self.server.add("/a.bin", data)
        dest = Path(self.tmp) / "out"
        with self.assertRaises(dl.ArtifactDownloadError):
            dl.download_artifact(
                self.server.url("/a.bin"), dest, "0" * 64, len(data), http_allowed=True  # wrong sha
            )
        self.assertFalse((dest / "a.bin").exists())
        self.assertFalse(list(dest.glob("*.part")))

    def test_size_mismatch_fails(self):
        data = b"actual-bytes"
        self.server.add("/a.bin", data)
        dest = Path(self.tmp) / "out"
        with self.assertRaises(dl.ArtifactDownloadError) as ctx:
            dl.download_artifact(
                self.server.url("/a.bin"), dest, hashlib.sha256(data).hexdigest(), len(data) + 100, http_allowed=True
            )
        self.assertIn("大小不匹配", str(ctx.exception))
        self.assertFalse((dest / "a.bin").exists())

    def test_interrupted_fails(self):
        data = b"x" * 4096
        self.server.add("/a.bin", data, abort=True)
        dest = Path(self.tmp) / "out"
        with self.assertRaises(dl.ArtifactDownloadError) as ctx:
            dl.download_artifact(self.server.url("/a.bin"), dest, hashlib.sha256(data).hexdigest(), len(data), http_allowed=True)
        self.assertTrue(any(k in str(ctx.exception) for k in ("中断", "下载失败", "大小不匹配", "校验失败")))
        self.assertFalse((dest / "a.bin").exists())

    def test_cancel_removes_temp_and_raises(self):
        data = b"y" * 4096
        self.server.add("/slow.bin", data, chunk_delay=0.5, chunk_size=16)
        dest = Path(self.tmp) / "out"
        cancel = threading.Event()
        results = {}

        def run():
            try:
                dl.download_artifact(
                    self.server.url("/slow.bin"), dest,
                    hashlib.sha256(data).hexdigest(), len(data),
                    cancel_event=cancel,
                    http_allowed=True,
                )
                results["ok"] = True
            except dl.ArtifactDownloadCancelled:
                results["cancelled"] = True

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(0.3)
        cancel.set()
        t.join(5)
        self.assertTrue(results.get("cancelled"), results)
        self.assertFalse((dest / "slow.bin").exists())
        self.assertFalse(list(dest.glob("*.part")))

    def test_redirect_to_other_host_refused(self):
        data = b"redirect-target"
        other = FakeArtifactServer()
        other.start()
        try:
            self.server.add("/r.bin", data)
            other.add("/target.bin", data)
            dest = Path(self.tmp) / "out"
            # redirect to a DIFFERENT netloc (port) -> must be refused.
            self.server.add("/r.bin", data, redirect=other.url("/target.bin"))
            with self.assertRaises(dl.ArtifactDownloadError) as ctx:
                dl.download_artifact(
                    self.server.url("/r.bin"), dest, hashlib.sha256(data).hexdigest(), len(data), http_allowed=True
                )
            self.assertIn("host", str(ctx.exception))
            self.assertFalse((dest / "r.bin").exists())
        finally:
            other.stop()

    def test_http_requires_allow_flag(self):
        data = b"x"
        self.server.add("/h.bin", data)
        dest = Path(self.tmp) / "out"
        with self.assertRaises(dl.ArtifactDownloadError):
            dl.download_artifact(self.server.url("/h.bin"), dest, "", 0, http_allowed=False)
        # Explicit allow -> works (local fake server, no external network).
        dl.download_artifact(self.server.url("/h.bin"), dest, "", 0, http_allowed=True)
        self.assertTrue((dest / "h.bin").exists())

    def test_non_http_scheme_rejected(self):
        dest = Path(self.tmp) / "out"
        for bad in ("file:///C:/evil/x.bin", "C:\\evil\\x.bin", "ftp://x/y.bin"):
            with self.assertRaises(dl.ArtifactDownloadError, msg=bad):
                dl.download_artifact(bad, dest, "", 0, http_allowed=True)

    def test_filename_sanitized_no_traversal(self):
        data = b"x"
        self.server.add("/dir/../../evil.bin", data)
        dest = Path(self.tmp) / "out"
        # The name must be sanitized to "evil.bin" inside dest (no traversal).
        final = dl.download_artifact(self.server.url("/dir/../../evil.bin"), dest, "", 0, http_allowed=True)
        self.assertEqual(final, dest / "evil.bin")
        self.assertFalse((dest / ".." / ".." / "evil.bin").exists())


class InstallerSchemaSecurityTest(unittest.TestCase):
    def test_http_artifact_requires_allow_flag(self):
        m = build_manifest(FakeArtifactServer())
        art = {"path": "a.bin", "url": "http://127.0.0.1:1/a.bin", "sha256": "", "sizeBytes": 0, "httpAllowed": False}
        m["packages"][1]["artifacts"] = [art]
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(m)
        art["httpAllowed"] = True
        Ai3DRuntimeManifest.model_validate(m)

    def test_artifact_path_traversal_rejected(self):
        m = build_manifest(FakeArtifactServer())
        for bad in ("../../evil.bin", "C:\\evil.bin", "/abs.bin", "..\\evil.bin"):
            m["packages"][1]["artifacts"] = [
                {"path": bad, "url": "https://example.com/a.bin", "sha256": "a" * 64, "sizeBytes": 1, "httpAllowed": False}
            ]
            with self.assertRaises(Exception, msg=bad):
                Ai3DRuntimeManifest.model_validate(m)

    def test_package_install_dir_traversal_rejected(self):
        m = build_manifest(FakeArtifactServer())
        m["packages"][1]["installDir"] = "../../evil"
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(m)

    def test_artifact_url_must_be_http(self):
        m = build_manifest(FakeArtifactServer())
        for bad in ("file:///C:/evil/a.bin", "C:\\evil\\a.bin", "data:image/png;base64,x"):
            m["packages"][1]["artifacts"] = [
                {"path": "a.bin", "url": bad, "sha256": "a" * 64, "sizeBytes": 1, "httpAllowed": True}
            ]
            with self.assertRaises(Exception, msg=bad):
                Ai3DRuntimeManifest.model_validate(m)

    def test_executable_must_be_relative(self):
        m = build_manifest(FakeArtifactServer())
        m["files"]["executable"] = "C:/evil/aivcs.exe"
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(m)


class HunyuanInstallerTest(IsolatedEnvTest):
    def runtime_artifacts(self):
        return [
            artifact(self.server, "api_server.py", RUNTIME_CONTENT),
            artifact(self.server, "LICENSE", LICENSE_CONTENT),
            artifact(self.server, "NOTICE", NOTICE_CONTENT),
        ]

    def model_artifacts(self):
        return [artifact(self.server, "model.fp16.safetensors", MODEL_CONTENT)]

    def test_install_blocked_without_downloader(self):
        self.write_manifest(
            self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )
        result = rm.install_package("h3d", "model", downloader=None, fetcher=None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "not-installed")
        self.assertEqual(result["packageState"], PackageInstallState.NOT_INSTALLED.value)
        self.assertIn("自动下载未启用", result["results"][0]["error"])

    def test_install_runtime_and_model_success(self):
        m = self.write_manifest(
            self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )

        def fetcher(url, sha256, size_bytes, on_progress):
            # Only serve bytes for URLs the manifest actually declares.
            for art in (self.runtime_artifacts() + self.model_artifacts()):
                if art["url"] == url:
                    return {"ok": True, "bytes": bytes(self._payload_for(art["path"]))}
            return {"ok": False, "error": "no route"}

        # Simple in-class helper: map artifact path -> bytes.
        result = rm.install_package("h3d", "all", fetcher=fetcher)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["packageState"], PackageInstallState.INSTALLED.value)
        self.assertEqual(rm.compute_install_state(m), InstallState.INSTALLED)
        self.assertEqual(rm.package_kind_state(m, "runtime", make_hw()).value, PackageInstallState.INSTALLED.value)
        self.assertEqual(rm.package_kind_state(m, "model", make_hw()).value, PackageInstallState.INSTALLED.value)
        # Both complete + compatible hardware -> READY.
        self.assertEqual(rm.package_state_for(m, make_hw()).value, PackageInstallState.READY.value)
        exe = self.base / "runtimes" / "h3d" / "api_server.py"
        self.assertTrue(exe.is_file())
        self.assertEqual(exe.read_bytes(), RUNTIME_CONTENT)

    def _payload_for(self, path):
        return {
            "api_server.py": RUNTIME_CONTENT,
            "LICENSE": LICENSE_CONTENT,
            "NOTICE": NOTICE_CONTENT,
            "model.fp16.safetensors": MODEL_CONTENT,
        }[path]

    def test_install_runtime_only_is_partial(self):
        m = self.write_manifest(
            self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )

        def fetcher(url, sha256, size_bytes, on_progress):
            for art in self.runtime_artifacts():
                if art["url"] == url:
                    return {"ok": True, "bytes": self._payload_for(art["path"])}
            return {"ok": False, "error": "no route"}

        result = rm.install_package("h3d", "runtime", fetcher=fetcher)
        self.assertTrue(result["ok"], result)
        self.assertEqual(rm.package_kind_state(m, "runtime", make_hw()).value, PackageInstallState.INSTALLED.value)
        self.assertEqual(rm.package_kind_state(m, "model", make_hw()).value, PackageInstallState.NOT_INSTALLED.value)
        # Runtime only -> overall PARTIAL (never READY).
        self.assertEqual(rm.package_state_for(m, make_hw()).value, PackageInstallState.PARTIAL.value)

    def test_install_model_only_is_partial(self):
        m = self.write_manifest(
            self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )

        def fetcher(url, sha256, size_bytes, on_progress):
            for art in self.model_artifacts():
                if art["url"] == url:
                    return {"ok": True, "bytes": self._payload_for(art["path"])}
            return {"ok": False, "error": "no route"}

        result = rm.install_package("h3d", "model", fetcher=fetcher)
        self.assertTrue(result["ok"], result)
        self.assertEqual(rm.package_state_for(m, make_hw()).value, PackageInstallState.PARTIAL.value)

    def test_checksum_failure_keeps_failed(self):
        m = self.write_manifest(
            self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )

        def fetcher(url, sha256, size_bytes, on_progress):
            # Serve WRONG bytes for the model artifact -> verify must fail.
            for art in self.model_artifacts():
                if art["url"] == url:
                    return {"ok": True, "bytes": b"corrupted-bytes"}
            for art in self.runtime_artifacts():
                if art["url"] == url:
                    return {"ok": True, "bytes": self._payload_for(art["path"])}
            return {"ok": False, "error": "no route"}

        result = rm.install_package("h3d", "model", fetcher=fetcher)
        self.assertFalse(result["ok"])
        self.assertEqual(result["packageState"], PackageInstallState.FAILED.value)
        # Corrupted file is never presented as INSTALLED.
        self.assertEqual(rm.package_kind_state(m, "model", make_hw()).value, PackageInstallState.NOT_INSTALLED.value)

    def test_size_mismatch_keeps_failed(self):
        m = self.write_manifest(
            self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )
        # Override the model artifact's declared size to force a mismatch.
        payload = self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        payload["packages"][1]["artifacts"][0]["sizeBytes"] = len(MODEL_CONTENT) + 100
        m = self.write_manifest(payload)

        def fetcher(url, sha256, size_bytes, on_progress):
            for art in self.model_artifacts():
                if art["url"] == url:
                    return {"ok": True, "bytes": MODEL_CONTENT}
            for art in self.runtime_artifacts():
                if art["url"] == url:
                    return {"ok": True, "bytes": self._payload_for(art["path"])}
            return {"ok": False, "error": "no route"}

        result = rm.install_package("h3d", "model", fetcher=fetcher)
        self.assertFalse(result["ok"])
        self.assertEqual(result["packageState"], PackageInstallState.FAILED.value)
        per_kind = result["results"][0]
        self.assertTrue(any("大小不匹配" in e for e in (per_kind.get("errors") or [])))
        self.assertEqual(rm.package_kind_state(m, "model", make_hw()).value, PackageInstallState.NOT_INSTALLED.value)

    def test_cancel_returns_not_installed(self):
        model_art = artifact(self.server, "model.fp16.safetensors", MODEL_CONTENT, chunk_delay=0.5, chunk_size=16)
        self.write_manifest(self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=[model_art]))

        cancel = threading.Event()

        def set_cancel():
            time.sleep(0.3)
            cancel.set()

        threading.Thread(target=set_cancel, daemon=True).start()
        result = rm.install_package("h3d", "model", downloader=dl.download_artifact, cancel_event=cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["packageState"], PackageInstallState.NOT_INSTALLED.value)
        target = self.base / "models" / "h3d" / "model.fp16.safetensors"
        self.assertFalse(target.exists())
        self.assertFalse(list((self.base / "models" / "h3d").glob("*.part")))

    def test_cancel_package_install_via_registry(self):
        model_art = artifact(self.server, "model.fp16.safetensors", MODEL_CONTENT, chunk_delay=1.0, chunk_size=16)
        self.write_manifest(self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=[model_art]))

        # No external cancel_event: the manager registers its own; the registry
        # (cancel_package_install) sets it.
        result_holder = {}

        def run():
            result_holder["r"] = rm.install_package("h3d", "model", downloader=dl.download_artifact)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        time.sleep(0.3)
        cancelled = rm.cancel_package_install("h3d", "model")
        self.assertTrue(cancelled["cancelled"])
        t.join(5)
        self.assertEqual(result_holder["r"]["status"], "cancelled")

    def test_progress_reported(self):
        model_art = artifact(self.server, "model.fp16.safetensors", MODEL_CONTENT)
        self.write_manifest(self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=[model_art]))
        pcts = []

        def on_progress(pct):
            pcts.append(pct)

        result = rm.install_package("h3d", "model", downloader=dl.download_artifact, on_progress=on_progress)
        self.assertTrue(result["ok"], result)
        self.assertGreater(len(pcts), 0)
        self.assertAlmostEqual(pcts[-1], 100.0, delta=0.1)
        progress = rm.install_progress("h3d")
        self.assertEqual(progress["model"]["status"], "done")
        self.assertEqual(progress["model"]["percent"], 100.0)

    def test_atomic_no_partial_file_on_download_failure(self):
        # Wrong declared size -> downloader rejects BEFORE commit (atomic).
        model_art = artifact(self.server, "model.fp16.safetensors", MODEL_CONTENT)
        model_art["sizeBytes"] = len(MODEL_CONTENT) + 1000  # size mismatch
        self.write_manifest(self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=[model_art]))
        result = rm.install_package("h3d", "model", downloader=dl.download_artifact)
        self.assertFalse(result["ok"])
        self.assertEqual(result["packageState"], PackageInstallState.FAILED.value)
        target = self.base / "models" / "h3d" / "model.fp16.safetensors"
        self.assertFalse(target.exists())
        self.assertFalse(list((self.base / "models" / "h3d").glob("*.part")))

    def test_no_artifact_url_reports_explicit_error(self):
        payload = self.default_payload(runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        payload["packages"][0]["artifacts"][0]["url"] = ""  # runtime code has no official single-file URL
        self.write_manifest(payload)

        def fetcher(url, sha256, size_bytes, on_progress):
            return {"ok": False, "error": "unused"}

        result = rm.install_package("h3d", "runtime", fetcher=fetcher)
        self.assertFalse(result["ok"])
        self.assertEqual(result["packageState"], PackageInstallState.FAILED.value)
        self.assertIn("未提供官方下载源", result["results"][0]["error"])


class RuntimeStartGatingTest(IsolatedEnvTest):
    def setUp(self):
        super().setUp()
        self._orig_detect = rm.detect_hardware
        self._hw_patched = False

    def tearDown(self):
        if self._hw_patched:
            rm.detect_hardware = self._orig_detect
        super().tearDown()

    def patch_hw(self, gpu="nvidia", vram=12288):
        rm.detect_hardware = lambda: make_hw(gpu=gpu, vram=vram)
        self._hw_patched = True

    def runtime_artifacts(self):
        return [
            artifact(self.server, "api_server.py", RUNTIME_CONTENT),
            artifact(self.server, "LICENSE", LICENSE_CONTENT),
            artifact(self.server, "NOTICE", NOTICE_CONTENT),
        ]

    def model_artifacts(self):
        return [artifact(self.server, "model.fp16.safetensors", MODEL_CONTENT)]

    def install_all(self, m):
        artifacts = self.runtime_artifacts() + self.model_artifacts()

        def fetcher(url, sha256, size_bytes, on_progress):
            for art in artifacts:
                if art["url"] == url:
                    name = art["path"]
                    return {"ok": True, "bytes": {
                        "api_server.py": RUNTIME_CONTENT,
                        "LICENSE": LICENSE_CONTENT,
                        "NOTICE": NOTICE_CONTENT,
                        "model.fp16.safetensors": MODEL_CONTENT,
                    }[name]}
            return {"ok": False, "error": "no route"}

        return rm.install_package("h3d", "all", fetcher=fetcher)

    def test_start_blocked_before_installation(self):
        m = self.write_manifest(
            self.default_payload(requires_acceptance=False, runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )
        self.patch_hw()  # compatible NVIDIA hardware -> install gate is next.
        self.assertTrue(rm.hardware_compatible(m, make_hw()))
        result = rm.start_runtime("h3d")
        self.assertFalse(result["ok"])
        self.assertIn("未安装", result["error"])

    def test_start_blocked_before_license_acceptance(self):
        m = self.write_manifest(
            self.default_payload(requires_acceptance=True, runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )
        self.patch_hw()
        self.assertTrue(self.install_all(m)["ok"])
        self.assertFalse(rm.license_accepted("h3d"))
        result = rm.start_runtime("h3d")
        self.assertFalse(result["ok"])
        self.assertIn("许可证", result["error"])

    def test_license_acceptance_gate_flow(self):
        m = self.write_manifest(
            self.default_payload(requires_acceptance=True, runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )
        self.patch_hw()  # compatible NVIDIA hardware: the license gate is reached.
        self.assertTrue(self.install_all(m)["ok"])
        self.assertFalse(rm.license_accepted("h3d"))
        # Without acceptance -> license gate blocks (never spawns).
        first = rm.start_runtime("h3d")
        self.assertIn("许可证", first["error"])
        accepted = rm.set_license_accepted("h3d", True)
        self.assertTrue(accepted["ok"])
        self.assertTrue(rm.license_accepted("h3d"))
        # Now re-patch hardware to incompatible (no NVIDIA): the hardware gate
        # blocks even when license + install both pass (never READY, never spawn).
        rm.detect_hardware = lambda: make_hw(gpu="unknown", vram=None)
        result = rm.start_runtime("h3d")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], RuntimeStatus.INCOMPATIBLE.value)
        self.assertIn("硬件", result["error"])

    def test_start_blocked_on_incompatible_hardware(self):
        m = self.write_manifest(
            self.default_payload(requires_acceptance=False, runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )
        self.patch_hw(gpu="unknown", vram=None)
        self.assertTrue(self.install_all(m)["ok"])
        result = rm.start_runtime("h3d")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], RuntimeStatus.INCOMPATIBLE.value)
        self.assertIn("硬件", result["error"])

    def test_no_arbitrary_executable(self):
        # Executable outside the allow-root can never be resolved/executed.
        payload = self.default_payload(requires_acceptance=False, runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        payload["files"]["executable"] = "h3d/../../evil/api_server.py"
        with self.assertRaises(Exception):
            Ai3DRuntimeManifest.model_validate(payload)

    def test_runtime_status_includes_package_states(self):
        m = self.write_manifest(
            self.default_payload(requires_acceptance=True, runtime_artifacts=self.runtime_artifacts(), model_artifacts=self.model_artifacts())
        )
        status = rm.runtime_status("h3d")
        self.assertTrue(status["ok"])
        self.assertIn("runtimePackageState", status)
        self.assertIn("modelPackageState", status)
        self.assertIn("licenseAccepted", status)
        self.assertIn("licenseRequiresAcceptance", status)


class ResourcesManifestTest(unittest.TestCase):
    def test_repo_hunyuan_manifest_valid(self):
        """The shipped hunyuan manifest must parse with the Phase 3-D schema."""
        here = Path(__file__).resolve().parents[2]
        manifest_path = here / "resources" / "ai" / "3d" / "manifests" / "hunyuan3d-2mini.runtime.json"
        m = Ai3DRuntimeManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
        self.assertEqual(m.id, "hunyuan3d-2mini")
        self.assertEqual(len(m.packages), 2)
        kinds = {p.kind for p in m.packages}
        self.assertEqual(kinds, {"runtime", "model"})
        self.assertTrue(m.license.requires_acceptance)
        model_pkg = next(p for p in m.packages if p.kind == "model")
        self.assertTrue(model_pkg.artifacts)
        self.assertTrue(model_pkg.artifacts[0].sha256)
        self.assertEqual(len(model_pkg.artifacts[0].sha256), 64)
        self.assertFalse(model_pkg.artifacts[0].http_allowed)  # HTTPS default


if __name__ == "__main__":
    unittest.main()
