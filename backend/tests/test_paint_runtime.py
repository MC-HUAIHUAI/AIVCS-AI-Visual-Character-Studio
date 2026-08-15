"""Phase 3-H: Real Texture/Paint Runtime tests.

Covers (NO GPU / NO real inference / NO weight download - fake runtime only):
  - official Paint manifest (texture.supported=true, kind=paint, VRAM, blocked install)
  - paint output adaptation (verify_textured_glb / adapt_paint_output -> texture metadata)
  - HunyuanPaintClient protocol against a local fake Paint server (/send texture:true)
  - paint output -> ModelStore texture metadata round-trip
  - textured GLB -> auto-rig -> VRM preserves texture (paint never breaks the rig pipeline)
  - registry selects the paint client for `--enable_tex` manifests
  - paint runtime not installed -> explicit generate block (no mock fallback)
  - job texture metadata auto-attach (fault tolerant, shape-only stays None)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import struct
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app import jobs  # noqa: E402
from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.schemas.ai3d_runtime import Ai3DRuntimeManifest  # noqa: E402
from backend.app.services import ai3d_runtime_manager as rm  # noqa: E402
from backend.app.services.glb_builder import Primitive, build_glb, serialize_glb  # noqa: E402
from backend.app.services.model_store import ModelStore  # noqa: E402
from backend.app.services.paint_output import PaintOutputError, adapt_paint_output, verify_textured_glb  # noqa: E402
from backend.app.services.local3d_rigger import rig_glb_to_vrm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_1PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def make_spec(**over):
    base = dict(
        id="s", name="t", style="stylized", gender="female", heightCm=160, description="",
        referenceImageIds=[], tags=[], createdAt="2026-01-01T00:00:00Z", updatedAt="2026-01-01T00:00:00Z",
    )
    base.update(over)
    return CharacterSpec(**base)


def build_textured_glb() -> bytes:
    """A valid textured GLB (quad + UVs + baseColor/normal/metallicRoughness tex)."""
    pos = [-0.5, 0, 0.5, 0.5, 0, 0.5, 0.5, 0, -0.5, -0.5, 0, -0.5]
    nrm = [0, 1, 0] * 4
    uv = [0, 1, 1, 1, 1, 0, 0, 0]
    idx = [0, 1, 2, 0, 2, 3]
    png = _1PX_PNG
    buffer = bytearray()
    views: list[dict] = []
    accessors: list[dict] = []

    def add(data: bytes, target: int | None) -> int:
        while len(buffer) % 4:
            buffer.append(0)
        view = {"buffer": 0, "byteOffset": len(buffer), "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        views.append(view)
        buffer.extend(data)
        return len(views) - 1

    pv = add(struct.pack("<%df" % len(pos), *pos), 34962)
    accessors.append({"bufferView": pv, "componentType": 5126, "count": 4, "type": "VEC3", "min": [-0.5, 0, -0.5], "max": [0.5, 0, 0.5]})
    nv = add(struct.pack("<%df" % len(nrm), *nrm), 34962)
    accessors.append({"bufferView": nv, "componentType": 5126, "count": 4, "type": "VEC3"})
    tv = add(struct.pack("<%df" % len(uv), *uv), 34962)
    accessors.append({"bufferView": tv, "componentType": 5126, "count": 4, "type": "VEC2"})
    iv = add(struct.pack("<%dI" % len(idx), *idx), 34963)
    accessors.append({"bufferView": iv, "componentType": 5125, "count": len(idx), "type": "SCALAR"})
    imv = add(png, None)

    gltf = {
        "asset": {"version": "2.0", "generator": "aivcs-test-textured"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
        "materials": [
            {
                "name": "tex",
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": 0},
                    "metallicRoughnessTexture": {"index": 1},
                },
                "normalTexture": {"index": 2},
            }
        ],
        "textures": [{"sampler": 0, "source": 0}, {"sampler": 0, "source": 0}, {"sampler": 0, "source": 0}],
        "images": [{"bufferView": imv, "mimeType": "image/png"}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(buffer)}],
    }
    return serialize_glb(gltf, bytes(buffer))


PAINT_MANIFEST = {
    "id": "hunyuan3d-2mini-paint",
    "name": "Hunyuan3D-2 mini Paint（本地 AI 纹理）",
    "version": "0.1.0",
    "modelVersion": "hunyuan3d-paint-v2-0-turbo 1.3B + hunyuan3d-delight-v2-0",
    "inputTypes": ["image"],
    "outputTypes": ["glb"],
    "capabilities": {
        "supportsCancel": False,
        "supportsProgress": False,
        "supportsResume": False,
        "texture": {"supported": True, "kind": "paint", "notes": "official paint"},
    },
    "hardware": {
        "requiresGPU": True,
        "minimumVRAMMB": 16384,
        "recommendedVRAMMB": 24576,
        "minimumRAMMB": 32768,
        "supportedOS": ["windows-x64", "windows-amd64"],
        "supportedBackends": ["cuda"],
    },
    "files": {
        "executable": "hunyuan3d-2mini-paint/api_server.py",
        "modelPath": "hunyuan3d-2mini-paint",
        "relativeTo": "resources/ai/3d/",
        "license": "hunyuan3d-2mini-paint/LICENSE",
        "notice": "hunyuan3d-2mini-paint/NOTICE",
    },
    "license": {
        "id": "tencent-hunyuan-3d-2-community",
        "url": "https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/LICENSE",
        "modelSource": "huggingface",
        "modelSourceUrl": "https://huggingface.co/tencent/Hunyuan3D-2",
        "territoryRestrictions": "不得在欧盟 / 英国 / 韩国使用或分发",
        "commercialThreshold": "月活跃用户超过 100 万须向腾讯申请商业许可",
        "requiresAcceptance": True,
    },
    "packages": [
        {
            "id": "paint-runtime",
            "kind": "runtime",
            "version": "0.1.0",
            "source": "github",
            "sourceUrl": "https://github.com/Tencent-Hunyuan/Hunyuan3D-2",
            "license": "tencent-hunyuan-3d-2-community",
            "notice": "hunyuan3d-2mini-paint/NOTICE",
            "installDir": "hunyuan3d-2mini-paint",
            "artifacts": [
                {"path": "api_server.py", "url": "", "sha256": "", "sizeBytes": 0, "httpAllowed": False},
                {"path": "LICENSE", "url": "", "sha256": "", "sizeBytes": 0, "httpAllowed": False},
                {"path": "NOTICE", "url": "", "sha256": "", "sizeBytes": 0, "httpAllowed": False},
            ],
        },
        {
            "id": "paint-model",
            "kind": "model",
            "version": "paint+delight",
            "source": "huggingface",
            "sourceUrl": "https://huggingface.co/tencent/Hunyuan3D-2",
            "license": "tencent-hunyuan-3d-2-community",
            "notice": "hunyuan3d-2mini-paint/NOTICE",
            "installDir": "hunyuan3d-2mini-paint",
            "artifacts": [
                {"path": "hunyuan3d-paint-v2-0-turbo", "url": "", "sha256": "", "sizeBytes": 0, "httpAllowed": False},
                {"path": "hunyuan3d-delight-v2-0", "url": "", "sha256": "", "sizeBytes": 0, "httpAllowed": False},
            ],
        },
    ],
    "launch": {
        "args": [
            "--host", "127.0.0.1", "--port", "{port}",
            "--model_path", "tencent/Hunyuan3D-2mini",
            "--tex_model_path", "tencent/Hunyuan3D-2",
            "--device", "cuda",
            "--enable_tex",
        ],
        "healthPath": "/",
        "readyTimeoutSeconds": 300.0,
    },
}


class FakePaintServer:
    """Local fake of the official api_server /send + /status texture path."""

    def __init__(self, glb: bytes):
        self.glb = glb
        self.last_params: dict | None = None
        self._server = None
        self._thread = None
        self.port = 0

    def start(self) -> int:
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
                if self.path != "/send":
                    self._json(404, {"detail": "not found"})
                    return
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(length) if length else b"{}"
                params = json.loads(body.decode("utf-8") or "{}")
                server.last_params = params
                self._json(200, {"uid": "paint-uid-1"})

            def do_GET(self):
                if self.path.startswith("/status/"):
                    self._json(
                        200,
                        {"status": "completed", "model_base64": base64.b64encode(server.glb).decode("ascii")},
                    )
                else:
                    self._json(404, {"detail": "not found"})

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


class PaintOutputAdaptationTest(unittest.TestCase):
    def test_verify_textured_glb_metadata(self):
        tex = verify_textured_glb(build_textured_glb())
        self.assertIsNotNone(tex)
        self.assertTrue(tex["supported"])
        self.assertEqual(tex["kind"], "paint")
        self.assertTrue(tex["maps"]["baseColor"])
        self.assertTrue(tex["maps"]["normal"])
        self.assertTrue(tex["maps"]["metallicRoughness"])
        self.assertEqual(tex["textureCount"], 3)
        self.assertTrue(tex["hasUVs"])

    def test_verify_textured_glb_negative_fault_tolerant(self):
        self.assertIsNone(verify_textured_glb(build_glb([Primitive("box", (1, 1, 1))])))
        self.assertIsNone(verify_textured_glb(b"not-a-glb"))

    def test_adapt_paint_output(self):
        adapted = adapt_paint_output(build_textured_glb())
        self.assertTrue(adapted["ok"])
        self.assertTrue(adapted["textured"])
        self.assertEqual(adapted["format"], "glb")
        self.assertIn("maps", adapted["texture"])

    def test_adapt_rejects_non_textured(self):
        with self.assertRaises(PaintOutputError):
            adapt_paint_output(build_glb([Primitive("box", (1, 1, 1))]))


class PaintClientProtocolTest(unittest.TestCase):
    def setUp(self):
        self.server = FakePaintServer(build_textured_glb())
        self.port = self.server.start()

    def tearDown(self):
        self.server.stop()

    def client(self):
        from backend.app.providers.remote.hunyuan_paint_client import HunyuanPaintClient

        return HunyuanPaintClient(f"http://127.0.0.1:{self.port}", "tok")

    def _refs(self):
        from backend.app.schemas.vision import VisionImageInput

        return [VisionImageInput(imageId="i1", dataUrl="data:image/png;base64,aGVsbG8=", view="front")]

    def test_create_sends_texture_true(self):
        info = asyncio.run(self.client().create_task(make_spec(), self._refs()))
        self.assertEqual(info.task_id, "paint-uid-1")
        self.assertEqual(info.status, "queued")
        self.assertIsNotNone(self.server.last_params)
        self.assertIs(self.server.last_params["texture"], True)
        self.assertNotIn("mesh", self.server.last_params)

    def test_create_with_mesh_sends_mesh_param(self):
        c = self.client()
        c.set_paint_mesh(b"glb-shape-mesh")
        asyncio.run(c.create_task(make_spec(), self._refs()))
        self.assertIn("mesh", self.server.last_params)
        self.assertEqual(base64.b64decode(self.server.last_params["mesh"]), b"glb-shape-mesh")

    def test_poll_and_download_textured_glb(self):
        c = self.client()
        info = asyncio.run(c.poll_task("paint-uid-1"))
        self.assertEqual(info.status, "done")
        data = asyncio.run(c.download_model("paint-uid-1", ""))
        self.assertEqual(data, build_textured_glb())
        self.assertIsNotNone(verify_textured_glb(data))

    def test_capability_real_no_fake(self):
        from backend.app.providers.remote.hunyuan_paint_client import HunyuanPaintClient

        cap = self.client().capability()
        self.assertEqual(cap.kind, "real")
        self.assertFalse(cap.supports_cancel)
        self.assertIsInstance(self.client(), HunyuanPaintClient)


class PaintModelStoreRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_store = jobs._store
        jobs._store = ModelStore(Path(self.tmp))

    def tearDown(self):
        jobs._store = self._orig_store

    def test_paint_output_to_modelstore_texture_metadata(self):
        glb = build_textured_glb()
        adapted = adapt_paint_output(glb)
        rec = jobs.save_model_bytes(glb, provider_id="hunyuan3d-2mini-paint", source_job_id="paint-j", texture=adapted["texture"])
        meta = jobs.get_model_record(rec.id)
        self.assertEqual(meta.texture, adapted["texture"])
        self.assertEqual(meta.provider_id, "hunyuan3d-2mini-paint")
        self.assertEqual(jobs.get_model(rec.id), glb)


class JobTextureHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_store = jobs._store
        jobs._store = ModelStore(Path(self.tmp))

    def tearDown(self):
        jobs._store = self._orig_store

    def _run_job(self, result_bytes):
        async def runner(on_progress, cancel_token):
            return result_bytes

        async def go():
            job = jobs.create_job("test", runner, spec_hash="h")
            await jobs.run_job(job, runner)
            return job

        return asyncio.run(go())

    def test_textured_job_auto_attaches_texture_metadata(self):
        job = self._run_job(build_textured_glb())
        self.assertEqual(job.status, "done")
        rec = jobs._store.get(job.result.model_id)
        self.assertIsNotNone(rec.texture)
        self.assertTrue(rec.texture["maps"]["baseColor"])
        # Phase 3-J: the texture metadata is also carried on the job result so
        # it flows ModelStore -> API -> renderer.
        self.assertIsNotNone(job.result.texture)
        self.assertTrue(job.result.texture["maps"]["baseColor"])

    def test_shape_job_stays_shape_only(self):
        job = self._run_job(build_glb([Primitive("box", (1, 1, 1), color="#4466AA")]))
        self.assertEqual(job.status, "done")
        rec = jobs._store.get(job.result.model_id)
        self.assertIsNone(rec.texture)
        self.assertIsNone(job.result.texture)


class PaintRigCompatibilityTest(unittest.TestCase):
    def test_textured_glb_auto_rig_preserves_texture(self):
        r = rig_glb_to_vrm(build_textured_glb(), body_type="humanoid", model_name="tex")
        self.assertTrue(r["ok"])
        self.assertTrue(r["autoRigged"])
        vrm = r["vrmBytes"]
        clen, _c = struct.unpack("<I4s", vrm[12:20])
        gltf = json.loads(vrm[20 : 20 + clen])
        prim = gltf["meshes"][0]["primitives"][0]
        self.assertIn("TEXCOORD_0", prim["attributes"])  # UV preserved
        self.assertIn("JOINTS_0", prim["attributes"])  # rig added
        mat = gltf["materials"][prim["material"]]
        self.assertIn("baseColorTexture", mat.get("pbrMetallicRoughness", {}))
        self.assertIn("textures", gltf)
        self.assertTrue(gltf.get("skins"))


class PaintManifestAndGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.resources = Path(self.tmp) / "resources" / "ai" / "3d"
        self.manifests = self.resources / "manifests"
        self.manifests.mkdir(parents=True, exist_ok=True)
        (self.resources / "runtimes" / "hunyuan3d-2mini-paint").mkdir(parents=True, exist_ok=True)
        self._old_res = os.environ.get(rm.AI3D_RESOURCES_ENV)
        self._old_man = os.environ.get(rm.MANIFESTS_DIR_ENV)
        os.environ[rm.AI3D_RESOURCES_ENV] = str(self.resources)
        os.environ[rm.MANIFESTS_DIR_ENV] = str(self.manifests)
        rm._transient_states.clear()
        with rm._install_lock:
            rm._progress.clear()
            rm._cancel_events.clear()

    def tearDown(self):
        rm._transient_states.clear()
        with rm._install_lock:
            rm._progress.clear()
            rm._cancel_events.clear()
        for env, old in ((rm.AI3D_RESOURCES_ENV, self._old_res), (rm.MANIFESTS_DIR_ENV, self._old_man)):
            if old is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = old

    def _write_manifest(self):
        (self.manifests / "paint.json").write_text(json.dumps(PAINT_MANIFEST), encoding="utf-8")
        return Ai3DRuntimeManifest.model_validate(PAINT_MANIFEST)

    def test_repo_paint_manifest_parses(self):
        path = Path(ROOT) / "resources" / "ai" / "3d" / "manifests" / "hunyuan3d-2mini-paint.runtime.json"
        m = Ai3DRuntimeManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(m.id, "hunyuan3d-2mini-paint")
        self.assertTrue(m.capabilities.texture.supported)
        self.assertEqual(m.capabilities.texture.kind, "paint")
        self.assertEqual(m.hardware.minimum_vram_mb, 16384)
        self.assertIn("--enable_tex", m.launch.args)
        self.assertIn("--tex_model_path", m.launch.args)

    def test_paint_runtime_not_ready_on_this_machine(self):
        self._write_manifest()
        info = rm.build_runtime_info(self._write_manifest(), rm.detect_hardware())
        self.assertFalse(info.compatible)
        self.assertEqual(info.package_state, "not-installed")
        self.assertEqual(info.capabilities["texture"]["kind"], "paint")
        self.assertTrue(info.capabilities["texture"]["supported"])

    def test_paint_install_blocked_no_download_source(self):
        self._write_manifest()
        # No downloader: default gate blocks (honest NOT_INSTALLED, no network).
        result = rm.install_package("hunyuan3d-2mini-paint", "model", fetcher=None)
        self.assertFalse(result["ok"])
        self.assertIn("自动下载未启用", result["results"][0]["error"])
        # Even with a fetcher injected, the model artifacts declare NO official
        # download source -> explicit failure (never faked installed).
        result2 = rm.install_package(
            "hunyuan3d-2mini-paint",
            "model",
            fetcher=lambda url, sha, size, on_progress: {"ok": True, "bytes": b"x"},
        )
        self.assertFalse(result2["ok"])
        self.assertIn("未提供官方下载源", result2["results"][0]["error"])

    def test_registry_selects_paint_client(self):
        self._write_manifest()
        from backend.app.providers.registry import _RuntimeManagerClient
        from backend.app.providers.remote.hunyuan_paint_client import HunyuanPaintClient

        client = _RuntimeManagerClient._client_for("hunyuan3d-2mini-paint", "http://127.0.0.1:1", "tok")
        self.assertIsInstance(client, HunyuanPaintClient)

    def test_paint_runtime_not_installed_blocks_generate_no_mock(self):
        self._write_manifest()
        from backend.app.providers.registry import _RuntimeManagerClient
        from backend.app.providers.remote.embedded_client import EmbeddedClientError

        client = _RuntimeManagerClient()
        with self.assertRaises(EmbeddedClientError) as ctx:
            asyncio.run(client.create_task(make_spec(), [], None, "hunyuan3d-2mini-paint"))
        self.assertIn("未安装", str(ctx.exception))

    def test_paint_runtime_never_claims_ready(self):
        self._write_manifest()
        m = self._write_manifest()
        for hw_ok in (True, False):
            status, compatible = rm.compute_status(m, rm.detect_hardware())
            self.assertNotEqual(status, "ready")
        self.assertEqual(rm.compute_status(m, rm.detect_hardware())[0], "not-installed")


if __name__ == "__main__":
    unittest.main()
