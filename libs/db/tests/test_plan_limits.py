"""Unit tests for plan-limit resolution + enforcement."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from llamatrade_db.plan_limits import (
    FREE_TIER_LIMITS,
    UNLIMITED,
    PlanLimitExceededError,
    enforce_plan_limit,
    get_plan_limit,
)

pytestmark = pytest.mark.asyncio


async def test_get_plan_limit_from_active_plan() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value={"live_strategies": 5})
    assert await get_plan_limit(db, uuid4(), "live_strategies") == 5


async def test_null_limit_means_unlimited() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value={"backtests_per_month": None})
    assert await get_plan_limit(db, uuid4(), "backtests_per_month") == UNLIMITED


async def test_enforce_never_raises_on_unlimited() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value={"backtests_per_month": None})
    await enforce_plan_limit(db, uuid4(), "backtests_per_month", 10_000_000)


async def test_get_plan_limit_free_tier_without_subscription() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    assert (
        await get_plan_limit(db, uuid4(), "live_strategies") == FREE_TIER_LIMITS["live_strategies"]
    )


async def test_get_plan_limit_free_tier_when_key_absent() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value={"other": 3})
    assert (
        await get_plan_limit(db, uuid4(), "backtests_per_month")
        == FREE_TIER_LIMITS["backtests_per_month"]
    )


async def test_enforce_raises_at_limit() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value={"live_strategies": 2})
    with pytest.raises(PlanLimitExceededError):
        await enforce_plan_limit(db, uuid4(), "live_strategies", 2)


async def test_enforce_ok_below_limit() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value={"live_strategies": 2})
    await enforce_plan_limit(db, uuid4(), "live_strategies", 1)
