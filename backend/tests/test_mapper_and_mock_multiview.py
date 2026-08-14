"""vision_spec_mapper + MockVisionProvider multi-view tests (Phase 2.2-B).

Run from the project root:
    python -m unittest discover -s backend/tests -v
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.providers.vision.mock import MockVisionProvider  # noqa: E402
from backend.app.schemas.vision import VisionImageInput  # noqa: E402
from backend.app.services import vision_spec_mapper  # noqa: E402
from backend.app.services.cross_view_resolver import resolve_cross_view  # noqa: E402


class MapperPerViewTest(unittest.TestCase):
    def test_normalize_with_valid_per_view(self):
        raw = {
            "spec_patch": {"characterType": "anthro"},
            "confidence": 0.8,
            "notes": ["ok"],
            "warnings": [],
            "source_image_ids": ["a", "b"],
            "provider_id": "kimi",
            "per_view": [
                {"view": "front", "source_image_id": "a", "spec_patch": {"characterType": "anthro"}, "confidence": 0.9},
                {"view": "back", "source_image_id": "b", "spec_patch": {"species": {"primary": "wolf"}}, "confidence": 0.7},
            ],
        }
        out = vision_spec_mapper.normalize(raw)
        self.assertEqual(len(out.per_view), 2)
        self.assertEqual(out.per_view[0].view, "front")
        self.assertEqual(out.per_view[0].source_image_id, "a")
        self.assertEqual(out.per_view[0].spec_patch["characterType"], "anthro")
        self.assertEqual(out.per_view[1].spec_patch["species"]["primary"], "wolf")

    def test_invalid_view_dropped(self):
        raw = {
            "provider_id": "kimi",
            "per_view": [
                {"view": "top", "source_image_id": "a", "spec_patch": {"characterType": "human"}, "confidence": 0.9},
                {"view": "front", "source_image_id": "b", "spec_patch": {"characterType": "human"}, "confidence": 0.9},
            ],
        }
        out = vision_spec_mapper.normalize(raw)
        self.assertEqual(len(out.per_view), 1)
        self.assertEqual(out.per_view[0].view, "front")

    def test_missing_source_image_id_dropped(self):
        raw = {"provider_id": "kimi", "per_view": [{"view": "front", "spec_patch": {}, "confidence": 0.9}]}
        out = vision_spec_mapper.normalize(raw)
        self.assertIsNone(out.per_view)

    def test_absent_per_view_is_none(self):
        raw = {"provider_id": "kimi", "spec_patch": {"characterType": "human"}}
        out = vision_spec_mapper.normalize(raw)
        self.assertIsNone(out.per_view)
        self.assertEqual(out.spec_patch.character_type, "human")

    def test_per_view_spec_patch_clamped(self):
        raw = {
            "provider_id": "kimi",
            "per_view": [
                {
                    "view": "front",
                    "source_image_id": "a",
                    "spec_patch": {
                        "characterType": "alien-ish",
                        "species": {"primary": "Fox"},
                        "appearance": {"palette": ["#FF0000", "red", "rgb(1,2,3)"]},
                        "heightCm": 9999,
                    },
                    "confidence": 2.0,
                }
            ],
        }
        out = vision_spec_mapper.normalize(raw)
        pv = out.per_view[0]
        self.assertNotIn("characterType", pv.spec_patch)  # unknown enum dropped
        self.assertNotIn("species", pv.spec_patch)  # "Fox" not in enum (case-sensitive)
        self.assertEqual(pv.spec_patch["appearance"]["palette"], ["#FF0000"])
        self.assertEqual(pv.spec_patch["heightCm"], 300)  # clamped to [50,300]
        self.assertEqual(pv.confidence, 1.0)  # clamped to 0..1

    def test_validate_spec_patch_dict(self):
        model = vision_spec_mapper.validate_spec_patch_dict(
            {"characterType": "anthro", "species": {"primary": "fox", "confidence": 0.8}}
        )
        self.assertEqual(model.character_type, "anthro")
        self.assertEqual(model.species.primary, "fox")

    def test_asset_patch_normalized(self):
        raw = {
            "provider_id": "kimi",
            "spec_patch": {
                "assetPatch": {
                    "hairColor": "#111222",
                    "eyeColor": "#333444",
                    "skinColor": "#E8CDB3",
                    "outfitColors": ["#FF0000", "red"],
                    "backPattern": " 背部白色条纹 ",
                }
            },
        }
        out = vision_spec_mapper.normalize(raw)
        ap = out.spec_patch.asset_patch
        self.assertIsNotNone(ap)
        self.assertEqual(ap.hair_color, "#111222")
        self.assertEqual(ap.eye_color, "#333444")
        self.assertEqual(ap.skin_color, "#E8CDB3")
        self.assertEqual(ap.outfit_colors, ["#FF0000"])
        self.assertEqual(ap.back_pattern, "背部白色条纹")

    def test_asset_patch_invalid_values_dropped(self):
        raw = {"provider_id": "kimi", "spec_patch": {"assetPatch": {"hairColor": "nope", "outfitColors": []}}}
        out = vision_spec_mapper.normalize(raw)
        self.assertIsNone(out.spec_patch.asset_patch)


class MockMultiViewTest(unittest.TestCase):
    def run_provider(self, refs):
        provider = MockVisionProvider()
        return asyncio.run(provider.analyze(refs, lambda _p: None))

    def test_mock_multi_view_per_view_matches_inputs(self):
        refs = [
            VisionImageInput(imageId="img_front", dataUrl="data:image/png;base64,AA", view="front"),
            VisionImageInput(imageId="img_side", dataUrl="data:image/png;base64,BB", view="side"),
            VisionImageInput(imageId="img_back", dataUrl="data:image/png;base64,CC", view="back"),
        ]
        raw = self.run_provider(refs)
        self.assertEqual(raw["source_image_ids"], ["img_front", "img_side", "img_back"])
        self.assertEqual(len(raw["per_view"]), 3)
        views = {pv["view"] for pv in raw["per_view"]}
        self.assertEqual(views, {"front", "side", "back"})
        ids = {pv["source_image_id"] for pv in raw["per_view"]}
        self.assertEqual(ids, {"img_front", "img_side", "img_back"})

        mapped = vision_spec_mapper.normalize(raw)
        self.assertEqual(len(mapped.per_view), 3)
        resolved = resolve_cross_view(mapped.per_view)
        self.assertEqual(resolved["conflicts"], [])
        self.assertEqual(resolved["unifiedPatch"]["characterType"], "human")

    def test_mock_single_view(self):
        refs = [VisionImageInput(imageId="img1", dataUrl="data:image/png;base64,AA", view="front")]
        raw = self.run_provider(refs)
        self.assertEqual(len(raw["per_view"]), 1)
        self.assertEqual(raw["per_view"][0]["view"], "front")
        self.assertEqual(raw["per_view"][0]["source_image_id"], "img1")
        mapped = vision_spec_mapper.normalize(raw)
        resolved = resolve_cross_view(mapped.per_view)
        self.assertEqual(resolved["conflicts"], [])
        self.assertEqual(resolved["unifiedPatch"]["characterType"], "human")

    def test_mock_no_view_defaults_front(self):
        refs = [VisionImageInput(imageId="img1", dataUrl="data:image/png;base64,AA", view=None)]
        raw = self.run_provider(refs)
        self.assertEqual(raw["per_view"][0]["view"], "front")


if __name__ == "__main__":
    unittest.main()
