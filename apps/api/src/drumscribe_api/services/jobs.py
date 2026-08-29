import uuid
from datetime import datetime, timedelta
from hashlib import sha256
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import (
    FRIENDLY_JOB_STAGES,
    JOB_STAGE_PROGRESS,
    TERMINAL_JOB_STAGES,
    JobErrorCode,
    JobStage,
    ProjectStatus,
)
from ..errors import APIError, not_found
from ..models import ProcessingJob, Project
from ..schemas import JobResponse
from ..security import utcnow

STAGE_ORDER = [
    JobStage.RECEIVED,
    JobStage.VALIDATING,
    JobStage.NORMALIZING,
    JobStage.SEPARATING_DRUMS,
    JobStage.TRANSCRIBING,
    JobStage.DETECTING_BEATS,
    JobStage.QUANTIZING,
    JobStage.GENERATING_SCORE,
    JobStage.FINALIZING,
    JobStage.READY,
]

ALLOWED_TRANSITIONS: dict[JobStage, set[JobStage]] = {
    current: {next_stage, JobStage.FAILED, JobStage.CANCELLED}
    for current, next_stage in pairwise(STAGE_ORDER)
}
ALLOWED_TRANSITIONS[JobStage.READY] = set()
ALLOWED_TRANSITIONS[JobStage.FAILED] = set()
ALLOWED_TRANSITIONS[JobStage.CANCELLED] = set()

PUBLIC_ERROR_MESSAGES: dict[JobErrorCode, str] = {
    JobErrorCode.INVALID_AUDIO: "The uploaded file is not valid audio.",
    JobErrorCode.UNSUPPORTED_CODEC: "This audio codec is not supported.",
    JobErrorCode.AUDIO_TOO_LONG: "The recording is longer than the current limit.",
    JobErrorCode.AUDIO_TOO_LARGE: "The recording is larger than the current limit.",
    JobErrorCode.SEPARATION_FAILED: "We could not isolate the drums in this recording.",
    JobErrorCode.TRANSCRIPTION_FAILED: "We could not identify enough drum hits reliably.",
    JobErrorCode.BEAT_TRACKING_FAILED: "We could not build a stable rhythm grid.",
    JobErrorCode.SCORE_GENERATION_FAILED: "We could not create the chart.",
    JobErrorCode.WORKER_TIMEOUT: "Processing took too long. You can retry the job.",
    JobErrorCode.INTERNAL_ERROR: "Something went wrong while processing. You can retry the job.",
}


def job_response(job: ProcessingJob) -> JobResponse:
    return JobResponse(
        id=job.id,
        project_id=job.project_id,
        stage=job.stage,
        friendly_stage=FRIENDLY_JOB_STAGES[job.stage],
        approximate_progress=job.approximate_progress,
        started_at=job.started_at,
        finished_at=job.finished_at,
        cancel_requested_at=job.cancel_requested_at,
        error_code=job.error_code,
        error_message=PUBLIC_ERROR_MESSAGES.get(job.error_code) if job.error_code else None,
        retry_count=job.retry_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


async def transition_job(
    db: AsyncSession,
    job: ProcessingJob,
    next_stage: JobStage,
    *,
    worker: str | None = None,
    error_code: JobErrorCode | None = None,
    error_detail: str | None = None,
) -> None:
    if next_stage not in ALLOWED_TRANSITIONS[job.stage]:
        raise APIError(
            409,
            "INVALID_JOB_TRANSITION",
            f"A job cannot transition from {job.stage.value} to {next_stage.value}.",
        )
    now = utcnow()
    if job.started_at is None and next_stage not in {JobStage.CANCELLED, JobStage.FAILED}:
        job.started_at = now
    if next_stage in {JobStage.FAILED, JobStage.CANCELLED, JobStage.READY}:
        job.finished_at = now
    else:
        job.last_completed_stage = job.stage
    job.stage = next_stage
    job.approximate_progress = JOB_STAGE_PROGRESS[next_stage]
    job.worker = worker or job.worker
    job.error_code = error_code
    job.error_detail = error_detail
    job.updated_at = now
    await db.flush()


async def create_or_get_job(
    db: AsyncSession,
    project: Project,
    idempotency_key: str,
) -> tuple[ProcessingJob, bool]:
    if project.original_asset_id is None:
        raise APIError(409, "UPLOAD_REQUIRED", "Complete an audio upload before processing.")
    input_asset_id = project.original_asset_id
    # Scope idempotency to the immutable input object. Reusing a client key after
    # replacing a recording must create a new job, while retries for the same input
    # still resolve to the original durable row.
    scoped_idempotency_key = sha256(f"{input_asset_id}:{idempotency_key}".encode()).hexdigest()
    existing = (
        await db.execute(
            select(ProcessingJob).where(
                ProcessingJob.project_id == project.id,
                ProcessingJob.idempotency_key == scoped_idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, False
    active = (
        (
            await db.execute(
                select(ProcessingJob)
                .where(
                    ProcessingJob.project_id == project.id,
                    ProcessingJob.stage.not_in(TERMINAL_JOB_STAGES),
                )
                .order_by(ProcessingJob.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if active:
        return active, False
    job = ProcessingJob(
        project_id=project.id,
        idempotency_key=scoped_idempotency_key,
        stage=JobStage.RECEIVED,
        approximate_progress=JOB_STAGE_PROGRESS[JobStage.RECEIVED],
        provider_versions={"inputAssetId": str(input_asset_id)},
    )
    db.add(job)
    project.status = ProjectStatus.PROCESSING
    await db.flush()
    return job, True


async def request_cancel(db: AsyncSession, job: ProcessingJob) -> None:
    if job.stage in TERMINAL_JOB_STAGES:
        return
    job.cancel_requested_at = utcnow()
    if job.stage == JobStage.RECEIVED:
        await transition_job(db, job, JobStage.CANCELLED)
    await db.flush()


async def prepare_retry(db: AsyncSession, job: ProcessingJob) -> None:
    if job.stage not in {JobStage.FAILED, JobStage.CANCELLED}:
        raise APIError(409, "JOB_NOT_RETRYABLE", "Only a failed or cancelled job can be retried.")
    if job.retry_count >= 3:
        raise APIError(409, "RETRY_LIMIT_REACHED", "This job has reached its retry limit.")
    job.retry_count += 1
    if job.last_completed_stage in STAGE_ORDER[:-1]:
        completed_index = STAGE_ORDER.index(job.last_completed_stage)
        job.stage = STAGE_ORDER[completed_index + 1]
    else:
        job.stage = JobStage.RECEIVED
    job.approximate_progress = JOB_STAGE_PROGRESS[job.stage]
    job.started_at = None
    job.finished_at = None
    job.cancel_requested_at = None
    job.error_code = None
    job.error_detail = None
    job.updated_at = utcnow()
    await db.flush()


async def get_owned_job(db: AsyncSession, job_id: uuid.UUID, owner_id: uuid.UUID) -> ProcessingJob:
    job = (
        await db.execute(
            select(ProcessingJob)
            .join(Project, Project.id == ProcessingJob.project_id)
            .where(
                ProcessingJob.id == job_id,
                Project.owner_id == owner_id,
                Project.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise not_found("Processing job")
    return job


def stale_job_cutoff(timeout_minutes: int = 30) -> datetime:
    return utcnow() - timedelta(minutes=timeout_minutes)
