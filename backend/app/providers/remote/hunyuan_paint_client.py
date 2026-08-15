"""Hunyuan3D-2 Paint Runtime client (Phase 3-H).

Extends the shape `HunyuanEmbeddedClient` for the OFFICIAL texture/paint path:
the same official `api_server.py` run with `--enable_tex --tex_model_path
tencent/Hunyuan3D-2` accepts `texture: true` (and optionally a base64 `mesh`
for re-texturing an existing GLB) and returns a TEXTURED GLB through the same
`/send` + `/status/{uid}` protocol.

    create_task   -> POST /send {"image": ..., "texture": true, "mesh": ...?}
    poll_task     -> GET /status/{uid}
    download_model-> decode model_base64 (textured GLB)

Capability: texture supported (kind=paint). Still localhost-only, token via
X-AIVCS-Token, no shell. Cancellation stays process-level (official API has no
cancel) - never faked.

Paint inference runs in the SEPARATE local Paint Runtime process; AIVCS only
talks to it over 127.0.0.1. The AIVCS backend never runs paint inference.
"""

from __future__ import annotations

import base64

from ...schemas.character import CharacterSpec
from ...schemas.vision import VisionImageInput
from ..base import CancellationToken
from .contract import ProviderCapability
from .hunyuan_client import HunyuanEmbeddedClient
from .remote_base import RemoteTaskInfo


class HunyuanPaintClient(HunyuanEmbeddedClient):
    id = "hunyuan-paint"

    def __init__(self, base_url: str = "", token: str = ""):
        super().__init__(base_url, token)
        self._paint_mesh: bytes | None = None

    def set_paint_mesh(self, glb_bytes: bytes | None) -> None:
        """Optionally re-texture an existing shape GLB (official `mesh` param)."""
        self._paint_mesh = glb_bytes

    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            mode="local",
            gpu_required=True,
            max_references=4,
            output_format="glb",
            supports_cancel=False,
            supports_timeout=True,
            kind="real",
        )

    async def create_task(
        self,
        spec: CharacterSpec,
        references: list[VisionImageInput],
        cancel_event: CancellationToken | None = None,
        runtime_id: str | None = None,
    ) -> RemoteTaskInfo:
        image_b64 = ""
        for ref in references:
            if ref.data_url and "," in ref.data_url:
                image_b64 = ref.data_url.split(",", 1)[1]
                break
        if not image_b64:
            raise RuntimeError("Hunyuan Paint runtime 需要至少一张参考图（image）")

        params = {
            "image": image_b64,
            "type": "glb",
            "texture": True,
            "num_inference_steps": 5,
            "octree_resolution": 380,
            "guidance_scale": 5.0,
        }
        if self._paint_mesh:
            params["mesh"] = base64.b64encode(self._paint_mesh).decode("ascii")

        status, payload = self._request_json("POST", "/send", params, timeout=30.0)
        if status != 200 or "uid" not in payload:
            raise RuntimeError(f"create_task 失败（HTTP {status}）：{payload}")
        uid = str(payload["uid"])
        return self._to_remote_task(uid, "queued", 0.0, "Hunyuan Paint 任务已提交")
