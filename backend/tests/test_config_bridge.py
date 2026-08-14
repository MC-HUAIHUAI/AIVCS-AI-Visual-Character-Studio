"""Phase 3-5A runtime config bridge tests."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.app import config  # noqa: E402
from backend.app.providers.vision import registry as vision_registry  # noqa: E402
from backend.app.routers import config as config_router  # noqa: E402


class RuntimeVisionConfigTest(unittest.TestCase):
    def setUp(self):
        # Isolate runtime overrides + env-captured constants.
        self._old_vision = dict(config._RUNTIME_VISION)
        self._old_key = config.KIMI_API_KEY
        self._old_base = config.KIMI_BASE_URL
        self._old_model = config.KIMI_MODEL
        config.set_runtime_vision()
        config.KIMI_API_KEY = ""
        config.KIMI_BASE_URL = "https://env.example.com"
        config.KIMI_MODEL = "kimi-env"

    def tearDown(self):
        config._RUNTIME_VISION.update(self._old_vision)
        config.KIMI_API_KEY = self._old_key
        config.KIMI_BASE_URL = self._old_base
        config.KIMI_MODEL = self._old_model
        from backend.app.providers.vision import registry as vision_registry

        vision_registry.rebuild_registry()

    def test_effective_config_env_wins(self):
        config.set_runtime_vision(base_url="https://runtime.example.com", api_key="runtime-key")
        config.KIMI_API_KEY = "env-key"
        config.KIMI_BASE_URL = "https://env.example.com"
        eff = config.effective_kimi_config()
        self.assertEqual(eff["api_key"], "env-key")
        self.assertEqual(eff["base_url"], "https://env.example.com")

    def test_effective_config_runtime_fallback(self):
        config.set_runtime_vision(base_url="https://runtime.example.com", api_key="runtime-key", model="m")
        eff = config.effective_kimi_config()
        self.assertEqual(eff["api_key"], "runtime-key")
        self.assertEqual(eff["base_url"], "https://runtime.example.com")
        self.assertEqual(eff["model"], "m")

    def test_no_key_anywhere(self):
        config.set_runtime_vision()
        eff = config.effective_kimi_config()
        self.assertEqual(eff["api_key"], "")

    def test_config_endpoint_requires_token(self):
        from fastapi import HTTPException

        async def run():
            await config_router.set_vision_config(
                config_router.VisionConfigRequest(baseUrl="https://x.example.com", apiKey="k"),
                x_aivcs_config_token=None,
            )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(run())
        self.assertEqual(ctx.exception.status_code, 403)

    def test_config_endpoint_ok_no_key_in_response(self):
        async def run():
            return await config_router.set_vision_config(
                config_router.VisionConfigRequest(
                    baseUrl="https://runtime.example.com",
                    apiKey="secret-key",
                    model="m",
                ),
                x_aivcs_config_token=config.LOCAL_CONFIG_TOKEN,
            )

        result = asyncio.run(run())
        self.assertTrue(result["ok"])
        self.assertIn("visionConfigured", result)
        self.assertNotIn("apiKey", result)
        self.assertNotIn("secret-key", str(result))

    def test_vision_registry_kimi_absent_without_key(self):
        config.set_runtime_vision()
        config.KIMI_API_KEY = ""
        from backend.app.providers.vision import registry as vision_registry

        vision_registry.rebuild_registry()
        self.assertNotIn("kimi", vision_registry.REGISTRY)
        self.assertIn("mock", vision_registry.REGISTRY)


if __name__ == "__main__":
    unittest.main()
