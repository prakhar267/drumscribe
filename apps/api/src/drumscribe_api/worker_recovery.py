"""Requeue durable in-progress jobs before a single-worker deployment starts."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from .config import get_settings
from .database import Database
from .enums import TERMINAL_JOB_STAGES, JobStage
from .models import ProcessingJob, Project
from .queue import CeleryWorkQueue, WorkQueue


async def recover_interrupted_jobs(database: Database, queue: WorkQueue) -> tuple[uuid.UUID, ...]:
    """Requeue jobs whose durable stage proves a worker had started them.

    RECEIVED jobs remain in the broker and are deliberately excluded. The
    pipeline is stage-checkpointed and terminal-aware, so a stale Redis
    delivery that becomes visible later exits without repeating model work.
    """

    async with database.session_factory() as db:
        job_ids = tuple(
            (
                await db.execute(
                    select(ProcessingJob.id)
                    .join(Project, Project.id == ProcessingJob.project_id)
                    .where(
                        ProcessingJob.stage.not_in(TERMINAL_JOB_STAGES),
                        ProcessingJob.stage != JobStage.RECEIVED,
                        Project.deleted_at.is_(None),
                    )
                    .order_by(ProcessingJob.created_at, ProcessingJob.id)
                )
            ).scalars()
        )
    for job_id in job_ids:
        await queue.enqueue_processing(job_id)
    return job_ids


async def _main() -> int:
    settings = get_settings()
    database = Database(settings)
    queue = CeleryWorkQueue(settings)
    try:
        recovered = await recover_interrupted_jobs(database, queue)
    finally:
        await queue.close()
        await database.dispose()
    print(f"requeued_interrupted_jobs={len(recovered)}")
    return 0


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
