"""Persistent ModelStore tests (Phase 2.3-B)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.services.model_store import ModelStore, spec_hash  # noqa: E402


def make_spec(name="t", user_notes=""):
    return CharacterSpec(
        id="s",
        name=name,
        style="stylized",
        gender="female",
        heightCm=160,
        description="",
        referenceImageIds=[],
        tags=[],
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:00Z",
        characterType="human",
        userNotes=user_notes,
    )


class ModelStoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = ModelStore(self.dir)

    def test_save_creates_file_and_sidecar(self):
        rec = self.store.save(b"GLB", "mock", "job1", "hash1")
        self.assertTrue((Path(self.dir) / f"{rec.id}.glb").exists())
        self.assertTrue((Path(self.dir) / f"{rec.id}.glb.meta.json").exists())

    def test_read_matches_original(self):
        rec = self.store.save(b"GLB_DATA", "mock", "job1", "hash1")
        self.assertEqual(self.store.read_bytes(rec.id), b"GLB_DATA")

    def test_metadata_correct(self):
        rec = self.store.save(b"xyz", "mock", "job42", "abc123")
        self.assertEqual(rec.format, "glb")
        self.assertEqual(rec.mime, "model/gltf-binary")
        self.assertEqual(rec.size_bytes, 3)
        self.assertEqual(rec.provider_id, "mock")
        self.assertEqual(rec.source_job_id, "job42")
        self.assertEqual(rec.spec_hash, "abc123")
        self.assertTrue(rec.created_at > 0)

    def test_reinstantiation_reads_persisted(self):
        rec = self.store.save(b"PERSIST", "mock", "job1", "h")
        store2 = ModelStore(self.dir)  # simulates backend restart
        self.assertEqual(store2.get(rec.id).spec_hash, "h")
        self.assertEqual(store2.read_bytes(rec.id), b"PERSIST")

    def test_missing_model_safe(self):
        self.assertIsNone(self.store.get("nope"))
        self.assertIsNone(self.store.read_bytes("nope"))

    def test_texture_metadata_round_trip(self):
        # Phase 3-G: optional texture metadata persists through restart.
        rec = self.store.save(b"GLB", "mock", "job1", "h", texture={"supported": True, "kind": "paint"})
        self.assertEqual(rec.texture, {"supported": True, "kind": "paint"})
        store2 = ModelStore(self.dir)  # restart
        self.assertEqual(store2.get(rec.id).texture, {"supported": True, "kind": "paint"})
        # shape-only default stays None
        rec2 = self.store.save(b"G", "mock", "job2", "h")
        self.assertIsNone(store2.get(rec2.id).texture)

    def test_tmp_file_not_exposed(self):
        (Path(self.dir) / ".tmp_zzz.glb").write_bytes(b"partial")
        self.assertIsNone(self.store.get("zzz"))
        removed = self.store.cleanup_expired(now=time.time() + 100000)
        self.assertEqual(removed, 0)
        self.assertTrue((Path(self.dir) / ".tmp_zzz.glb").exists())

    def test_ttl_kept_within_window(self):
        rec = self.store.save(b"K", "mock", "j", "h")
        self.assertEqual(self.store.cleanup_expired(now=rec.created_at + 60), 0)
        self.assertIsNotNone(self.store.get(rec.id))

    def test_ttl_expired_via_old_mtime(self):
        rec = self.store.save(b"K", "mock", "j", "h")
        old = time.time() - 25 * 3600
        os.utime(Path(self.dir) / f"{rec.id}.glb", (old, old))
        os.utime(Path(self.dir) / f"{rec.id}.glb.meta.json", (old, old))
        removed = self.store.cleanup_expired()
        self.assertEqual(removed, 1)
        self.assertIsNone(self.store.get(rec.id))
        self.assertFalse((Path(self.dir) / f"{rec.id}.glb").exists())

    def test_ttl_expired_via_injected_now(self):
        rec = self.store.save(b"K2", "mock", "j", "h")
        removed = self.store.cleanup_expired(now=rec.created_at + 25 * 3600 + 1, ttl_hours=24)
        self.assertEqual(removed, 1)

    def test_delete_failure_does_not_abort_cleanup(self):
        rec = self.store.save(b"X", "mock", "j", "h")
        with mock.patch("pathlib.Path.unlink", side_effect=OSError("locked")):
            removed = self.store.cleanup_expired(now=time.time() + 100000)
            self.assertEqual(removed, 0)  # no crash, nothing removed
        self.assertIsNotNone(self.store.get(rec.id))

    def test_spec_hash_stable_and_distinct(self):
        self.assertEqual(spec_hash(make_spec(name="A")), spec_hash(make_spec(name="A")))
        self.assertNotEqual(spec_hash(make_spec(name="A")), spec_hash(make_spec(name="B")))

    def test_sidecar_json_is_light(self):
        rec = self.store.save(b"L", "mock", "j", "h")
        side = json.loads((Path(self.dir) / f"{rec.id}.glb.meta.json").read_text(encoding="utf-8"))
        self.assertNotIn("spec", side)  # no full CharacterSpec persisted


if __name__ == "__main__":
    unittest.main()
