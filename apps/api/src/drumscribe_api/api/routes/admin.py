import uuid

from fastapi import APIRouter
from sqlalchemy import func, select

from ...dependencies import AdminPrincipal, DBSession
from ...errors import not_found
from ...models import AudioAsset, DrumEvent, ModelRun, ProcessingJob
from ...schemas import AdminJobDiagnostics, AdminModelRun, AssetResponse
from ...services.jobs import job_response

router = APIRouter(prefix="/admin", tags=["internal admin"])


@router.get("/jobs/{job_id}", response_model=AdminJobDiagnostics)
async def job_diagnostics(
    job_id: uuid.UUID,
    db: DBSession,
    principal: AdminPrincipal,
) -> AdminJobDiagnostics:
    del principal
    job = await db.get(ProcessingJob, job_id)
    if job is None:
        raise not_found("Processing job")
    assets = list(
        (
            await db.execute(
                select(AudioAsset).where(
                    AudioAsset.project_id == job.project_id,
                    AudioAsset.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    model_runs = list(
        (await db.execute(select(ModelRun).where(ModelRun.job_id == job.id))).scalars()
    )
    event_count = int(
        await db.scalar(
            select(func.count(DrumEvent.id)).where(
                DrumEvent.project_id == job.project_id,
                DrumEvent.deleted_at.is_(None),
            )
        )
        or 0
    )
    low_confidence_count = int(
        await db.scalar(
            select(func.count(DrumEvent.id)).where(
                DrumEvent.project_id == job.project_id,
                DrumEvent.deleted_at.is_(None),
                DrumEvent.confidence < 0.75,
            )
        )
        or 0
    )
    return AdminJobDiagnostics(
        job=job_response(job),
        provider_versions=job.provider_versions,
        stage_timings=job.stage_timings,
        technical_error_detail=job.error_detail,
        assets=[AssetResponse.model_validate(asset) for asset in assets],
        model_runs=[AdminModelRun.model_validate(run) for run in model_runs],
        event_count=event_count,
        low_confidence_event_count=low_confidence_count,
    )
