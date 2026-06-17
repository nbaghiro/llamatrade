"""Proto adapters for live minute bars on the internal event bus.

The ingest role publishes closed minute bars to the platform-wide bar channel
(``llamatrade_events.BarEvents``, raw ``market_data_pb2.Bar`` payload); the
serving role's fan-out tails it and routes to subscribed clients. These adapters
map the store's :class:`BarRow` domain type to/from the proto wire and into the
streaming :class:`BarData` the StreamManager broadcasts. Kept pure + symmetric so
they are unit-testable without Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from llamatrade_proto.generated import common_pb2, market_data_pb2

from src.models import BarData
from src.store.models import BarRow


def _decimal(value: Decimal) -> common_pb2.Decimal:
    return common_pb2.Decimal(value=str(value))


def bar_row_to_proto(row: BarRow) -> market_data_pb2.Bar:
    """Serialize a store :class:`BarRow` to a proto ``Bar``.

    The timestamp carries sub-second precision via ``nanos`` so the round-trip is
    lossless; optional ``vwap``/``trade_count`` are only set when present.
    """
    bar = market_data_pb2.Bar(
        symbol=row.symbol,
        timestamp=common_pb2.Timestamp(
            seconds=int(row.time.timestamp()),
            nanos=row.time.microsecond * 1000,
        ),
        open=_decimal(row.open),
        high=_decimal(row.high),
        low=_decimal(row.low),
        close=_decimal(row.close),
        volume=row.volume,
    )
    if row.trade_count is not None:
        bar.trade_count = row.trade_count
    if row.vwap is not None:
        bar.vwap.CopyFrom(_decimal(row.vwap))
    return bar


def proto_to_bar_data(bar: market_data_pb2.Bar) -> BarData:
    """Adapt a proto ``Bar`` to the streaming :class:`BarData` the manager expects.

    The symbol is delivered separately to ``broadcast_bar``; ``BarData`` itself
    only carries the OHLCV + timestamp the client wire needs.
    """
    ts = datetime.fromtimestamp(bar.timestamp.seconds + bar.timestamp.nanos / 1_000_000_000, tz=UTC)
    return BarData(
        open=float(bar.open.value) if bar.HasField("open") else 0.0,
        high=float(bar.high.value) if bar.HasField("high") else 0.0,
        low=float(bar.low.value) if bar.HasField("low") else 0.0,
        close=float(bar.close.value) if bar.HasField("close") else 0.0,
        volume=bar.volume,
        timestamp=ts.isoformat(),
    )
