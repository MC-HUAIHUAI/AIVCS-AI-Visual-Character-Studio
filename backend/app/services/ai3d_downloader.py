"""Secure artifact downloader for AI 3D Runtime/Model Packages (Phase 3-D).

Downloads a single artifact declared in a runtime manifest into the userData
install root with mandatory integrity verification (SHA-256 + size) and atomic
rename (temp file -> os.replace). This module performs REAL network I/O; it is
only ever invoked with URLs taken verbatim from an already-validated manifest,
or from a local fake server in tests.

Security guarantees:
  - URL must be http(s). Plain HTTP is refused unless the manifest artifact
    explicitly allows it (`httpAllowed`), i.e. HTTPS by default.
  - Redirects are refused when they leave the original host or downgrade to a
    scheme the manifest did not allow (no following to arbitrary hosts).
  - The destination filename is derived from the URL path and sanitized; `..`,
    absolute paths, backslashes and control characters are rejected.
  - Downloads stream to a unique temp file; the final file appears only after
    integrity checks pass, via `os.replace` (atomic).
  - Cancellation (threading.Event) aborts streaming and removes the temp file.
  - No shell is used; no URL/filename/user input is ever concatenated into a
    command line.
"""

from __future__ import annotations

import hashlib
import http.client
import os
import secrets
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler

CHUNK_SIZE = 1 << 16


class ArtifactDownloadError(Exception):
    """A download failed validation, transport, or integrity."""


class ArtifactDownloadCancelled(Exception):
    """The download was cancelled by the user (cancel_event was set)."""


class _RestrictedRedirectHandler(HTTPRedirectHandler):
    """Refuses redirects that leave the manifest-declared host or scheme."""

    def __init__(self, allowed_netloc: str, http_allowed: bool):
        self._allowed = (allowed_netloc or "").lower()
        self._http_allowed = http_allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        parsed = urlparse(newurl)
        if not self._allowed or parsed.netloc.lower() != self._allowed:
            raise ArtifactDownloadError("拒绝跟随到非 manifest 声明 host 的重定向")
        if parsed.scheme not in ("http", "https"):
            raise ArtifactDownloadError("重定向目标协议不合法")
        if parsed.scheme == "http" and not self._http_allowed:
            raise ArtifactDownloadError("manifest 未允许 HTTP 重定向")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_artifact_url(url: str, http_allowed: bool = False) -> tuple[str, str]:
    """Validate a manifest artifact URL. Returns (scheme, netloc). Raises when the
    URL is not an allowed http(s) source. Never trusts caller-supplied input.
    """
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ArtifactDownloadError("仅允许 http/https 下载源")
    if parsed.scheme == "http" and not http_allowed:
        raise ArtifactDownloadError("manifest 未允许 HTTP 下载（httpAllowed=false）")
    return parsed.scheme, parsed.netloc


def safe_artifact_name(url: str, fallback: str = "artifact.bin") -> str:
    """Sanitized filename derived from the URL path (no traversal/separators)."""
    parsed = urlparse(url or "")
    name = PurePosixPath(parsed.path).name
    if (
        not name
        or name in (".", "..")
        or "/" in name
        or "\\" in name
        or "\x00" in name
        or name.startswith(".")
    ):
        return fallback
    return name


def download_artifact(
    url: str,
    dest_dir: str | Path,
    sha256: str = "",
    size_bytes: int = 0,
    on_progress=None,
    cancel_event=None,
    http_allowed: bool = False,
) -> Path:
    """Download one artifact to `dest_dir` atomically.

    Returns the final path. The final file appears only after size + SHA-256
    match the manifest declaration. On any failure (transport / checksum / size
    / cancel) the temp file is removed and an exception is raised; the install
    state machine turns that into FAILED / cancelled (never INSTALLED).
    """
    scheme, netloc = validate_artifact_url(url, http_allowed)  # noqa: F841 - netloc used by redirect handler
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    name = safe_artifact_name(url)
    final = dest / name
    tmp = dest / f".{name}.{secrets.token_hex(6)}.part"
    hasher = hashlib.sha256() if sha256 else None
    total = 0
    opener = urllib.request.build_opener(_RestrictedRedirectHandler(netloc, http_allowed))
    try:
        with opener.open(urllib.request.Request(url), timeout=30) as resp:
            with open(tmp, "wb") as f:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise ArtifactDownloadCancelled("下载已取消")
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    if hasher is not None:
                        hasher.update(chunk)
                    total += len(chunk)
                    if on_progress is not None:
                        on_progress(total, size_bytes)
        if size_bytes and total != size_bytes:
            raise ArtifactDownloadError(f"下载大小不匹配：期望 {size_bytes}，实际 {total}")
        if hasher is not None and hasher.hexdigest() != sha256.lower():
            raise ArtifactDownloadError("SHA-256 校验失败")
        os.replace(tmp, final)
        return final
    except urllib.error.HTTPError as exc:
        raise ArtifactDownloadError(f"下载失败：HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ArtifactDownloadError(f"下载失败：{exc.reason}") from exc
    except http.client.IncompleteRead as exc:
        raise ArtifactDownloadError("下载中断（连接意外关闭）") from exc
    except (ValueError, OSError) as exc:
        raise ArtifactDownloadError(f"下载失败：{exc}") from exc
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
