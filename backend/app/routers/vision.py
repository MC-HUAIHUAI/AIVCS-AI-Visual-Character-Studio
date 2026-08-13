from fastapi import APIRouter, HTTPException

from ..providers.vision.base import VisionProviderError
from ..providers.vision.registry import select_vision_provider
from ..schemas.vision import VisionAnalysisResponse, VisionRequest
from ..services import vision_spec_mapper

router = APIRouter(prefix="/api/v1")


@router.post("/vision/analyze", response_model=VisionAnalysisResponse)
async def vision_analyze(request: VisionRequest):
    provider = select_vision_provider(request.provider)
    if provider is None:
        raise HTTPException(status_code=503, detail="视觉分析提供方不可用（未配置 API Key）")
    try:
        raw = await provider.analyze(request.references, lambda _p: None)
    except VisionProviderError as exc:
        # Provider errors are already user-safe (no keys, no raw dumps).
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return vision_spec_mapper.normalize(raw)
