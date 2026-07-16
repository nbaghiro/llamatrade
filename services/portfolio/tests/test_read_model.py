"""Pure read-model tests: projection aggregation → read views."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger.projection import AccountProjection, PositionState
from src.ledger.read_model import (
    aggregate_positions,
    portfolio_summary,
    sleeve_trade_stats,
    transactions_view,
)

ZERO = Decimal("0")


def _proj_with(cash: str, symbol: str, qty: str, cost: str) -> AccountProjection:
    acc = AccountProjection()
    s = acc.sleeve("s1")
    s.cash = Decimal(cash)
    s.positions[symbol] = PositionState(qty=Decimal(qty), cost_basis=Decimal(cost))
    return acc


def test_aggregate_positions_marks_to_market() -> None:
    proj = _proj_with("1000", "AAPL", "10", "1500")  # avg entry 150
    [pos] = aggregate_positions([proj], {"AAPL": Decimal("200")})
    assert pos.symbol == "AAPL"
    assert pos.qty == 10.0
    assert pos.side == "long"
    assert pos.avg_entry_price == 150.0
    assert pos.current_price == 200.0
    assert pos.market_value == 2000.0
    assert pos.unrealized_pnl == 500.0  # (200-150)*10
    assert pos.cost_basis == 1500.0


def test_aggregate_positions_sums_across_sleeves_and_accounts() -> None:
    a = _proj_with("0", "SPY", "10", "1000")
    b = AccountProjection()
    b.sleeve("x").positions["SPY"] = PositionState(qty=Decimal("5"), cost_basis=Decimal("600"))
    [pos] = aggregate_positions([a, b], {"SPY": Decimal("110")})
    assert pos.qty == 15.0
    assert pos.cost_basis == 1600.0


def test_aggregate_positions_missing_price_falls_back_to_avg_entry() -> None:
    proj = _proj_with("0", "X", "4", "400")  # avg 100
    [pos] = aggregate_positions([proj], {})  # no price
    assert pos.current_price == 100.0
    assert pos.unrealized_pnl == 0.0


def test_portfolio_summary_aggregates_and_day_pnl() -> None:
    proj = _proj_with("1000", "AAPL", "10", "1500")
    proj.sleeve("s1").realized_pnl = Decimal("250")
    view = portfolio_summary([proj], {"AAPL": Decimal("200")}, prior_equity=2800.0)
    # equity = cash 1000 + mkt 2000 = 3000
    assert view.total_equity == 3000.0
    assert view.cash == 1000.0
    assert view.market_value == 2000.0
    assert view.total_unrealized_pnl == 500.0
    assert view.total_realized_pnl == 250.0
    assert view.positions_count == 1
    assert view.day_pnl == 200.0  # 3000 - 2800
    assert round(view.day_pnl_percent, 4) == round(200 / 2800 * 100, 4)


def test_portfolio_summary_no_prior_equity_zero_day_pnl() -> None:
    proj = _proj_with("500", "X", "1", "100")
    view = portfolio_summary([proj], {"X": Decimal("100")}, prior_equity=None)
    assert view.day_pnl == 0.0
    assert view.day_pnl_percent == 0.0


def test_transactions_view_from_events() -> None:
    sleeve = str(uuid4())
    events = [
        SimpleNamespace(
            event_id=str(uuid4()),
            event_type=LedgerEventType.FUNDS_DEPOSITED,
            data={"sleeve_id": sleeve, "amount": "10000"},
            occurred_at=None,
        ),
        SimpleNamespace(
            event_id=str(uuid4()),
            event_type=LedgerEventType.ORDER_FILLED,
            data={
                "sleeve_id": sleeve,
                "symbol": "AAPL",
                "side": "buy",
                "qty": "10",
                "price": "150",
            },
            occurred_at=None,
        ),
        # lifecycle event — no postings → skipped
        SimpleNamespace(
            event_id=str(uuid4()),
            event_type=LedgerEventType.ORDER_SUBMITTED,
            data={"sleeve_id": sleeve, "client_order_id": "x", "reserved": "1500"},
            occurred_at=None,
        ),
    ]
    views = transactions_view(events)
    assert len(views) == 2  # deposit + fill, submit skipped
    # newest-first: fill is last appended → first out
    assert views[0].type == "buy"
    assert views[0].symbol == "AAPL"
    assert views[0].amount == 1500.0  # 10 * 150
    assert views[1].type == "deposit"
    assert views[1].amount == 10000.0


def test_transactions_view_allocation_carries_target_sleeve() -> None:
    """CAPITAL_ALLOCATED renders as transfer_in and exposes the target sleeve id."""
    unallocated = str(uuid4())
    strategy_sleeve = str(uuid4())
    events = [
        SimpleNamespace(
            event_id=str(uuid4()),
            event_type=LedgerEventType.CAPITAL_ALLOCATED,
            data={
                "from_sleeve_id": unallocated,
                "to_sleeve_id": strategy_sleeve,
                "amount": "15000",
            },
            occurred_at=None,
        ),
    ]
    views = transactions_view(events)
    assert len(views) == 1
    assert views[0].type == "transfer_in"
    assert views[0].amount == 15000.0
    assert views[0].sleeve_id == strategy_sleeve  # so the caller can name the strategy


def test_sleeve_trade_stats_wins_losses() -> None:
    sleeve = "s1"

    def fill(side, realized=None):
        data = {"sleeve_id": sleeve, "symbol": "X", "side": side, "qty": "1", "price": "10"}
        if realized is not None:
            data["realized_pnl"] = realized
        return SimpleNamespace(event_type=LedgerEventType.ORDER_FILLED, data=data)

    events = [
        fill("buy"),  # not a realized trade
        fill("sell", "100"),  # win
        fill("sell", "-40"),  # loss
        fill("sell", "60"),  # win
        SimpleNamespace(  # other sleeve — ignored
            event_type=LedgerEventType.ORDER_FILLED,
            data={
                "sleeve_id": "other",
                "side": "sell",
                "realized_pnl": "999",
                "qty": "1",
                "price": "1",
                "symbol": "Y",
            },
        ),
    ]
    stats = sleeve_trade_stats(events, sleeve)
    assert stats.total_trades == 3
    assert stats.winning_trades == 2
    assert stats.losing_trades == 1
    assert round(stats.win_rate, 2) == round(2 / 3 * 100, 2)
    assert stats.profit_factor == 160.0 / 40.0
    assert stats.average_win == 80.0  # (100+60)/2
    assert stats.average_loss == -40.0
    assert stats.realized_pnl == 120.0  # 160 - 40
