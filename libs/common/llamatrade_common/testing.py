"""In-memory test doubles shipped with the lib so consuming suites reuse them.

``FakeRedis`` satisfies the async Redis surface the lib's own consumers use
(:class:`~llamatrade_common.ratelimit.RateLimiter`,
:class:`~llamatrade_common.revocation.RevocationStore`,
:func:`~llamatrade_common.revocation.consume_once`): INCR/EXPIRE counters,
SETEX and SET-NX writes, EXISTS/GET reads. TTLs are captured in ``ttls`` for
assertions rather than enforced. ``error=True`` makes every call raise
``ConnectionError``, which exercises fail-open/fail-closed paths. Mirrors how
``llamatrade_events`` ships :class:`FakeTransport` in ``testing.py``.
"""

from __future__ import annotations


class FakeRedis:
    """Dict-backed async Redis stand-in (no server; TTL capture; optional errors)."""

    def __init__(self, *, error: bool = False) -> None:
        self.store: dict[str, object] = {}
        self.ttls: dict[str, int] = {}
        self.error = error

    def _maybe_fail(self) -> None:
        if self.error:
            raise ConnectionError("redis down")

    async def incr(self, key: str) -> int:
        self._maybe_fail()
        current = self.store.get(key, 0)
        value = (current if isinstance(current, int) else int(str(current))) + 1
        self.store[key] = value
        return value

    async def expire(self, key: str, ttl: int) -> bool:
        self._maybe_fail()
        self.ttls[key] = ttl
        return True

    async def setex(self, key: str, ttl: int, value: object) -> None:
        self._maybe_fail()
        self.store[key] = value
        self.ttls[key] = ttl

    async def set(self, key: str, value: object, nx: bool = False, ex: int | None = None) -> bool:
        self._maybe_fail()
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def exists(self, key: str) -> int:
        self._maybe_fail()
        return int(key in self.store)

    async def get(self, key: str) -> object | None:
        self._maybe_fail()
        return self.store.get(key)
