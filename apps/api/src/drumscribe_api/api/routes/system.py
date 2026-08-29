from typing import Literal

from fastapi import APIRouter
from sqlalchemy import text

from ... import __version__
from ...dependencies import DBSession
from ...schemas import HealthResponse

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
