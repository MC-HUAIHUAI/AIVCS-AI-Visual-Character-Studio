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
from pydantic import BaseModel, ConfigDict, Field

from .. import config

router = APIRouter(prefix="/api/v1/config")


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class VisionConfigRequest(_CamelModel):
    base_url: str = Field(default="", alias="baseUrl")
    model: str = ""
    api_key: str = Field(default="", alias="apiKey")


class External3DConfigRequest(_CamelModel):
    enabled: bool = False


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
        # Never return the apiKey; only report whether a key is present + source.
        "visionConfigured": bool(effective["api_key"]),
        "source": effective["source"],
    }


@router.post("/external3d")
async def set_external3d_enabled(req: External3DConfigRequest, x_aivcs_config_token: str | None = Header(default=None)):
    """Toggle external-3d availability (Phase 3-5B).

    Does NOT unregister the provider identity. When disabled, the external-3d
    adapter cannot run real generation and no network request is made. The apiKey
    is never part of this call or response.
    """
    _require_token(x_aivcs_config_token)
    config.set_runtime_external3d(req.enabled)
    return {
        "ok": True,
        "external3dEnabled": config.is_external3d_enabled(),
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
