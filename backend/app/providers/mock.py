"""Mock provider: simulates the image-to-3D pipeline and returns a demo GLB.

This is what keeps Demo Mode fully functional with no AI API and no network.
The pipeline is character-aware: steps and the returned model reflect the
character type (human chibi vs anthro fox), proving the system is not hardwired
to humans.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .base import AIImage3DProvider, ProgressCallback
from ..schemas.character import CharacterSpec
from .. import config

NON_HUMAN_TYPES = {"anthro", "animal", "fantasy-creature", "robot", "alien", "custom"}

DEFAULTS = {
    "parsing": 0.35,
    "species": 0.45,
    "images": 0.45,
    "topology": 1.2,
    "materials": 0.6,
    "fur": 0.5,
    "rigging": 0.6,
    "final": 0.4,
}


def _build_steps(spec: CharacterSpec) -> list[str]:
    type_label = {
        "human": "人类",
        "anime-human": "二次元人类",
        "anthro": "兽人 / Furry",
        "animal": "动物",
        "fantasy-creature": "奇幻生物",
        "robot": "机器人",
        "alien": "外星生物",
        "custom": "自定义生物",
    }.get(spec.character_type, spec.character_type)
    steps: list[str] = [f"解析角色规格（{type_label}）"]
    if spec.character_type in NON_HUMAN_TYPES:
        steps.append("识别物种与解剖结构（模拟）")
    steps.append("生成 3D 拓扑（模拟）")
    steps.append("应用材质与贴图（模拟）")
    if spec.fur.enabled:
        fur_label = {
            "toon": "Toon 毛发",
            "anime": "动漫毛发",
            "stylized": "风格化毛发",
            "realistic": "写实毛发",
        }.get(spec.fur.style, "毛发")
        steps.append(f"应用{fur_label}（模拟）")
    rig_label = {
        "humanoid": "人类",
        "biped-anthro": "兽人（直立）",
        "quadruped": "四足动物",
        "bird": "鸟类",
        "dragon": "龙",
        "custom": "自定义",
    }.get(spec.body_type, "自定义")
    steps.append(f"按「{rig_label}」RigProfile 生成骨骼（模拟）")
    steps.append("导出 GLB")
    return steps


class MockImage3DProvider(AIImage3DProvider):
    id = "mock"
    name = "Mock"
    description = "Local mock that returns a bundled demo model matching the character type. No AI API required."

    async def generate(self, spec: CharacterSpec, on_progress: ProgressCallback) -> bytes:
        steps = _build_steps(spec)
        total = len(steps)
        for i, label in enumerate(steps):
            message = label
            if "物种" in label and spec.species.confidence is None:
                message = "无法确定角色物种，请选择或补充参考图。继续使用当前设定生成。"
            on_progress(i, total, message)
            await asyncio.sleep(DEFAULTS["parsing"] if i == 0 else 0.5)
        on_progress(total, total, "生成完成")

        is_creature = spec.character_type in NON_HUMAN_TYPES
        path: Path = config.DEMO_FOX_MODEL_PATH if is_creature else config.DEMO_MODEL_PATH
        if not path.exists():
            raise FileNotFoundError(f"Demo model missing: {path}")
        return path.read_bytes()
