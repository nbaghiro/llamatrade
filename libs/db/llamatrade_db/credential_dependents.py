"""Read what still depends on a broker credential set (shared read helper).

Auth owns the ``AlpacaCredentials`` rows but not the state keyed off them, so the
dependency query lives here with the models it reads: trading sessions that name
the credential set, and funded sleeves on the ledger ``Account`` that is unique
per ``credentials_id``. Auth refuses deletion while either exists, because a
deleted credential leaves live trading unable to reach the broker and leaves the
account's reconciliation permanently stale.

Every query is tenant-scoped in the app layer: auth runs with the RLS system
bypass (it is a cross-tenant identity authority), so the filters here are the
isolation boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import Account, Sleeve, SleeveStatus
from llamatrade_db.models.trading import TradingSession
from llamatrade_proto.generated import common_pb2

# Sessions in these states still trade, or resume trading, against the broker.
# STOPPED / ERROR sessions hold no broker connection and never resume on their own.
BLOCKING_SESSION_STATUSES: tuple[common_pb2.ExecutionStatus.ValueType, ...] = (
    common_pb2.EXECUTION_STATUS_RUNNING,
    common_pb2.EXECUTION_STATUS_PAUSED,
)

# Live cash is projected from the event log, so ``allocated_capital`` is the only
# durable funded marker on the row. It also excludes the three base singleton
# sleeves (Unallocated / Manual / Unmanaged), which are always open and always
# carry zero allocated capital, so an account is not blocked forever.
_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class CredentialDependents:
    """Live sessions and funded sleeves still bound to a credential set."""

    session_ids: tuple[UUID, ...] = ()
    sleeve_ids: tuple[UUID, ...] = ()
    strategy_execution_ids: tuple[UUID, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.session_ids or self.sleeve_ids)


async def get_credential_dependents(
    db: AsyncSession, tenant_id: UUID, credentials_id: UUID
) -> CredentialDependents:
    """Everything that blocks deleting ``credentials_id`` for ``tenant_id``."""
    session_ids = (
        await db.scalars(
            select(TradingSession.id)
            .where(
                TradingSession.tenant_id == tenant_id,
                TradingSession.credentials_id == credentials_id,
                TradingSession.status.in_(BLOCKING_SESSION_STATUSES),
            )
            .order_by(TradingSession.created_at)
        )
    ).all()

    sleeve_rows = (
        (
            await db.execute(
                select(Sleeve.id, Sleeve.strategy_execution_id)
                .join(Account, Account.id == Sleeve.account_id)
                .where(
                    Sleeve.tenant_id == tenant_id,
                    Account.tenant_id == tenant_id,
                    Account.credentials_id == credentials_id,
                    Sleeve.status != SleeveStatus.CLOSED.value,
                    Sleeve.allocated_capital > _ZERO,
                )
                .order_by(Sleeve.created_at)
            )
        )
        .tuples()
        .all()
    )

    return CredentialDependents(
        session_ids=tuple(session_ids),
        sleeve_ids=tuple(sleeve_id for sleeve_id, _ in sleeve_rows),
        strategy_execution_ids=tuple(
            execution_id for _, execution_id in sleeve_rows if execution_id is not None
        ),
    )
