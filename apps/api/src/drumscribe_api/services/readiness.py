import asyncio
import time
from collections.abc import Awaitable, Callable

import structlog

from ..config import Settings
from ..database import Database
from ..queue import WorkQueue
from ..schemas import DependencyHealthResponse, ReadinessResponse
from .pipeline import PipelineService
from .storage import PrivateStorage

logger = structlog.get_logger(__name__)


class ReadinessService:
    """Bounded, non-mutating dependency checks for traffic admission."""

    def __init__(
        self,
        settings: Settings,
        database: Database,
        queue: WorkQueue,
        storage: PrivateStorage,
        pipeline: PipelineService,
    ) -> None:
        self.settings = settings
        self.database = database
        self.queue = queue
        self.storage = storage
        self.pipeline = pipeline

    async def _provider_healthcheck(self) -> None:
        await asyncio.to_thread(self.pipeline.music.validate_configuration)

    async def _check(
        self,
        name: str,
        operation: Callable[[], Awaitable[None]],
    ) -> DependencyHealthResponse:
        started = time.monotonic()
        try:
            await asyncio.wait_for(operation(), timeout=self.settings.readiness_timeout_seconds)
        except Exception as exc:
            latency_ms = round((time.monotonic() - started) * 1000, 2)
            logger.warning(
                "readiness_dependency_unavailable",
                dependency=name,
                error_type=type(exc).__name__,
                latency_ms=latency_ms,
            )
            return DependencyHealthResponse(status="unavailable", latency_ms=latency_ms)
        return DependencyHealthResponse(
            status="ok", latency_ms=round((time.monotonic() - started) * 1000, 2)
        )

    async def run(self, version: str) -> ReadinessResponse:
        operations: dict[str, Callable[[], Awaitable[None]]] = {
            "database": self.database.healthcheck,
            "queue": self.queue.healthcheck,
            "storage": self.storage.healthcheck,
            "provider": self._provider_healthcheck,
        }
        results = await asyncio.gather(
            *(self._check(name, operation) for name, operation in operations.items())
        )
        checks = dict(zip(operations, results, strict=True))
        ready = all(result.status == "ok" for result in results)
        return ReadinessResponse(
            status="ready" if ready else "unready",
            checks=checks,
            version=version,
        )
