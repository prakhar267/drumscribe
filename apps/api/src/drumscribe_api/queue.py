import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import structlog
from celery import Celery  # type: ignore[import-untyped]
from redis.asyncio import Redis

from .config import Settings

logger = structlog.get_logger(__name__)


class WorkQueue(Protocol):
    async def enqueue_processing(self, job_id: uuid.UUID) -> None: ...

    async def enqueue_export(self, export_id: uuid.UUID) -> None: ...

    async def healthcheck(self) -> None: ...

    async def close(self) -> None: ...


class NoopQueue:
    async def enqueue_processing(self, job_id: uuid.UUID) -> None:
        del job_id

    async def enqueue_export(self, export_id: uuid.UUID) -> None:
        del export_id

    async def healthcheck(self) -> None:
        return

    async def close(self) -> None:
        return


class InlineDevelopmentQueue:
    def __init__(
        self,
        process_job: Callable[[uuid.UUID], Awaitable[None]],
        process_export: Callable[[uuid.UUID], Awaitable[None]],
    ) -> None:
        self.process_job = process_job
        self.process_export = process_export
        self.tasks: set[asyncio.Task[None]] = set()

    def _spawn(self, coroutine: Awaitable[None]) -> None:
        async def guarded() -> None:
            try:
                await coroutine
            except Exception:
                # The durable job/export row already contains the failure detail.
                logger.exception("inline_background_work_failed")

        task = asyncio.create_task(guarded())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def enqueue_processing(self, job_id: uuid.UUID) -> None:
        self._spawn(self.process_job(job_id))

    async def enqueue_export(self, export_id: uuid.UUID) -> None:
        self._spawn(self.process_export(export_id))

    async def healthcheck(self) -> None:
        return

    async def close(self) -> None:
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)


class CeleryWorkQueue:
    def __init__(self, settings: Settings) -> None:
        self.app = Celery("drumscribe-api-client", broker=settings.redis_url)
        self.redis: Any = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    async def enqueue_processing(self, job_id: uuid.UUID) -> None:
        await asyncio.to_thread(self.app.send_task, "drumscribe.process_job", args=[str(job_id)])

    async def enqueue_export(self, export_id: uuid.UUID) -> None:
        await asyncio.to_thread(
            self.app.send_task, "drumscribe.generate_export", args=[str(export_id)]
        )

    async def healthcheck(self) -> None:
        if not await self.redis.ping():
            raise RuntimeError("queue broker did not acknowledge ping")

    async def close(self) -> None:
        await self.redis.aclose()
        await asyncio.to_thread(self.app.close)


def create_queue(
    settings: Settings,
    process_job: Callable[[uuid.UUID], Awaitable[None]],
    process_export: Callable[[uuid.UUID], Awaitable[None]],
) -> WorkQueue:
    if settings.queue_backend == "celery":
        return CeleryWorkQueue(settings)
    if settings.queue_backend == "inline":
        return InlineDevelopmentQueue(process_job, process_export)
    return NoopQueue()
