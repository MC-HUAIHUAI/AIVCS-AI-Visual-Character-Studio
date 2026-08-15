"""Hunyuan3D-2mini Embedded Runtime client (Phase 3-C).

Maps the OFFICIAL Hunyuan3D API server (`api_server.py`) to the existing
IRemote3DClient seam used by RealAIImage3DProvider / EmbeddedClient:

    create_task    -> POST /send  {"image": "<base64>", "type": "glb", ...}
                      returns {"uid": ...}  (async submit)
    poll_task      -> GET  /status/{uid}    -> processing | completed(+model_base64)
    download_model -> decode model_base64 (GLB bytes)
    cancel_task    -> NOT supported by the official API. Phase 3-C marks this
                      explicitly: cancellation is process-level (the Runtime
                      Manager terminates the runtime process). We record the
                      capability as unsupported and never fake a cancel ack.

State mapping (wrapper-derived, NEVER fabricated as real progress):
    send accepted  -> "queued"
    status=processing -> "running"
    status=completed  -> "done"
    HTTP/JSON error   -> "failed"
    user cancel       -> "cancelled" (via cancel_event; process-level)

The official API is synchronous `POST /generate` OR async `POST /send` +
`GET /status/{uid}`. This client uses the async variant so poll/status works
through the unified job state machine. progress stays a coarse 0/1 (binary
processing/completed) because the official API exposes no real percentage.

Security: 127.0.0.1 only, token via X-AIVCS-Token header, no shell, no user
input in argv (Runtime Manager builds the process).
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from ...schemas.character import CharacterSpec
from ...schemas.vision import VisionImageInput
from ..base import CancellationToken
from .contract import ProviderCapability
from .remote_base import IRemote3DClient, RemoteTaskError, RemoteTaskInfo


class HunyuanClientError(RemoteTaskError):
    """Raised when the Hunyuan runtime API is unreachable or errors."""


class HunyuanEmbeddedClient(IRemote3DClient):
    id = "hunyuan-embedded"

    def __init__(self, base_url: str = "", token: str = ""):
        self._base_url = (base_url or "http://127.0.0.1:8081").rstrip("/")
        self._token = token or ""
        self._validate_localhost(self._base_url)

    @staticmethod
    def _validate_localhost(base_url: str) -> None:
        if "127.0.0.1" not in base_url and "localhost" not in base_url:
            raise HunyuanClientError("Hunyuan runtime 只允许 127.0.0.1")

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def set_runtime_endpoint(self, base_url: str, token: str) -> None:
        self._validate_localhost(base_url)
        self._base_url = base_url.rstrip("/")
        self._token = token or ""

    def capability(self) -> ProviderCapability:
        # The official Hunyuan API has NO cancel endpoint and NO real progress.
        # We report the truth (supportsCancel=False, supportsProgress=False);
        # the wrapper provides process-level cancellation and coarse status.
        return ProviderCapability(
            mode="local",
            gpu_required=True,
            max_references=4,
            output_format="glb",
            supports_cancel=False,
            supports_timeout=True,
            kind="real",
        )

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _request_json(self, method: str, path: str, body: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
        if not self._token:
            raise HunyuanClientError("Hunyuan runtime 未配置 token（未启动）")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self._url(path), data=data, method=method)
        req.add_header("X-AIVCS-Token", self._token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw or b"{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise HunyuanClientError(f"Hunyuan runtime HTTP {exc.code}: {raw}") from exc
        except urllib.error.URLError as exc:
            raise HunyuanClientError(f"Hunyuan runtime 连接失败：{exc.reason}") from exc

    @staticmethod
    def _to_remote_task(uid: str, status: str, progress: float, message: str = "", error: str | None = None) -> RemoteTaskInfo:
        return RemoteTaskInfo(
            task_id=uid,
            status=status,
            progress=progress,
            message=message,
            error=error,
        )

    async def create_task(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        cancel_event: CancellationToken | None = None,
        runtime_id: str | None = None,
    ) -> RemoteTaskInfo:
        # Hunyuan needs the reference image as base64 PNG. The renderer sends
        # references as data URLs; we pass the first one through (rembg handles
        # background removal on the official server side).
        image_b64 = ""
        for ref in references:
            if ref.data_url and "," in ref.data_url:
                image_b64 = ref.data_url.split(",", 1)[1]
                break
        if not image_b64:
            raise HunyuanClientError("Hunyuan runtime 需要至少一张参考图（image）")

        params = {
            "image": image_b64,
            "type": "glb",
            "num_inference_steps": 5,
            "octree_resolution": 380,
            "guidance_scale": 5.0,
        }
        status, payload = self._request_json("POST", "/send", params, timeout=30.0)
        if status != 200 or "uid" not in payload:
            raise HunyuanClientError(f"create_task 失败（HTTP {status}）：{payload}")
        uid = str(payload["uid"])
        return self._to_remote_task(uid, "queued", 0.0, "Hunyuan 任务已提交")

    async def poll_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> RemoteTaskInfo:
        if cancel_event is not None and cancel_event.is_cancelled:
            return self._to_remote_task(task_id, "cancelled", 0.0, "已取消（进程级）")
        status, payload = self._request_json("GET", f"/status/{task_id}", timeout=60.0)
        if status != 200:
            raise HunyuanClientError(f"poll_task 失败（HTTP {status}）")
        state = str(payload.get("status", "processing"))
        if state == "completed":
            return self._to_remote_task(task_id, "done", 1.0, "Hunyuan 生成完成")
        return self._to_remote_task(task_id, "running", 0.0, "Hunyuan 生成中")

    async def cancel_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> None:
        # The official Hunyuan API has no cancel endpoint. Cancellation is
        # process-level (Runtime Manager terminates the process). We never fake
        # an ack; the caller (RealAIImage3DProvider) treats user cancel as a
        # ProviderCancelledError regardless of this method.
        return

    async def download_model(
        self,
        task_id: str,
        model_url: str,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        # /status returns the completed GLB as base64 in model_base64.
        status, payload = self._request_json("GET", f"/status/{task_id}", timeout=60.0)
        if status != 200 or payload.get("status") != "completed":
            raise HunyuanClientError("模型输出未就绪")
        b64 = payload.get("model_base64", "")
        if not b64:
            raise HunyuanClientError("模型输出缺少 model_base64")
        try:
            return base64.b64decode(b64)
        except Exception as exc:  # noqa: BLE001
            raise HunyuanClientError(f"模型输出解码失败：{exc}") from exc
