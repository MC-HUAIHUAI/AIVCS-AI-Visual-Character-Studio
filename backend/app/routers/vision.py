from fastapi import APIRouter, HTTPException

from ..providers.vision.base import VisionProviderError
from ..providers.vision.registry import select_vision_provider
from ..schemas.vision import VisionAnalysisResponse, VisionRequest
from ..services import cross_view_resolver, vision_spec_mapper

router = APIRouter(prefix="/api/v1")


@router.post("/vision/analyze", response_model=VisionAnalysisResponse)
async def vision_analyze(request: VisionRequest):
    if request.analysis_mode != "joint":
        raise HTTPException(status_code=400, detail="per-view 模式尚未实现，请使用 joint 模式")

    provider = select_vision_provider(request.provider)
    if provider is None:
        raise HTTPException(status_code=503, detail="视觉分析提供方不可用（未配置 API Key）")

    try:
        raw = await provider.analyze(request.references, lambda _p: None)
    except VisionProviderError as exc:
        # Provider errors are already user-safe (no keys, no raw dumps).
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Provider output -> mapper (normalize, incl. perView) -> CrossViewResolver.
    # The final unified patch AND conflicts always come from the resolver.
    mapped = vision_spec_mapper.normalize(raw)
    if mapped.per_view:
        resolved = cross_view_resolver.resolve_cross_view(mapped.per_view)
        mapped.spec_patch = vision_spec_mapper.validate_spec_patch_dict(resolved["unifiedPatch"])
        mapped.conflicts = resolved["conflicts"] or None
        # Phase 3-2: surface the merged assetPatch to the client (goes through
        # the review/confirmation flow before reaching the CharacterAsset).
        asset_patch = resolved["unifiedPatch"].get("assetPatch")
        if isinstance(asset_patch, dict):
            from ..schemas.vision import VisionAssetPatch

            try:
                mapped.asset_patch = VisionAssetPatch.model_validate(asset_patch)
            except Exception:  # noqa: BLE001 - invalid patch is dropped, never crashes
                mapped.asset_patch = None

    return mapped
