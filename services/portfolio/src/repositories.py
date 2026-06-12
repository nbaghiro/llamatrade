"""SQLAlchemy adapters for the ledger persistence ports.

These wrap an ``AsyncSession`` and are the production implementation of
``ports.SleeveRepository``. They contain only thin query/insert logic so the
service-layer business logic can be unit-tested against in-memory fakes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import Account, LedgerEvent, LedgerEventType, Sleeve, SleeveType

from src.ledger.projection import AccountProjection
from src.ledger.projector import LedgerProjector
from src.ledger.writer import LedgerWriter


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

    async def get_sleeve(self, tenant_id: UUID, sleeve_id: UUID) -> Sleeve | None:
        return await self.db.scalar(
            select(Sleeve).where(Sleeve.tenant_id == tenant_id, Sleeve.id == sleeve_id)
        )

    async def get_sleeve_by_type(
        self, tenant_id: UUID, account_id: UUID, sleeve_type: SleeveType
    ) -> Sleeve | None:
        # Base sleeves (unallocated/manual/unmanaged) are singletons per account
        # and carry no strategy_execution_id. Tenant-scoped for defense in depth.
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
    ) -> LedgerEvent:
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
