"""Embedded AI 3D Runtime client (Multi AI 3D Runtime Manager - Phase 2).

Implements the IRemote3DClient seam for a local AI 3D runtime that AIVCS
manages. Phase 2 wires the real localhost HTTP protocol (random token in
X-AIVCS-Token header) to the Runtime Manager process. It does NOT run real AI
inference - the Dummy runtime validates the pipeline end-to-end.

Protocol:
    127.0.0.1 HTTP only, token via X-AIVCS-Token header:
        GET  /health
        POST /task                 -> { "taskId", "status" }
        GET  /task/{id}            -> RemoteTaskInfo payload
        POST /task/{id}/cancel     -> { "cancelled": true }
        GET  /task/{id}/output     -> GLB bytes

Security:
  - no shell, no command construction from user input;
  - never accepts an arbitrary executable path;
  - only talks to the Runtime Manager-provided localhost endpoint;
  - all communication bound to 127.0.0.1.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ...schemas.character import CharacterSpec
from ...schemas.vision import VisionImageInput
from ..base import CancellationToken
from .contract import ProviderCapability
from .remote_base import IRemote3DClient, RemoteTaskError, RemoteTaskInfo


class EmbeddedClientError(RemoteTaskError):
    """Raised when the embedded runtime is unavailable or unreachable."""


class EmbeddedClient(IRemote3DClient):
    id = "embedded-ai-3d"

    def __init__(self, base_url: str = "", token: str = ""):
        # Only allow localhost. Reject anything else.
        self._base_url = (base_url or "http://127.0.0.1:18321").rstrip("/")
        self._token = token or ""
        self._validate_localhost(self._base_url)

    @staticmethod
    def _validate_localhost(base_url: str) -> None:
        if "127.0.0.1" not in base_url and "localhost" not in base_url:
            raise EmbeddedClientError("embedded runtime 只允许 127.0.0.1")

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def set_runtime_endpoint(self, base_url: str, token: str) -> None:
        """Bind to a Runtime Manager-provided endpoint + token."""
        self._validate_localhost(base_url)
        self._base_url = base_url.rstrip("/")
        self._token = token or ""

    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            mode="local",
            gpu_required=True,
            max_references=4,
            output_format="glb",
            supports_cancel=True,
            supports_timeout=True,
            kind="real",
        )

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | bytes]:
        if not self._token:
            raise EmbeddedClientError("embedded runtime 未配置 token（未启动）")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self._url(path), data=data, method=method)
        req.add_header("X-AIVCS-Token", self._token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.status == 200 and path.endswith("/output"):
                    return resp.status, raw
                return resp.status, json.loads(raw or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise EmbeddedClientError(f"embedded runtime HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise EmbeddedClientError(f"embedded runtime 连接失败：{exc.reason}") from exc

    @staticmethod
    def _to_remote_task(payload: dict) -> RemoteTaskInfo:
        return RemoteTaskInfo(
            task_id=str(payload.get("taskId", "")),
            status=str(payload.get("status", "unknown")),
            progress=float(payload.get("progress", 0.0) or 0.0),
            message=str(payload.get("message", "")),
            error=payload.get("error"),
        )

    async def create_task(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        cancel_event: CancellationToken | None = None,
        runtime_id: str | None = None,
    ) -> RemoteTaskInfo:
        summary = getattr(spec, "name", "") if spec is not None else ""
        status, payload = self._request("POST", "/task", {"summary": summary})
        if status != 202:
            raise EmbeddedClientError(f"create_task 失败（HTTP {status}）")
        return self._to_remote_task(payload)

    async def poll_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> RemoteTaskInfo:
        status, payload = self._request("GET", f"/task/{task_id}")
        if status != 200:
            raise EmbeddedClientError(f"poll_task 失败（HTTP {status}）")
        return self._to_remote_task(payload)

    async def cancel_task(
        self,
        task_id: str,
        cancel_event: CancellationToken | None = None,
    ) -> None:
        status, _ = self._request("POST", f"/task/{task_id}/cancel")
        if status not in (200, 409):
            raise EmbeddedClientError(f"cancel_task 失败（HTTP {status}）")

    async def download_model(
        self,
        task_id: str,
        model_url: str,
        cancel_event: CancellationToken | None = None,
    ) -> bytes:
        status, payload = self._request("GET", f"/task/{task_id}/output")
        if status != 200 or not isinstance(payload, (bytes, bytearray)):
            raise EmbeddedClientError("下载模型失败：输出未就绪")
        return bytes(payload)
