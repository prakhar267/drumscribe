import uuid

from fastapi import APIRouter, Header, Request, status
from sqlalchemy import func, select

from ...dependencies import CurrentPrincipal, DBSession, owned_project
from ...enums import TERMINAL_JOB_STAGES, AssetStatus, JobStage, ProjectStatus, UserKind
from ...errors import APIError
from ...models import AudioAsset, ProcessingJob, Project
from ...schemas import JobResponse, ProcessingStartRequest
from ...services.audit import record_audit, record_product_event
from ...services.jobs import (
    create_or_get_job,
    get_owned_job,
    job_response,
    prepare_retry,
    request_cancel,
)

router = APIRouter(tags=["processing jobs"])


def _idempotency_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise APIError(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Provide an Idempotency-Key header for this operation.",
        )
    clean = value.strip()
    if len(clean) > 128:
        raise APIError(400, "IDEMPOTENCY_KEY_INVALID", "Idempotency-Key is too long.")
    return clean


@router.post(
    "/projects/{project_id}/process",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_processing(
    project_id: uuid.UUID,
    payload: ProcessingStartRequest,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobResponse:
    del payload
    project = await owned_project(str(project_id), db, principal)
    if project.original_asset_id is None:
        raise APIError(409, "UPLOAD_REQUIRED", "Complete an audio upload before processing.")
    asset = await db.get(AudioAsset, project.original_asset_id)
    if (
        asset is None
        or asset.status not in {AssetStatus.UPLOADED, AssetStatus.VERIFIED}
        or asset.deleted_at is not None
    ):
        raise APIError(409, "UPLOAD_REQUIRED", "Complete a valid audio upload before processing.")
    asset.expires_at = None
    job, created = await create_or_get_job(db, project, _idempotency_key(idempotency_key))
    if created:
        concurrent = int(
            await db.scalar(
                select(func.count(ProcessingJob.id))
                .join(Project, Project.id == ProcessingJob.project_id)
                .where(
                    Project.owner_id == principal.user.id,
                    Project.deleted_at.is_(None),
                    ProcessingJob.stage.not_in(TERMINAL_JOB_STAGES),
                )
            )
            or 0
        )
        limit = (
            request.app.state.settings.max_concurrent_jobs_anonymous
            if principal.user.kind == UserKind.ANONYMOUS
            else request.app.state.settings.max_concurrent_jobs_per_user
        )
        if concurrent > limit:
            await db.rollback()
            raise APIError(
                429,
                "PROCESSING_LIMIT_REACHED",
                "Wait for another transcription to finish before starting this one.",
                headers={"Retry-After": "30"},
            )
        record_audit(
            db,
            "processing.started",
            user_id=principal.user.id,
            project_id=project.id,
            request_id=getattr(request.state, "request_id", None),
            metadata={"jobId": str(job.id)},
        )
        record_product_event(
            db,
            "processing_started",
            user_id=principal.user.id,
            project_id=project.id,
        )
    await db.commit()
    if created:
        await request.app.state.queue.enqueue_processing(job.id)
    return job_response(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: DBSession,
    principal: CurrentPrincipal,
) -> JobResponse:
    return job_response(await get_owned_job(db, job_id, principal.user.id))


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: uuid.UUID,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> JobResponse:
    job = await get_owned_job(db, job_id, principal.user.id)
    await request_cancel(db, job)
    if job.stage == JobStage.CANCELLED:
        project = await db.get(Project, job.project_id)
        if project:
            project.status = ProjectStatus.CANCELLED
    record_audit(
        db,
        "processing.cancel_requested",
        user_id=principal.user.id,
        project_id=job.project_id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"jobId": str(job.id)},
    )
    await db.commit()
    return job_response(job)


@router.post("/jobs/{job_id}/retry", response_model=JobResponse, status_code=202)
async def retry_job(
    job_id: uuid.UUID,
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
) -> JobResponse:
    job = await get_owned_job(db, job_id, principal.user.id)
    await prepare_retry(db, job)
    project = await db.get(Project, job.project_id)
    if project:
        project.status = ProjectStatus.PROCESSING
    record_audit(
        db,
        "processing.retried",
        user_id=principal.user.id,
        project_id=job.project_id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"jobId": str(job.id), "retryCount": job.retry_count},
    )
    await db.commit()
    await request.app.state.queue.enqueue_processing(job.id)
    return job_response(job)
