"""Shared row-seeding and fake-client helpers for the integration tier."""

from __future__ import annotations

import datetime as dt
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from llamatrade_db.models.backtest import Backtest, BacktestResult
from llamatrade_db.models.strategy import Strategy, StrategyVersion
from llamatrade_proto.generated.strategy_pb2 import STRATEGY_STATUS_ACTIVE

from src.services.backtest_service import MarketDataFetcher

CONFIG_SEXPR = '(strategy "Test" :benchmark SPY :rebalance daily (asset AAPL :weight 100))'


def bars_for(base: float) -> list[dict[str, object]]:
    """Deterministic market data: 40 trending days."""
    out: list[dict[str, object]] = []
    for i in range(40):
        close = base * (1 + 0.002 * i)
        out.append(
            {
                "timestamp": datetime(2024, 1, 1, 16, tzinfo=UTC) + dt.timedelta(days=i),
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1_000_000,
            }
        )
    return out


def market_client() -> AsyncMock:
    """A spec-bound market-data double serving the deterministic AAPL + SPY dataset."""
    client = AsyncMock(spec=MarketDataFetcher)
    client.fetch_bars.return_value = {"AAPL": bars_for(150.0), "SPY": bars_for(400.0)}
    return client


def backtest_row(
    tenant_id: UUID,
    strategy_id: UUID,
    *,
    status: int,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
) -> Backtest:
    row = Backtest(
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        strategy_version=1,
        name="pg-integration",
        status=status,
        config={
            "commission": 0.0,
            "slippage": 0.0,
            "timeframe": "1D",
            "benchmark_symbol": "SPY",
            "include_benchmark": True,
        },
        symbols=["AAPL"],
        start_date=date(2024, 1, 20),
        end_date=date(2024, 2, 9),
        initial_capital=Decimal("100000"),
        created_by=uuid4(),
    )
    if created_at is not None:
        row.created_at = created_at
    row.started_at = started_at
    return row


async def seed_backtest(
    factory: async_sessionmaker,
    tenant_id: UUID,
    *,
    status: int,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    with_strategy: bool = False,
) -> UUID:
    """Insert a backtest row (optionally with its strategy + version) and return its id."""
    strategy_id = uuid4()
    async with factory() as db:
        if with_strategy:
            db.add(
                Strategy(
                    id=strategy_id,
                    tenant_id=tenant_id,
                    name="pg-strategy",
                    status=STRATEGY_STATUS_ACTIVE,
                    current_version=1,
                    created_by=uuid4(),
                )
            )
            await db.flush()
            db.add(
                StrategyVersion(
                    tenant_id=tenant_id,
                    strategy_id=strategy_id,
                    version=1,
                    config_sexpr=CONFIG_SEXPR,
                    symbols=["AAPL"],
                    rebalance="daily",
                    created_by=uuid4(),
                )
            )
        row = backtest_row(
            tenant_id, strategy_id, status=status, created_at=created_at, started_at=started_at
        )
        db.add(row)
        await db.commit()
        return row.id


async def get_status(factory: async_sessionmaker, backtest_id: UUID) -> tuple[int, str | None]:
    async with factory() as db:
        row = (await db.execute(select(Backtest).where(Backtest.id == backtest_id))).scalar_one()
        return row.status, row.error_message


async def result_count(factory: async_sessionmaker, backtest_id: UUID) -> int:
    async with factory() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(BacktestResult)
            .where(BacktestResult.backtest_id == backtest_id)
        )
        return count or 0
