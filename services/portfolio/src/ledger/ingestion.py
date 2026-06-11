"""Fill ingestion: trading-service fills → ledger events (shadow mode).

The trading service is the execution arm; on each fill it emits an
``OrderFilled`` event (tagged with the deterministic ``client_order_id`` that
maps to a sleeve). The portfolio ledger consumes those fills and records them.

The translation (`fill_to_append`) is a pure function so it can be unit-tested;
``FillConsumer`` is the thin Redis pub/sub adapter that drives it. In shadow
mode this only *records* — it does not drive execution.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from llamatrade_db.models.ledger import LedgerEventType

logger = logging.getLogger(__name__)

# Redis channel the trading service publishes fills to (per account).
FILL_CHANNEL_PREFIX = "ledger:fills"


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

    Idempotency: the ledger ``event_id`` is derived from the broker
    ``client_order_id`` so a re-delivered fill is a no-op at the writer.
    """
    data: dict[str, Any] = {
        "sleeve_id": str(fill["sleeve_id"]),
        "symbol": str(fill["symbol"]),
        "side": str(fill["side"]).lower(),
        "qty": str(fill["qty"]),
        "price": str(fill["price"]),
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
                except Exception:  # noqa: BLE001 - never let one bad fill kill the loop
                    logger.exception("failed to ingest fill")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
