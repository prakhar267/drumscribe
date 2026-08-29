from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from drumscribe_api.config import Settings
from drumscribe_api.enums import Environment
from drumscribe_api.middleware import PlatformMiddleware
from drumscribe_api.services.rate_limits import (
    InMemoryRateLimiter,
    RateLimiterUnavailable,
    RateLimitPolicy,
    RedisRateLimiter,
    create_rate_limiter,
)


class MutableClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeRedis:
    def __init__(self, result: object = (1, 1, 60), error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, int, tuple[str | int, ...]]] = []
        self.closed = False

    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> object:
        self.calls.append((script, numkeys, keys_and_args))
        if self.error is not None:
            raise self.error
        return self.result

    async def aclose(self) -> None:
        self.closed = True


class UnavailableLimiter:
    async def check(self, key: str, policy: RateLimitPolicy) -> Any:
        raise RateLimiterUnavailable("offline")


@pytest.mark.asyncio
async def test_in_memory_limiter_uses_a_sliding_window_and_isolates_policies() -> None:
    clock = MutableClock()
    limiter = InMemoryRateLimiter(clock=clock)
    auth = RateLimitPolicy(name="auth", limit=2, window_seconds=60)
    general = RateLimitPolicy(name="general", limit=1, window_seconds=60)

    assert (await limiter.check("client", auth)).allowed
    assert (await limiter.check("client", auth)).allowed
    rejected = await limiter.check("client", auth)
    assert not rejected.allowed
    assert rejected.retry_after_seconds == 60
    assert (await limiter.check("client", general)).allowed

    clock.now = 60.0
    reset = await limiter.check("client", auth)
    assert reset.allowed
    assert reset.remaining == 1


@pytest.mark.asyncio
async def test_in_memory_cleanup_preserves_live_and_current_buckets() -> None:
    clock = MutableClock()
    limiter = InMemoryRateLimiter(clock=clock)
    long_window = RateLimitPolicy(name="long", limit=1, window_seconds=120)
    short_window = RateLimitPolicy(name="short", limit=1, window_seconds=60)
    assert (await limiter.check("long-client", long_window)).allowed
    for index in range(998):
        assert (await limiter.check(f"expired-{index}", short_window)).allowed

    clock.now = 61.0
    assert (await limiter.check("current-client", short_window)).allowed
    assert not (await limiter.check("current-client", short_window)).allowed
    assert not (await limiter.check("long-client", long_window)).allowed


@pytest.mark.asyncio
async def test_redis_limiter_maps_atomic_script_result() -> None:
    redis = FakeRedis(result=(0, 3, 17))
    limiter = RedisRateLimiter(redis, namespace="test")

    decision = await limiter.check("private-client-hash", RateLimitPolicy(name="auth", limit=3))

    assert not decision.allowed
    assert decision.remaining == 0
    assert decision.retry_after_seconds == 17
    _, numkeys, arguments = redis.calls[0]
    assert numkeys == 1
    assert arguments[0] == "test:auth:private-client-hash"
    assert arguments[1:3] == (60_000, 3)
    await limiter.close()
    assert redis.closed


@pytest.mark.asyncio
async def test_redis_limiter_normalizes_backend_failures() -> None:
    limiter = RedisRateLimiter(FakeRedis(error=RedisConnectionError("offline")))

    with pytest.raises(RateLimiterUnavailable):
        await limiter.check("client", RateLimitPolicy(name="general", limit=10))


def test_factory_keeps_memory_limiter_out_of_production(settings: Settings) -> None:
    assert isinstance(create_rate_limiter(settings), InMemoryRateLimiter)
    production_like = Settings.model_construct(
        environment=Environment.PRODUCTION,
        redis_url="redis://rate-limits:6379/0",
    )
    assert isinstance(create_rate_limiter(production_like), RedisRateLimiter)


def _middleware_app(
    settings: Settings,
    *,
    limiter: object | None = None,
) -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/auth/login")
    async def auth_route() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/projects")
    async def general_route() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/health")
    async def health_route() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/health/ready")
    async def readiness_route() -> dict[str, bool]:
        return {"ok": True}

    middleware_options: dict[str, Any] = {"settings": settings}
    if limiter is not None:
        middleware_options["limiter"] = limiter
    app.add_middleware(PlatformMiddleware, **middleware_options)
    return app


def test_middleware_applies_auth_and_general_policies_independently(
    settings: Settings,
) -> None:
    configured = settings.model_copy(
        update={
            "enable_rate_limiting": True,
            "auth_rate_limit_per_minute": 1,
            "rate_limit_per_minute": 2,
        }
    )
    with TestClient(_middleware_app(configured)) as client:
        assert client.get("/api/v1/auth/login").status_code == 200
        auth_rejected = client.get("/api/v1/auth/login")
        assert auth_rejected.status_code == 429
        assert auth_rejected.headers["Retry-After"] == "60"
        assert auth_rejected.headers["X-RateLimit-Limit"] == "1"
        assert client.get("/api/v1/projects").status_code == 200
        assert client.get("/api/v1/projects").status_code == 200
        assert client.get("/api/v1/projects").status_code == 429
        for _ in range(3):
            assert client.get("/api/v1/health").status_code == 200
            assert client.get("/api/v1/health/ready").status_code == 200


def test_middleware_fails_closed_for_auth_and_open_for_general_routes(
    settings: Settings,
) -> None:
    configured = settings.model_copy(update={"enable_rate_limiting": True})
    app = _middleware_app(configured, limiter=UnavailableLimiter())

    with TestClient(app) as client:
        auth_response = client.get("/api/v1/auth/login")
        assert auth_response.status_code == 503
        assert auth_response.json()["code"] == "RATE_LIMIT_UNAVAILABLE"
        assert auth_response.headers["Retry-After"] == "1"
        assert client.get("/api/v1/projects").status_code == 200


def test_production_middleware_sets_hsts(settings: Settings) -> None:
    configured = settings.model_copy(
        update={
            "environment": Environment.PRODUCTION,
            "enable_rate_limiting": False,
            "hsts_max_age_seconds": 31_536_000,
        }
    )
    with TestClient(_middleware_app(configured)) as client:
        response = client.get("/api/v1/projects")
    assert response.headers["Strict-Transport-Security"] == ("max-age=31536000; includeSubDomains")
