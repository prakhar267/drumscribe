from typing import Any

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        detail: str,
        *,
        title: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.title = title or code.replace("_", " ").title()
        self.headers = headers


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    detail: str,
    title: str,
    headers: dict[str, str] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://api.drumscribe.app/problems/{code.lower().replace('_', '-')}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "requestId": getattr(request.state, "request_id", None),
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(
        status_code=status,
        content=body,
        headers={"Content-Type": "application/problem+json", **(headers or {})},
    )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return problem_response(
        request,
        status=exc.status_code,
        code=exc.code,
        detail=exc.detail,
        title=exc.title,
        headers=exc.headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "location": [str(part) for part in error["loc"]],
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status=422,
        code="VALIDATION_ERROR",
        detail="The request did not satisfy the API contract.",
        title="Invalid request",
        errors=errors,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_request_error",
        request_id=getattr(request.state, "request_id", None),
        method=request.method,
        route=request.url.path,
        error_type=type(exc).__name__,
    )
    return problem_response(
        request,
        status=500,
        code="INTERNAL_ERROR",
        detail="An unexpected error occurred.",
        title="Internal server error",
    )


def not_found(resource: str = "Resource") -> APIError:
    return APIError(404, "NOT_FOUND", f"{resource} was not found.")
