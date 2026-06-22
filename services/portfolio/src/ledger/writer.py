"""Append-only writer for the portfolio ledger.

The single mutating entry point: every value-moving fact is appended exactly
once as a :class:`LedgerEvent`. Writes are:

- **idempotent** — re-appending the same ``event_id`` is a no-op (returns the
  existing row), so a re-delivered fill or a crash-replay can't double-count;
- **balance-checked** — economic events must expand to balanced postings, or
  the append is rejected (conservation enforced at write time).

It consumes fills emitted by the trading service and records them as the
book of record.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import LedgerEvent, LedgerEventType
from llamatrade_telemetry import metrics

from src.ledger.postings import assert_balanced, build_postings

logger = logging.getLogger(__name__)


class LedgerWriter:
    """Appends balanced, idempotent events to the ledger."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def append(
        self,
        *,
        tenant_id: UUID,
        account_id: UUID,
        event_type: LedgerEventType,
        data: dict[str, Any],
        sleeve_id: UUID | None = None,
        event_id: UUID | None = None,
        occurred_at: datetime | None = None,
    ) -> LedgerEvent:
        """Append one event. Idempotent on ``event_id``; balance-checked.

        Returns the persisted (or pre-existing) :class:`LedgerEvent`.

        The insert is a single ``INSERT ... ON CONFLICT (event_id) DO NOTHING``:
        the happy path is one atomic round-trip, and a re-delivered event (same
        ``event_id``) is a no-op that yields no inserted row — so concurrent or
        dual-path delivery can never raise an ``IntegrityError`` (which would
        poison the per-fill transaction). Only on an actual conflict do we pay a
        second round-trip to fetch the pre-existing row.
        """
        event_id = event_id or uuid4()

        with metrics.ledger.event_append_latency.time():
            # Conservation check — economic events must balance (no-op events return []).
            assert_balanced(build_postings(event_type, data))

            stmt = (
                pg_insert(LedgerEvent)
                .values(
                    event_id=event_id,
                    tenant_id=tenant_id,
                    account_id=account_id,
                    sleeve_id=sleeve_id,
                    event_type=event_type.value,
                    data=data,
                    occurred_at=occurred_at or datetime.now(UTC),
                )
                .on_conflict_do_nothing(index_elements=["event_id"])
                .returning(LedgerEvent)
            )
            inserted = (await self.db.execute(stmt)).scalars().first()

        if inserted is not None:
            return inserted

        # Conflict: the event already exists (idempotent re-delivery / dual path).
        logger.debug("ledger append deduped (existing event_id=%s)", event_id)
        existing = await self.db.scalar(select(LedgerEvent).where(LedgerEvent.event_id == event_id))
        if existing is None:  # pragma: no cover - ON CONFLICT guarantees it exists
            raise RuntimeError(f"event {event_id} conflicted on insert but is absent")
        return existing

    async def read_account_events(self, tenant_id: UUID, account_id: UUID) -> list[LedgerEvent]:
        """Read an account's events in ledger order (for projection folding)."""
        result = await self.db.scalars(
            select(LedgerEvent)
            .where(LedgerEvent.tenant_id == tenant_id)
            .where(LedgerEvent.account_id == account_id)
            .order_by(LedgerEvent.sequence)
        )
        return list(result)

    async def read_account_events_since(
        self, tenant_id: UUID, account_id: UUID, after_sequence: int
    ) -> list[LedgerEvent]:
        """Read an account's events with ``sequence > after_sequence`` (the delta
        the incremental projection folds onto a checkpoint)."""
        result = await self.db.scalars(
            select(LedgerEvent)
            .where(LedgerEvent.tenant_id == tenant_id)
            .where(LedgerEvent.account_id == account_id)
            .where(LedgerEvent.sequence > after_sequence)
            .order_by(LedgerEvent.sequence)
        )
        return list(result)
