"""Ledger fill + reservation events — trading → portfolio (durable consumer group).

One global stream (``ledger:fills``); per-account FIFO is preserved by global
order, and payloads carry ``account_id`` (CONTRACTS.md §1). Two payload types ride
the same stream, discriminated by ``EventType``:

- ``LedgerFill`` — a terminal fill (idempotency seed: ``client_order_id``).
- ``LedgerReservation`` — cash reservation lifecycle (seed:
  ``client_order_id:event_type``).

Producer: trading's fill publisher. Consumer: portfolio's ledger ingestion, via a
:class:`StreamConsumer` over this channel.
"""

from __future__ import annotations

from typing import cast

from llamatrade_events.bus import EventBus
from llamatrade_events.channels import LEDGER_FILLS
from llamatrade_events.codec import EventEnvelope, make_envelope, parse_payload, register_payload
from llamatrade_events.consumer import StreamConsumer
from llamatrade_events.idempotency import DedupStore, derive_event_id
from llamatrade_events.transport.base import CURSOR_BEGIN, Cursor
from llamatrade_proto.generated import events_pb2

LedgerFill = events_pb2.LedgerFill
LedgerReservation = events_pb2.LedgerReservation

register_payload(events_pb2.EVENT_TYPE_LEDGER_FILL, LedgerFill)
register_payload(events_pb2.EVENT_TYPE_LEDGER_RESERVATION, LedgerReservation)

# Portfolio's durable consumer group on the ledger stream.
PORTFOLIO_GROUP = "portfolio-ledger"


class FillEvents:
    """Durable trading→portfolio ledger stream (produce + consumer factory)."""

    def __init__(self, *, bus: EventBus | None = None) -> None:
        self._bus = bus or EventBus()
        self._stream = LEDGER_FILLS.key()

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def stream(self) -> str:
        return self._stream

    async def publish_fill(self, fill: LedgerFill, *, event_id: str | None = None) -> Cursor:
        env = make_envelope(
            events_pb2.EVENT_TYPE_LEDGER_FILL,
            fill,
            event_id=event_id or derive_event_id(fill.client_order_id),
            tenant_id=fill.tenant_id,
        )
        return await self._bus.publish_envelope(self._stream, env, maxlen=LEDGER_FILLS.maxlen)

    async def publish_reservation(
        self, reservation: LedgerReservation, *, event_id: str | None = None
    ) -> Cursor:
        env = make_envelope(
            events_pb2.EVENT_TYPE_LEDGER_RESERVATION,
            reservation,
            event_id=event_id
            or derive_event_id(reservation.client_order_id, reservation.event_type),
            tenant_id=reservation.tenant_id,
        )
        return await self._bus.publish_envelope(self._stream, env, maxlen=LEDGER_FILLS.maxlen)

    def consumer(
        self,
        *,
        consumer_name: str,
        group: str = PORTFOLIO_GROUP,
        dedup: DedupStore | None = None,
        group_start: str = CURSOR_BEGIN,
        claim_min_idle_ms: int = 60_000,
    ) -> StreamConsumer:
        """A durable consumer for the ledger stream (handler gets the envelope).

        Defaults to ``group_start=CURSOR_BEGIN`` (never miss a fill: a fresh group
        replays the retained stream — safe given the writer's event-id dedupe).
        """
        return StreamConsumer(
            self._bus,
            self._stream,
            group,
            consumer_name=consumer_name,
            dedup=dedup,
            group_start=group_start,
            claim_min_idle_ms=claim_min_idle_ms,
        )

    @staticmethod
    def payload(envelope: EventEnvelope) -> LedgerFill | LedgerReservation:
        """Parse a consumed envelope into its fill / reservation message.

        Both EventTypes on this stream are registered to one of these two
        messages, so the registry guarantees the narrowed type.
        """
        return cast("LedgerFill | LedgerReservation", parse_payload(envelope))

    async def close(self) -> None:
        await self._bus.close()
