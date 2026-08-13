"""Kimi (Moonshot) vision provider - Phase 2.2-B multi-view joint analysis.

Sends ALL reference views in ONE request (joint mode) so the org RPM limit is
never multiplied by the number of images. Each image is labeled with its view
(front/side/back/custom). The provider only emits per-view observations; the
final unified patch and conflicts are computed by the CrossViewResolver.

Source image ids are ALWAYS rebound server-side from the request references -
the model's own ids/views are never trusted.

Only stdlib (urllib) is used - no SDK, no new dependencies.

API Key: read from AIVCS_KIMI_API_KEY in the backend environment only.
It is never logged, never returned in responses, and never exposed to the
frontend.
"""

from __future__ import annotations

import asyncio
import json
from urllib import error, request

from .base import AIVisionProvider, VisionProgressCallback, VisionProviderError
from ... import config
from ...schemas.vision import VisionImageInput

MAX_REFERENCES = 4

VIEW_LABELS = {
    "front": "这是同一角色的正面视角（front）：",
    "side": "这是同一角色的侧面视角（side）：",
    "back": "这是同一角色的背面视角（back）：",
    "custom": "这是同一角色的自定义视角（custom）：",
}

SYSTEM_PROMPT = """你是一个专业的角色设定分析器。以下所有图片都属于【同一个角色】，只是不同的观察视角（正面 front / 侧面 side / 背面 back / 自定义 custom）。

严格输出要求：
- 只输出一个 JSON 对象，不要输出任何其他文字。
- 不要使用 Markdown 代码围栏（```）。
- 不要添加任何解释。
- 所有枚举值必须使用下面给定的取值；无法确定时使用 "custom" 或置为 null，绝对不要猜测。

跨视角一致性规则（非常重要）：
- 所有视角是同一个角色。禁止因为视角不同而改变：characterType、species、bodyType、fur、anatomy、palette、markings。
- 某个视角看不到的身体部位不要猜测；例如侧面或背面看不到脸部时，不要强行推断脸部特征。
- 背面视角可以补充尾巴、背部花纹、背面配色等信息。
- 为每个视角单独输出它观察到的 specPatch（perView[]），并额外输出一份统一的 specPatch。
- 无法判断时：species.primary 用 "custom"、species.confidence 用 null，并在 warnings 中写明"无法确定角色物种，请选择或补充参考图"。
- conflicts 请一律输出 []（系统会自行做跨视角冲突检测，不要输出自定义 conflicts）。

输出结构：
{
  "specPatch": { },
  "perView": [
    {
      "view": "front" | "side" | "back" | "custom",
      "specPatch": { },
      "confidence": 0.0,
      "notes": [],
      "warnings": []
    }
  ],
  "confidence": 0.0,
  "notes": [],
  "warnings": []
}

specPatch 允许的字段与取值（camelCase）：
- characterType: "human" | "anime-human" | "anthro" | "animal" | "fantasy-creature" | "robot" | "alien" | "custom"
- style: "stylized" | "realistic" | "anime" | "pixel"
- gender: "female" | "male" | "neutral"
- bodyType: "humanoid" | "biped-anthro" | "quadruped" | "bird" | "dragon" | "custom"
- heightCm: 整数，范围 50-300
- name: 建议的角色名称（可省略）
- description: 简短的外观/服装描述（可省略）
- userNotes: 其他补充说明（可省略）
- species: {
    "primary": "wolf"|"fox"|"cat"|"dog"|"bear"|"rabbit"|"deer"|"dragon"|"bird"|"reptile"|"aquatic"|"insect"|"custom",
    "secondary": 同上 或 null,
    "confidence": 0.0-1.0 或 null,
    "label": 自定义物种名称或 null
  }
- anatomy: {
    "tail": "none"|"single"|"multiple",
    "ears"/"horns"/"antlers"/"wings"/"snout"/"muzzle"/"beak"/"paws"/"claws"/"hooves"/"fins"/"tentacles"/"extraLimbs": true/false（只放有信心的项）
  }
- fur: {
    "enabled": true/false,
    "style": "none"|"toon"|"anime"|"stylized"|"realistic",
    "length": "short"|"medium"|"long",
    "colors": ["#RRGGBB"]
  }
- appearance: {
    "baseColor": "#RRGGBB" 或 null,
    "secondaryColors": ["#RRGGBB"],
    "patterns": [],
    "markings": [],
    "palette": ["#RRGGBB"]
  }

规则：
1. 无法确定物种时：species.primary 必须为 "custom"，species.confidence 必须为 null，并在 warnings 中写明"无法确定角色物种，请选择或补充参考图"。
2. 不要为了完整性而猜测。没有把握的字段直接省略。
3. confidence 是本次整体分析的置信度，范围 0.0-1.0；perView 每项也有各自的 confidence（该视角观察的置信度）。
4. 只输出 specPatch / perView / confidence / notes / warnings 五个顶层字段。不要输出 sourceImageIds、visionAnalysis、project、assets、mesh 等任何其他字段。
5. perView 每一项的 view 必须与输入视角一致，不要输出 sourceImageId（服务端会绑定）。
6. palette 只接受 #RRGGBB 格式，其他格式一律丢弃。
7. 人类与二次元人类都是合法角色类型，不要强行把二次元角色判成 "human"。
"""

USER_FINAL_INSTRUCTION = "请基于以上所有视角，按 system 提示词要求输出 JSON。"


class KimiVisionProvider(AIVisionProvider):
    id = "kimi"
    display_name = "Kimi Vision"
    requires_backend = True
    description = "Moonshot Kimi (kimi-k2.6) 官方视觉理解，支持多视角联合分析。需配置 AIVCS_KIMI_API_KEY。"

    async def analyze(
        self,
        inputs: list[VisionImageInput],
        on_progress: VisionProgressCallback,
    ) -> dict:
        if not config.KIMI_API_KEY:
            raise VisionProviderError("Kimi API Key 未配置")
        if len(inputs) > MAX_REFERENCES:
            raise VisionProviderError(f"一次最多支持 {MAX_REFERENCES} 张参考图（front/side/back/custom）")
        on_progress(0.0)

        content: list[dict] = []
        for item in inputs:
            label = VIEW_LABELS.get(item.view or "front", VIEW_LABELS["custom"])
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": {"url": item.data_url}})
        content.append({"type": "text", "text": USER_FINAL_INSTRUCTION})

        payload = {
            "model": config.KIMI_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 5000,
            "stream": False,
        }

        on_progress(0.3)
        raw_text = await asyncio.to_thread(self._call_api, payload)
        on_progress(0.7)
        parsed = self._parse_json(raw_text)
        on_progress(1.0)

        return {
            "spec_patch": parsed.get("specPatch", {}) if isinstance(parsed.get("specPatch"), dict) else {},
            "per_view": self._extract_per_views(parsed, inputs),
            "confidence": parsed.get("confidence"),
            "notes": parsed.get("notes", []),
            "warnings": parsed.get("warnings", []),
            "source_image_ids": [item.image_id for item in inputs],
            "provider_id": self.id,
        }

    @staticmethod
    def _extract_per_views(parsed: dict, inputs: list[VisionImageInput]) -> list[dict]:
        """Rebind per-view observations to server-known ids.

        Only entries whose view matches one of the request references survive;
        their source image id is taken from the request, never from the model.
        """
        view_ids: dict[str, str] = {}
        for item in inputs:
            view = item.view or "front"
            view_ids.setdefault(view, item.image_id)

        raw_per_view = parsed.get("perView")
        out: list[dict] = []
        if isinstance(raw_per_view, list):
            for pv in raw_per_view:
                if not isinstance(pv, dict):
                    continue
                view = pv.get("view")
                image_id = view_ids.get(view)
                if image_id is None:
                    continue  # unknown/unmatched view -> drop
                out.append(
                    {
                        "view": view,
                        "source_image_id": image_id,
                        "spec_patch": pv.get("specPatch", {}) if isinstance(pv.get("specPatch"), dict) else {},
                        "confidence": pv.get("confidence"),
                        "notes": pv.get("notes", []),
                        "warnings": pv.get("warnings", []),
                    }
                )
        return out

    # ------------------------------------------------------------------ #
    # HTTP + parsing (kept separate so it can be unit-tested offline)     #
    # ------------------------------------------------------------------ #

    def _call_api(self, payload: dict) -> str:
        url = config.KIMI_BASE_URL.rstrip("/") + "/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {config.KIMI_API_KEY}")
        try:
            with request.urlopen(req, timeout=config.KIMI_TIMEOUT_SECONDS) as resp:
                raw_body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            self._raise_http_error(exc)
        except TimeoutError as exc:
            raise VisionProviderError("Kimi 请求超时，请稍后重试") from exc
        except error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, TimeoutError):
                raise VisionProviderError("Kimi 请求超时，请稍后重试") from exc
            raise VisionProviderError("Kimi 请求失败，请稍后重试") from exc

        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise VisionProviderError("Kimi 返回格式错误（响应不是 JSON）") from exc
        if not isinstance(data, dict):
            raise VisionProviderError("Kimi 返回格式错误（响应不是 JSON 对象）")

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise VisionProviderError("Kimi 返回了无效响应（无 choices）")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content is None or not str(content).strip():
            raise VisionProviderError("Kimi 返回了空内容")
        return str(content)

    @staticmethod
    def _raise_http_error(exc: error.HTTPError) -> None:
        code = exc.code
        if code in (401, 403):
            raise VisionProviderError("Kimi API Key 无效或未授权") from exc
        if code == 429:
            raise VisionProviderError("Kimi 请求过于频繁，请稍后重试") from exc
        if code >= 500:
            raise VisionProviderError("Kimi 服务异常，请稍后重试") from exc
        raise VisionProviderError(f"Kimi 请求失败（HTTP {code}）") from exc

    @staticmethod
    def _parse_json(content: str) -> dict:
        text = content.strip()
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl + 1 :]
            if text.endswith("```"):
                text = text[: -len("```")]
            text = text.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise VisionProviderError("Kimi 返回格式错误（无法解析 JSON）") from exc
        if not isinstance(parsed, dict):
            raise VisionProviderError("Kimi 返回格式错误（顶层不是 JSON 对象）")
        return parsed
