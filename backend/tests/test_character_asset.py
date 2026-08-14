"""CharacterAsset tests (Phase 3-1)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.services.character_asset import apply_asset_patch, derive_character_asset  # noqa: E402


def make_spec():
    return CharacterSpec(
        id="s",
        name="t",
        style="stylized",
        gender="female",
        heightCm=160,
        description="",
        referenceImageIds=[],
        tags=[],
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:00Z",
        appearance={"baseColor": "#123456", "secondaryColors": ["#AABBCC"], "palette": ["#FF0000", "#00FF00"]},
        fur={"enabled": True, "style": "toon", "length": "medium", "colors": ["#111111"], "patterns": ["条纹"]},
    )


class CharacterAssetTest(unittest.TestCase):
    def test_derive_deterministic(self):
        a = derive_character_asset(make_spec())
        b = derive_character_asset(make_spec())
        self.assertEqual(a.model_dump(), b.model_dump())

    def test_derive_palette_and_provenance(self):
        asset = derive_character_asset(make_spec())
        self.assertEqual(asset.palette, ["#FF0000", "#00FF00"])
        self.assertEqual(asset.base_color, "#123456")
        self.assertEqual(asset.source["palette"], "derived")
        self.assertEqual(asset.source["baseColor"], "derived")
        self.assertEqual(asset.source["outfitColors"], "derived")
        self.assertEqual(asset.outfit_colors, ["#FF0000", "#00FF00"])

    def test_derive_absent_fields_none(self):
        asset = derive_character_asset(make_spec())
        self.assertIsNone(asset.hair_color)
        self.assertIsNone(asset.eye_color)
        self.assertIsNone(asset.skin_color)
        self.assertIsNone(asset.back_pattern)
        self.assertNotIn("hairColor", asset.source)
        self.assertNotIn("eyeColor", asset.source)

    def test_derive_empty_spec(self):
        asset = derive_character_asset(make_spec().model_copy(update={"appearance": None, "fur": None}))
        self.assertEqual(asset.palette, [])
        self.assertIsNone(asset.base_color)
        self.assertEqual(asset.source, {})

    def test_apply_patch_observed(self):
        base = derive_character_asset(make_spec())
        merged = apply_asset_patch(
            base,
            {
                "hairColor": "#111222",
                "eyeColor": "#333444",
                "skinColor": "#E8CDB3",
                "outfitColors": ["#FF0000", "#0000FF"],
                "backPattern": "背部白色条纹",
            },
        )
        self.assertEqual(merged.hair_color, "#111222")
        self.assertEqual(merged.source["hairColor"], "observed")
        self.assertEqual(merged.eye_color, "#333444")
        self.assertEqual(merged.skin_color, "#E8CDB3")
        self.assertEqual(merged.outfit_colors, ["#FF0000", "#0000FF"])
        self.assertEqual(merged.back_pattern, "背部白色条纹")
        # derived palette untouched
        self.assertEqual(merged.palette, ["#FF0000", "#00FF00"])

    def test_apply_patch_clamps_invalid(self):
        base = derive_character_asset(make_spec())
        merged = apply_asset_patch(base, {"hairColor": "nope", "outfitColors": ["red", "#00AA00"]})
        self.assertIsNone(merged.hair_color)
        self.assertEqual(merged.outfit_colors, ["#00AA00"])


if __name__ == "__main__":
    unittest.main()
