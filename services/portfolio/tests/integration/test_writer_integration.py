"""LedgerWriter against real Postgres — the write path fakes can't cover.

Idempotency (the real ``event_id`` unique constraint) and the monotonic
``sequence`` assignment are DB-level guarantees, exercised here end-to-end.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db.models.ledger import LedgerEvent, LedgerEventType

from src.ledger.writer import LedgerWriter

pytestmark = pytest.mark.integration

TENANT = uuid4()
ACCOUNT = uuid4()


async def _event_count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(LedgerEvent)) or 0)


async def test_append_is_idempotent_on_event_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Re-appending the same event_id is a no-op — never a duplicate row."""
    eid = uuid4()
    data = {"sleeve_id": str(uuid4()), "amount": "1000"}

    async with session_factory() as s:
        first = await LedgerWriter(s).append(
            tenant_id=TENANT,
            account_id=ACCOUNT,
            event_type=LedgerEventType.FUNDS_DEPOSITED,
            data=data,
            event_id=eid,
        )
        await s.commit()
        first_seq = first.sequence

    async with session_factory() as s:
        again = await LedgerWriter(s).append(
            tenant_id=TENANT,
            account_id=ACCOUNT,
            event_type=LedgerEventType.FUNDS_DEPOSITED,
            data=data,
            event_id=eid,
        )
        await s.commit()
        assert again.sequence == first_seq  # returned the existing row
        assert await _event_count(s) == 1  # no duplicate inserted


async def test_sequence_is_monotonic(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Each appended event gets a strictly increasing global sequence."""
    seqs: list[int] = []
    async with session_factory() as s:
        writer = LedgerWriter(s)
        for _ in range(3):
            ev = await writer.append(
                tenant_id=TENANT,
                account_id=ACCOUNT,
                event_type=LedgerEventType.FUNDS_DEPOSITED,
                data={"sleeve_id": str(uuid4()), "amount": "10"},
                event_id=uuid4(),
            )
            seqs.append(ev.sequence)
        await s.commit()

    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 3  # all distinct
