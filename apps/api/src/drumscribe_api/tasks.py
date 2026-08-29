import asyncio
import uuid
from typing import Any

from celery import Celery  # type: ignore[import-untyped]

from .config import get_settings
from .database import Database
from .enums import TERMINAL_JOB_STAGES, JobErrorCode, JobStage, ProjectStatus
from .models import ProcessingJob, Project
from .services.exports import ExportService
from .services.jobs import transition_job
from .services.pipeline import TRANSIENT_PIPELINE_ERRORS, PipelineService
from .services.retention import RetentionService
from .services.storage import create_storage

settings = get_settings()
celery_app = Celery(
    "drumscribe",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 28,
    beat_schedule={
        "purge-expired-private-data-hourly": {
            "task": "drumscribe.purge_expired_data",
            "schedule": 60 * 60,
        }
    },
)


async def _run_processing(job_id: uuid.UUID) -> None:
    database = Database(settings)
    try:
        await PipelineService(settings, database, create_storage(settings)).run(job_id)
    finally:
        await database.dispose()


async def _run_export(export_id: uuid.UUID) -> None:
    database = Database(settings)
    try:
        await ExportService(settings, database, create_storage(settings)).run(export_id)
    finally:
        await database.dispose()


async def _run_retention() -> None:
    database = Database(settings)
    try:
        await RetentionService(settings, database, create_storage(settings)).run()
    finally:
        await database.dispose()


async def _mark_processing_retry_exhausted(
    job_id: uuid.UUID, error: Exception
) -> None:
    database = Database(settings)
    try:
        async with database.session_factory() as db:
            job = await db.get(ProcessingJob, job_id)
            if job is None or job.stage in TERMINAL_JOB_STAGES:
                return
            await transition_job(
                db,
                job,
                JobStage.FAILED,
                error_code=JobErrorCode.WORKER_TIMEOUT,
                error_detail=f"{type(error).__name__}: {str(error)[:1000]}",
            )
            project = await db.get(Project, job.project_id)
            if project is not None:
                project.status = ProjectStatus.FAILED
            await db.commit()
    finally:
        await database.dispose()


@celery_app.task(
    bind=True,
    name="drumscribe.process_job",
    max_retries=3,
)  # type: ignore[untyped-decorator]
def process_job_task(self: Any, job_id: str) -> None:
    parsed_job_id = uuid.UUID(job_id)
    try:
        asyncio.run(_run_processing(parsed_job_id))
    except TRANSIENT_PIPELINE_ERRORS as exc:
        retries = int(self.request.retries)
        if retries >= int(self.max_retries):
            asyncio.run(_mark_processing_retry_exhausted(parsed_job_id, exc))
            raise
        countdown = min(60, 2 ** (retries + 1))
        raise self.retry(exc=exc, countdown=countdown) from exc


@celery_app.task(
    bind=True,
    name="drumscribe.generate_export",
)  # type: ignore[untyped-decorator]
def generate_export_task(self: object, export_id: str) -> None:
    del self
    asyncio.run(_run_export(uuid.UUID(export_id)))


@celery_app.task(name="drumscribe.purge_expired_data")  # type: ignore[untyped-decorator]
def purge_expired_data_task() -> None:
    asyncio.run(_run_retention())
