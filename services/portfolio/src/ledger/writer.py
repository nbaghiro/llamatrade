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
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import LedgerEvent, LedgerEventType

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
        """
        event_id = event_id or uuid4()

        existing = await self.db.scalar(select(LedgerEvent).where(LedgerEvent.event_id == event_id))
        if existing is not None:
            logger.debug("ledger append skipped (duplicate event_id=%s)", event_id)
            return existing

        # Conservation check — economic events must balance (no-op events return []).
        assert_balanced(build_postings(event_type, data))

        event = LedgerEvent(
            event_id=event_id,
            tenant_id=tenant_id,
            account_id=account_id,
            sleeve_id=sleeve_id,
            event_type=event_type.value,
            data=data,
            occurred_at=occurred_at or datetime.now(UTC),
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def read_account_events(self, tenant_id: UUID, account_id: UUID) -> list[LedgerEvent]:
        """Read an account's events in ledger order (for projection folding)."""
        result = await self.db.scalars(
            select(LedgerEvent)
            .where(LedgerEvent.tenant_id == tenant_id)
            .where(LedgerEvent.account_id == account_id)
            .order_by(LedgerEvent.sequence)
        )
        return list(result)
