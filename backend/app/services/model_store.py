"""Persistent on-disk ModelStore (Phase 2.3-B).

Stores generated GLB bytes under backend/data/models/{modelId}.glb with a light
JSON sidecar for metadata. Writes are atomic (temp file + os.replace) so a
crash mid-write never leaves a corrupt .glb. No database dependency.

TTL cleanup is deterministic and testable: the cutoff is computed from file
mtime and accepts an injected `now` so tests never wait real hours.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .. import config
from ..schemas.character import CharacterSpec

FORMAT = "glb"
MIME = "model/gltf-binary"


@dataclass
class ModelRecord:
    id: str
    format: str = FORMAT
    mime: str = MIME
    size_bytes: int = 0
    provider_id: str = "unknown"
    source_job_id: str = ""
    spec_hash: str = ""
    created_at: float = 0.0
    file_path: str = ""


def spec_hash(spec: CharacterSpec) -> str:
    """Stable deterministic hash of a CharacterSpec. Contains no API keys or
    secrets - only the canonical JSON of the spec itself."""
    canonical = json.dumps(spec.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ModelStore:
    def __init__(self, base_dir: Path | str | None = None):
        self.base_dir = Path(base_dir) if base_dir is not None else Path(config.MODEL_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # paths
    # ------------------------------------------------------------------ #

    def _model_path(self, model_id: str) -> Path:
        return self.base_dir / f"{model_id}.glb"

    def _meta_path(self, model_id: str) -> Path:
        return self.base_dir / f"{model_id}.glb.meta.json"

    # ------------------------------------------------------------------ #
    # write (atomic)
    # ------------------------------------------------------------------ #

    def save(self, data: bytes, provider_id: str, source_job_id: str, spec_hash: str) -> ModelRecord:
        model_id = str(uuid.uuid4())
        target = self._model_path(model_id)

        tmp = self.base_dir / f".tmp_{model_id}.glb"
        tmp.write_bytes(data)
        os.replace(tmp, target)

        record = ModelRecord(
            id=model_id,
            size_bytes=len(data),
            provider_id=provider_id,
            source_job_id=source_job_id,
            spec_hash=spec_hash,
            created_at=time.time(),
            file_path=str(target),
        )
        self._write_meta(record)
        return record

    def _write_meta(self, record: ModelRecord) -> None:
        tmp = self.base_dir / f".tmp_{record.id}.meta.json"
        tmp.write_text(json.dumps(asdict(record), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._meta_path(record.id))

    # ------------------------------------------------------------------ #
    # read
    # ------------------------------------------------------------------ #

    def get(self, model_id: str) -> ModelRecord | None:
        path = self._model_path(model_id)
        if not path.exists():
            return None
        meta = self._meta_path(model_id)
        record: ModelRecord | None = None
        if meta.exists():
            try:
                record = self._load_meta(meta)
            except Exception:  # noqa: BLE001 - corrupt sidecar -> fall back
                record = None
        if record is None:
            record = ModelRecord(
                id=model_id,
                size_bytes=path.stat().st_size,
                file_path=str(path),
                created_at=path.stat().st_mtime,
            )
        return record

    def read_bytes(self, model_id: str) -> bytes | None:
        record = self.get(model_id)
        if record is None:
            return None
        try:
            return Path(record.file_path).read_bytes()
        except OSError:
            return None

    def _load_meta(self, meta: Path) -> ModelRecord:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return ModelRecord(**data)

    # ------------------------------------------------------------------ #
    # delete / ttl
    # ------------------------------------------------------------------ #

    def _delete_one(self, model_id: str) -> bool:
        ok = True
        for path in (self._model_path(model_id), self._meta_path(model_id)):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                ok = False
        return ok

    def delete(self, model_id: str) -> bool:
        return self._delete_one(model_id)

    def cleanup_expired(self, now: float | None = None, ttl_hours: float | None = None) -> int:
        """Remove .glb (and sidecar) files older than the TTL. A single file that
        cannot be removed never aborts the whole cleanup."""
        now = now if now is not None else time.time()
        ttl = ttl_hours if ttl_hours is not None else float(config.MODEL_TTL_HOURS)
        cutoff = now - ttl * 3600
        removed = 0

        for path in sorted(self.base_dir.glob("*.glb")):
            if path.name.startswith(".tmp"):
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    if self._delete_one(path.stem):
                        removed += 1
            except OSError:
                continue

        # orphan sidecars (no matching .glb) older than the cutoff
        for meta in sorted(self.base_dir.glob("*.glb.meta.json")):
            model_id = meta.name.split(".glb.meta.json")[0]
            if (self.base_dir / f"{model_id}.glb").exists():
                continue
            try:
                if meta.stat().st_mtime < cutoff:
                    meta.unlink()
            except OSError:
                continue

        return removed
