"""StrategyPerformanceReadService tests.

Per-strategy performance derived from the sleeve projection + snapshot series.
DB-touching helpers are overridden on the instance so these run with no DB.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_RUNNING,
)

from src.ledger.projection import PositionState, SleeveProjection
from src.services.strategy_performance_read_service import StrategyPerformanceReadService

TENANT = uuid4()


def _svc() -> StrategyPerformanceReadService:
    return StrategyPerformanceReadService(db=AsyncMock(), market_data=None)


def _execution(sleeve_id, account_id):
    return SimpleNamespace(
        id=uuid4(),
        strategy_id=uuid4(),
        strategy=SimpleNamespace(name="Trend"),
        mode=EXECUTION_MODE_PAPER,
        status=EXECUTION_STATUS_RUNNING,
        color="#fff",
        allocated_capital=Decimal("10000"),
        current_value=Decimal("0"),
        positions_count=0,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        sleeve_id=sleeve_id,
        account_id=account_id,
    )


def _sleeve() -> SleeveProjection:
    s = SleeveProjection()
    s.cash = Decimal("5000")
    s.realized_pnl = Decimal("250")
    s.positions["AAPL"] = PositionState(qty=Decimal("10"), cost_basis=Decimal("4000"))
    return s


def test_positions_marks_to_market() -> None:
    svc = _svc()
    out = svc._positions(_sleeve(), {"AAPL": Decimal("500")})
    assert len(out) == 1
    p = out[0]
    assert p.symbol == "AAPL"
    assert p.avg_entry_price == Decimal("400")
    assert p.market_value == Decimal("5000")  # 10 * 500
    assert p.unrealized_pnl == Decimal("1000")  # 5000 - 4000


def test_period_returns_from_series() -> None:
    svc = _svc()
    now = datetime(2026, 6, 1, tzinfo=UTC)
    # equity 1000 a year ago and 30d ago start, 1200 now
    series = [
        (now - timedelta(days=400), 1000.0),
        (now - timedelta(days=20), 1000.0),
        (now, 1200.0),
    ]
    pr = svc._period_returns(series)
    assert pr.return_1m == Decimal("20.0")  # (1200-1000)/1000
    assert pr.return_all == Decimal("20.0")


def test_period_returns_too_short_is_empty() -> None:
    svc = _svc()
    assert svc._period_returns([(datetime(2026, 1, 1, tzinfo=UTC), 1.0)]).return_1m is None


async def test_get_strategy_performance_assembles_detail() -> None:
    svc = _svc()
    sleeve_id, account_id = uuid4(), uuid4()
    execution = _execution(sleeve_id, account_id)
    sleeve = _sleeve()

    svc._execution = AsyncMock(return_value=execution)
    svc._sleeve_state = AsyncMock(return_value=(sleeve, {"AAPL": Decimal("500")}))
    series = [
        (datetime(2026, 1, 1, tzinfo=UTC), Decimal("10000")),
        (datetime(2026, 1, 2, tzinfo=UTC), Decimal("10250")),
    ]
    svc._sleeve_series = AsyncMock(return_value=series)

    sell = SimpleNamespace(
        event_type=LedgerEventType.ORDER_FILLED,
        data={
            "sleeve_id": str(sleeve_id),
            "side": "sell",
            "realized_pnl": "250",
            "qty": "1",
            "price": "10",
            "symbol": "AAPL",
        },
    )
    svc._projector = SimpleNamespace(
        project_account=AsyncMock(),
        read_events=AsyncMock(return_value=[sell]),
    )

    detail = await svc.get_strategy_performance(TENANT, execution.id)
    assert detail is not None
    assert detail.summary.strategy_name == "Trend"
    assert detail.summary.mode == "paper"
    assert detail.summary.current_value == Decimal("10000")  # 5000 cash + 5000 mkt
    assert detail.summary.positions_count == 1
    assert detail.metrics.total_trades == 1
    assert detail.metrics.winning_trades == 1
    assert detail.metrics.total_pnl == Decimal("250")
    assert len(detail.positions) == 1


async def test_get_strategy_performance_missing_returns_none() -> None:
    svc = _svc()
    svc._execution = AsyncMock(return_value=None)
    assert await svc.get_strategy_performance(TENANT, uuid4()) is None


async def test_get_strategy_equity_curve_builds_points() -> None:
    svc = _svc()
    sleeve_id, account_id = uuid4(), uuid4()
    execution = _execution(sleeve_id, account_id)
    svc._execution = AsyncMock(return_value=execution)
    series = [
        (datetime(2026, 1, 1, tzinfo=UTC), Decimal("10000")),
        (datetime(2026, 1, 2, tzinfo=UTC), Decimal("10500")),
    ]
    svc._sleeve_series = AsyncMock(return_value=series)
    result = await svc.get_strategy_equity_curve(TENANT, execution.id)
    assert result is not None
    assert len(result.equity_curve) == 2
    assert result.equity_curve[-1].equity == Decimal("10500")
