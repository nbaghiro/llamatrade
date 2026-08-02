"""Shared async Redis client for auth security features.

Revocation, single-use tokens, and rate limits are enabled only when
``REDIS_URL`` is set; without it they are off (unit tests, minimal deploys).
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
