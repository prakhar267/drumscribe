import time
import uuid

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .config import Settings
from .errors import problem_response
from .security import privacy_hash
from .services.rate_limits import (
    RateLimiter,
    RateLimiterUnavailable,
    RateLimitPolicy,
    RateLimitPolicyResolver,
    create_rate_limiter,
)

logger = structlog.get_logger(__name__)


class PlatformMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: object,
        settings: Settings,
        limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.settings = settings
        self._limiter = limiter or create_rate_limiter(settings)
        self._rate_limit_policies = RateLimitPolicyResolver(settings)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id[:64]
        started = time.monotonic()

        csrf_response = self._check_origin(request)
        if csrf_response is not None:
            return self._secure(csrf_response, request_id)
        if self.settings.enable_rate_limiting:
            rate_limit_response = await self._check_rate_limit(request)
            if rate_limit_response is not None:
                return self._secure(rate_limit_response, request_id)

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

    async def _check_rate_limit(self, request: Request) -> Response | None:
        policy = self._rate_limit_policies.resolve(request.url.path)
        if policy is None:
            return None
        client = request.client.host if request.client else "unknown"
        identity = privacy_hash(client, self.settings.session_secret_bytes)
        try:
            decision = await self._limiter.check(identity, policy)
        except RateLimiterUnavailable:
            return self._handle_limiter_unavailable(request, policy)
        if decision.allowed:
            return None
        return problem_response(
            request,
            status=429,
            code="RATE_LIMITED",
            detail="Too many requests. Wait briefly and try again.",
            title="Too many requests",
            headers={
                "Retry-After": str(decision.retry_after_seconds),
                "X-RateLimit-Limit": str(decision.limit),
                "X-RateLimit-Remaining": str(decision.remaining),
            },
        )

    @staticmethod
    def _handle_limiter_unavailable(request: Request, policy: RateLimitPolicy) -> Response | None:
        logger.error(
            "rate_limiter_unavailable",
            policy=policy.name,
            route=request.url.path,
            fail_closed=policy.name == "auth",
        )
        if policy.name != "auth":
            return None
        return problem_response(
            request,
            status=503,
            code="RATE_LIMIT_UNAVAILABLE",
            detail="Authentication is temporarily unavailable. Try again shortly.",
            title="Service unavailable",
            headers={"Retry-After": "1"},
        )

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
