import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .config import Settings, get_settings
from .database import Database
from .enums import Environment
from .errors import (
    APIError,
    api_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from .middleware import PlatformMiddleware
from .models import Base
from .queue import create_queue
from .services.exports import ExportService
from .services.pipeline import PipelineService
from .services.rate_limits import create_rate_limiter
from .services.readiness import ReadinessService
from .services.storage import S3PrivateStorage, create_storage


def configure_logging(environment: Environment) -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if environment == Environment.PRODUCTION
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    rate_limiter = create_rate_limiter(app_settings)
    configure_logging(app_settings.environment)
    if app_settings.sentry_dsn:
        sentry_sdk.init(
            dsn=app_settings.sentry_dsn.get_secret_value(),
            environment=app_settings.environment.value,
            traces_sample_rate=app_settings.sentry_traces_sample_rate,
            send_default_pii=False,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(app_settings)
        if app_settings.auto_create_schema:
            async with database.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        storage = create_storage(app_settings)
        if isinstance(storage, S3PrivateStorage) and app_settings.s3_configure_bucket_cors:
            await storage.configure_browser_cors(app_settings.web_origins)
        pipeline = PipelineService(app_settings, database, storage)
        pipeline.music.validate_configuration()
        exports = ExportService(app_settings, database, storage)
        queue = create_queue(app_settings, pipeline.run, exports.run)
        readiness = ReadinessService(app_settings, database, queue, storage, pipeline)
        app.state.settings = app_settings
        app.state.database = database
        app.state.storage = storage
        app.state.pipeline = pipeline
        app.state.export_service = exports
        app.state.queue = queue
        app.state.readiness = readiness
        app.state.rate_limiter = rate_limiter
        try:
            yield
        finally:
            await queue.close()
            await rate_limiter.close()
            await database.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if app_settings.environment == Environment.PRODUCTION else "/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.add_middleware(
        PlatformMiddleware,
        settings=app_settings,
        limiter=rate_limiter,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.web_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=[
            "X-Request-ID",
            "Retry-After",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
        ],
        max_age=600,
    )
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(api_router)
    return app


app = create_app()
