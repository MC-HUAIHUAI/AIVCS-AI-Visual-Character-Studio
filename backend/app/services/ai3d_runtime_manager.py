"""AI 3D Runtime Manager (Multi AI 3D Runtime Manager - Phase 1/2).

Phase 1: discovery / manifest loading / install-state / path validation /
hardware-compatibility / runtime-status / health abstraction.
Phase 2: real process lifecycle - start/stop/health/status for a local runtime
executable (localhost HTTP + random token). Does NOT run real AI inference.

    State machine (explicit, non-contradictory):

    DISCOVERED   - manifest loaded + paths validated, but not yet classified
    NOT_INSTALLED- neither executable nor model present
    PARTIAL      - one of executable/model present, the other missing
    INSTALLED    - both present (hardware may still be incompatible)
    INCOMPATIBLE - installed=true AND hardware check failed (installed=true AND
                   compatible=false is legal)
    READY        - installed + compatible + health check passes
    RUNNING      - runtime process started and healthy
    STOPPED      - runtime process stopped
    FAILED       - start/health failed or process crashed

    Package install state machine (Phase 3-C / 3-D):

    NOT_INSTALLED -> DOWNLOADING -> VERIFYING -> INSTALLED -> READY / INCOMPATIBLE
         |               |             |                |
         +---> FAILED <--+             +---> PARTIAL <--+
    (cancel) -> NOT_INSTALLED

    Runtime Package and Model Package are INDEPENDENT install units. READY only
    when both are installed AND hardware-compatible. When only one of them is
    installed the state is PARTIAL; a failed download stays FAILED and is never
    presented as INSTALLED.

    Install state is computed from on-disk file presence, NEVER written back to the
    manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Callable

from ..schemas.ai3d_runtime import (
    Ai3DRuntimeManifest,
    RuntimeArtifact,
    RuntimePackage,
)
from .ai3d_downloader import (
    ArtifactDownloadCancelled,
    ArtifactDownloadError,
    download_artifact,
)

# Where manifests live (repo or packaged resources).
MANIFESTS_DIR_ENV = "AIVCS_AI3D_MANIFESTS_DIR"
# Base dir that manifest relative paths resolve against.
AI3D_RESOURCES_ENV = "AIVCS_AI3D_RESOURCES_DIR"
# userData override for downloaded Runtime/Model packages (Phase 3-D).
USERDATA_ENV = "AIVCS_AI3D_USERDATA_DIR"
# Gate for the REAL network downloader (off by default: no external requests).
ALLOW_DOWNLOAD_ENV = "AIVCS_AI3D_ALLOW_DOWNLOAD"
# Lower bound for runtime localhost port allocation.
RUNTIME_PORT_BASE = 18321

# Which executable interpreter to use when the runtime is a script (.py).
# Phase 2 test runtime is a Python script; real runtimes would be .exe.
PYTHON_INTERPRETER = os.environ.get("AIVCS_AI3D_PYTHON", "python")



class InstallState(str, Enum):
    DISCOVERED = "discovered"
    NOT_INSTALLED = "not-installed"
    PARTIAL = "partial"
    INSTALLED = "installed"


class PackageInstallState(str, Enum):
    """Runtime/Model Package install state (Phase 3-C).

    Explicit state machine for the Runtime Package / Model Package download +
    verify flow. NOT_INSTALLED -> DOWNLOADING -> VERIFYING -> INSTALLED, with
    PARTIAL / FAILED / INCOMPATIBLE as explicit terminal/blocked states. READY
    is the combined "installed + hardware-compatible" state used by the UI.

    These states are computed/derived from on-disk presence + verification
    results; they are NEVER written back into a manifest.
    """

    NOT_INSTALLED = "not-installed"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLED = "installed"
    PARTIAL = "partial"
    FAILED = "failed"
    INCOMPATIBLE = "incompatible"
    READY = "ready"


class RuntimeStatus(str, Enum):
    DISCOVERED = "discovered"
    NOT_INSTALLED = "not-installed"
    PARTIAL = "partial"
    INSTALLED = "installed"
    INCOMPATIBLE = "incompatible"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"


# Backends we can currently drive for real. The detection report adds `cuda`
# only when an NVIDIA GPU is found; AMD/Intel backends are NOT claimed today
# (extension point: future hip/dx12/metal detection populates this list).
KNOWN_GPU_BACKENDS: tuple[str, ...] = ("cuda",)
# DXGI PCI vendor ids (NVIDIA/AMD/Intel) -> normalized vendor.
_DXGI_VENDOR_IDS: dict[int, str] = {0x10DE: "nvidia", 0x1002: "amd", 0x8086: "intel"}


@dataclass(frozen=True)
class HardwareCapability:
    os_name: str
    architecture: str
    ram_mb: int
    gpu_vendor: str  # "nvidia" | "amd" | "intel" | "unknown"
    gpu_name: str
    vram_mb: int | None  # None = unknown
    available_backends: list[str] = field(default_factory=list)
    # Phase 3-I: DXGI PCI ids (honest detection; None when undetected).
    gpu_vendor_id: int | None = None
    gpu_device_id: int | None = None


@dataclass
class RuntimeInfo:
    id: str
    name: str
    version: str
    model_version: str
    install_state: str
    compatible: bool
    status: str
    capabilities: dict
    hardware_requirements: dict
    license: dict
    manifest_path: str = ""
    download: dict | None = None
    package_state: str = ""
    # Phase 3-D: independent Runtime/Model package states + license acceptance.
    runtime_package_state: str = ""
    model_package_state: str = ""
    license_accepted: bool = False
    license_requires_acceptance: bool = True
    # Phase 3-I: declared input/output types (e.g. ["image"] -> ["glb"]).
    input_types: list = field(default_factory=list)
    output_types: list = field(default_factory=list)


def _candidate_roots() -> list[Path]:
    """Base dirs that manifest relative paths resolve against."""
    env = os.environ.get(AI3D_RESOURCES_ENV)
    if env:
        return [Path(env)]
    # Repo layout: <repo>/resources/ai/3d/
    here = Path(__file__).resolve()
    repo = here.parent.parent.parent.parent  # backend/app/services -> repo root
    return [repo / "resources" / "ai" / "3d"]


def manifests_dir() -> Path:
    env = os.environ.get(MANIFESTS_DIR_ENV)
    if env:
        return Path(env)
    roots = _candidate_roots()
    # manifests live under <root>/manifests
    return roots[0] / "manifests"


def install_base() -> Path:
    """Base directory that downloaded Runtime/Model packages land in.

    Phase 3-D: downloads go to userData/ai/3d (never app.asar). When
    AIVCS_AI3D_USERDATA_DIR is set (Electron main sets it to app.getPath('userData'))
    the base is `<userData>/ai/3d`. Otherwise it falls back to the repo/resources
    root so dev + tests stay hermetic.
    """
    env = os.environ.get(USERDATA_ENV)
    if env:
        return Path(env) / "ai" / "3d"
    roots = _candidate_roots()
    return roots[0] if roots else Path.cwd()


def _resolution_roots() -> list[Path]:
    """Allow-list roots searched when resolving installed files on disk.

    Searches the manifest/resources root first (dev dummy runtime), then the
    userData install base (downloaded packages). Never trusts arbitrary paths.
    """
    roots = list(_candidate_roots())
    base = install_base()
    if base not in roots:
        roots.append(base)
    return roots


def _resolve_paths(manifest: Ai3DRuntimeManifest) -> dict[str, Path | None]:
    """Resolve executable/model/license/notice absolute paths against allow-list
    roots. Returns None when the path does not exist on disk. Rejects
    absolute/`..` (schema already validates; double-check here).

    `model_path` is a MODEL DIRECTORY (weights folder) so `exists()` is used for
    it; executable/license/notice are files (`is_file()`). A bare directory must
    never count as an installed executable.
    """
    roots = _resolution_roots()
    result: dict[str, Path | None] = {}
    for key, root_path, must_file in (
        ("executable", PurePosixPath("runtimes"), True),
        ("model_path", PurePosixPath("models"), False),
        ("license", PurePosixPath("runtimes"), True),
        ("notice", PurePosixPath("runtimes"), True),
    ):
        raw = getattr(manifest.files, key)
        if not raw:
            result[key] = None
            continue
        rel = PurePosixPath(raw)
        if rel.is_absolute() or ".." in rel.parts:
            result[key] = None
            continue
        found: Path | None = None
        for root in roots:
            candidate = root / root_path / rel
            ok = candidate.is_file() if must_file else candidate.exists()
            if ok:
                found = candidate
                break
        result[key] = found
    return result


def load_manifests(manifests: Path | None = None) -> list[Ai3DRuntimeManifest]:
    """Discover + parse all manifests. Invalid manifests are skipped (logged)."""
    directory = manifests or manifests_dir()
    if not directory.exists():
        return []
    out: list[Ai3DRuntimeManifest] = []
    for f in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            out.append(Ai3DRuntimeManifest.model_validate(raw))
        except Exception:  # noqa: BLE001 - skip invalid manifests
            continue
    return out


def _license_files_present(manifest: Ai3DRuntimeManifest) -> bool:
    """True when every declared license/notice file exists on disk.

    A runtime without declared license/notice files is considered complete
    (nothing to verify). If the manifest declares them, their existence is part
    of the install-state check so a partial download never reports INSTALLED.
    """
    resolved = _resolve_paths(manifest)
    for key in ("license", "notice"):
        rel = getattr(manifest.files, key)
        if not rel:
            continue
        if resolved.get(key) is None:
            return False
    return True


def compute_install_state(manifest: Ai3DRuntimeManifest) -> InstallState:
    resolved = _resolve_paths(manifest)
    has_exe = resolved["executable"] is not None
    has_model = resolved["model_path"] is not None
    has_legal = _license_files_present(manifest)
    if has_exe and has_model and has_legal:
        return InstallState.INSTALLED
    if has_exe or has_model:
        return InstallState.PARTIAL
    return InstallState.NOT_INSTALLED


def hardware_compatible(manifest: Ai3DRuntimeManifest, hw: HardwareCapability) -> bool:
    """Hardware compatibility check (does NOT modify install state)."""
    req = manifest.hardware
    if req.requires_gpu and hw.gpu_vendor == "unknown":
        return False
    if req.requires_gpu and hw.vram_mb is None:
        return False
    if req.requires_gpu and hw.vram_mb is not None and hw.vram_mb < req.minimum_vram_mb:
        return False
    if hw.ram_mb and hw.ram_mb < req.minimum_ram_mb:
        return False
    if req.supported_os and f"{hw.os_name}-{hw.architecture}" not in req.supported_os:
        return False
    # Backend match: CPU is always available (fallback); a GPU requirement
    # without a detected backend is handled above.
    if req.supported_backends:
        backends = set(hw.available_backends)
        if "cpu" in req.supported_backends:
            backends.add("cpu")
        if not backends.intersection(req.supported_backends):
            return False
    return True


def compute_status(manifest: Ai3DRuntimeManifest, hw: HardwareCapability) -> tuple[str, bool]:
    """Return (status, compatible). install + compat are independent.

    DOWNLOADING / VERIFYING are transient states recorded per-package during an
    in-flight install (never persisted); when absent they fall back to the
    on-disk derived state.
    """
    install = compute_install_state(manifest)
    compatible = hardware_compatible(manifest, hw)

    for kind in ("runtime", "model"):
        transient = _transient_states.get(_transient_key(manifest.id, kind))
        if transient in (RuntimeStatus.DOWNLOADING.value, RuntimeStatus.VERIFYING.value):
            return transient, compatible

    if install == InstallState.NOT_INSTALLED:
        return RuntimeStatus.NOT_INSTALLED.value, compatible
    if install == InstallState.PARTIAL:
        return RuntimeStatus.PARTIAL.value, compatible
    # INSTALLED
    if not compatible:
        return RuntimeStatus.INCOMPATIBLE.value, False
    return RuntimeStatus.READY.value, True


# Per-package transient install states (in-memory; not persisted). Key is
# "<runtime_id>:<kind>". Set while a download/verify is in flight so status shows
# DOWNLOADING / VERIFYING; cleared on completion/failure.
_transient_states: dict[str, str] = {}


def _transient_key(runtime_id: str, kind: str) -> str:
    return f"{runtime_id}:{kind}"


def build_runtime_info(manifest: Ai3DRuntimeManifest, hw: HardwareCapability) -> RuntimeInfo:
    status, compatible = compute_status(manifest, hw)
    return RuntimeInfo(
        id=manifest.id,
        name=manifest.name,
        version=manifest.version,
        model_version=manifest.model_version,
        install_state=compute_install_state(manifest).value,
        compatible=compatible,
        status=status,
        capabilities={
            "supportsCancel": manifest.capabilities.supports_cancel,
            "supportsProgress": manifest.capabilities.supports_progress,
            "supportsResume": manifest.capabilities.supports_resume,
            # Phase 3-G: texture/paint output capability (shape-only default).
            "texture": (
                {
                    "supported": manifest.capabilities.texture.supported,
                    "kind": manifest.capabilities.texture.kind,
                    "notes": manifest.capabilities.texture.notes,
                }
                if manifest.capabilities.texture is not None
                else {"supported": False, "kind": "none", "notes": "shape-only"}
            ),
        },
        hardware_requirements={
            "requiresGPU": manifest.hardware.requires_gpu,
            "minimumVRAMMB": manifest.hardware.minimum_vram_mb,
            "recommendedVRAMMB": manifest.hardware.recommended_vram_mb,
            "minimumRAMMB": manifest.hardware.minimum_ram_mb,
            "supportedOS": list(manifest.hardware.supported_os),
            "supportedBackends": list(manifest.hardware.supported_backends),
        },
        license={
            "id": manifest.license.id,
            "url": manifest.license.url,
            "modelSource": manifest.license.model_source,
            "modelSourceUrl": manifest.license.model_source_url,
            "noticeFile": manifest.license.notice_file,
            "territoryRestrictions": manifest.license.territory_restrictions,
            "commercialThreshold": manifest.license.commercial_threshold,
            "requiresAcceptance": manifest.license.requires_acceptance,
        },
        download={
            "kind": manifest.download.kind,
            "url": manifest.download.url,
            "sha256": manifest.download.sha256,
            "sizeBytes": manifest.download.size_bytes,
            "httpAllowed": manifest.download.http_allowed,
        } if manifest.download.url else None,
        package_state=package_state_for(manifest, hw).value,
        runtime_package_state=package_kind_state(manifest, "runtime", hw).value,
        model_package_state=package_kind_state(manifest, "model", hw).value,
        license_accepted=license_accepted(manifest.id),
        license_requires_acceptance=manifest.license.requires_acceptance,
        input_types=list(manifest.input_types),
        output_types=list(manifest.output_types),
    )


def runtime_info_to_dict(info: RuntimeInfo) -> dict:
    """Serialize a RuntimeInfo to a camelCase JSON dict."""
    return {
        "id": info.id,
        "name": info.name,
        "version": info.version,
        "modelVersion": info.model_version,
        "installState": info.install_state,
        "compatible": info.compatible,
        "status": info.status,
        "capabilities": info.capabilities,
        "hardwareRequirements": info.hardware_requirements,
        "license": info.license,
        "download": info.download,
        "packageState": info.package_state,
        "runtimePackageState": info.runtime_package_state,
        "modelPackageState": info.model_package_state,
        "licenseAccepted": info.license_accepted,
        "licenseRequiresAcceptance": info.license_requires_acceptance,
        "inputTypes": list(info.input_types),
        "outputTypes": list(info.output_types),
    }


def list_runtimes(hw: HardwareCapability | None = None) -> list[dict]:
    """Return all discovered runtimes with dynamic status (Phase 1, no spawn)."""
    hw = hw or detect_hardware()
    return [runtime_info_to_dict(build_runtime_info(m, hw)) for m in load_manifests()]


def any_installed_runtime() -> bool:
    """True when at least one discovered runtime is installed AND compatible."""
    hw = detect_hardware()
    for m in load_manifests():
        info = build_runtime_info(m, hw)
        if info.install_state == InstallState.INSTALLED.value and info.compatible:
            return True
    return False


# --------------------------------------------------------------------------- #
# Phase 3-C / 3-D: Runtime/Model Package install state + verification + download.
#
# Phase 3-C introduced the state machine + pluggable downloader; no real network.
# Phase 3-D formalizes Runtime Package and Model Package as INDEPENDENT install
# units (manifest `packages[]` with `artifacts[]`), adds a real secure downloader
# (ai3d_downloader.py: redirect-host restriction, HTTPS-by-default, atomic rename,
# cancel), a user-visible progress feed, and license acceptance gating.
#
# Real network I/O is gated behind AIVCS_AI3D_ALLOW_DOWNLOAD (off by default):
# the default runtime path never performs external requests. Tests inject a fake
# `fetcher`/`downloader` (or a local 127.0.0.1 fake server) directly.
# --------------------------------------------------------------------------- #


def _real_download_allowed() -> bool:
    return os.environ.get(ALLOW_DOWNLOAD_ENV, "").strip().lower() in ("1", "true", "yes")


# Progress + cancel bookkeeping for in-flight installs (in-memory; not persisted).
_install_lock = RLock()
_progress: dict[tuple[str, str], dict] = {}
_cancel_events: dict[tuple[str, str], threading.Event] = {}


def _idle_progress() -> dict:
    return {
        "status": "idle",
        "percent": 0,
        "downloadedBytes": 0,
        "totalBytes": 0,
        "speedBps": 0,
        "etaSeconds": None,
        "error": "",
    }


def _progress_state(runtime_id: str, kind: str) -> dict:
    with _install_lock:
        return _progress.setdefault((runtime_id, kind), _idle_progress())


def install_progress(runtime_id: str) -> dict:
    """Current per-kind install progress for the UI (idle when nothing running)."""
    with _install_lock:
        return {
            "runtime": dict(_progress.get((runtime_id, "runtime"), _idle_progress())),
            "model": dict(_progress.get((runtime_id, "model"), _idle_progress())),
        }


def cancel_package_install(runtime_id: str, kind: str = "all") -> dict:
    """Request cancellation of an in-flight package download (best-effort)."""
    kinds = ("runtime", "model") if kind == "all" else (kind,)
    cancelled: list[str] = []
    with _install_lock:
        for k in kinds:
            ev = _cancel_events.get((runtime_id, k))
            if ev is not None:
                ev.set()
                cancelled.append(k)
    return {"ok": True, "cancelled": bool(cancelled), "kinds": cancelled}


class _ProgressTracker:
    """Computes percent / speed / ETA from cumulative downloaded bytes."""

    def __init__(self, grand_total: int):
        self.grand = max(1, grand_total)
        self.done = 0
        self._t0 = time.monotonic()
        self._last_t = self._t0
        self._last_done = 0
        self._speed = 0.0

    def add(self, delta: int) -> None:
        self.done += delta
        now = time.monotonic()
        dt = now - self._last_t
        if dt >= 0.25:
            inst = (self.done - self._last_done) / dt
            self._speed = inst if self._speed <= 0 else 0.7 * self._speed + 0.3 * inst
            self._last_t = now
            self._last_done = self.done

    def snapshot(self) -> tuple[float, int, float, float | None]:
        pct = min(1.0, self.done / self.grand)
        remaining = max(0, self.grand - self.done)
        eta = remaining / self._speed if self._speed > 0 else None
        return pct, self.done, self._speed, eta


def package_state_for(manifest: Ai3DRuntimeManifest, hw: HardwareCapability | None = None) -> PackageInstallState:
    """Derive the combined Runtime/Model Package install state (never written back).

    Priority: transient (download/verify) -> on-disk presence -> hardware.
    With `packages[]` declared, BOTH the runtime and model package must be
    INSTALLED before READY / INCOMPATIBLE; one installed alone is PARTIAL.
    """
    for kind in ("runtime", "model"):
        transient = _transient_states.get(_transient_key(manifest.id, kind))
        if transient == RuntimeStatus.DOWNLOADING.value:
            return PackageInstallState.DOWNLOADING
        if transient == RuntimeStatus.VERIFYING.value:
            return PackageInstallState.VERIFYING

    hw = hw or detect_hardware()

    if manifest.packages:
        rt = package_kind_state(manifest, "runtime", hw)
        md = package_kind_state(manifest, "model", hw)
        if rt == PackageInstallState.INSTALLED and md == PackageInstallState.INSTALLED:
            if not hardware_compatible(manifest, hw):
                return PackageInstallState.INCOMPATIBLE
            return PackageInstallState.READY
        if rt == PackageInstallState.INSTALLED or md == PackageInstallState.INSTALLED:
            return PackageInstallState.PARTIAL
        return PackageInstallState.NOT_INSTALLED

    install = compute_install_state(manifest)
    if install == InstallState.INSTALLED:
        if not hardware_compatible(manifest, hw):
            return PackageInstallState.INCOMPATIBLE
        return PackageInstallState.READY
    if install == InstallState.PARTIAL:
        return PackageInstallState.PARTIAL
    return PackageInstallState.NOT_INSTALLED


def package_kind_state(manifest: Ai3DRuntimeManifest, kind: str, hw: HardwareCapability | None = None) -> PackageInstallState:
    """Install state of ONE package kind (runtime | model), independently."""
    transient = _transient_states.get(_transient_key(manifest.id, kind))
    if transient == RuntimeStatus.DOWNLOADING.value:
        return PackageInstallState.DOWNLOADING
    if transient == RuntimeStatus.VERIFYING.value:
        return PackageInstallState.VERIFYING

    pkgs = [p for p in manifest.packages if p.kind == kind]
    if pkgs:
        installed = [_package_installed(manifest, p) for p in pkgs]
        if all(installed):
            return PackageInstallState.INSTALLED
        if any(installed):
            return PackageInstallState.PARTIAL
        return PackageInstallState.NOT_INSTALLED

    # Legacy (no `packages[]`): derive from on-disk file presence.
    resolved = _resolve_paths(manifest)
    if kind == "runtime":
        return PackageInstallState.INSTALLED if resolved["executable"] is not None else PackageInstallState.NOT_INSTALLED
    return PackageInstallState.INSTALLED if resolved["model_path"] is not None else PackageInstallState.NOT_INSTALLED


def _package_dir(manifest: Ai3DRuntimeManifest, pkg: RuntimePackage) -> Path | None:
    """Absolute install dir for a package under the allow-list root (userData/ai/3d)."""
    if pkg.kind not in ("runtime", "model"):
        return None
    rel = PurePosixPath(pkg.install_dir or "")
    if rel.is_absolute() or ".." in rel.parts:
        return None
    sub = "runtimes" if pkg.kind == "runtime" else "models"
    return install_base() / sub / rel


def _artifact_target(pkg_dir: Path, artifact: RuntimeArtifact) -> Path | None:
    rel = PurePosixPath(artifact.path or "")
    if rel.is_absolute() or ".." in rel.parts or "\\" in str(rel):
        return None
    return pkg_dir / rel


def _package_installed(manifest: Ai3DRuntimeManifest, pkg: RuntimePackage) -> bool:
    """Quick on-disk presence check for a package (no hashing on status polls).

    The runtime package additionally requires the executable + license/notice
    files; a bare directory never counts as installed.
    """
    if pkg.kind == "runtime":
        resolved = _resolve_paths(manifest)
        if resolved["executable"] is None:
            return False
        if not _license_files_present(manifest):
            return False
    pkg_dir = _package_dir(manifest, pkg)
    if pkg_dir is None:
        return False
    for artifact in pkg.artifacts:
        target = _artifact_target(pkg_dir, artifact)
        if target is None or not target.is_file():
            return False
        if artifact.size_bytes and target.stat().st_size != artifact.size_bytes:
            return False
    return True


def verify_package(manifest: Ai3DRuntimeManifest, pkg: RuntimePackage) -> dict:
    """Full verification of an installed package (SHA-256 + size + presence).

    Returns {ok, errors, state}. INSTALLED only when every artifact matches its
    declared size AND sha256 AND (for the runtime package) LICENSE/NOTICE exist.
    """
    errors: list[str] = []
    pkg_dir = _package_dir(manifest, pkg)
    if pkg_dir is None:
        errors.append(f"{pkg.kind} 包 installDir 非法")
    else:
        for artifact in pkg.artifacts:
            target = _artifact_target(pkg_dir, artifact)
            if target is None:
                errors.append(f"artifact 路径非法：{artifact.path}")
                continue
            if not target.is_file():
                errors.append(f"artifact 缺失：{artifact.path}")
                continue
            if artifact.size_bytes and target.stat().st_size != artifact.size_bytes:
                errors.append(f"{artifact.path} 大小不匹配：期望 {artifact.size_bytes}，实际 {target.stat().st_size}")
            if artifact.sha256:
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                if actual != artifact.sha256:
                    errors.append(f"{artifact.path} SHA-256 校验失败")
    if pkg.kind == "runtime" and not _license_files_present(manifest):
        errors.append("LICENSE/NOTICE 文件缺失（或与 manifest 声明不一致）")

    ok = not errors
    return {
        "ok": ok,
        "errors": errors,
        "state": PackageInstallState.INSTALLED.value if ok else PackageInstallState.FAILED.value,
    }


def resolve_package_target(manifest: Ai3DRuntimeManifest) -> Path | None:
    """Absolute target path for the legacy model download (under the model allow-root).

    The model directory is `manifest.files.model_path`; the download lands as
    `<model_dir>/<filename>` where the filename is taken from the download URL.
    Returns None when the manifest declares no download or paths are invalid.
    """
    if not manifest.download.url:
        return None
    rel = PurePosixPath(manifest.files.model_path)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    filename = PurePosixPath(manifest.download.url.split("?", 1)[0].rstrip("/")).name
    if not filename or filename in (".", ".."):
        filename = "model.bin"
    return install_base() / "models" / rel / filename


def verify_downloaded_package(manifest: Ai3DRuntimeManifest) -> dict:
    """Verify a downloaded Runtime/Model Package on disk (legacy single download).

    Checks (in order):
      1. declared model directory exists at the resolved allow-list path;
      2. when download is declared, the downloaded file (under the model dir)
         matches size + SHA-256;
      3. license/notice files exist (when declared).

    Pure / no network. Returns {ok, errors: [...], state}.
    """
    errors: list[str] = []
    resolved = _resolve_paths(manifest)

    model_dir = resolved.get("model_path")
    if model_dir is None:
        errors.append(f"模型目录不存在：{manifest.files.model_path}")
    elif manifest.download.url and manifest.download.size_bytes > 0:
        target = resolve_package_target(manifest)
        if target is None or not target.is_file():
            errors.append(f"下载的模型文件不存在：{manifest.files.model_path}")
        else:
            if target.stat().st_size != manifest.download.size_bytes:
                errors.append(
                    f"模型大小不匹配：期望 {manifest.download.size_bytes}，实际 {target.stat().st_size}"
                )
            if manifest.download.sha256:
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                if actual != manifest.download.sha256:
                    errors.append("模型 SHA-256 校验失败")

    if not _license_files_present(manifest):
        errors.append("LICENSE/NOTICE 文件缺失（或与 manifest 声明不一致）")

    ok = not errors
    return {
        "ok": ok,
        "errors": errors,
        "state": PackageInstallState.INSTALLED.value if ok else PackageInstallState.FAILED.value,
        "sha256": manifest.download.sha256,
        "sizeBytes": manifest.download.size_bytes,
    }


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write bytes to a temp file then atomically rename into place.

    A failed write never leaves a stale `.part` file behind (Phase 3-K).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.{secrets.token_hex(4)}.part"
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _install_package_one(
    manifest: Ai3DRuntimeManifest,
    kind: str,
    fetcher=None,
    downloader=None,
    cancel_event=None,
    on_progress: Callable[[float], None] | None = None,
) -> dict:
    """Install ONE package kind (runtime | model) with artifacts[].

    Download flow per artifact: manifest-declared URL -> temp file -> SHA-256 +
    size verified -> atomic rename. After all artifacts, `verify_package` runs
    (sha + size + manifest + LICENSE/NOTICE). Any failure -> FAILED / cancelled
    and the transient state is cleared; INSTALLED is never faked.
    """
    pkgs = [p for p in manifest.packages if p.kind == kind]
    if not pkgs:
        return _install_legacy_download(manifest, kind, fetcher, on_progress)

    key = _transient_key(manifest.id, kind)
    pkg = pkgs[0]

    if _package_installed(manifest, pkg):
        result = verify_package(manifest, pkg)
        return {
            "ok": result["ok"],
            "status": RuntimeStatus.INSTALLED.value if result["ok"] else RuntimeStatus.FAILED.value,
            "packageState": result["state"],
            "errors": result["errors"],
        }

    if fetcher is None and downloader is None and not _real_download_allowed():
        # Real downloads are disabled by default: report NOT_INSTALLED explicitly
        # so a caller can never mistake this for a successful install.
        return {
            "ok": False,
            "status": RuntimeStatus.NOT_INSTALLED.value,
            "packageState": PackageInstallState.NOT_INSTALLED.value,
            "error": f"{kind} 包未安装：需要下载官方包（自动下载未启用）",
        }

    pkg_dir = _package_dir(manifest, pkg)
    if pkg_dir is None:
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": f"{kind} 包 installDir 非法"}

    if cancel_event is None:
        cancel_event = threading.Event()
        with _install_lock:
            _cancel_events[(manifest.id, kind)] = cancel_event

    grand_total = sum(artifact.size_bytes for artifact in pkg.artifacts)
    tracker = _ProgressTracker(grand_total)
    state = _progress_state(manifest.id, kind)
    state.update(
        {
            "status": "downloading",
            "percent": 0,
            "downloadedBytes": 0,
            "totalBytes": grand_total,
            "speedBps": 0,
            "etaSeconds": None,
            "error": "",
        }
    )

    def _emit() -> None:
        pct, done, speed, eta = tracker.snapshot()
        state.update(
            {
                "status": "downloading",
                "percent": round(pct * 100, 1),
                "downloadedBytes": done,
                "speedBps": round(speed),
                "etaSeconds": eta,
            }
        )
        if on_progress is not None:
            on_progress(round(pct * 100, 1))

    _transient_states[key] = RuntimeStatus.DOWNLOADING.value
    try:
        for artifact in pkg.artifacts:
            if cancel_event.is_set():
                raise ArtifactDownloadCancelled("下载已取消")
            target = _artifact_target(pkg_dir, artifact)
            if target is None:
                raise ArtifactDownloadError(f"artifact 路径非法：{artifact.path}")
            if not artifact.url:
                raise ArtifactDownloadError(f"artifact '{artifact.path}' 未提供官方下载源")

            if fetcher is not None:
                result = fetcher(artifact.url, artifact.sha256, artifact.size_bytes, _emit)
                if not (result or {}).get("ok"):
                    raise ArtifactDownloadError((result or {}).get("error") or "下载失败")
                data = result.get("bytes")
                if data is None:
                    raise ArtifactDownloadError("下载结果缺少字节")
                _atomic_write_bytes(target, data)
                tracker.add(len(data))
                _emit()
            else:
                dl = downloader or download_artifact
                last = [0]

                def _cb(downloaded: int, _total_artifact: int) -> None:
                    tracker.add(max(0, downloaded - last[0]))
                    last[0] = downloaded
                    _emit()

                dl(
                    url=artifact.url,
                    dest_dir=str(pkg_dir),
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                    on_progress=_cb,
                    cancel_event=cancel_event,
                    http_allowed=artifact.http_allowed,
                )

        # All artifacts committed -> full verification.
        state["status"] = "verifying"
        _transient_states[key] = RuntimeStatus.VERIFYING.value
        verification = verify_package(manifest, pkg)
        if not verification["ok"]:
            state.update({"status": "failed", "error": "; ".join(verification["errors"])})
            return {
                "ok": False,
                "status": RuntimeStatus.FAILED.value,
                "packageState": PackageInstallState.FAILED.value,
                "errors": verification["errors"],
            }
        state.update({"status": "done", "percent": 100.0})
        return {"ok": True, "status": RuntimeStatus.INSTALLED.value, "packageState": PackageInstallState.INSTALLED.value}
    except ArtifactDownloadCancelled as exc:
        state.update({"status": "cancelled", "error": str(exc)})
        return {
            "ok": False,
            "status": "cancelled",
            "packageState": PackageInstallState.NOT_INSTALLED.value,
            "error": str(exc),
        }
    except ArtifactDownloadError as exc:
        state.update({"status": "failed", "error": str(exc)})
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        state.update({"status": "failed", "error": str(exc)})
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": str(exc)}
    finally:
        _transient_states.pop(key, None)
        with _install_lock:
            _cancel_events.pop((manifest.id, kind), None)


def _install_legacy_download(manifest: Ai3DRuntimeManifest, kind: str, fetcher=None, on_progress=None) -> dict:
    """Legacy single-`download`-block install (Phase 3-C behavior, kept for the
    no-`packages` manifests). Only meaningful for the model package.
    """
    if kind == "runtime":
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": "manifest 未声明 runtime package"}

    key = _transient_key(manifest.id, kind)
    target = resolve_package_target(manifest)
    if target is None:
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": "manifest 未声明 download 来源或路径非法"}

    if compute_install_state(manifest) == InstallState.INSTALLED:
        result = verify_downloaded_package(manifest)
        return {
            "ok": result["ok"],
            "status": RuntimeStatus.INSTALLED.value if result["ok"] else RuntimeStatus.FAILED.value,
            "packageState": result["state"],
            "errors": result["errors"],
        }

    if fetcher is None:
        return {
            "ok": False,
            "status": RuntimeStatus.NOT_INSTALLED.value,
            "packageState": PackageInstallState.NOT_INSTALLED.value,
            "error": "未安装：需要下载 Hunyuan3D Runtime/Model 包（本阶段不执行真实下载）",
        }

    _transient_states[key] = RuntimeStatus.DOWNLOADING.value
    try:
        result = fetcher(
            url=manifest.download.url,
            sha256=manifest.download.sha256,
            size_bytes=manifest.download.size_bytes,
            on_progress=on_progress,
        )
        if not result.get("ok"):
            return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": result.get("error") or "下载失败"}
        data = result.get("bytes")
        if data is None:
            return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": "下载结果缺少字节"}
        _atomic_write_bytes(target, data)
        verification = verify_downloaded_package(manifest)
        if not verification["ok"]:
            return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "errors": verification["errors"]}
        return {"ok": True, "status": RuntimeStatus.INSTALLED.value, "packageState": PackageInstallState.INSTALLED.value}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": str(exc)}
    finally:
        _transient_states.pop(key, None)


def install_package(
    runtime_id: str,
    kind: str = "all",
    fetcher=None,
    downloader=None,
    cancel_event=None,
    on_progress: Callable[[float], None] | None = None,
) -> dict:
    """Begin the package install state machine for one kind (or all kinds).

    `fetcher(url, sha256, size_bytes, on_progress)` returns {"ok", "bytes"|"error"}
    and is injected by tests. `downloader` is the streaming downloader
    (default `download_artifact`, gated by AIVCS_AI3D_ALLOW_DOWNLOAD). The API
    route passes neither -> installs are blocked by default (no external requests).
    """
    manifest = next((m for m in load_manifests() if m.id == runtime_id), None)
    if manifest is None:
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": f"runtime '{runtime_id}' 未发现"}
    if kind not in ("all", "runtime", "model"):
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": f"未知 package kind：{kind}"}

    kinds = ("runtime", "model") if kind == "all" else (kind,)
    results: list[dict] = []
    for k in kinds:
        if manifest.packages and not any(p.kind == k for p in manifest.packages):
            if kind != "all":
                return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": f"manifest 未声明 {k} package"}
            continue
        result = _install_package_one(manifest, k, fetcher, downloader, cancel_event, on_progress)
        results.append({"kind": k, **result})

    if not results:
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "packageState": PackageInstallState.FAILED.value, "error": "manifest 未声明任何 package"}
    ok = all(r["ok"] for r in results)
    if ok:
        status = RuntimeStatus.INSTALLED.value
        package_state = PackageInstallState.INSTALLED.value
    elif "cancelled" in [r.get("status") for r in results]:
        status = "cancelled"
        package_state = PackageInstallState.NOT_INSTALLED.value
    elif all(r.get("status") == RuntimeStatus.NOT_INSTALLED.value for r in results):
        status = RuntimeStatus.NOT_INSTALLED.value
        package_state = PackageInstallState.NOT_INSTALLED.value
    else:
        status = RuntimeStatus.FAILED.value
        package_state = PackageInstallState.FAILED.value
    return {
        "ok": ok,
        "status": status,
        "packageState": package_state,
        "results": results,
    }


def install_runtime_package(runtime_id: str, fetcher=None, cancel_event=None) -> dict:
    """Backward-compatible entry point for the package install state machine.

    With `packages[]` declared it installs every missing package; otherwise it
    keeps the legacy single-`download` behavior. No real network by default.
    """
    manifest = next((m for m in load_manifests() if m.id == runtime_id), None)
    if manifest is None:
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": f"runtime '{runtime_id}' 未发现"}
    if manifest.packages:
        return install_package(runtime_id, "all", fetcher=fetcher, cancel_event=cancel_event)
    return _install_legacy_download(manifest, "model", fetcher)


# --------------------------------------------------------------------------- #
# License acceptance (Phase 3-D)
# --------------------------------------------------------------------------- #


def _state_dir() -> Path:
    return install_base() / "state"


def _license_marker(runtime_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", runtime_id or "")
    return _state_dir() / f"{safe}.license-accepted"


def license_accepted(runtime_id: str) -> bool:
    """True when the user has explicitly accepted the runtime license on this machine."""
    try:
        return _license_marker(runtime_id).is_file()
    except Exception:  # noqa: BLE001
        return False


def set_license_accepted(runtime_id: str, accepted: bool = True) -> dict:
    """Record/revoke explicit license acceptance. Persisted under userData so it
    survives restarts. Never auto-accepted for tests without an explicit call."""
    marker = _license_marker(runtime_id)
    try:
        if accepted:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("accepted\n", encoding="utf-8")
        elif marker.exists():
            marker.unlink()
    except OSError as exc:
        return {"ok": False, "error": f"无法保存许可证确认：{exc}"}
    return {"ok": True, "accepted": accepted}


# --------------------------------------------------------------------------- #
# Hardware detection (Phase 1 - reliable base abstraction, no heavy deps)
# --------------------------------------------------------------------------- #


def _read_sys_mem_mb() -> int | None:
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullTotalPhys // (1024 * 1024))
    except Exception:  # noqa: BLE001
        pass
    return None


def _nvidia_vram_mb() -> tuple[str, str, int] | None:
    """Best-effort NVIDIA detection via nvidia-smi if present. Returns (vendor, name, vramMB)."""
    try:
        import shutil

        exe = shutil.which("nvidia-smi")
        if not exe:
            return None
        import subprocess

        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return None
        line = out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
        if not line:
            return None
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            return ("nvidia", parts[0], int(float(parts[1])))
    except Exception:  # noqa: BLE001
        pass
    return None


def _dxgi_gpu() -> dict | None:
    """Detect the primary GPU via DXGI (stdlib ctypes, no subprocess/shell).

    Returns {vendor, name, vram_mb, vendor_id, device_id} or None. Dedicated
    video memory comes straight from the adapter description (never fabricated);
    NVIDIA/AMD/Intel are identified by PCI vendor id. This is read-only.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", ctypes.c_long)]

        class DXGI_ADAPTER_DESC(ctypes.Structure):
            _fields_ = [
                ("Description", ctypes.c_wchar * 128),
                ("VendorId", wintypes.UINT),
                ("DeviceId", wintypes.UINT),
                ("SubSysId", wintypes.UINT),
                ("Revision", wintypes.UINT),
                ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory", ctypes.c_size_t),
                ("AdapterLuid", LUID),
            ]

        ole32 = ctypes.WinDLL("ole32", use_last_error=True)
        dxgi = ctypes.WinDLL("dxgi", use_last_error=True)
        ole32.CoInitializeEx(None, 0)

        def guid(d1, d2, d3, d4):
            return GUID(d1, d2, d3, (ctypes.c_ubyte * 8)(*d4))

        iid = guid(0x770AAE78, 0xF26F, 0x4DBA, (0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
        create = dxgi.CreateDXGIFactory1
        create.restype = ctypes.c_long
        create.argtypes = [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        factory = ctypes.c_void_p()
        if create(ctypes.byref(iid), ctypes.byref(factory)) != 0:
            return None
        vtable = ctypes.cast(factory, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        enum_adapters1 = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))(vtable[12])
        adapter = ctypes.c_void_p()
        if enum_adapters1(factory, 0, ctypes.byref(adapter)) != 0:
            return None
        avt = ctypes.cast(adapter, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        desc = DXGI_ADAPTER_DESC()
        get_desc = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(DXGI_ADAPTER_DESC))(avt[8])
        if get_desc(adapter, ctypes.byref(desc)) != 0:
            return None
        vendor_id = int(desc.VendorId)
        vendor = _DXGI_VENDOR_IDS.get(vendor_id, "unknown")
        return {
            "vendor": vendor,
            "name": str(desc.Description).strip() or "unknown",
            "vram_mb": int(desc.DedicatedVideoMemory // (1024 * 1024)),
            "vendor_id": vendor_id,
            "device_id": int(desc.DeviceId),
        }
    except Exception:  # noqa: BLE001 - detection must never crash
        return None


def detect_hardware() -> HardwareCapability:
    """Detect base hardware capability. Unknown fields are 'unknown'/None, never
    fabricated as 0 VRAM or 'no GPU' when not actually detected.

    NVIDIA is authoritative via nvidia-smi. When nvidia-smi is absent, DXGI
    (stdlib) reports the primary GPU vendor + name + dedicated VRAM for
    NVIDIA/AMD/Intel by PCI vendor id. Only `cuda` is listed as an available
    backend (and only for NVIDIA); AMD/Intel backends are NOT claimed.
    """
    import platform

    os_name = platform.system().lower()
    arch = platform.machine().lower() or "x64"
    ram_mb = _read_sys_mem_mb() or 0

    gpu_vendor = "unknown"
    gpu_name = "unknown"
    vram_mb: int | None = None
    vendor_id: int | None = None
    device_id: int | None = None
    available_backends: list[str] = []

    nvidia = _nvidia_vram_mb()
    if nvidia:
        gpu_vendor, gpu_name, vram_mb = nvidia
        vendor_id = 0x10DE
        available_backends.append("cuda")
    else:
        dxgi = _dxgi_gpu()
        if dxgi:
            gpu_vendor = dxgi["vendor"]
            gpu_name = dxgi["name"]
            vram_mb = dxgi["vram_mb"]
            vendor_id = dxgi["vendor_id"]
            device_id = dxgi["device_id"]
            if gpu_vendor == "nvidia":
                available_backends.append("cuda")

    return HardwareCapability(
        os_name=os_name,
        architecture=arch,
        ram_mb=ram_mb,
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        vram_mb=vram_mb,
        available_backends=available_backends,
        gpu_vendor_id=vendor_id,
        gpu_device_id=device_id,
    )


def hardware_to_dict(hw: HardwareCapability) -> dict:
    return {
        "os": hw.os_name,
        "architecture": hw.architecture,
        "ramMB": hw.ram_mb,
        "gpuVendor": hw.gpu_vendor,
        "gpuName": hw.gpu_name,
        "vramMB": hw.vram_mb,
        "availableBackends": hw.available_backends,
        "gpuVendorId": hw.gpu_vendor_id,
        "gpuDeviceId": hw.gpu_device_id,
        "knownBackends": list(KNOWN_GPU_BACKENDS),
    }


# --------------------------------------------------------------------------- #
# Phase 2: Runtime process management (localhost HTTP + random token)
# --------------------------------------------------------------------------- #


@dataclass
class RuntimeProcess:
    runtime_id: str
    port: int
    token: str
    process: subprocess.Popen | None = None
    status: str = RuntimeStatus.DISCOVERED.value
    last_error: str = ""
    started_at: float = 0.0


# runtime_id -> RuntimeProcess (in-memory; not persisted).
_processes: dict[str, RuntimeProcess] = {}
_process_lock = RLock()
_next_port = [RUNTIME_PORT_BASE]


def get_runtime_process(runtime_id: str) -> RuntimeProcess | None:
    with _process_lock:
        return _processes.get(runtime_id)


def _port_free(port: int) -> bool:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _alloc_port() -> int:
    with _process_lock:
        for _ in range(32):
            port = _next_port[0]
            _next_port[0] += 1
            if _port_free(port):
                return port
        raise RuntimeError("无法分配空闲 runtime 端口")


def _executable_path(manifest: Ai3DRuntimeManifest) -> Path | None:
    """Resolve the runtime executable path against the allow-list root."""
    resolved = _resolve_paths(manifest)
    return resolved.get("executable")


def _is_script(manifest: Ai3DRuntimeManifest) -> bool:
    return manifest.files.executable.lower().endswith(".py")


def start_runtime(runtime_id: str) -> dict:
    """Validate manifest/paths, spawn the runtime, wait for /health.

    Phase 3-D gates (all must hold; otherwise an explicit error, never Mock):
      runtime package installed && model package installed &&
      license accepted (when required) && hardware compatible.
    Returns a dict {ok, status, error?, port?}. On any failure the process is
    cleaned up and status becomes FAILED. Never falls back to Mock.
    """
    with _process_lock:
        existing = _processes.get(runtime_id)
        if existing is not None and existing.process and existing.process.poll() is None:
            return {"ok": True, "status": RuntimeStatus.RUNNING.value, "port": existing.port}

    manifest = next((m for m in load_manifests() if m.id == runtime_id), None)
    if manifest is None:
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": f"runtime '{runtime_id}' 未发现"}

    # Gate 1: hardware compatible.
    hw = detect_hardware()
    if not hardware_compatible(manifest, hw):
        return {
            "ok": False,
            "status": RuntimeStatus.INCOMPATIBLE.value,
            "error": "硬件不兼容：需要 NVIDIA CUDA GPU，最低 6GB VRAM，无法启动",
        }

    # Gate 2: license explicitly accepted (when required).
    if manifest.license.requires_acceptance and not license_accepted(runtime_id):
        return {
            "ok": False,
            "status": RuntimeStatus.FAILED.value,
            "error": "尚未接受许可证（Tencent Hunyuan 3D Community License），无法启动 Runtime",
        }

    # Gate 3: both packages installed (runtime + model + legal files).
    install = compute_install_state(manifest)
    if install != InstallState.INSTALLED:
        if install == InstallState.PARTIAL:
            return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": "Runtime/Model 包部分安装，无法启动"}
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": "Runtime/Model 包未安装，无法启动"}

    exe = _executable_path(manifest)
    if exe is None:
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": "runtime executable 未安装（manifest 路径不匹配磁盘）"}

    model = _resolve_paths(manifest).get("model_path")
    if model is None:
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": "runtime model 未安装（manifest modelPath 不匹配磁盘）"}

    port = _alloc_port()
    token = secrets.token_urlsafe(24)

    cmd = _build_command(exe, manifest, port, token)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(exe.parent),
            shell=False,  # never shell
        )
    except Exception as exc:  # noqa: BLE001
        _mark_failed(runtime_id, f"启动失败：{exc}")
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": f"启动失败：{exc}"}

    rp = RuntimeProcess(runtime_id=runtime_id, port=port, token=token, process=proc)
    with _process_lock:
        _processes[runtime_id] = rp

    # Wait for readiness (bounded). The probe path comes from the manifest
    # (default /health); Hunyuan exposes a uvicorn root instead, so manifests
    # may declare healthPath="/" for it.
    deadline = time.monotonic() + manifest.launch.ready_timeout_seconds
    ok = False
    last_err = ""
    probe = _health_path(manifest)
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            # Phase 3-K: never surface the runtime token in a user-visible error
            # even if a crashed process echoed it to stderr.
            last_err = _redact_token(_read_process_error(proc), token)
            break
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}{probe}")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    ok = True
                    break
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.3)

    if not ok:
        _stop_process(runtime_id)
        _mark_failed(runtime_id, last_err or "health 检查超时")
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": last_err or "health 检查超时"}

    rp.status = RuntimeStatus.RUNNING.value
    rp.started_at = time.time()
    return {"ok": True, "status": RuntimeStatus.RUNNING.value, "port": port}


def _build_command(exe: Path, manifest: Ai3DRuntimeManifest, port: int, token: str) -> list[str]:
    """Build argv WITHOUT shell. Only the whitelisted manifest executable is used.

    `manifest.launch.args` is a fixed template (no user input); `{port}` and
    `{token}` are replaced with the allocated values. When the template declares
    `--port` (Hunyuan official api_server), it is the COMPLETE argv and nothing
    is appended. Otherwise `--port/--token` defaults are appended (dummy etc.).
    """
    base = [str(exe)] if not _is_script(manifest) else [PYTHON_INTERPRETER, str(exe)]
    args = [entry.replace("{port}", str(port)).replace("{token}", token) for entry in manifest.launch.args]
    has_port = any(a.startswith("--port") for a in args)
    # Never accept user input into argv; only fixed runtime args.
    # Use `--port=.. / --token=..` (equals form): a token_urlsafe value can start
    # with '-', which space-separated argparse would misparse as another flag.
    if not has_port:
        args += [f"--port={port}", f"--token={token}"]
    return base + args


def _health_path(manifest: Ai3DRuntimeManifest) -> str:
    return manifest.launch.health_path or "/health"


def _read_process_error(proc: subprocess.Popen) -> str:
    try:
        if proc.stderr:
            return (proc.stderr.read(512).decode("utf-8", errors="replace") or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return "process exited"


def _redact_token(text: str, token: str) -> str:
    """Redact the runtime token from any user-visible message (Phase 3-K)."""
    if not text or not token:
        return text or ""
    return text.replace(token, "[redacted]")


def _mark_failed(runtime_id: str, error: str) -> None:
    with _process_lock:
        rp = _processes.get(runtime_id)
        if rp:
            rp.status = RuntimeStatus.FAILED.value
            rp.last_error = error


def _stop_process(runtime_id: str) -> None:
    with _process_lock:
        rp = _processes.get(runtime_id)
        if rp is None:
            return
        if rp.process and rp.process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/pid", str(rp.process.pid), "/T", "/F"], capture_output=True)
            else:
                rp.process.terminate()
        rp.process = None
        rp.status = RuntimeStatus.STOPPED.value


def stop_runtime(runtime_id: str) -> dict:
    """Stop a running runtime process (idempotent)."""
    with _process_lock:
        rp = _processes.get(runtime_id)
        if rp is None:
            return {"ok": False, "status": RuntimeStatus.STOPPED.value, "error": "runtime 未运行"}
        if rp.process and rp.process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/pid", str(rp.process.pid), "/T", "/F"], capture_output=True)
            else:
                rp.process.terminate()
        rp.process = None
        rp.status = RuntimeStatus.STOPPED.value
        return {"ok": True, "status": RuntimeStatus.STOPPED.value}


def runtime_health(runtime_id: str) -> dict:
    """Live health probe. Returns status; marks FAILED on crash. Never fallback."""
    with _process_lock:
        rp = _processes.get(runtime_id)
        if rp is None or rp.process is None or rp.process.poll() is not None:
            if rp is not None:
                rp.status = RuntimeStatus.FAILED.value
            return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": "runtime 未运行或已崩溃"}
        port = rp.port
    probe = "/health"
    for m in load_manifests():
        if m.id == runtime_id:
            probe = _health_path(m)
            break
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{probe}")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                rp.status = RuntimeStatus.RUNNING.value
                return {"ok": True, "status": RuntimeStatus.RUNNING.value}
            rp.status = RuntimeStatus.FAILED.value
            return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": f"health HTTP {resp.status}"}
    except Exception as exc:  # noqa: BLE001
        rp.status = RuntimeStatus.FAILED.value
        return {"ok": False, "status": RuntimeStatus.FAILED.value, "error": str(exc)}


def runtime_status(runtime_id: str) -> dict:
    """Status of a runtime (process + install + compat)."""
    manifest = next((m for m in load_manifests() if m.id == runtime_id), None)
    if manifest is None:
        return {"ok": False, "status": RuntimeStatus.DISCOVERED.value, "error": "runtime 未发现"}
    info = build_runtime_info(manifest, detect_hardware())
    rp = get_runtime_process(runtime_id)
    process_status = rp.status if rp else (RuntimeStatus.READY.value if info.status == RuntimeStatus.READY.value else info.status)
    if process_status == RuntimeStatus.RUNNING.value and rp and rp.process and rp.process.poll() is not None:
        process_status = RuntimeStatus.FAILED.value
    return {
        "ok": True,
        "id": runtime_id,
        "installState": info.install_state,
        "compatible": info.compatible,
        "processStatus": process_status,
        "packageState": info.package_state,
        "runtimePackageState": info.runtime_package_state,
        "modelPackageState": info.model_package_state,
        "licenseAccepted": info.license_accepted,
        "licenseRequiresAcceptance": info.license_requires_acceptance,
        "port": rp.port if rp else None,
    }

