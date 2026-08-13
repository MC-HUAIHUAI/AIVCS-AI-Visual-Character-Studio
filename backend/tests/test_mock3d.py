"""MockImage3DProvider behavior tests (Phase 2.3-A)."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app import config  # noqa: E402
from backend.app.providers.base import CancellationToken, ProviderCancelledError, ProviderError  # noqa: E402
from backend.app.providers.mock import MockImage3DProvider  # noqa: E402
from backend.app.schemas.character import CharacterSpec  # noqa: E402
from backend.app.schemas.vision import VisionImageInput  # noqa: E402


def make_spec(character_type="human", user_notes=""):
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
        characterType=character_type,
        userNotes=user_notes,
    )


class Mock3DTest(unittest.TestCase):
    def setUp(self):
        self._old_duration = config.MOCK3D_DURATION_SECONDS
        config.MOCK3D_DURATION_SECONDS = 0.02

    def tearDown(self):
        config.MOCK3D_DURATION_SECONDS = self._old_duration

    def run_gen(self, spec, cancel=None, refs=None):
        provider = MockImage3DProvider()
        return asyncio.run(provider.generate(spec, refs or [], lambda _i, _t, _m: None, cancel))

    def test_success_returns_demo_glb(self):
        data = self.run_gen(make_spec())
        self.assertEqual(data, config.DEMO_MODEL_PATH.read_bytes())

    def test_non_human_returns_fox(self):
        data = self.run_gen(make_spec(character_type="anthro"))
        self.assertEqual(data, config.DEMO_FOX_MODEL_PATH.read_bytes())

    def test_fail3d_raises_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_gen(make_spec(user_notes="please fail3d now"))
        self.assertIn("fail3d", str(ctx.exception))

    def test_cancelled_token_raises_cancelled(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(ProviderCancelledError):
            self.run_gen(make_spec(), cancel=token)

    def test_cancel_midway(self):
        config.MOCK3D_DURATION_SECONDS = 2.0
        token = CancellationToken()

        async def run_and_cancel():
            provider = MockImage3DProvider()
            task = asyncio.ensure_future(
                provider.generate(make_spec(), [], lambda _i, _t, _m: None, token)
            )
            await asyncio.sleep(0.05)
            token.cancel()
            try:
                await task
            except ProviderCancelledError:
                return True
            return False

        self.assertTrue(asyncio.run(run_and_cancel()))

    def test_references_accepted(self):
        refs = [VisionImageInput(imageId="a", dataUrl="data:image/png;base64,AA", view="front")]
        data = self.run_gen(make_spec(), refs=refs)
        self.assertEqual(data, config.DEMO_MODEL_PATH.read_bytes())


if __name__ == "__main__":
    unittest.main()
