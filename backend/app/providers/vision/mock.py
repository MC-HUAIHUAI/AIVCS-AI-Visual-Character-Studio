"""Mock vision provider (multi-view aware).

Deliberately does not analyze image content: it returns a deterministic,
honest result flagged as mock so the whole pipeline is testable without any AI
API. Every per-view entry is built from the actual request references (view and
image id) - never hardcoded.
"""

from __future__ import annotations

import asyncio

from .base import AIVisionProvider, VisionProgressCallback
from ...schemas.vision import VisionImageInput


class MockVisionProvider(AIVisionProvider):
    id = "mock"
    display_name = "Mock"
    requires_backend = False
    description = "本地模拟视觉分析，未真正识别图片，无需 API。"

    async def analyze(
        self,
        inputs: list[VisionImageInput],
        on_progress: VisionProgressCallback,
    ) -> dict:
        on_progress(0.0)
        await asyncio.sleep(0.15)
        on_progress(0.6)
        await asyncio.sleep(0.15)
        on_progress(1.0)

        per_view = [
            {
                "view": item.view if item.view else "front",
                "source_image_id": item.image_id,
                "spec_patch": {
                    "characterType": "human",
                    "assetPatch": {},
                },
                "confidence": 0.1,
                "notes": ["Mock 模式：未真正分析图片"],
                "warnings": ["无法确定角色物种，请选择或补充参考图。"],
            }
            for item in inputs
        ]

        return {
            "spec_patch": {"character_type": "human", "asset_patch": {}},
            "per_view": per_view,
            "confidence": 0.1,
            "notes": ["Mock 模式：未真正分析图片"],
            "warnings": ["无法确定角色物种，请选择或补充参考图。"],
            "source_image_ids": [item.image_id for item in inputs],
            "provider_id": self.id,
        }
