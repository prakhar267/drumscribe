import asyncio
import math
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..config import Settings
from ..enums import Environment


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int = 60

    def __post_init__(self) -> None:
        if self.limit <= 0 or self.window_seconds <= 0:
            raise ValueError("rate-limit policy values must be positive")


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RateLimiterUnavailable(RuntimeError):
    """The shared rate-limit store could not make a reliable decision."""


class RateLimiter(Protocol):
    async def check(self, key: str, policy: RateLimitPolicy) -> RateLimitDecision: ...

    async def close(self) -> None: ...


class AsyncRedisClient(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any: ...

    async def aclose(self) -> None: ...


class InMemoryRateLimiter:
    """Single-process limiter for development and tests only."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._window_seconds: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._operations = 0

    async def check(self, key: str, policy: RateLimitPolicy) -> RateLimitDecision:
        now = self._clock()
        bucket_key = f"{policy.name}:{key}"
        cutoff = now - policy.window_seconds
        async with self._lock:
            self._operations += 1
            if self._operations % 1_000 == 0:
                self._discard_expired_buckets(now)
            bucket = self._requests[bucket_key]
            self._window_seconds[bucket_key] = policy.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= policy.limit:
                retry_after = max(1, math.ceil(bucket[0] + policy.window_seconds - now))
                return RateLimitDecision(
                    allowed=False,
                    limit=policy.limit,
                    remaining=0,
                    retry_after_seconds=retry_after,
                )

            bucket.append(now)
            return RateLimitDecision(
                allowed=True,
                limit=policy.limit,
                remaining=policy.limit - len(bucket),
                retry_after_seconds=max(1, math.ceil(policy.window_seconds)),
            )

    async def close(self) -> None:
        async with self._lock:
            self._requests.clear()
            self._window_seconds.clear()

    def _discard_expired_buckets(self, now: float) -> None:
        expired = [
            key
            for key, bucket in self._requests.items()
            if not bucket or bucket[-1] <= now - self._window_seconds.get(key, 0)
        ]
        for key in expired:
            self._requests.pop(key, None)
            self._window_seconds.pop(key, None)


class RedisRateLimiter:
    """Atomic sliding-window limiter shared by every API replica."""

    _CHECK_SCRIPT = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local member = ARGV[3]
local server_time = redis.call('TIME')
local now_ms = (tonumber(server_time[1]) * 1000) + math.floor(tonumber(server_time[2]) / 1000)
local cutoff = now_ms - window_ms

redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
local count = redis.call('ZCARD', key)

if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry_ms = math.max(1, tonumber(oldest[2]) + window_ms - now_ms)
  redis.call('PEXPIRE', key, window_ms)
  return {0, count, math.ceil(retry_ms / 1000)}
end

redis.call('ZADD', key, now_ms, member)
redis.call('PEXPIRE', key, window_ms)
return {1, count + 1, math.ceil(window_ms / 1000)}
"""

    def __init__(self, client: AsyncRedisClient, *, namespace: str = "drumscribe:rl") -> None:
        self._client = client
        self._namespace = namespace

    @classmethod
    def from_url(cls, redis_url: str) -> "RedisRateLimiter":
        client = Redis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            health_check_interval=30,
        )
        return cls(cast(AsyncRedisClient, client))

    async def check(self, key: str, policy: RateLimitPolicy) -> RateLimitDecision:
        redis_key = f"{self._namespace}:{policy.name}:{key}"
        try:
            raw_result = await self._client.eval(
                self._CHECK_SCRIPT,
                1,
                redis_key,
                policy.window_seconds * 1_000,
                policy.limit,
                uuid.uuid4().hex,
            )
            allowed_raw, count_raw, retry_raw = raw_result
            allowed = bool(int(allowed_raw))
            count = int(count_raw)
            retry_after = max(1, int(retry_raw))
        except (RedisError, OSError, TimeoutError, TypeError, ValueError) as exc:
            raise RateLimiterUnavailable("Redis rate-limit decision failed") from exc

        return RateLimitDecision(
            allowed=allowed,
            limit=policy.limit,
            remaining=max(0, policy.limit - count),
            retry_after_seconds=retry_after,
        )

    async def close(self) -> None:
        await self._client.aclose()


class RateLimitPolicyResolver:
    def __init__(self, settings: Settings) -> None:
        self.general = RateLimitPolicy(name="general", limit=settings.rate_limit_per_minute)
        self.auth = RateLimitPolicy(name="auth", limit=settings.auth_rate_limit_per_minute)

    def resolve(self, path: str) -> RateLimitPolicy | None:
        normalized_path = path.rstrip("/") or "/"
        health_prefix = "/api/v1/health"
        if normalized_path == health_prefix or normalized_path.startswith(f"{health_prefix}/"):
            return None
        auth_prefix = "/api/v1/auth"
        if normalized_path == auth_prefix or normalized_path.startswith(f"{auth_prefix}/"):
            return self.auth
        return self.general


def create_rate_limiter(settings: Settings) -> RateLimiter:
    if settings.environment is Environment.PRODUCTION:
        return RedisRateLimiter.from_url(settings.redis_url)
    return InMemoryRateLimiter()
