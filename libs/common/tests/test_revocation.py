"""Tests for the Redis-backed revocation store and single-use consumption."""

from __future__ import annotations

import time
from uuid import uuid4

from llamatrade_common.revocation import RevocationStore, consume_once


class FakeRedis:
    """Dict-backed async Redis stand-in (with TTL capture and optional errors)."""

    def __init__(self, *, error: bool = False) -> None:
        self.store: dict[str, object] = {}
        self.ttls: dict[str, int] = {}
        self.error = error

    def _maybe_fail(self) -> None:
        if self.error:
            raise ConnectionError("redis down")

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


def _claims(
    jti: str | None = None, sub: str = "user-1", iat: int | None = None
) -> dict[str, object]:
    claims: dict[str, object] = {"sub": sub}
    if jti is not None:
        claims["jti"] = jti
    claims["iat"] = iat if iat is not None else int(time.time())
    return claims


class TestRevokeToken:
    async def test_revoked_jti_is_revoked(self) -> None:
        redis = FakeRedis()
        store = RevocationStore(redis)
        jti = uuid4().hex

        await store.revoke_token(jti, int(time.time()) + 300)

        assert await store.is_revoked(_claims(jti=jti)) is True
        assert await store.is_revoked(_claims(jti=uuid4().hex)) is False

    async def test_denylist_ttl_matches_remaining_token_life(self) -> None:
        redis = FakeRedis()
        store = RevocationStore(redis)
        jti = uuid4().hex

        await store.revoke_token(jti, int(time.time()) + 300)

        (ttl,) = redis.ttls.values()
        assert 295 <= ttl <= 300

    async def test_already_expired_token_not_stored(self) -> None:
        redis = FakeRedis()
        store = RevocationStore(redis)

        await store.revoke_token(uuid4().hex, int(time.time()) - 10)

        assert redis.store == {}


class TestRevokeAllForUser:
    async def test_tokens_minted_before_cutoff_are_revoked(self) -> None:
        redis = FakeRedis()
        store = RevocationStore(redis)
        now = int(time.time())

        await store.revoke_all_for_user("user-1", now)

        assert await store.is_revoked(_claims(sub="user-1", iat=now - 10)) is True
        assert await store.is_revoked(_claims(sub="user-1", iat=now + 10)) is False
        assert await store.is_revoked(_claims(sub="user-2", iat=now - 10)) is False

    async def test_cutoff_key_carries_ttl(self) -> None:
        redis = FakeRedis()
        store = RevocationStore(redis, user_ttl_seconds=123)

        await store.revoke_all_for_user("user-1", int(time.time()))

        (ttl,) = redis.ttls.values()
        assert ttl == 123


class TestFailOpen:
    async def test_is_revoked_fails_open_on_redis_error(self) -> None:
        store = RevocationStore(FakeRedis(error=True))
        assert await store.is_revoked(_claims(jti=uuid4().hex)) is False

    async def test_revoke_token_swallows_redis_error(self) -> None:
        store = RevocationStore(FakeRedis(error=True))
        await store.revoke_token(uuid4().hex, int(time.time()) + 60)

    async def test_revoke_all_swallows_redis_error(self) -> None:
        store = RevocationStore(FakeRedis(error=True))
        await store.revoke_all_for_user("user-1", int(time.time()))


class TestConsumeOnce:
    async def test_first_claim_wins_second_rejected(self) -> None:
        redis = FakeRedis()
        assert await consume_once(redis, "k1", 60) is True
        assert await consume_once(redis, "k1", 60) is False
        assert await consume_once(redis, "k2", 60) is True

    async def test_ttl_applied(self) -> None:
        redis = FakeRedis()
        await consume_once(redis, "k1", 60)
        assert redis.ttls["k1"] == 60

    async def test_fails_open_on_redis_error(self) -> None:
        assert await consume_once(FakeRedis(error=True), "k1", 60) is True
