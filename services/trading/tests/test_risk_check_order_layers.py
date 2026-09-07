"""Risk layers 3-5 (position size, daily loss, order rate) through ``check_order``.

The DB-backed layers were previously exercised only via private helpers; these
tests drive the public gate the executor and runner call, plus multi-violation
accumulation in one result and ``reference_price`` seeding of the price cache.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import RiskLimits
from src.risk.risk_manager import RiskManager

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=value)
    result.scalar = MagicMock(return_value=value)
    return result


def _position(qty: str, price: str) -> MagicMock:
    position = MagicMock()
    position.qty = Decimal(qty)
    position.current_price = Decimal(price)
    return position


def _daily_pnl(total: str) -> MagicMock:
    daily = MagicMock()
    daily.total_pnl = Decimal(total)
    daily.date = datetime.now(UTC)
    return daily


@pytest.fixture(autouse=True)
def _clear_config_cache():
    RiskManager._config_cache.clear()
    yield
    RiskManager._config_cache.clear()


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def manager(db: AsyncMock) -> RiskManager:
    risk = RiskManager(db=db)
    risk._default_limits = RiskLimits(
        max_position_size=Decimal("10000"),
        max_daily_loss=Decimal("1000"),
        max_order_value=Decimal("5000"),
        allow_outside_market_hours=True,
    )
    return risk


def _stack_db_results(
    db: AsyncMock,
    *,
    position: MagicMock | None,
    daily: MagicMock | None,
    order_count: int,
    config_lookups: int = 2,
) -> None:
    """Queue results in ``check_order``'s query order: the config lookups
    (session then tenant, both empty; an empty config is re-queried every call
    since the cache cannot distinguish a stored None from a miss), then the
    position row, the daily P&L row, and the rate-limit count."""
    results = [_scalar_result(None) for _ in range(config_lookups)]
    results += [_scalar_result(position), _scalar_result(daily), _scalar_result(order_count)]
    db.execute = AsyncMock(side_effect=results)


class TestCheckOrderDbLayers:
    async def test_layer3_position_size_violation_through_public_gate(self, manager, db):
        _stack_db_results(db, position=_position("90", "100"), daily=_daily_pnl("0"), order_count=0)

        result = await manager.check_order(
            tenant_id=TENANT_ID,
            symbol="AAPL",
            side="buy",
            qty=Decimal("20"),
            order_type="limit",
            limit_price=Decimal("100"),
            session_id=SESSION_ID,
        )

        assert result.passed is False
        assert result.violations == ["Position would exceed max size $10000.00"]

    async def test_layer4_daily_loss_violation_through_public_gate(self, manager, db):
        _stack_db_results(
            db, position=_position("1", "100"), daily=_daily_pnl("-1500"), order_count=0
        )

        result = await manager.check_order(
            tenant_id=TENANT_ID,
            symbol="AAPL",
            side="buy",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("100"),
            session_id=SESSION_ID,
        )

        assert result.passed is False
        assert result.violations == ["Daily loss limit $1000.00 exceeded"]

    async def test_layer5_rate_limit_violation_through_public_gate(self, manager, db):
        _stack_db_results(db, position=_position("1", "100"), daily=_daily_pnl("0"), order_count=10)

        result = await manager.check_order(
            tenant_id=TENANT_ID,
            symbol="AAPL",
            side="buy",
            qty=Decimal("1"),
            order_type="limit",
            limit_price=Decimal("100"),
            session_id=SESSION_ID,
        )

        assert result.passed is False
        assert result.violations == ["Order rate limit exceeded (max 10 orders/minute)"]

    async def test_all_db_layers_pass_produces_clean_result(self, manager, db):
        _stack_db_results(
            db, position=_position("10", "100"), daily=_daily_pnl("-100"), order_count=3
        )

        result = await manager.check_order(
            tenant_id=TENANT_ID,
            symbol="AAPL",
            side="buy",
            qty=Decimal("5"),
            order_type="limit",
            limit_price=Decimal("100"),
            session_id=SESSION_ID,
        )

        assert result.passed is True
        assert result.violations == []

    async def test_multiple_violations_accumulate_in_one_result(self, manager, db):
        """Order value, position size, daily loss, and rate limit all report at
        once instead of stopping at the first failure."""
        _stack_db_results(
            db, position=_position("90", "100"), daily=_daily_pnl("-1500"), order_count=10
        )

        result = await manager.check_order(
            tenant_id=TENANT_ID,
            symbol="AAPL",
            side="buy",
            qty=Decimal("60"),
            order_type="limit",
            limit_price=Decimal("100"),
            session_id=SESSION_ID,
        )

        assert result.passed is False
        assert len(result.violations) == 4
        assert result.violations[0] == "Order value $6000.00 exceeds limit $5000.00"
        assert "Position would exceed max size" in result.violations[1]
        assert "Daily loss limit" in result.violations[2]
        assert "rate limit" in result.violations[3]


class TestReferencePriceSeeding:
    async def test_reference_price_values_a_market_order(self, manager, db):
        """A market order with no limit price is valued at the caller's
        reference price, surfaced verbatim in the violation."""
        _stack_db_results(db, position=None, daily=None, order_count=0)

        result = await manager.check_order(
            tenant_id=TENANT_ID,
            symbol="AAPL",
            side="buy",
            qty=Decimal("40"),
            order_type="market",
            session_id=SESSION_ID,
            reference_price=Decimal("150"),
        )

        assert result.passed is False
        assert result.violations == ["Order value $6000.00 exceeds limit $5000.00"]

    async def test_reference_price_seeds_the_cache_for_later_checks(self, manager, db):
        """A later market-order check with no reference price and no market-data
        client still resolves the seeded price instead of failing closed."""
        _stack_db_results(db, position=None, daily=None, order_count=0)
        first = await manager.check_order(
            tenant_id=TENANT_ID,
            symbol="AAPL",
            side="buy",
            qty=Decimal("10"),
            order_type="market",
            session_id=SESSION_ID,
            reference_price=Decimal("150"),
        )
        assert first.passed is True

        _stack_db_results(db, position=None, daily=None, order_count=0)
        second = await manager.check_order(
            tenant_id=TENANT_ID,
            symbol="aapl",
            side="buy",
            qty=Decimal("40"),
            order_type="market",
            session_id=SESSION_ID,
        )

        assert second.passed is False
        assert second.violations == ["Order value $6000.00 exceeds limit $5000.00"]

    async def test_reference_price_feeds_the_position_size_layer(self, manager, db):
        """A position row with no stored price is valued at the reference price."""
        position = _position("90", "0")
        position.current_price = None
        _stack_db_results(db, position=position, daily=None, order_count=0)

        result = await manager.check_order(
            tenant_id=TENANT_ID,
            symbol="AAPL",
            side="buy",
            qty=Decimal("20"),
            order_type="limit",
            limit_price=Decimal("100"),
            session_id=SESSION_ID,
            reference_price=Decimal("100"),
        )

        assert result.passed is False
        assert result.violations == ["Position would exceed max size $10000.00"]
