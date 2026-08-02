"""Shared async Redis client for the agent service.

The per-tenant LLM rate limiter is enabled only when ``REDIS_URL`` is set;
without it the limiter is off (unit tests, minimal deploys).
"""

from __future__ import annotations

import os

from redis.asyncio import Redis

_client: Redis | None = None


def get_redis() -> Redis | None:
    """Lazily created process-wide client, or None when ``REDIS_URL`` is unset."""
    global _client
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    if _client is None:
        _client = Redis.from_url(url)
    return _client
