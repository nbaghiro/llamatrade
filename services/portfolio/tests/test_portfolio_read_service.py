"""PortfolioReadService tests.

Orchestration + response-mapping over the pure read-model. DB-touching helpers
are overridden on the instance so these run with no DB; the read-model itself is
covered in ``test_read_model``.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_proto.generated.portfolio_pb2 import (
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_TRANSFER_IN,
)

from src.ledger.projection import AccountProjection, PositionState
from src.services.portfolio_read_service import PortfolioReadService

TENANT = uuid4()


class FakeMarketData:
    def __init__(self, prices: dict[str, Decimal] | None = None) -> None:
        self._prices = prices or {}

    async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        return {s: self._prices.get(s, Decimal("0")) for s in symbols}

    async def get_daily_closes(self, symbol, start, end) -> dict[date, float]:
        return {}


def _proj(cash: str, symbol: str, qty: str, cost: str) -> AccountProjection:
    acc = AccountProjection()
    s = acc.sleeve("s1")
    s.cash = Decimal(cash)
    s.positions[symbol] = PositionState(qty=Decimal(qty), cost_basis=Decimal(cost))
    return acc


def _svc(prices: dict[str, Decimal] | None = None) -> PortfolioReadService:
    return PortfolioReadService(db=AsyncMock(), market_data=FakeMarketData(prices))


async def test_get_summary_maps_view_to_schema() -> None:
    svc = _svc({"AAPL": Decimal("200")})
    svc._projections = AsyncMock(return_value=[_proj("1000", "AAPL", "10", "1500")])
    svc._prior_equity = AsyncMock(return_value=2800.0)
    summary = await svc.get_summary(TENANT)
    assert summary.total_equity == 3000.0
    assert summary.cash == 1000.0
    assert summary.positions_count == 1
    assert summary.day_pnl == 200.0
    assert summary.updated_at.tzinfo is not None


async def test_list_positions_maps_to_schema() -> None:
    svc = _svc({"AAPL": Decimal("200")})
    svc._projections = AsyncMock(return_value=[_proj("0", "AAPL", "10", "1500")])
    positions = await svc.list_positions(TENANT)
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].unrealized_pnl == 500.0


async def test_get_position_filters_by_symbol() -> None:
    svc = _svc({"AAPL": Decimal("200")})
    svc._projections = AsyncMock(return_value=[_proj("0", "AAPL", "10", "1500")])
    assert (await svc.get_position(TENANT, "aapl")).symbol == "AAPL"
    assert await svc.get_position(TENANT, "MSFT") is None


async def test_get_metrics_insufficient_history_returns_zeros() -> None:
    svc = _svc()
    svc._daily_equity_series = AsyncMock(return_value=[(date(2026, 1, 1), 1000.0)])
    m = await svc.get_metrics(TENANT, "1M")
    assert m.period == "1M"
    assert m.total_return == 0.0
    assert m.sharpe_ratio == 0.0


async def test_get_metrics_computes_over_series() -> None:
    svc = _svc()
    series = [(date(2026, 1, i + 1), 1000.0 + 10 * i) for i in range(10)]
    svc._daily_equity_series = AsyncMock(return_value=series)
    m = await svc.get_metrics(TENANT, "1M")
    assert m.total_return == 90.0  # 1090 - 1000
    assert m.total_return_percent == pytest.approx(9.0)
    assert m.max_drawdown == 0.0  # monotonic up


async def test_list_transactions_paginates_newest_first() -> None:
    svc = _svc()
    sleeve = str(uuid4())
    acct = SimpleNamespace(id=uuid4(), tenant_id=TENANT)
    svc._accounts = AsyncMock(return_value=[acct])

    def ev(etype, data, ts):
        return SimpleNamespace(event_id=str(uuid4()), event_type=etype, data=data, occurred_at=ts)

    events = [
        ev(
            LedgerEventType.FUNDS_DEPOSITED,
            {"sleeve_id": sleeve, "amount": "1000"},
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
        ev(
            LedgerEventType.ORDER_FILLED,
            {"sleeve_id": sleeve, "symbol": "AAPL", "side": "buy", "qty": "2", "price": "100"},
            datetime(2026, 1, 2, tzinfo=UTC),
        ),
    ]
    svc._projector = SimpleNamespace(read_events=AsyncMock(return_value=events))

    txns, total = await svc.list_transactions(TENANT, type=None, symbol=None, page=1, page_size=1)
    assert total == 2
    assert len(txns) == 1
    assert txns[0].symbol == "AAPL"  # newest (Jan 2) first
    assert txns[0].type == TRANSACTION_TYPE_BUY


async def test_list_transactions_symbol_filter() -> None:
    svc = _svc()
    sleeve = str(uuid4())
    acct = SimpleNamespace(id=uuid4(), tenant_id=TENANT)
    svc._accounts = AsyncMock(return_value=[acct])
    events = [
        SimpleNamespace(
            event_id=str(uuid4()),
            event_type=LedgerEventType.ORDER_FILLED,
            data={"sleeve_id": sleeve, "symbol": "AAPL", "side": "buy", "qty": "1", "price": "10"},
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        SimpleNamespace(
            event_id=str(uuid4()),
            event_type=LedgerEventType.ORDER_FILLED,
            data={"sleeve_id": sleeve, "symbol": "MSFT", "side": "buy", "qty": "1", "price": "20"},
            occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
    ]
    svc._projector = SimpleNamespace(read_events=AsyncMock(return_value=events))
    txns, total = await svc.list_transactions(
        TENANT, type=None, symbol="aapl", page=1, page_size=10
    )
    assert total == 1
    assert txns[0].symbol == "AAPL"


async def test_list_transactions_labels_allocation_with_strategy() -> None:
    """An allocation row surfaces as transfer_in and is described by its strategy."""
    svc = _svc()
    unallocated, strategy_sleeve = str(uuid4()), str(uuid4())
    acct = SimpleNamespace(id=uuid4(), tenant_id=TENANT)
    svc._accounts = AsyncMock(return_value=[acct])
    events = [
        SimpleNamespace(
            event_id=str(uuid4()),
            event_type=LedgerEventType.CAPITAL_ALLOCATED,
            data={
                "from_sleeve_id": unallocated,
                "to_sleeve_id": strategy_sleeve,
                "amount": "15000",
            },
            occurred_at=datetime(2026, 1, 4, tzinfo=UTC),
        ),
    ]
    svc._projector = SimpleNamespace(read_events=AsyncMock(return_value=events))
    svc._sleeve_names = AsyncMock(return_value={strategy_sleeve: "Momentum Rotation"})

    txns, total = await svc.list_transactions(TENANT, type=None, symbol=None, page=1, page_size=10)

    assert total == 1
    assert txns[0].type == TRANSACTION_TYPE_TRANSFER_IN
    assert txns[0].amount == 15000.0
    assert txns[0].description == "Momentum Rotation"
    svc._sleeve_names.assert_awaited_once_with({strategy_sleeve})
