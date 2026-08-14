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

    def test_runtime_wins_over_env(self):
        # User Settings (runtime) MUST override a developer .env key.
        config.set_runtime_vision(base_url="https://user.example.com", api_key="user-key")
        config.KIMI_API_KEY = "env-key"
        config.KIMI_BASE_URL = "https://env.example.com"
        eff = config.effective_kimi_config()
        self.assertEqual(eff["api_key"], "user-key")
        self.assertEqual(eff["base_url"], "https://user.example.com")
        self.assertEqual(eff["source"], "runtime")

    def test_only_env_falls_back_to_env(self):
        config.set_runtime_vision()
        config.KIMI_API_KEY = "env-key"
        config.KIMI_BASE_URL = "https://env.example.com"
        eff = config.effective_kimi_config()
        self.assertEqual(eff["api_key"], "env-key")
        self.assertEqual(eff["source"], "env")

    def test_only_runtime(self):
        config.set_runtime_vision(base_url="https://runtime.example.com", api_key="runtime-key", model="m")
        config.KIMI_API_KEY = ""
        eff = config.effective_kimi_config()
        self.assertEqual(eff["api_key"], "runtime-key")
        self.assertEqual(eff["base_url"], "https://runtime.example.com")
        self.assertEqual(eff["model"], "m")
        self.assertEqual(eff["source"], "runtime")

    def test_none_configured_mock(self):
        config.set_runtime_vision()
        config.KIMI_API_KEY = ""
        eff = config.effective_kimi_config()
        self.assertEqual(eff["api_key"], "")
        self.assertEqual(eff["source"], "mock")

    def test_runtime_cleared_falls_back_to_env(self):
        # runtime key cleared -> env fallback allowed.
        config.set_runtime_vision(base_url="https://user.example.com", api_key="user-key")
        config.KIMI_API_KEY = "env-key"
        config.set_runtime_vision()  # user clears Settings
        eff = config.effective_kimi_config()
        self.assertEqual(eff["api_key"], "env-key")
        self.assertEqual(eff["source"], "env")

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
        self.assertIn("source", result)
        self.assertNotIn("apiKey", result)
        self.assertNotIn("secret-key", str(result))

    def test_vision_registry_kimi_absent_without_key(self):
        config.set_runtime_vision()
        config.KIMI_API_KEY = ""
        from backend.app.providers.vision import registry as vision_registry

        vision_registry.rebuild_registry()
        self.assertNotIn("kimi", vision_registry.REGISTRY)
        self.assertIn("mock", vision_registry.REGISTRY)

    def test_external3d_toggle_requires_token(self):
        from fastapi import HTTPException

        async def run():
            await config_router.set_external3d_enabled(
                config_router.External3DConfigRequest(enabled=True),
                x_aivcs_config_token=None,
            )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(run())
        self.assertEqual(ctx.exception.status_code, 403)

    def test_external3d_toggle_ok_keeps_identity(self):
        async def run():
            return await config_router.set_external3d_enabled(
                config_router.External3DConfigRequest(enabled=True),
                x_aivcs_config_token=config.LOCAL_CONFIG_TOKEN,
            )

        result = asyncio.run(run())
        self.assertTrue(result["ok"])
        self.assertTrue(result["external3dEnabled"])
        # identity still registered, just enabled
        from backend.app.providers import registry

        self.assertIn("real-placeholder", registry.REGISTRY)
        self.assertTrue(registry.is_provider_available("real-placeholder"))

    def test_external3d_default_disabled(self):
        from backend.app import config as cfg

        cfg.set_runtime_external3d(False)
        from backend.app.providers import registry

        self.assertFalse(registry.is_provider_available("real-placeholder"))
        self.assertTrue(registry.is_provider_available("mock"))
        self.assertTrue(registry.is_provider_available("mock-remote"))

    def test_runtime_token_file_honors_env(self):
        # Packaged scenario: launcher sets AIVCS_RUNTIME_TOKEN_FILE to a
        # writable userData path; backend must write the token there.
        import tempfile

        from backend.app import config as cfg

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "runtime_config_token")
            old = cfg.RUNTIME_TOKEN_FILE
            try:
                cfg.RUNTIME_TOKEN_FILE = __import__("pathlib").Path(target)
                cfg.write_runtime_token_file()
                self.assertTrue(os.path.exists(target))
                content = open(target, encoding="utf-8").read().strip()
                self.assertEqual(content, cfg.LOCAL_CONFIG_TOKEN)
            finally:
                cfg.RUNTIME_TOKEN_FILE = old


if __name__ == "__main__":
    unittest.main()
