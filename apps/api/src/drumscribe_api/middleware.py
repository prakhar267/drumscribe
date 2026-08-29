import asyncio
import time
import uuid
from collections import defaultdict, deque

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .config import Settings
from .errors import problem_response
from .security import privacy_hash

logger = structlog.get_logger(__name__)


class PlatformMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id[:64]
        started = time.monotonic()

        csrf_response = self._check_origin(request)
        if csrf_response is not None:
            return self._secure(csrf_response, request_id)
        if self.settings.enable_rate_limiting and await self._rate_limited(request):
            response: Response = problem_response(
                request,
                status=429,
                code="RATE_LIMITED",
                detail="Too many requests. Wait briefly and try again.",
                title="Too many requests",
                headers={"Retry-After": "60"},
            )
            return self._secure(response, request_id)

        response = await call_next(request)
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        logger.info(
            "http_request",
            request_id=request_id,
            method=request.method,
            route=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return self._secure(response, request_id)

    def _check_origin(self, request: Request) -> Response | None:
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return None
        if self.settings.session_cookie_name not in request.cookies:
            return None
        origin = request.headers.get("origin")
        if origin is not None and origin.rstrip("/") not in {
            allowed.rstrip("/") for allowed in self.settings.web_origins
        }:
            return problem_response(
                request,
                status=403,
                code="ORIGIN_NOT_ALLOWED",
                detail="The request origin is not allowed.",
                title="Origin not allowed",
            )
        return None

    async def _rate_limited(self, request: Request) -> bool:
        if request.url.path.endswith("/health"):
            return False
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        identity = privacy_hash(client, self.settings.session_secret_bytes)
        auth_route = "/auth/" in request.url.path
        limit = (
            self.settings.auth_rate_limit_per_minute
            if auth_route
            else self.settings.rate_limit_per_minute
        )
        bucket_key = f"{identity}:{'auth' if auth_route else 'general'}"
        async with self._lock:
            bucket = self._requests[bucket_key]
            cutoff = now - 60
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return True
            bucket.append(now)
            return False

    @staticmethod
    def _secure(response: Response, request_id: str) -> Response:
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers.setdefault("Cache-Control", "no-store")
        return response
