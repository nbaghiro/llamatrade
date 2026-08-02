"""Redis-backed token revocation and single-use consumption.

Two mechanisms, both consulted by :func:`RevocationStore.is_revoked`:

- a per-token denylist keyed on the JWT ``jti`` claim (SETEX until the token's
  own expiry), and
- a per-user revocation timestamp (``revoke_all_for_user``): any token whose
  ``iat`` predates it is dead, so a password change kills every live session.

Best-effort: a Redis outage fails OPEN (token accepted, with a warning log and
a metric) because an unavailable revocation store must not take the platform
down; token expiry still bounds the exposure.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping

from redis.asyncio import Redis

from llamatrade_telemetry import registry

logger = logging.getLogger(__name__)

_JTI_PREFIX = "llamatrade:auth:revoked:jti"
_USER_PREFIX = "llamatrade:auth:revoked:user"
_DEFAULT_USER_TTL_SECONDS = 7 * 86400  # longest refresh-token lifetime

_backend_errors = registry.counter(
    "llamatrade_auth_revocation_backend_errors_total",
    (),
    "Revocation-store Redis failures (failed open)",
)


class RevocationStore:
    """Denylist for issued JWTs (per-``jti`` and per-user cutoff)."""

    def __init__(self, redis: Redis, *, user_ttl_seconds: int = _DEFAULT_USER_TTL_SECONDS) -> None:
        self._redis = redis
        self._user_ttl_seconds = user_ttl_seconds

    async def revoke_token(self, jti: str, exp: int) -> None:
        """Denylist a single token until its own expiry."""
        ttl = exp - int(time.time())
        if ttl <= 0:
            return
        try:
            await self._redis.setex(f"{_JTI_PREFIX}:{jti}", ttl, "1")
        except Exception as exc:
            logger.warning("Revocation store unavailable, revoke_token skipped: %s", exc)
            _backend_errors.inc()

    async def revoke_all_for_user(self, user_id: str, now: int) -> None:
        """Invalidate every token minted for ``user_id`` before ``now``."""
        try:
            await self._redis.set(f"{_USER_PREFIX}:{user_id}", now, ex=self._user_ttl_seconds)
        except Exception as exc:
            logger.warning("Revocation store unavailable, revoke_all_for_user skipped: %s", exc)
            _backend_errors.inc()

    async def is_revoked(self, claims: Mapping[str, object]) -> bool:
        """Whether the token behind ``claims`` (jti/sub/iat) has been revoked."""
        jti = claims.get("jti")
        sub = claims.get("sub")
        iat = claims.get("iat")
        try:
            if jti and bool(await self._redis.exists(f"{_JTI_PREFIX}:{jti}")):
                return True
            if sub and isinstance(iat, int | float):
                cutoff = await self._redis.get(f"{_USER_PREFIX}:{sub}")
                if cutoff is not None and float(iat) < float(int(cutoff)):
                    return True
            return False
        except Exception as exc:
            logger.warning("Revocation store unavailable, failing open: %s", exc)
            _backend_errors.inc()
            return False


async def consume_once(redis: Redis, key: str, ttl_seconds: int) -> bool:
    """Claim ``key`` exactly once (SET NX with TTL); False when already consumed.

    Fails OPEN on Redis errors — the caller's token TTL still bounds replay.
    """
    try:
        return bool(await redis.set(key, "1", nx=True, ex=ttl_seconds))
    except Exception as exc:
        logger.warning("Single-use store unavailable, failing open: %s", exc)
        _backend_errors.inc()
        return True
