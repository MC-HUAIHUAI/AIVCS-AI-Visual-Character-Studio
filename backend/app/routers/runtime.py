"""AI 3D Runtime API (Multi AI 3D Runtime Manager - Phase 2 / 3-C / 3-D / 3-I).

Read-only status + runtime process control (start/stop/health) + Runtime/Model
Package install state (download/verify/cancel/progress) + license acceptance +
read-only AI 3D settings (install dirs, download toggle).

Phase 3-D: `POST /runtime/{id}/install?kind=runtime|model` starts the package
install in a background thread; real network downloads are gated behind
AIVCS_AI3D_ALLOW_DOWNLOAD (off by default), so the default path reports an
explicit NOT_INSTALLED result instead of faking success. All localhost-only.
"""

from __future__ import annotations

import os
import threading

from fastapi import APIRouter, HTTPException, Query

from ..schemas.ai3d_runtime import Ai3DRuntimeManifest
from ..services.ai3d_runtime_manager import (
    ALLOW_DOWNLOAD_ENV,
    MANIFESTS_DIR_ENV,
    PYTHON_INTERPRETER,
    USERDATA_ENV,
    _real_download_allowed,
    cancel_package_install,
    detect_hardware,
    hardware_to_dict,
    install_base,
    install_package,
    install_progress,
    list_runtimes,
    manifests_dir,
    runtime_health,
    runtime_status,
    set_license_accepted,
    start_runtime,
    stop_runtime,
    verify_downloaded_package,
    verify_package,
    load_manifests,
)

router = APIRouter(prefix="/api/v1")


@router.get("/runtime")
async def get_runtimes():
    """Return all discovered AI 3D runtimes with dynamic status."""
    return {"runtimes": list_runtimes()}


@router.get("/ai3d/settings")
async def get_ai3d_settings():
    """Read-only AI 3D settings for the Settings UI.

    Exposes install/model/runtime/manifest directories and the real-download
    toggle state (env-gated, off by default). Never exposes runtime tokens,
    secrets, or runtime process internals - the renderer only reads these paths
    for display and NEVER touches the runtime process/filesystem directly.
    """
    base = install_base()
    return {
        "installBase": str(base),
        "modelsDir": str(base / "models"),
        "runtimesDir": str(base / "runtimes"),
        "manifestsDir": str(manifests_dir()),
        "allowDownload": _real_download_allowed(),
        "allowDownloadEnv": os.environ.get(ALLOW_DOWNLOAD_ENV, ""),
        "userDataEnv": os.environ.get(USERDATA_ENV),
        "manifestsDirEnv": os.environ.get(MANIFESTS_DIR_ENV),
        "pythonInterpreter": PYTHON_INTERPRETER,
    }


@router.get("/system/hardware")
async def get_hardware():
    """Return current machine hardware capability (unknown-safe)."""
    return hardware_to_dict(detect_hardware())


@router.post("/runtime/{runtime_id}/start")
async def start_runtime_api(runtime_id: str):
    result = start_runtime(runtime_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error") or "runtime 启动失败")
    return result


@router.post("/runtime/{runtime_id}/stop")
async def stop_runtime_api(runtime_id: str):
    return stop_runtime(runtime_id)


@router.get("/runtime/{runtime_id}/health")
async def runtime_health_api(runtime_id: str):
    result = runtime_health(runtime_id)
    if not result["ok"]:
        raise HTTPException(status_code=503, detail=result.get("error") or "runtime 不健康")
    return result


@router.get("/runtime/{runtime_id}/status")
async def runtime_status_api(runtime_id: str):
    result = runtime_status(runtime_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result.get("error") or "runtime 未发现")
    return result


def _find_manifest(runtime_id: str) -> Ai3DRuntimeManifest:
    manifest = next((m for m in load_manifests() if m.id == runtime_id), None)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"runtime '{runtime_id}' 未发现")
    return manifest


@router.post("/runtime/{runtime_id}/install")
async def install_runtime_api(
    runtime_id: str,
    kind: str = Query(default="all", pattern="^(all|runtime|model)$"),
):
    """Start the Runtime/Model Package install state machine (background thread).

    Real network downloads are disabled by default (AIVCS_AI3D_ALLOW_DOWNLOAD not
    set): the worker records an explicit NOT_INSTALLED result so the UI never
    shows a fake success. Progress is polled via GET .../install/progress.
    """
    manifest = _find_manifest(runtime_id)
    kinds = ("runtime", "model") if kind == "all" else (kind,)
    for k in kinds:
        if manifest.packages and not any(p.kind == k for p in manifest.packages):
            raise HTTPException(status_code=400, detail=f"runtime '{runtime_id}' 未声明 {k} package")

    def _worker() -> None:
        install_package(runtime_id, kind=kind, downloader=None)

    threading.Thread(target=_worker, daemon=True, name=f"ai3d-install-{runtime_id}-{kind}").start()
    return {"ok": True, "started": True, "kind": kind, "runtimeId": runtime_id}


@router.post("/runtime/{runtime_id}/install/cancel")
async def cancel_install_api(
    runtime_id: str,
    kind: str = Query(default="all", pattern="^(all|runtime|model)$"),
):
    """Request cancellation of an in-flight package download."""
    return cancel_package_install(runtime_id, kind)


@router.get("/runtime/{runtime_id}/install/progress")
async def install_progress_api(runtime_id: str):
    """Per-kind install progress (download percent / size / speed / ETA)."""
    return install_progress(runtime_id)


@router.post("/runtime/{runtime_id}/license/accept")
async def accept_license_api(runtime_id: str, body: dict | None = None):
    """Record explicit license acceptance (before install/start is allowed)."""
    _find_manifest(runtime_id)
    accepted = bool((body or {}).get("accepted", True))
    return set_license_accepted(runtime_id, accepted)


@router.get("/runtime/{runtime_id}/verify")
async def verify_runtime_api(runtime_id: str, kind: str = Query(default="all", pattern="^(all|runtime|model)$")):
    """Verify a downloaded Runtime/Model Package on disk (checksum/size/manifest/license)."""
    manifest = _find_manifest(runtime_id)
    if not manifest.packages:
        return verify_downloaded_package(manifest)
    results = []
    for k in ("runtime", "model"):
        if kind != "all" and kind != k:
            continue
        pkg = next((p for p in manifest.packages if p.kind == k), None)
        if pkg is None:
            continue
        result = verify_package(manifest, pkg)
        results.append({"kind": k, **result})
    ok = all(r["ok"] for r in results)
    return {"ok": ok, "results": results, "state": "installed" if ok else "failed"}
