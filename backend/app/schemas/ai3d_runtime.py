"""AI 3D Runtime manifest schema (Multi AI 3D Runtime Manager - Phase 1 / 3-C / 3-D).

Static metadata describing a local AI 3D runtime + its model weights. The
manifest is READ-ONLY static data: install state is NEVER written back into a
manifest - the Runtime Manager computes install/compat/status dynamically.

Phase 3-C additions (Hunyuan3D Runtime Package / Model Package):
  - `download` block: explicit official source URL(s), expected size and SHA-256
    checksum. Used by the install/download state machine (NOT auto-downloaded).
  - `files.notice` / `files.license` (relative paths under the runtime root):
    existence of these files is verified after download.

Phase 3-D additions (Runtime Package / Model Package as independent install
units + secure download):
  - `packages[]`: each Runtime or Model package declares its own `installDir`
    (under the runtime/model allow-root), its license/notice/source and a list
    of `artifacts[]`. The installer downloads + verifies each artifact into
    `userData/ai/3d/<runtimes|models>/<installDir>/<artifact.path>` atomically.
    Runtime and Model are verified INSTALLED independently; READY only when both
    are complete AND hardware-compatible.
  - `artifact.httpAllowed`: plain-HTTP downloads are refused unless the manifest
    explicitly allows them (HTTPS is the default).
  - `license.requiresAcceptance`: the user must explicitly accept the license
    before the runtime may start.

Path safety:
  - `executable` / `modelPath` / `notice` / `license` / `package.installDir` /
    `artifact.path` MUST be relative paths;
  - absolute paths and `..` traversal are rejected by validation;
  - `download.url` / `artifact.url` MUST be http(s) (no file://, no arbitrary
    protocol); HTTP requires an explicit `httpAllowed` flag;
  - paths are resolved against a fixed allow-list root (runtime root / model
    root), never against user input or arbitrary directories.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Only http(s) download sources are allowed. File/protocol-relative URLs are
# rejected so a manifest can never point at a local file or drive letter.
ALLOWED_URL_SCHEMES = ("http", "https")


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class RuntimeTextureCapability(_CamelModel):
    """Phase 3-G: Texture/Paint output capability of a Runtime.

    `supported=false` means the runtime does NOT currently produce texture /
    paint output (shape-only). `kind` separates "none" (never planned for this
    runtime) from "future" (declared roadmap, e.g. Hunyuan Paint which needs a
    separate install gate / compiled extensions - NOT claimed as available).
    """

    supported: bool = False
    kind: Literal["none", "paint", "future"] = "none"
    notes: str = ""


class RuntimeCapabilities(_CamelModel):
    supports_cancel: bool = Field(alias="supportsCancel")
    supports_progress: bool = Field(alias="supportsProgress")
    supports_resume: bool = Field(alias="supportsResume")
    # Phase 3-G: optional texture/paint capability (absent -> shape-only).
    texture: RuntimeTextureCapability | None = None


class RuntimeHardwareRequirements(_CamelModel):
    requires_gpu: bool = Field(alias="requiresGPU")
    minimum_vram_mb: int = Field(alias="minimumVRAMMB")
    recommended_vram_mb: int = Field(alias="recommendedVRAMMB")
    minimum_ram_mb: int = Field(alias="minimumRAMMB")
    supported_os: list[str] = Field(default_factory=list, alias="supportedOS")
    supported_backends: list[str] = Field(default_factory=list, alias="supportedBackends")


def _validate_relative(value: str, field_name: str) -> str:
    """Reject absolute (posix/windows/UNC), traversal and backslash paths.

    Shared by `RuntimeFiles` and `RuntimeArtifact.path` / `RuntimePackage.installDir`.
    """
    if not value:
        return value
    if value.startswith(("/", "\\")):
        raise ValueError(f"{field_name} 必须是相对路径（不允许绝对路径）")
    if value.startswith("\\\\") or "\\" in value or ":" in value.split("/", 1)[0]:
        raise ValueError(f"{field_name} 必须是合法相对路径")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"{field_name} 不允许包含 ..")
    return value


def _validate_url_scheme(value: str, field_name: str) -> str:
    if not value:
        return value
    if "://" not in value:
        raise ValueError(f"{field_name} 必须是 http(s) URL")
    scheme = value.split("://", 1)[0].lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        raise ValueError(f"{field_name} 只允许 http/https 来源")
    return value


class RuntimeDownload(_CamelModel):
    """Official source + integrity metadata for a Runtime/Model Package.

    `url` must be an explicit official http(s) source declared in the manifest
    (never guessed, never derived from user input). `sha256` (hex) and `sizeBytes`
    are verified after download; `kind` separates the runtime code package from
    the model weights package so install state tracks them independently.
    """

    kind: Literal["runtime", "model"] = "runtime"
    url: str = ""
    sha256: str = ""
    size_bytes: int = Field(default=0, alias="sizeBytes")
    http_allowed: bool = Field(default=False, alias="httpAllowed")

    @field_validator("url")
    @classmethod
    def _validate_download_url(cls, value: str) -> str:
        return _validate_url_scheme(value, "download.url")

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if not value:
            return value
        value = value.strip().lower()
        if len(value) != 64 or not all(c in "0123456789abcdef" for c in value):
            raise ValueError("download.sha256 必须是 64 位十六进制")
        return value

    @field_validator("size_bytes")
    @classmethod
    def _validate_size(cls, value: int) -> int:
        if value < 0:
            raise ValueError("download.sizeBytes 不能为负")
        return value


class RuntimeArtifact(_CamelModel):
    """One downloadable file of a Runtime/Model Package (Phase 3-D).

    `path` is the RELATIVE destination under the package install dir (no
    traversal/absolute allowed); `url` is the EXPLICIT official http(s) source
    declared in the manifest (never guessed, never user-supplied); `sha256`
    (64-hex) + `sizeBytes` are verified before the file is atomically committed.
    `httpAllowed` gates plain-HTTP downloads (default false: HTTPS only).
    """

    path: str = ""
    url: str = ""
    sha256: str = ""
    size_bytes: int = Field(default=0, alias="sizeBytes")
    http_allowed: bool = Field(default=False, alias="httpAllowed")

    @field_validator("path")
    @classmethod
    def _validate_artifact_path(cls, value: str) -> str:
        return _validate_relative(value, "artifact.path")

    @field_validator("url")
    @classmethod
    def _validate_artifact_url(cls, value: str) -> str:
        return _validate_url_scheme(value, "artifact.url")

    @field_validator("sha256")
    @classmethod
    def _validate_artifact_sha256(cls, value: str) -> str:
        if not value:
            return value
        value = value.strip().lower()
        if len(value) != 64 or not all(c in "0123456789abcdef" for c in value):
            raise ValueError("artifact.sha256 必须是 64 位十六进制")
        return value

    @field_validator("size_bytes")
    @classmethod
    def _validate_artifact_size(cls, value: int) -> int:
        if value < 0:
            raise ValueError("artifact.sizeBytes 不能为负")
        return value

    @model_validator(mode="after")
    def _enforce_http_gate(self):
        if self.url.startswith("http://") and not self.http_allowed:
            raise ValueError("artifact.url 使用 http:// 但未显式允许（httpAllowed=false）")
        return self


class RuntimePackage(_CamelModel):
    """One install unit (Phase 3-D): the runtime code package (kind=runtime) or
    the model weights package (kind=model). Installed + verified independently.

    `installDir` is a RELATIVE directory under the runtime/model allow-root
    (`<base>/runtimes/<installDir>` or `<base>/models/<installDir>`). `artifacts`
    are downloaded into that directory; `license`/`notice` name the license terms
    (the actual LICENSE/NOTICE files are runtime-package artifacts that must
    exist after install). `source` / `sourceUrl` document the official origin.
    """

    id: str = ""
    kind: Literal["runtime", "model"]
    version: str = ""
    source: str = ""
    source_url: str = Field(default="", alias="sourceUrl")
    license: str = ""
    notice: str = ""
    install_dir: str = Field(default="", alias="installDir")
    artifacts: list[RuntimeArtifact] = Field(default_factory=list)

    @field_validator("install_dir")
    @classmethod
    def _validate_install_dir(cls, value: str) -> str:
        if not value:
            raise ValueError("package.installDir 不能为空")
        return _validate_relative(value, "package.installDir")

    @model_validator(mode="after")
    def _validate_artifacts_have_urls(self):
        for artifact in self.artifacts:
            if artifact.url and not artifact.path:
                raise ValueError("artifact 声明了 url 但缺少 path")
        return self


class RuntimeLaunch(_CamelModel):
    """Process launch metadata (optional). Fixed, non-user-supplied arguments.

    `args` is a template of fixed argv entries appended after the executable
    (never any user input). `{port}` is replaced with the allocated port.
    `healthPath` overrides the default `/health` readiness probe.
    """

    args: list[str] = Field(default_factory=list)
    health_path: str = Field(default="/health", alias="healthPath")
    ready_timeout_seconds: float = Field(default=20.0, alias="readyTimeoutSeconds")


class RuntimeFiles(_CamelModel):
    executable: str
    model_path: str = Field(alias="modelPath")
    relative_to: str = Field(alias="relativeTo")
    # Optional relative files that must exist after install (license/notice).
    license: str = ""
    notice: str = ""


class RuntimeLicense(_CamelModel):
    id: str = ""
    url: str = ""
    model_source: str = Field(default="", alias="modelSource")
    model_source_url: str = Field(default="", alias="modelSourceUrl")
    # Terms text location (relative under runtime root) + geo/business notes.
    notice_file: str = Field(default="", alias="noticeFile")
    territory_restrictions: str = Field(default="", alias="territoryRestrictions")
    commercial_threshold: str = Field(default="", alias="commercialThreshold")
    # Phase 3-D: the user must explicitly accept the license before the runtime
    # may start. True by default; test-only runtimes opt out explicitly.
    requires_acceptance: bool = Field(default=True, alias="requiresAcceptance")


class Ai3DRuntimeManifest(_CamelModel):
    """Static metadata for one local AI 3D runtime (see module docstring)."""

    id: str
    name: str
    version: str
    model_version: str = Field(alias="modelVersion")
    input_types: list[str] = Field(default_factory=list, alias="inputTypes")
    output_types: list[str] = Field(default_factory=list, alias="outputTypes")
    capabilities: RuntimeCapabilities
    hardware: RuntimeHardwareRequirements
    files: RuntimeFiles
    license: RuntimeLicense = Field(default_factory=RuntimeLicense)
    download: RuntimeDownload = Field(default_factory=RuntimeDownload)
    launch: RuntimeLaunch = Field(default_factory=RuntimeLaunch)
    # Phase 3-D: independent Runtime Package / Model Package install units.
    packages: list[RuntimePackage] = Field(default_factory=list)

    @field_validator("files")
    @classmethod
    def _validate_relative_paths(cls, files: RuntimeFiles) -> RuntimeFiles:
        optional = {"license", "notice"}
        for field_name in ("executable", "model_path", "relative_to", "license", "notice"):
            value = getattr(files, field_name)
            if not value:
                # license/notice are optional (empty string allowed); the rest are required.
                if field_name in optional:
                    continue
                raise ValueError(f"files.{field_name} 不能为空")
            # Reject POSIX absolute, Windows drive/UNC, and traversal.
            if value.startswith(("/", "\\")):
                raise ValueError(f"files.{field_name} 必须是相对路径（不允许绝对路径）")
            if ":" in value.split("/", 1)[0] or value.startswith("\\\\") or "\\" in value:
                # Windows drive letter, UNC, or backslash separators are not allowed
                # in manifests (path is resolved against a fixed posix allow-root).
                raise ValueError(f"files.{field_name} 必须是合法相对路径")
            p = PurePosixPath(value)
            if p.is_absolute():
                raise ValueError(f"files.{field_name} 必须是相对路径（不允许绝对路径）")
            parts = p.parts
            if ".." in parts:
                raise ValueError(f"files.{field_name} 不允许包含 ..")
        return files

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("id 不能为空")
        return value.strip()


# Allowed runtime root for executable resolution.
RUNTIME_ROOT = PurePosixPath("resources/ai/3d/runtimes")
# Allowed model root for modelPath resolution.
MODEL_ROOT = PurePosixPath("resources/ai/3d/models")


def resolve_runtime_file(files: RuntimeFiles, key: Literal["executable", "model_path", "license", "notice"]) -> PurePosixPath | None:
    """Resolve a manifest file path against the fixed allow-list root.

    Rejects absolute paths and any `..`. Returns a PurePosixPath relative path
    that callers must further resolve against a concrete on-disk base directory.
    Optional files (license/notice) return None when empty.
    """
    raw = getattr(files, key)
    if not raw:
        return None if key in ("license", "notice") else (_ for _ in ()).throw(ValueError(f"{key} 不能为空"))
    p = PurePosixPath(raw)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"{key} 非法路径：{raw}")
    root = RUNTIME_ROOT if key in ("executable", "license", "notice") else MODEL_ROOT
    return root / p
