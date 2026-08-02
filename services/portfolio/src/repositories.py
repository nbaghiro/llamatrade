"""SQLAlchemy adapters for the ledger persistence ports.

These wrap an ``AsyncSession`` and are the production implementation of
``ports.SleeveRepository``. They contain only thin query/insert logic so the
service-layer business logic can be unit-tested against in-memory fakes.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import Account, LedgerEvent, LedgerEventType, Sleeve, SleeveType

from src.ledger.projection import AccountProjection, open_lots
from src.ledger.projector import LedgerProjector
from src.ledger.sizing import Lot
from src.ledger.writer import LedgerWriter
from src.ports import DuplicateBrokerAccounts

_XACT_LOCK_SQL = text("SELECT pg_advisory_xact_lock(cast(:key as bigint))")
_SIGNED_64_OFFSET = 1 << 63


def _account_lock_key(account_id: UUID) -> int:
    """A stable signed 64-bit advisory-lock key derived from an account id."""
    digest = hashlib.sha256(account_id.bytes).digest()[:8]
    return int.from_bytes(digest, "big") - _SIGNED_64_OFFSET


async def lock_account_for_write(db: AsyncSession, account_id: UUID) -> None:
    """Take a transaction-level advisory lock on ``account_id`` (blocks until held).

    Serializes concurrent capital operations on one account so two allocates can
    never both pass the free-cash check under READ COMMITTED and drive a sleeve
    negative. ``pg_advisory_xact_lock`` auto-releases at commit or rollback, so
    the caller must run inside the fund op's transaction.
    """
    await db.execute(_XACT_LOCK_SQL, {"key": _account_lock_key(account_id)})


async def find_duplicate_broker_accounts(db: AsyncSession) -> list[DuplicateBrokerAccounts]:
    """Accounts sharing a broker account within one tenant, across all tenants.

    The unique constraint makes this unreachable for rows written after it landed;
    the sweep exists so anything loaded out of band (or predating the constraint)
    is surfaced rather than silently double-counted. Needs a session that can read
    across tenants.
    """
    keys = (
        await db.execute(
            select(Account.tenant_id, Account.alpaca_account_id)
            .where(Account.alpaca_account_id.is_not(None))
            .group_by(Account.tenant_id, Account.alpaca_account_id)
            .having(func.count() > 1)
        )
    ).all()
    if not keys:
        return []

    rows = (
        await db.execute(
            select(Account.tenant_id, Account.alpaca_account_id, Account.id)
            .where(
                or_(
                    *(
                        and_(
                            Account.tenant_id == tenant_id,
                            Account.alpaca_account_id == broker_account_id,
                        )
                        for tenant_id, broker_account_id in keys
                    )
                )
            )
            .order_by(Account.created_at)
        )
    ).all()
    grouped: dict[tuple[UUID, str], list[UUID]] = {}
    for tenant_id, broker_account_id, account_id in rows:
        if broker_account_id is None:
            continue
        grouped.setdefault((tenant_id, broker_account_id), []).append(account_id)
    return [
        DuplicateBrokerAccounts(
            tenant_id=tenant_id,
            broker_account_id=broker_account_id,
            account_ids=tuple(account_ids),
        )
        for (tenant_id, broker_account_id), account_ids in grouped.items()
    ]


class SqlSleeveRepository:
    """``ports.SleeveRepository`` backed by a SQLAlchemy session."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_account_by_credentials(
        self, tenant_id: UUID, credentials_id: UUID
    ) -> Account | None:
        return await self.db.scalar(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.credentials_id == credentials_id,
            )
        )

    async def get_account_by_broker_id(
        self, tenant_id: UUID, broker_account_id: str
    ) -> Account | None:
        return await self.db.scalar(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.alpaca_account_id == broker_account_id,
            )
        )

    async def get_account(self, tenant_id: UUID, account_id: UUID) -> Account | None:
        return await self.db.scalar(
            select(Account).where(
                Account.tenant_id == tenant_id,
                Account.id == account_id,
            )
        )

    async def add_account(self, account: Account) -> None:
        self.db.add(account)
        await self.db.flush()

    async def set_account_credentials(self, account: Account, credentials_id: UUID) -> None:
        account.credentials_id = credentials_id
        await self.db.flush()

    async def set_account_broker_id(self, account: Account, broker_account_id: str) -> None:
        account.alpaca_account_id = broker_account_id
        await self.db.flush()

    async def get_sleeve(self, tenant_id: UUID, sleeve_id: UUID) -> Sleeve | None:
        return await self.db.scalar(
            select(Sleeve).where(Sleeve.tenant_id == tenant_id, Sleeve.id == sleeve_id)
        )

    async def get_sleeve_by_type(
        self, tenant_id: UUID, account_id: UUID, sleeve_type: SleeveType
    ) -> Sleeve | None:
        # Base sleeves (unallocated/manual/unmanaged) are singletons per account with no strategy_execution_id; tenant-scoped for defense in depth.
        return await self.db.scalar(
            select(Sleeve).where(
                Sleeve.tenant_id == tenant_id,
                Sleeve.account_id == account_id,
                Sleeve.type == sleeve_type.value,
                Sleeve.strategy_execution_id.is_(None),
            )
        )

    async def get_strategy_sleeve(
        self, tenant_id: UUID, account_id: UUID, strategy_execution_id: UUID
    ) -> Sleeve | None:
        return await self.db.scalar(
            select(Sleeve).where(
                Sleeve.tenant_id == tenant_id,
                Sleeve.account_id == account_id,
                Sleeve.type == SleeveType.STRATEGY.value,
                Sleeve.strategy_execution_id == strategy_execution_id,
            )
        )

    async def list_sleeves(self, tenant_id: UUID, account_id: UUID) -> list[Sleeve]:
        result = await self.db.scalars(
            select(Sleeve)
            .where(Sleeve.tenant_id == tenant_id, Sleeve.account_id == account_id)
            .order_by(Sleeve.created_at)
        )
        return list(result.all())

    async def set_sleeve_status(self, sleeve: Sleeve, status: str) -> None:
        sleeve.status = status
        await self.db.flush()

    async def add_sleeve(self, sleeve: Sleeve) -> None:
        self.db.add(sleeve)
        await self.db.flush()


class SqlLedgerStore:
    """``ports.LedgerStore`` backed by ``LedgerWriter`` + ``LedgerProjector``."""

    def __init__(self, db: AsyncSession) -> None:
        self._writer = LedgerWriter(db)
        self._projector = LedgerProjector(db)

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
    ) -> tuple[LedgerEvent, bool]:
        return await self._writer.append(
            tenant_id=tenant_id,
            account_id=account_id,
            event_type=event_type,
            data=data,
            sleeve_id=sleeve_id,
            event_id=event_id,
            occurred_at=occurred_at,
        )

    async def project_account(self, tenant_id: UUID, account_id: UUID) -> AccountProjection:
        return await self._projector.project_account(tenant_id, account_id)

    async def open_lots(
        self, tenant_id: UUID, account_id: UUID, sleeve_id: UUID, symbol: str
    ) -> list[Lot]:
        events = await self._projector.read_events(tenant_id, account_id)
        return open_lots(events, str(sleeve_id), symbol)
