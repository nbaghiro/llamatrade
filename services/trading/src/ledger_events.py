"""Ledger event payload builders (pure; see .docs/planning/CONTRACTS.md).

Trading publishes to ``ledger:fills:{account_id}`` exactly ONE fill payload
per order, at terminal state:

- ``fill`` → the cumulative ``filled_qty`` / ``filled_avg_price``;
- ``canceled`` / ``expired`` with a nonzero filled quantity → the filled
  portion.

Partial fills never publish — the ledger dedups on
``event_id = sha256(client_order_id)``, so per-partial publishing would drop
all but the first. ``cost_basis``/``realized_pnl`` are intentionally absent:
the portfolio consumer resolves them via FIFO at ingestion (amendment 3A).

Order lifecycle payloads (``order_submitted`` / ``order_cancelled`` /
``order_rejected``) carry the reservation contract (§4); they share the
envelope but set ``event_type`` so the consumer routes them separately.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from llamatrade_alpaca.models import TradeEvent, TradeEventType
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FILLED,
)

if TYPE_CHECKING:
    from llamatrade_db.models.trading import Order

# Terminal states that close out an order at the broker.
_TERMINAL_WITH_FILL = {TradeEventType.CANCELED, TradeEventType.EXPIRED}

# Order-row statuses that may carry a publishable filled portion.
_TERMINAL_STATUSES_WITH_FILL = {ORDER_STATUS_CANCELLED, ORDER_STATUS_EXPIRED}


def build_ledger_fill_payload(
    *,
    tenant_id: UUID,
    account_id: UUID,
    sleeve_id: UUID,
    event: TradeEvent,
    order_id: UUID | None = None,
) -> dict[str, str] | None:
    """The §1a fill payload for a terminal trade event, or None to skip.

    Returns None for partial fills (never published), for terminal events
    with nothing filled, and for fills missing an average price.
    """
    if event.event_type is TradeEventType.FILL:
        qty = event.filled_qty
    elif event.event_type in _TERMINAL_WITH_FILL:
        qty = event.filled_qty
        if qty <= 0:
            return None  # nothing filled — the reservation release covers cash
    else:
        return None

    price = event.filled_avg_price
    if qty <= 0 or price is None:
        return None

    return build_fill_payload(
        tenant_id=tenant_id,
        account_id=account_id,
        sleeve_id=sleeve_id,
        client_order_id=event.client_order_id,
        symbol=event.symbol,
        side=event.side,
        qty=qty,
        price=price,
        filled_at=event.timestamp,
        order_id=order_id,
    )


def build_ledger_fill_payload_from_order(order: Order) -> dict[str, str] | None:
    """The §1a fill payload from a persisted Order row, or None to skip.

    The REST recovery path (``sync_order_status`` / ``sync_all_pending_orders``)
    discovers terminal states the trade stream may have missed; emission is
    idempotent with the stream path (same ``client_order_id`` → same ledger
    ``event_id``), so double-firing is harmless and a missed stream event is
    not a permanent ledger gap.
    """
    if order.sleeve_id is None or order.account_id is None:
        return None

    if order.status == ORDER_STATUS_FILLED:
        qty = order.filled_qty
    elif order.status in _TERMINAL_STATUSES_WITH_FILL:
        qty = order.filled_qty
        if qty <= 0:
            return None  # nothing filled — the reservation release covers cash
    else:
        return None

    price = order.filled_avg_price
    if qty <= 0 or price is None:
        return None

    from src.models import order_side_to_str

    return build_fill_payload(
        tenant_id=order.tenant_id,
        account_id=order.account_id,
        sleeve_id=order.sleeve_id,
        client_order_id=order.client_order_id,
        symbol=order.symbol,
        side=order_side_to_str(order.side),
        qty=qty,
        price=price,
        filled_at=order.filled_at or order.canceled_at or datetime.now(UTC),
        order_id=order.id,
    )


def build_fill_payload(
    *,
    tenant_id: UUID,
    account_id: UUID,
    sleeve_id: UUID,
    client_order_id: str,
    symbol: str,
    side: str,
    qty: Decimal,
    price: Decimal,
    filled_at: datetime,
    order_id: UUID | None,
) -> dict[str, str]:
    payload = {
        "tenant_id": str(tenant_id),
        "account_id": str(account_id),
        "sleeve_id": str(sleeve_id),
        "client_order_id": client_order_id,
        "symbol": symbol,
        "side": side,
        "qty": str(qty),
        "price": str(price),
        "filled_at": filled_at.isoformat(),
    }
    if order_id is not None:
        payload["order_id"] = str(order_id)
    return payload


def build_ledger_lifecycle_payload(
    *,
    kind: str,  # "order_submitted" | "order_cancelled" | "order_rejected"
    tenant_id: UUID,
    account_id: UUID,
    sleeve_id: UUID,
    client_order_id: str,
    symbol: str,
    side: str,
    reserved: Decimal | None = None,
    order_id: UUID | None = None,
) -> dict[str, str]:
    """A reservation lifecycle payload (§4): reserve on submit, release on
    cancel/reject. ``reserved`` is the estimated notional earmarked for buys."""
    payload = {
        "event_type": kind,
        "tenant_id": str(tenant_id),
        "account_id": str(account_id),
        "sleeve_id": str(sleeve_id),
        "client_order_id": client_order_id,
        "symbol": symbol,
        "side": side,
    }
    if reserved is not None:
        payload["reserved"] = str(reserved)
    if order_id is not None:
        payload["order_id"] = str(order_id)
    return payload
