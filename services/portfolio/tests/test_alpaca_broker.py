"""Broker-translation tests — pure, no network.

Covers the Alpaca → ledger translation helpers. The credential resolution +
HTTP calls are the thin IO shell, exercised by the integration suite.
"""

from decimal import Decimal
from types import SimpleNamespace

from src.clients.alpaca import positions_to_holdings, positions_to_qty_map


def _pos(symbol: str, qty: str, avg: str = "100") -> SimpleNamespace:
    return SimpleNamespace(symbol=symbol, qty=qty, avg_entry_price=avg)


def test_qty_map_signs_and_aggregates() -> None:
    qty_map = positions_to_qty_map([_pos("AAPL", "10"), _pos("TSLA", "-3"), _pos("AAPL", "5")])
    assert qty_map == {"AAPL": Decimal("15"), "TSLA": Decimal("-3")}


def test_qty_map_empty() -> None:
    assert positions_to_qty_map([]) == {}


def test_holdings_translate_fields() -> None:
    holdings = positions_to_holdings([_pos("AAPL", "10", "150.25")])
    assert len(holdings) == 1
    assert holdings[0].symbol == "AAPL"
    assert holdings[0].qty == Decimal("10")
    assert holdings[0].avg_price == Decimal("150.25")


def test_holdings_skip_zero_qty() -> None:
    holdings = positions_to_holdings([_pos("AAPL", "0"), _pos("TSLA", "2")])
    assert [h.symbol for h in holdings] == ["TSLA"]
