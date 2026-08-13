"""Vision analysis schemas (Phase 2.1).

The request intentionally supports an array of references even though the
Phase 2.1 UI only sends one image, so multi-view (front/side/back) can be added
later without changing the API shape.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_DATA_URL_BYTES = 10 * 1024 * 1024
_DATA_URL_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,")

ReferenceView = Literal["front", "side", "back", "custom"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class VisionImageInput(_CamelModel):
    image_id: str = Field(alias="imageId")
    data_url: str = Field(alias="dataUrl")
    view: ReferenceView | None = None

    @field_validator("image_id")
    @classmethod
    def image_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("imageId 不能为空")
        return v

    @field_validator("data_url")
    @classmethod
    def validate_data_url(cls, v: str) -> str:
        if not _DATA_URL_RE.match(v):
            raise ValueError("dataUrl 必须是合法的 data:image/...;base64 格式")
        base64_part = v.split(",", 1)[1]
        approx_bytes = int(len(base64_part) * 3 / 4)
        if approx_bytes > MAX_DATA_URL_BYTES:
            raise ValueError("单张图片不能超过 10MB")
        return v


class VisionRequest(_CamelModel):
    provider: str = "mock"
    references: list[VisionImageInput] = Field(min_length=1)


class VisionSpeciesPatch(_CamelModel):
    primary: str | None = None
    secondary: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    label: str | None = None


class VisionAnatomyPatch(_CamelModel):
    has_head: bool | None = Field(default=None, alias="hasHead")
    has_face: bool | None = Field(default=None, alias="hasFace")
    has_torso: bool | None = Field(default=None, alias="hasTorso")
    has_limbs: bool | None = Field(default=None, alias="hasLimbs")
    tail: Literal["none", "single", "multiple"] | None = None
    wings: bool | None = None
    ears: bool | None = None
    horns: bool | None = None
    antlers: bool | None = None
    snout: bool | None = None
    muzzle: bool | None = None
    beak: bool | None = None
    paws: bool | None = None
    claws: bool | None = None
    hooves: bool | None = None
    fins: bool | None = None
    tentacles: bool | None = None
    extra_limbs: bool | None = Field(default=None, alias="extraLimbs")
    custom_appendages: list[str] | None = Field(default=None, alias="customAppendages")


class VisionFurPatch(_CamelModel):
    enabled: bool | None = None
    style: Literal["none", "toon", "anime", "stylized", "realistic"] | None = None
    length: Literal["short", "medium", "long"] | None = None
    colors: list[str] | None = None
    patterns: list[str] | None = None


class VisionAppearancePatch(_CamelModel):
    base_color: str | None = Field(default=None, alias="baseColor")
    secondary_colors: list[str] | None = Field(default=None, alias="secondaryColors")
    patterns: list[str] | None = None
    markings: list[str] | None = None
    palette: list[str] | None = None


class VisionAnalysisMeta(_CamelModel):
    provider_id: str = Field(alias="providerId")
    analyzed_at: str = Field(alias="analyzedAt")
    source_image_ids: list[str] = Field(alias="sourceImageIds")
    confidence: float


class VisionSpecPatch(_CamelModel):
    name: str | None = None
    description: str | None = None
    user_notes: str | None = Field(default=None, alias="userNotes")
    style: Literal["stylized", "realistic", "anime", "pixel"] | None = None
    gender: Literal["female", "male", "neutral"] | None = None
    height_cm: int | None = Field(default=None, alias="heightCm", ge=50, le=300)
    character_type: Literal[
        "human",
        "anime-human",
        "anthro",
        "animal",
        "fantasy-creature",
        "robot",
        "alien",
        "custom",
    ] | None = Field(default=None, alias="characterType")
    species: VisionSpeciesPatch | None = None
    body_type: Literal["humanoid", "biped-anthro", "quadruped", "bird", "dragon", "custom"] | None = Field(
        default=None, alias="bodyType"
    )
    anatomy: VisionAnatomyPatch | None = None
    fur: VisionFurPatch | None = None
    appearance: VisionAppearancePatch | None = None
    vision_analysis: VisionAnalysisMeta | None = Field(default=None, alias="visionAnalysis")


class VisionAnalysisResponse(_CamelModel):
    spec_patch: VisionSpecPatch = Field(alias="specPatch")
    confidence: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_image_ids: list[str] = Field(alias="sourceImageIds")
    provider_id: str = Field(alias="providerId")
