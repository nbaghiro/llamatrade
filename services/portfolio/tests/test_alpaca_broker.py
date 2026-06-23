"""Broker-translation tests — pure, no network.

Covers the Alpaca → ledger translation helpers. The credential resolution +
HTTP calls are the thin IO shell, exercised by the integration suite.
"""

from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import Account

from src.clients.alpaca import AlpacaBrokerPositions, positions_to_holdings, positions_to_qty_map
from src.ports import BrokerUnavailableError


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


def test_qty_map_skips_unparseable_qty() -> None:
    """A malformed broker qty is skipped (logged), not fatal."""
    qty_map = positions_to_qty_map(
        [_pos("AAPL", "10"), _pos("BAD", "not-a-number"), _pos("AAPL", "5")]
    )
    assert qty_map == {"AAPL": Decimal("15")}  # BAD dropped, AAPL aggregated


def test_holdings_skip_malformed_position() -> None:
    """A position with an unparseable qty or avg price is skipped, not fatal."""
    holdings = positions_to_holdings([_pos("AAPL", "10", "150.25"), _pos("BAD", "x", "y")])
    assert [h.symbol for h in holdings] == ["AAPL"]


class _NoCredsDB:
    """Minimal AsyncSession stand-in whose credential lookup finds nothing."""

    async def scalar(self, *args: object, **kwargs: object) -> None:
        return None


async def test_positions_raises_broker_unavailable_without_credentials() -> None:
    """No active credentials → BrokerUnavailableError (not an empty {} that would make
    reconciliation freeze every sleeve)."""
    account = cast(Account, SimpleNamespace(id=uuid4(), credentials_id=uuid4()))
    adapter = AlpacaBrokerPositions(cast(AsyncSession, _NoCredsDB()))
    with pytest.raises(BrokerUnavailableError):
        await adapter.positions(uuid4(), account)
