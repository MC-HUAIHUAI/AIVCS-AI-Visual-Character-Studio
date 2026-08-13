"""Backend schemas mirroring the shared TypeScript contracts (src/shared/types.ts)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .vision import VisionAnalysisMeta, VisionImageInput

CharacterStyle = Literal["stylized", "realistic", "anime", "pixel"]
CharacterGender = Literal["female", "male", "neutral"]
JobStatus = Literal["queued", "running", "done", "failed", "timed_out", "cancelled"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class SpeciesInfo(_CamelModel):
    primary: str = "custom"
    secondary: str | None = None
    confidence: float | None = None
    label: str | None = None


class FurProfile(_CamelModel):
    enabled: bool = False
    style: str = "stylized"
    length: str = "medium"
    colors: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class AppearanceProfile(_CamelModel):
    base_color: str | None = Field(default=None, alias="baseColor")
    secondary_colors: list[str] = Field(default_factory=list, alias="secondaryColors")
    patterns: list[str] = Field(default_factory=list)
    markings: list[str] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)


class AnatomyGraph(_CamelModel):
    has_head: bool = Field(default=True, alias="hasHead")
    has_face: bool = Field(default=True, alias="hasFace")
    has_torso: bool = Field(default=True, alias="hasTorso")
    has_limbs: bool = Field(default=True, alias="hasLimbs")
    tail: str = "none"
    wings: bool = False
    ears: bool = True
    horns: bool = False
    antlers: bool = False
    snout: bool = False
    muzzle: bool = False
    beak: bool = False
    paws: bool = False
    claws: bool = False
    hooves: bool = False
    fins: bool = False
    tentacles: bool = False
    extra_limbs: bool = Field(default=False, alias="extraLimbs")
    custom_appendages: list[str] = Field(default_factory=list, alias="customAppendages")


class CharacterSpec(_CamelModel):
    id: str
    name: str
    style: CharacterStyle
    gender: CharacterGender
    height_cm: int = Field(alias="heightCm")
    description: str
    reference_image_ids: list[str] = Field(alias="referenceImageIds")
    tags: list[str]
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")

    # Phase 1 - non-human support (all optional with defaults for old projects).
    character_type: str = Field(default="human", alias="characterType")
    species: SpeciesInfo = Field(default_factory=SpeciesInfo)
    body_type: str = Field(default="humanoid", alias="bodyType")
    anatomy: AnatomyGraph = Field(default_factory=AnatomyGraph)
    fur: FurProfile = Field(default_factory=FurProfile)
    appearance: AppearanceProfile = Field(default_factory=AppearanceProfile)

    # Phase 2.1 - vision provenance (optional, backward compatible).
    user_notes: str | None = Field(default=None, alias="userNotes")
    vision_analysis: VisionAnalysisMeta | None = Field(default=None, alias="visionAnalysis")


class GenerateRequest(_CamelModel):
    provider: str = "mock"
    spec: CharacterSpec
    reference_image_ids: list[str] = Field(default_factory=list, alias="referenceImageIds")
    # Phase 2.3: actual reference image payloads (data URLs) so a real image-to-3D
    # provider can consume them. Reuses VisionImageInput - no second input type.
    references: list[VisionImageInput] = Field(default_factory=list)
    timeout_seconds: float | None = Field(default=None, alias="timeoutSeconds")

    @field_validator("references")
    @classmethod
    def references_within_limit(cls, v: list[VisionImageInput]) -> list[VisionImageInput]:
        if len(v) > 4:
            raise ValueError("一次最多支持 4 张参考图（front/side/back/custom）")
        return v


class JobStep(_CamelModel):
    index: int
    label: str
    status: Literal["pending", "running", "done", "failed"]


class JobResult(_CamelModel):
    model_id: str = Field(alias="modelId")


class JobStatusResponse(_CamelModel):
    job_id: str = Field(alias="jobId")
    status: JobStatus
    progress: float  # 0..1
    message: str
    steps: list[JobStep]
    error: str | None = None
    result: JobResult | None = None
    # Phase 2.3 state machine metadata (all optional / backward compatible).
    deadline_at: float | None = Field(default=None, alias="deadlineAt")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    retryable: bool = False
    cancelled_by_user: bool = Field(default=False, alias="cancelledByUser")
    timed_out: bool = Field(default=False, alias="timedOut")
    attempt: int = 1


class HealthResponse(_CamelModel):
    status: str
    name: str
    version: str
    providers: list[str]
