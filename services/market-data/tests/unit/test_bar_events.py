"""Unit tests for the live-bar proto adapters (pure, no Redis)."""

from datetime import UTC, datetime
from decimal import Decimal

from src.store.models import BarRow
from src.streaming.bar_events import bar_row_to_proto, proto_to_bar_data


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


def test_bar_row_to_proto_maps_all_fields() -> None:
    bar = bar_row_to_proto(_row())
    assert bar.symbol == "AAPL"
    assert bar.timestamp.seconds == int(datetime(2026, 1, 5, 14, 30, tzinfo=UTC).timestamp())
    assert bar.open.value == "100.25"
    assert bar.high.value == "101.50"
    assert bar.low.value == "99.10"
    assert bar.close.value == "100.80"
    assert bar.volume == 12345
    assert bar.vwap.value == "100.5"
    assert bar.trade_count == 42


def test_optional_fields_unset_when_absent() -> None:
    bar = bar_row_to_proto(_row(vwap=None, trade_count=None))
    assert not bar.HasField("vwap")
    assert bar.trade_count == 0  # proto default for an unset int64


def test_proto_to_bar_data_maps_ohlcv_and_timestamp() -> None:
    bar = bar_row_to_proto(_row())
    data = proto_to_bar_data(bar)
    assert data["open"] == 100.25
    assert data["high"] == 101.50
    assert data["low"] == 99.10
    assert data["close"] == 100.80
    assert data["volume"] == 12345
    assert data["timestamp"] == datetime(2026, 1, 5, 14, 30, tzinfo=UTC).isoformat()


def test_proto_roundtrip_preserves_close() -> None:
    row = _row(close=Decimal("100.80000000"))
    bar = bar_row_to_proto(row)
    assert bar.close.value == "100.80000000"
    # BarData carries floats for the client wire; value is preserved numerically.
    assert proto_to_bar_data(bar)["close"] == 100.8


def test_serialized_proto_roundtrips_through_wire() -> None:
    """Mirrors the bus path: serialize, then parse back to a Bar."""
    from llamatrade_proto.generated import market_data_pb2

    bar = bar_row_to_proto(_row())
    restored = market_data_pb2.Bar.FromString(bar.SerializeToString())
    assert restored.symbol == "AAPL"
    assert restored.close.value == "100.80"
    assert proto_to_bar_data(restored)["volume"] == 12345
