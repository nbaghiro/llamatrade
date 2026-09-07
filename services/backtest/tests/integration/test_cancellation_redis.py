"""CancellationFlag against a real Redis: request/observe, latch, TTL, and fail-open."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
import redis as sync_redis

from src.progress import CancellationFlag

pytestmark = pytest.mark.integration


class TestCancellationFlagRedis:
    async def test_request_cancel_is_observed_and_latches(self, redis_url: str) -> None:
        flag = CancellationFlag(redis_url=redis_url)
        backtest_id = str(uuid4())
        should_abort = flag.make_should_abort(backtest_id, check_interval=0.0)

        assert should_abort() is False

        await flag.request_cancel(backtest_id)
        assert should_abort() is True

        # Latched: the checker stays True even after the key expires or is removed.
        client = sync_redis.Redis.from_url(redis_url)
        try:
            client.delete(CancellationFlag._key(backtest_id))
        finally:
            client.close()
        assert should_abort() is True

    async def test_flag_carries_a_ttl(self, redis_url: str) -> None:
        flag = CancellationFlag(redis_url=redis_url)
        backtest_id = str(uuid4())

        await flag.request_cancel(backtest_id)

        client = sync_redis.Redis.from_url(redis_url)
        try:
            ttl = client.ttl(CancellationFlag._key(backtest_id))
        finally:
            client.close()
        assert 0 < ttl <= CancellationFlag.TTL_SECONDS

    async def test_unrelated_backtest_is_not_cancelled(self, redis_url: str) -> None:
        flag = CancellationFlag(redis_url=redis_url)
        await flag.request_cancel(str(uuid4()))

        other_checker = flag.make_should_abort(str(uuid4()), check_interval=0.0)
        assert other_checker() is False

    async def test_checker_is_rate_limited_between_polls(self, redis_url: str) -> None:
        flag = CancellationFlag(redis_url=redis_url)
        backtest_id = str(uuid4())
        should_abort = flag.make_should_abort(backtest_id, check_interval=0.2)

        assert should_abort() is False
        await flag.request_cancel(backtest_id)
        # Inside the poll interval the checker does not hit Redis again.
        assert should_abort() is False

        time.sleep(0.25)
        assert should_abort() is True

    async def test_fail_open_when_redis_unreachable(self) -> None:
        """A broken Redis must neither abort running backtests nor hang them."""
        flag = CancellationFlag(redis_url="redis://127.0.0.1:1/0")
        should_abort = flag.make_should_abort(str(uuid4()), check_interval=0.0)

        assert should_abort() is False
        assert should_abort() is False

    async def test_request_cancel_raises_when_redis_unreachable(self) -> None:
        """The API-side setter surfaces the failure; cancel_backtest catches and logs it."""
        flag = CancellationFlag(redis_url="redis://127.0.0.1:1/0")

        with pytest.raises(sync_redis.exceptions.RedisError):
            await flag.request_cancel(str(uuid4()))
