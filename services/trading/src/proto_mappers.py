"""Canonical DB-row → proto mappers for trading reads.

Proto is the single source of truth for the read/wire shape (decision 1A): map
the persisted ``Position`` row straight to the generated proto message, money as
``Decimal`` end-to-end, with no intermediate Pydantic layer. This fully
populates fields the old ``PositionResponse`` dropped (id, tenant_id, session_id,
average_entry_price, realized_pnl, opened_at, updated_at) instead of blanking
them or reconstructing them at the servicer boundary.
"""

from decimal import Decimal

from llamatrade_db.models.trading import Order, Position
from llamatrade_proto.generated import common_pb2, trading_pb2
from llamatrade_proto.timestamps import to_proto_timestamp


def _dec(value: Decimal) -> common_pb2.Decimal:
    return common_pb2.Decimal(value=str(value))


def position_to_proto(p: Position) -> trading_pb2.Position:
    """Map a persisted Position row to a fully-populated proto Position.

    ``available_quantity`` has no DB column and is left unset.
    """
    proto = trading_pb2.Position(
        id=str(p.id),
        tenant_id=str(p.tenant_id),
        session_id=str(p.session_id),
        symbol=p.symbol,
        side=p.side,
        quantity=_dec(p.qty),
        cost_basis=_dec(p.cost_basis),
        average_entry_price=_dec(p.avg_entry_price),
        realized_pnl=_dec(p.realized_pl),
        opened_at=to_proto_timestamp(p.opened_at),
        updated_at=to_proto_timestamp(p.updated_at),
    )
    if p.current_price is not None:
        proto.current_price.CopyFrom(_dec(p.current_price))
    if p.market_value is not None:
        proto.market_value.CopyFrom(_dec(p.market_value))
    if p.unrealized_pl is not None:
        proto.unrealized_pnl.CopyFrom(_dec(p.unrealized_pl))
    if p.unrealized_plpc is not None:
        proto.unrealized_pnl_percent.CopyFrom(_dec(p.unrealized_plpc * 100))
    return proto


def order_to_proto(o: Order) -> trading_pb2.Order:
    """Map a persisted Order row to a proto Order.

    Proto Order carries no bracket fields, so bracket_type / stop_loss_price /
    take_profit_price (DB-only, REST-invisible) are intentionally not emitted.
    """
    proto = trading_pb2.Order(
        id=str(o.id),
        # The deterministic client_order_id (idempotency key), NOT the broker id.
        client_order_id=o.client_order_id or "",
        tenant_id=str(o.tenant_id) if o.tenant_id else "",
        session_id=str(o.session_id) if o.session_id else "",
        symbol=o.symbol,
        side=o.side,
        type=o.order_type,
        time_in_force=o.time_in_force,
        status=o.status,
        quantity=_dec(o.qty),
        sleeve_id=str(o.sleeve_id) if o.sleeve_id else "",
        account_id=str(o.account_id) if o.account_id else "",
    )
    if o.filled_qty:
        proto.filled_quantity.CopyFrom(_dec(o.filled_qty))
    if o.limit_price:
        proto.limit_price.CopyFrom(_dec(o.limit_price))
    if o.stop_price:
        proto.stop_price.CopyFrom(_dec(o.stop_price))
    if o.filled_avg_price:
        proto.average_fill_price.CopyFrom(_dec(o.filled_avg_price))
    submitted = o.submitted_at or o.created_at
    if submitted:
        proto.created_at.CopyFrom(to_proto_timestamp(submitted))
        proto.submitted_at.CopyFrom(to_proto_timestamp(submitted))
    if o.filled_at:
        proto.filled_at.CopyFrom(to_proto_timestamp(o.filled_at))
    if o.canceled_at:
        proto.cancelled_at.CopyFrom(to_proto_timestamp(o.canceled_at))
    return proto
