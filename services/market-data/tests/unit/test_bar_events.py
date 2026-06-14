"""Unit tests for the live-bar EventBus codec (pure, no Redis)."""

from datetime import UTC, datetime
from decimal import Decimal

from src.store.models import BarRow
from src.streaming.bar_events import decode_bar_event, encode_bar_event


def _row(**over: object) -> BarRow:
    base = {
        "symbol": "AAPL",
        "time": datetime(2026, 1, 5, 14, 30, tzinfo=UTC),
        "open": Decimal("100.25"),
        "high": Decimal("101.50"),
        "low": Decimal("99.10"),
        "close": Decimal("100.80"),
        "volume": 12345,
        "vwap": Decimal("100.5"),
        "trade_count": 42,
    }
    base.update(over)
    return BarRow(**base)


def test_roundtrip_full() -> None:
    row = _row()
    assert decode_bar_event(encode_bar_event(row)) == row


def test_roundtrip_without_optional_fields() -> None:
    row = _row(vwap=None, trade_count=None)
    fields = encode_bar_event(row)
    assert "vw" not in fields and "n" not in fields
    assert decode_bar_event(fields) == row


def test_fields_are_all_strings() -> None:
    fields = encode_bar_event(_row())
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in fields.items())


def test_decimal_precision_preserved() -> None:
    row = _row(close=Decimal("100.80000000"))
    restored = decode_bar_event(encode_bar_event(row))
    assert restored.close == Decimal("100.80000000")
