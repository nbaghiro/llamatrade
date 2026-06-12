"""Fill ingestion: trading-service fills → ledger events (shadow mode).

The trading service is the execution arm; it emits exactly ONE ``OrderFilled``
event per order, at terminal state (tagged with the deterministic
``client_order_id`` that maps to a sleeve):

- on ``fill``: the cumulative ``filled_qty`` / ``filled_avg_price``;
- on ``canceled``/``expired`` with a nonzero filled quantity: the filled
  portion only.

Partial fills never publish — the ledger ``event_id`` is derived from
``client_order_id``, so per-partial publishing would dedup all but the first.

``cost_basis``/``realized_pnl`` on sells are OPTIONAL in the payload: when
absent, the consumer handler computes them at ingestion via FIFO lot selection
against the account projection (the ledger owns the lots; trading reports
broker facts only).

The translation (`fill_to_append`) is a pure function so it can be unit-tested;
``FillConsumer`` is the thin Redis pub/sub adapter that drives it. In shadow
mode this only *records* — it does not drive execution.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger.sizing import Lot, select_lots_fifo

logger = logging.getLogger(__name__)

# Redis channel the trading service publishes fills to (per account).
FILL_CHANNEL_PREFIX = "ledger:fills"

# Non-fill order lifecycle stages trading publishes on the same channel
# (reservation addendum, CONTRACTS.md §4). Recorded without postings until
# LEDGER_EXECUTION posting rules land.
LIFECYCLE_EVENT_TYPES: dict[str, LedgerEventType] = {
    "order_submitted": LedgerEventType.ORDER_SUBMITTED,
    "order_cancelled": LedgerEventType.ORDER_CANCELLED,
    "order_rejected": LedgerEventType.ORDER_REJECTED,
}


def fill_channel(account_id: UUID | str) -> str:
    return f"{FILL_CHANNEL_PREFIX}:{account_id}"


@dataclass(frozen=True)
class LedgerAppend:
    """Resolved arguments for :meth:`LedgerWriter.append` (pure translation result)."""

    tenant_id: UUID
    account_id: UUID
    sleeve_id: UUID
    event_type: LedgerEventType
    data: dict[str, Any]
    event_id: UUID
    occurred_at: datetime


def fill_to_append(fill: dict[str, Any]) -> LedgerAppend:
    """Translate a trading ``OrderFilled`` payload into a ledger append.

    Expected payload keys: ``tenant_id``, ``account_id``, ``sleeve_id``,
    ``client_order_id`` (idempotency key), ``symbol``, ``side`` (buy/sell),
    ``qty``, ``price``; optional ``fees``, ``cost_basis`` (sells),
    ``realized_pnl`` (sells), ``order_id``, ``filled_at`` (ISO).

    ``qty``/``price`` are the order's terminal cumulative fill quantity and
    average fill price — one payload per order, never per partial fill.
    When ``cost_basis`` is absent on a sell, the consumer computes it at
    ingestion (FIFO against the projection) before appending.

    Idempotency: the ledger ``event_id`` is derived from the broker
    ``client_order_id`` so a re-delivered fill is a no-op at the writer.
    """
    data: dict[str, Any] = {
        "sleeve_id": str(fill["sleeve_id"]),
        "symbol": str(fill["symbol"]),
        "side": str(fill["side"]).lower(),
        "qty": str(fill["qty"]),
        "price": str(fill["price"]),
        # Carried in data so the fill releases its cash reservation (§4)
        "client_order_id": str(fill["client_order_id"]),
    }
    for optional in ("fees", "cost_basis", "realized_pnl", "order_id"):
        if optional in fill and fill[optional] is not None:
            data[optional] = str(fill[optional])

    occurred_at = _parse_ts(fill.get("filled_at"))
    return LedgerAppend(
        tenant_id=UUID(str(fill["tenant_id"])),
        account_id=UUID(str(fill["account_id"])),
        sleeve_id=UUID(str(fill["sleeve_id"])),
        event_type=LedgerEventType.ORDER_FILLED,
        data=data,
        event_id=_event_id_from_client_order_id(str(fill["client_order_id"])),
        occurred_at=occurred_at,
    )


def payload_to_append(payload: dict[str, Any]) -> LedgerAppend:
    """Route one channel payload to a ledger append by its ``event_type`` key.

    No ``event_type`` (or ``"order_filled"``) → a fill (``fill_to_append``).
    ``order_submitted`` / ``order_cancelled`` / ``order_rejected`` → an order
    lifecycle event whose ``event_id`` derives from ``client_order_id:stage``,
    so each stage is idempotent independently of the fill.
    """
    kind = str(payload.get("event_type", "order_filled")).lower()
    if kind == "order_filled":
        return fill_to_append(payload)

    try:
        event_type = LIFECYCLE_EVENT_TYPES[kind]
    except KeyError:
        raise ValueError(f"unknown ledger payload event_type: {kind!r}") from None

    data: dict[str, Any] = {
        "sleeve_id": str(payload["sleeve_id"]),
        "client_order_id": str(payload["client_order_id"]),
    }
    for optional in ("symbol", "side", "qty", "price", "reserved", "order_id"):
        if optional in payload and payload[optional] is not None:
            data[optional] = str(payload[optional])

    return LedgerAppend(
        tenant_id=UUID(str(payload["tenant_id"])),
        account_id=UUID(str(payload["account_id"])),
        sleeve_id=UUID(str(payload["sleeve_id"])),
        event_type=event_type,
        data=data,
        event_id=_event_id_from_client_order_id(f"{payload['client_order_id']}:{kind}"),
        occurred_at=_parse_ts(payload.get("occurred_at") or payload.get("filled_at")),
    )


def needs_cost_basis(append: LedgerAppend) -> bool:
    """True for a sell fill whose publisher did not resolve a cost basis."""
    return (
        append.event_type is LedgerEventType.ORDER_FILLED
        and append.data.get("side") == "sell"
        and "cost_basis" not in append.data
    )


def enrich_sell_fill(append: LedgerAppend, lots: list[Lot]) -> LedgerAppend:
    """Resolve FIFO cost basis + realized P&L into a sell fill's event data.

    The consumer calls this at ingestion (the ledger owns the lots; trading
    only reports broker facts). If the open lots can't cover the sell, the
    fill is recorded unenriched (cost defaults to notional → zero P&L) and
    reconciliation surfaces the discrepancy.
    """
    if not needs_cost_basis(append):
        return append

    qty = Decimal(append.data["qty"])
    try:
        result = select_lots_fifo(lots, qty)
    except ValueError as e:
        logger.warning(
            "cannot resolve FIFO cost basis for sell (sleeve=%s symbol=%s qty=%s): %s",
            append.sleeve_id,
            append.data.get("symbol"),
            qty,
            e,
        )
        return append

    price = Decimal(append.data["price"])
    fees = Decimal(append.data["fees"]) if "fees" in append.data else Decimal("0")
    realized = qty * price - result.closed_cost_basis - fees

    data = dict(append.data)
    data["cost_basis"] = str(result.closed_cost_basis)
    data.setdefault("realized_pnl", str(realized))
    return replace(append, data=data)


def _parse_ts(raw: object) -> datetime:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def _event_id_from_client_order_id(client_order_id: str) -> UUID:
    """Deterministic, idempotent ledger event id derived from the broker order id."""
    return UUID(bytes=hashlib.sha256(client_order_id.encode()).digest()[:16])


FillHandler = Callable[[LedgerAppend], Awaitable[None]]


class FillConsumer:
    """Subscribes to an account's fill channel and drives a handler.

    Thin Redis pub/sub adapter (mirrors the trading service's subscriber
    pattern); the economic logic lives in ``fill_to_append`` + ``LedgerWriter``.
    """

    def __init__(self, redis: Any, handler: FillHandler) -> None:
        self._redis = redis
        self._handler = handler

    async def run(self, account_id: UUID) -> None:  # pragma: no cover - IO loop
        import json

        pubsub = self._redis.pubsub()
        channel = fill_channel(account_id)
        await pubsub.subscribe(channel)
        logger.info("ledger fill consumer subscribed to %s", channel)
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=None)
                if message is None or message.get("type") != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    await self._handler(fill_to_append(payload))
                except Exception:  # never let one bad fill kill the loop
                    logger.exception("failed to ingest fill")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
