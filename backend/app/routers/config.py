"""Local runtime config endpoint (Phase 3-5A).

Bound to 127.0.0.1 only (uvicorn --host 127.0.0.1). POST only. Guarded by a
random per-process token so other local processes cannot configure providers
without authorization. The apiKey is accepted in the request body, never
logged, never returned in any response, and no external network request is
made from this endpoint.

Used by the Electron main process to push App Settings (Vision / External 3D)
into the backend runtime config. Env vars still take priority over runtime
overrides.
"""

from __future__ import annotations

import json
import urllib.request

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .. import config

router = APIRouter(prefix="/api/v1/config")


class VisionConfigRequest(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""


def _require_token(x_aivcs_config_token: str | None) -> None:
    if not config.LOCAL_CONFIG_TOKEN:
        return
    if x_aivcs_config_token != config.LOCAL_CONFIG_TOKEN:
        raise HTTPException(status_code=403, detail="unauthorized")


@router.post("/vision")
async def set_vision_config(req: VisionConfigRequest, x_aivcs_config_token: str | None = Header(default=None)):
    _require_token(x_aivcs_config_token)
    config.set_runtime_vision(base_url=req.base_url, model=req.model, api_key=req.api_key)
    effective = config.effective_kimi_config()
    return {
        "ok": True,
        # Never return the apiKey; only report whether a key is present.
        "visionConfigured": bool(effective["api_key"]),
        "source": "env" if config.KIMI_API_KEY else "runtime",
    }


@router.post("/vision/test")
async def test_vision_config(x_aivcs_config_token: str | None = Header(default=None)):
    """User-initiated connectivity test (only path that may touch the network).

    Uses the effective Kimi config (env priority, runtime fallback) to perform a
    minimal authenticated probe. The apiKey is never returned in the response.
    """
    _require_token(x_aivcs_config_token)
    eff = config.effective_kimi_config()
    if not eff["api_key"]:
        raise HTTPException(status_code=400, detail="Kimi API Key 未配置")
    url = eff["base_url"].rstrip("/") + "/models"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {eff['api_key']}")
        with urllib.request.urlopen(req, timeout=config.KIMI_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
        return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Kimi 测试连接失败（HTTP {exc.code}）") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=502, detail="Kimi 测试连接超时") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            raise HTTPException(status_code=502, detail="Kimi 测试连接超时") from exc
        raise HTTPException(status_code=502, detail="Kimi 测试连接失败") from exc
