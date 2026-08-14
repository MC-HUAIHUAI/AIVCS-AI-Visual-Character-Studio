"""CrossViewResolver unit tests (Phase 2.2-A).

Run from the project root:
    python -m unittest discover -s backend/tests -v
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app.schemas.vision import ViewAnalysis  # noqa: E402
from backend.app.services.cross_view_resolver import resolve_cross_view  # noqa: E402


def va(view, patch, conf, source="img"):
    return ViewAnalysis(view=view, sourceImageId=source, specPatch=patch, confidence=conf)


class CrossViewResolverTest(unittest.TestCase):
    def test_single_view_no_conflict(self):
        views = [va("front", {"characterType": "anthro", "species": {"primary": "fox"}}, 0.9)]
        out = resolve_cross_view(views)
        self.assertEqual(out["unifiedPatch"]["characterType"], "anthro")
        self.assertEqual(out["unifiedPatch"]["species"]["primary"], "fox")
        self.assertEqual(out["conflicts"], [])

    def test_multi_view_consistent_no_conflict(self):
        views = [
            va("front", {"characterType": "anthro", "species": {"primary": "fox"}}, 0.9),
            va("side", {"characterType": "anthro", "species": {"primary": "fox"}}, 0.8),
            va("back", {"characterType": "anthro", "species": {"primary": "fox"}}, 0.7),
        ]
        out = resolve_cross_view(views)
        self.assertEqual(out["unifiedPatch"]["species"]["primary"], "fox")
        self.assertEqual(out["conflicts"], [])

    def test_species_conflict_default_highest_confidence(self):
        views = [
            va("front", {"species": {"primary": "fox"}}, 0.9),
            va("back", {"species": {"primary": "wolf"}}, 0.8),
        ]
        out = resolve_cross_view(views)
        self.assertEqual(out["unifiedPatch"]["species"]["primary"], "fox")
        self.assertEqual(len(out["conflicts"]), 1)
        c = out["conflicts"][0]
        self.assertEqual(c.field, "species.primary")
        self.assertEqual(c.resolved_to.value, "fox")
        self.assertEqual({x.value for x in c.candidates}, {"fox", "wolf"})

    def test_species_conflict_winner_by_confidence(self):
        views = [
            va("front", {"species": {"primary": "fox"}}, 0.6),
            va("back", {"species": {"primary": "wolf"}}, 0.9),
        ]
        out = resolve_cross_view(views)
        self.assertEqual(out["unifiedPatch"]["species"]["primary"], "wolf")
        self.assertEqual(len(out["conflicts"]), 1)

    def test_anatomy_bool_conflict(self):
        views = [
            va("front", {"anatomy": {"ears": True}}, 0.9),
            va("back", {"anatomy": {"ears": False}}, 0.8),
        ]
        out = resolve_cross_view(views)
        self.assertEqual(out["unifiedPatch"]["anatomy"]["ears"], True)
        self.assertEqual(len(out["conflicts"]), 1)
        self.assertEqual(out["conflicts"][0].field, "anatomy.ears")

    def test_missing_field_in_one_view_no_conflict(self):
        views = [
            va("front", {"anatomy": {"tail": "single"}}, 0.9),
            va("side", {}, 0.8),  # no tail observed
        ]
        out = resolve_cross_view(views)
        self.assertEqual(out["unifiedPatch"]["anatomy"]["tail"], "single")
        self.assertEqual(out["conflicts"], [])

    def test_explicit_false_is_observed(self):
        views = [
            va("front", {"anatomy": {"tail": "single"}}, 0.9),
            va("back", {"anatomy": {"tail": "none"}}, 0.8),
        ]
        out = resolve_cross_view(views)
        self.assertEqual(out["unifiedPatch"]["anatomy"]["tail"], "single")
        self.assertEqual(len(out["conflicts"]), 1)
        self.assertEqual(out["conflicts"][0].field, "anatomy.tail")

    def test_absent_everywhere_not_in_patch(self):
        views = [va("front", {"characterType": "human"}, 0.9)]
        out = resolve_cross_view(views)
        self.assertNotIn("heightCm", out["unifiedPatch"])
        self.assertNotIn("fur", out["unifiedPatch"])

    def test_pass_through_single_source(self):
        views = [
            va("front", {"name": "fox_name", "fur": {"colors": ["#E67E22"]}}, 0.9),
            va("back", {"name": "other_name", "fur": {"colors": ["#000000"]}}, 0.5),
        ]
        out = resolve_cross_view(views)
        self.assertEqual(out["unifiedPatch"]["name"], "fox_name")
        self.assertEqual(out["unifiedPatch"]["fur"]["colors"], ["#E67E22"])
        self.assertEqual(out["conflicts"], [])

    def test_deterministic(self):
        views = [
            va("front", {"species": {"primary": "fox"}}, 0.9),
            va("back", {"species": {"primary": "wolf"}}, 0.8),
            va("side", {"anatomy": {"ears": True}}, 0.7),
        ]
        a = resolve_cross_view(views)
        b = resolve_cross_view(views)
        self.assertEqual(a, b)

    def test_asset_patch_merge_no_conflict(self):
        views = [
            va("front", {"assetPatch": {"hairColor": "#111222", "eyeColor": "#333444"}}, 0.9),
            va("back", {"assetPatch": {"outfitColors": ["#FF0000"], "backPattern": "白色背纹"}}, 0.7),
        ]
        out = resolve_cross_view(views)
        ap = out["unifiedPatch"]["assetPatch"]
        self.assertEqual(ap["hairColor"], "#111222")
        self.assertEqual(ap["outfitColors"], ["#FF0000"])
        self.assertEqual(ap["backPattern"], "白色背纹")
        self.assertEqual(out["conflicts"], [])

    def test_asset_patch_color_conflict(self):
        views = [
            va("front", {"assetPatch": {"hairColor": "#111222"}}, 0.9),
            va("back", {"assetPatch": {"hairColor": "#333444"}}, 0.8),
        ]
        out = resolve_cross_view(views)
        self.assertEqual(out["unifiedPatch"]["assetPatch"]["hairColor"], "#111222")
        fields = {c.field for c in out["conflicts"]}
        self.assertIn("assetPatch.hairColor", fields)

    def test_empty_and_malformed_do_not_crash(self):
        self.assertEqual(resolve_cross_view([])["conflicts"], [])
        # Pydantic already rejects specPatch=None; malformed nested values must
        # be tolerated (non-dict parents are treated as "not observed").
        weird = ViewAnalysis(
            view="front",
            sourceImageId="x",
            specPatch={"characterType": "human", "species": "nonsense", "anatomy": None},
            confidence=0.5,
        )
        out = resolve_cross_view([weird])
        self.assertEqual(out["unifiedPatch"]["characterType"], "human")
        self.assertNotIn("species", out["unifiedPatch"])
        self.assertEqual(out["conflicts"], [])


if __name__ == "__main__":
    unittest.main()
