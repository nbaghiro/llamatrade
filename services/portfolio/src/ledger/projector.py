"""DB-backed projector + reconciliation service (shadow mode).

Thin async wrappers around the pure kernel: read an account's events from the
ledger, fold them into an :class:`AccountProjection`, and reconcile the
aggregate against broker truth. In shadow mode the projection is computed
on-read from the event log (the source of truth); materializing it into
``Sleeve``/``Lot`` rows + ``SleeveSnapshot`` is a later optimization.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.ledger.projection import AccountProjection, fold, holding_history
from src.ledger.reconciliation import Drift, reconcile
from src.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)


class LedgerProjector:
    """Computes projections and reconciliation from the persisted event log."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._writer = LedgerWriter(db)

    async def project_account(self, tenant_id: UUID, account_id: UUID) -> AccountProjection:
        """Fold the account's full event history into a projection."""
        events = await self._writer.read_account_events(tenant_id, account_id)
        return fold(events)

    async def holding_history(self, tenant_id: UUID, account_id: UUID, symbol: str) -> list[object]:
        """Per-symbol provenance timeline (delegates to the pure kernel)."""
        events = await self._writer.read_account_events(tenant_id, account_id)
        return list(holding_history(events, symbol))

    async def reconcile_account(
        self,
        tenant_id: UUID,
        account_id: UUID,
        broker_positions: dict[str, Decimal],
    ) -> list[Drift]:
        """Shadow-compare the ledger aggregate against broker truth.

        Returns the (possibly empty) list of drifts. In shadow mode the caller
        only logs/alerts; once authoritative (Phase 3) it appends correction
        events (external → Unmanaged) and may freeze a sleeve on material drift.
        """
        projection = await self.project_account(tenant_id, account_id)
        drifts = reconcile(projection, broker_positions)
        if drifts:
            logger.warning(
                "ledger reconciliation drift on account %s: %s",
                account_id,
                [(d.symbol, d.kind.value, str(d.delta)) for d in drifts],
            )
        return drifts
