"""Local 3D -> VRM Rigging Pipeline API (Phase 3-F).

`POST /api/v1/local3d/rig/{model_id}` runs the full pipeline over a GLB that
already lives in ModelStore (any local provider output):

    GLB Analyzer -> Human/Creature classification -> Rig (reuse or auto-rig)
    -> skeleton / skin weights / bind pose / bone mapping -> VRM 1.0 export
    -> validate -> ModelStore (new VRM model record)

Security: input is read ONLY from ModelStore by id (no arbitrary paths); no
shell; no network; the VRM result is persisted back through ModelStore. A
non-human / unclassified GLB is refused with a clear reason - never forced into
a humanoid rig, never falls back to mock.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import jobs
from ..services.local3d_rigger import RigPipelineError, rig_glb_to_vrm
from ..services.vrm_exporter import VrmExportError

router = APIRouter(prefix="/api/v1/local3d")


@router.post("/rig/{model_id}")
async def rig_local3d(model_id: str, body: dict | None = None):
    """Rig a ModelStore GLB into a validated VRM 1.0 and persist it.

    Optional body: {bodyType?, characterType?, modelName?}. bodyType is the
    classification hint from the generating spec (humanoid/biped-anthro/custom
    riggable; quadruped/bird/dragon refused). Without any hint, only a GLB that
    already carries humanoid skeleton structure is accepted.
    """
    data = jobs.get_model(model_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"模型 '{model_id}' 不存在或已过期")
    record = jobs.get_model_record(model_id)

    body = body or {}
    model_name = (body.get("modelName") or "AIVCS Character").strip() or "AIVCS Character"
    try:
        result = rig_glb_to_vrm(
            data,
            body_type=body.get("bodyType"),
            character_type=body.get("characterType"),
            model_name=model_name,
        )
    except RigPipelineError as exc:
        raise HTTPException(status_code=400, detail=f"Rig 失败：{exc}") from exc
    except VrmExportError as exc:
        raise HTTPException(status_code=400, detail=f"VRM 导出失败：{exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Rig 校验失败：{exc}") from exc

    vrm_record = jobs.save_model_bytes(
        result["vrmBytes"],
        provider_id="local3d-rig",
        source_job_id=record.source_job_id if record else "",
        spec_hash=record.spec_hash if record else "",
    )

    result.pop("vrmBytes", None)  # never echo binary payload in the JSON response
    return {
        "ok": True,
        "vrmModelId": vrm_record.id,
        "sourceModelId": model_id,
        "format": vrm_record.format,
        **result,
    }
