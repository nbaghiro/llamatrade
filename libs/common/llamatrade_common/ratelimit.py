"""Redis-backed fixed-window rate limiter.

Best-effort abuse protection: a Redis outage fails OPEN by default (requests
allowed, with a warning log and a metric) because an unavailable limiter must
not take the platform down. A surface where an unavailable limiter is itself a
security hole (brute-force on auth) can opt into fail-closed via ``fail_closed``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from redis.asyncio import Redis

from llamatrade_telemetry import registry

logger = logging.getLogger(__name__)

_KEY_PREFIX = "llamatrade:ratelimit"

_backend_errors = registry.counter(
    "llamatrade_auth_ratelimit_backend_errors_total",
    (),
    "Rate-limit Redis failures",
)


class RateLimiter:
    """Fixed-window counter over Redis: at most ``limit`` hits per ``window``."""

    def __init__(
        self,
        redis: Redis,
        *,
        clock: Callable[[], float] = time.time,
        fail_closed: bool = False,
    ) -> None:
        self._redis = redis
        self._clock = clock
        self._fail_closed = fail_closed

    async def check_and_count(self, key: str, limit: int, window_seconds: int) -> bool:
        """Record one hit for ``key`` and return whether it is still allowed.

        Windows are aligned buckets of ``window_seconds``; the bucket index is
        part of the Redis key so counts reset automatically at each boundary. On a
        backend error the answer is the fail-open/fail-closed default this limiter
        was built with.
        """
        bucket = int(self._clock() // window_seconds)
        redis_key = f"{_KEY_PREFIX}:{key}:{window_seconds}:{bucket}"
        try:
            count = int(await self._redis.incr(redis_key))
            if count == 1:
                await self._redis.expire(redis_key, window_seconds)
            return count <= limit
        except Exception as exc:
            posture = "failing closed" if self._fail_closed else "failing open"
            logger.warning("Rate limiter unavailable, %s: %s", posture, exc)
            _backend_errors.inc()
            return not self._fail_closed
