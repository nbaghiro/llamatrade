"""Tests for the in-memory portfolio book."""

from datetime import UTC, datetime

import pytest

from llamatrade_runtime import Portfolio

D = datetime(2024, 1, 1, tzinfo=UTC)


def test_open_debits_cash_and_records_position() -> None:
    p = Portfolio(10000)
    out = p.open(D, "SPY", 100.0, 10, 1.0)
    assert out.fill is not None
    assert out.rejected is None
    assert p.cash == pytest.approx(10000 - 1000 - 1)
    assert p.positions["SPY"].quantity == 10


def test_open_scales_buy_down_to_affordable() -> None:
    # Want 10 @ $100 = $1000 but only $500 cash → fill the 5 shares cash affords, not reject.
    p = Portfolio(500)
    out = p.open(D, "SPY", 100.0, 10, 0.0)
    assert out.rejected is None
    assert out.fill is not None and out.fill.quantity == pytest.approx(5.0)
    assert p.positions["SPY"].quantity == pytest.approx(5.0)
    assert p.cash == pytest.approx(0.0)


def test_open_full_allocation_absorbs_fee() -> None:
    # 100% target costs all cash; the flat fee must trim the buy, not reject the whole position.
    p = Portfolio(10000)
    out = p.open(D, "SPY", 100.0, 100, 1.0)  # cost 10000 == cash, +$1 fee
    assert out.rejected is None
    assert out.fill is not None and out.fill.quantity == pytest.approx(99.99)
    assert p.cash == pytest.approx(0.0)


def test_open_rejects_when_cash_cannot_cover_fee() -> None:
    p = Portfolio(0.5)
    out = p.open(D, "SPY", 100.0, 10, 1.0)  # $0.50 cash can't even cover the $1 fee
    assert out.rejected is not None
    assert "Insufficient cash" in out.rejected.reason
    assert "SPY" not in p.positions
    assert p.cash == 0.5


def test_add_to_position_averages_entry_price() -> None:
    p = Portfolio(100000)
    p.open(D, "SPY", 100.0, 10, 0.0)
    p.open(D, "SPY", 200.0, 10, 0.0)
    assert p.positions["SPY"].quantity == 20
    assert p.positions["SPY"].entry_price == pytest.approx(150.0)


def test_close_full_records_trade_and_pnl() -> None:
    p = Portfolio(100000)
    p.open(D, "SPY", 100.0, 10, 0.0)
    out = p.close(D, "SPY", 120.0, None, 0.0)
    assert out.trade is not None
    assert out.trade.pnl == pytest.approx((120 - 100) * 10)
    assert "SPY" not in p.positions


def test_close_partial_allocates_entry_commission_proportionally() -> None:
    p = Portfolio(100000)
    p.open(D, "SPY", 100.0, 10, 4.0)  # entry commission 4
    out = p.close(D, "SPY", 110.0, 5, 2.0)  # sell half, exit commission 2
    assert out.trade is not None
    # entry alloc = 4 * 5/10 = 2 → total commission 2 + 2 = 4
    assert out.trade.commission == pytest.approx(4.0)
    assert p.positions["SPY"].quantity == 5
    assert p.positions["SPY"].entry_commission_remaining == pytest.approx(2.0)


def test_close_with_no_position_rejects() -> None:
    p = Portfolio(100000)
    out = p.close(D, "SPY", 100.0, None, 0.0)
    assert out.rejected is not None
    assert "no open position" in out.rejected.reason


def test_equity_marks_positions_to_market() -> None:
    p = Portfolio(10000)
    p.open(D, "SPY", 100.0, 10, 0.0)  # cash 9000, 10 shares
    p.update_prices({"SPY": 150.0})
    assert p.equity() == pytest.approx(9000 + 10 * 150)


def test_holdings_excludes_flat_symbols() -> None:
    p = Portfolio(10000)
    p.open(D, "SPY", 100.0, 10, 0.0)
    holdings = p.holdings()
    assert "SPY" in holdings
    assert holdings["SPY"].quantity == 10
