"""Golden round-trip tests for the DB-row -> proto trading mappers (10A).

Validates position_to_proto in isolation: DB Position row in, proto Position out,
with Decimal precision preserved (5A), every field the old PositionResponse
dropped now populated, and no proto Decimal field left unset outside an explicit
allowlist.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from google.protobuf.message import Message

from llamatrade_db.models.trading import Position
from llamatrade_proto.generated.trading_pb2 import POSITION_SIDE_LONG

from src.proto_mappers import position_to_proto

# available_quantity has no DB column; the engine does not compute it.
_POSITION_UNSET_ALLOWLIST = {"available_quantity"}

_ID = UUID("77777777-7777-7777-7777-777777777777")
_TENANT = UUID("11111111-1111-1111-1111-111111111111")
_SESSION = UUID("22222222-2222-2222-2222-222222222222")


def _decimal_field_names(message: Message) -> list[str]:
    return [
        f.name
        for f in message.DESCRIPTOR.fields
        if f.message_type is not None and f.message_type.name == "Decimal"
    ]


def _make_position() -> Position:
    return Position(
        id=_ID,
        tenant_id=_TENANT,
        session_id=_SESSION,
        symbol="AAPL",
        side=POSITION_SIDE_LONG,
        qty=Decimal("100.00000000"),
        avg_entry_price=Decimal("150.00000000"),
        current_price=Decimal("155.00000000"),
        market_value=Decimal("15500.00"),
        cost_basis=Decimal("15000.00"),
        unrealized_pl=Decimal("500.00"),
        unrealized_plpc=Decimal("0.033333"),
        realized_pl=Decimal("0.00"),
        is_open=True,
        opened_at=datetime(2024, 1, 2, tzinfo=UTC),
        updated_at=datetime(2024, 1, 3, tzinfo=UTC),
    )


def test_position_precision_and_dropped_fields_populated() -> None:
    proto = position_to_proto(_make_position())

    # Fields the old PositionResponse dropped are now populated directly from the row.
    assert proto.id == str(_ID)
    assert proto.tenant_id == str(_TENANT)
    assert proto.session_id == str(_SESSION)
    assert Decimal(proto.average_entry_price.value) == Decimal("150")  # not reconstructed
    assert Decimal(proto.realized_pnl.value) == Decimal("0")
    assert proto.opened_at.seconds == int(datetime(2024, 1, 2, tzinfo=UTC).timestamp())
    assert proto.updated_at.seconds == int(datetime(2024, 1, 3, tzinfo=UTC).timestamp())

    # 5A: DB Decimal preserved; side carried as the proto int enum.
    assert proto.side == POSITION_SIDE_LONG
    assert Decimal(proto.quantity.value) == Decimal("100")
    assert Decimal(proto.cost_basis.value) == Decimal("15000")
    # unrealized_plpc is scaled to a percentage.
    assert Decimal(proto.unrealized_pnl_percent.value) == Decimal("3.3333")


def test_position_completeness_no_unexpected_default() -> None:
    proto = position_to_proto(_make_position())
    for name in _decimal_field_names(proto):
        if name in _POSITION_UNSET_ALLOWLIST:
            assert not proto.HasField(name), f"{name} should be unset"
        else:
            assert proto.HasField(name), f"{name} unexpectedly left at default"


def test_position_nullable_price_fields_unset_when_none() -> None:
    pos = _make_position()
    pos.current_price = None
    pos.market_value = None
    pos.unrealized_pl = None
    pos.unrealized_plpc = None
    proto = position_to_proto(pos)
    for name in ("current_price", "market_value", "unrealized_pnl", "unrealized_pnl_percent"):
        assert not proto.HasField(name)
    # Non-nullable fields still populated.
    assert proto.HasField("cost_basis")
    assert proto.HasField("average_entry_price")
