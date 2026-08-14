from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .. import config
from ..jobs import cancel_job, create_job, get_job, get_model, get_model_record
from ..providers.registry import get_provider, list_providers
from ..schemas.asset import GlbStats
from ..schemas.character import GenerateRequest, JobStatusResponse, ModelMetaResponse
from ..services.vrm_exporter import VrmExportError, export_vrm
from ..services.model_store import spec_hash

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "name": config.BACKEND_NAME,
        "version": config.BACKEND_VERSION,
        "providers": list_providers(),
    }


@router.post("/generate/image-to-3d", status_code=202)
async def generate_image_to_3d(request: GenerateRequest):
    provider = get_provider(request.provider)
    # Safe default deadline when the caller omits timeoutSeconds; an explicit
    # value always wins (a 0 is treated as an explicit immediate timeout).
    timeout = request.timeout_seconds if request.timeout_seconds is not None else config.GENERATION_DEFAULT_TIMEOUT_SECONDS
    job = create_job(
        provider.name,
        lambda on_progress, cancel_event: provider.generate(
            request.spec, request.references, on_progress, cancel_event
        ),
        timeout_seconds=timeout,
        spec_hash=spec_hash(request.spec),
    )
    return {"jobId": job.job_id}


@router.get("/generate/jobs/{job_id}", response_model=JobStatusResponse)
async def get_generation_job(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_response()


@router.post("/generate/jobs/{job_id}/cancel")
async def cancel_generation_job(job_id: str):
    cancelled = cancel_job(job_id)
    if cancelled is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"jobId": job_id, "cancelled": cancelled}


@router.get("/models/{model_id}/meta", response_model=ModelMetaResponse)
async def model_meta(model_id: str):
    record = get_model_record(model_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelMetaResponse(
        modelId=record.id,
        format=record.format,
        mime=record.mime,
        sizeBytes=record.size_bytes,
        providerId=record.provider_id,
        sourceJobId=record.source_job_id,
        specHash=record.spec_hash,
        createdAt=record.created_at,
        stats=GlbStats.model_validate(record.stats) if record.stats else None,
    )


@router.get("/models/{model_id}")
async def download_model(model_id: str):
    record = get_model_record(model_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model not found")
    data = get_model(model_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Model file unavailable or corrupt")
    return Response(
        content=data,
        media_type=record.mime,
        headers={"Content-Disposition": f'attachment; filename="{model_id}.glb"'},
    )


@router.get("/models/{model_id}/vrm")
async def export_model_vrm(model_id: str, body_type: str = "humanoid", name: str = "AIVCS Character"):
    """Export a skinned GLB to a VRM 1.0 GLB (Phase 2.7-B)."""
    data = get_model(model_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Model not found")
    try:
        vrm_bytes = export_vrm(data, body_type=body_type, model_name=name)
    except VrmExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=vrm_bytes,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f'attachment; filename="{model_id}.vrm"'},
    )
