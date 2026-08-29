from typing import Literal

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from ... import __version__
from ...dependencies import DBSession
from ...schemas import HealthResponse, LivenessResponse, ReadinessResponse
from ...services.readiness import ReadinessService

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(db: DBSession) -> HealthResponse:
    database: Literal["ok", "unavailable"]
    try:
        await db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        database=database,
        version=__version__,
    )


@router.get("/health/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Process liveness only; safe for an orchestrator restart probe."""

    return LivenessResponse(version=__version__)


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(request: Request, response: Response) -> ReadinessResponse:
    """Traffic readiness across every required production dependency."""

    service: ReadinessService = request.app.state.readiness
    result = await service.run(__version__)
    if result.status == "unready":
        response.status_code = 503
    return result
