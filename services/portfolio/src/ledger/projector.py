"""DB-backed projector + reconciliation service.

Thin async wrappers around the pure kernel: read an account's events from the
ledger, fold them into an :class:`AccountProjection`, and reconcile the
aggregate against broker truth. The projection is computed on-read from the
event log (the source of truth); materializing it into ``Sleeve``/``Lot`` rows
is a later optimization (``SleeveSnapshot`` already backs the equity curve).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_telemetry import metrics

from src.ledger.projection import AccountProjection, LedgerEventLike, fold, holding_history
from src.ledger.reconciliation import Drift, reconcile
from src.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


def _mismatch_dollars(projection: AccountProjection, drifts: list[Drift]) -> Decimal:
    """Total absolute dollar mismatch of an account's reconciliation drift.

    Each per-symbol quantity drift is valued at the ledger's aggregate average
    cost for that symbol (Σ cost_basis ÷ Σ qty across sleeves) — the only honest
    price the projection itself carries, so no external price source is needed.
    When the ledger holds no quantity for a drifted symbol (``MISSING_IN_LEDGER``)
    there is no ledger cost to value it at, so it contributes zero.
    """
    cost_by: dict[str, Decimal] = {}
    qty_by: dict[str, Decimal] = {}
    for sleeve in projection.sleeves.values():
        for symbol, pos in sleeve.positions.items():
            cost_by[symbol] = cost_by.get(symbol, _ZERO) + pos.cost_basis
            qty_by[symbol] = qty_by.get(symbol, _ZERO) + pos.qty

    total = _ZERO
    for drift in drifts:
        qty = qty_by.get(drift.symbol, _ZERO)
        if qty == _ZERO:
            continue
        avg_cost = cost_by.get(drift.symbol, _ZERO) / qty
        total += abs(drift.delta * avg_cost)
    return total


class LedgerProjector:
    """Computes projections and reconciliation from the persisted event log."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._writer = LedgerWriter(db)

    async def project_account(self, tenant_id: UUID, account_id: UUID) -> AccountProjection:
        """Fold the account's full event history into a projection."""
        events = await self._read_events(tenant_id, account_id)
        with metrics.ledger.projection_fold_duration.time():
            return fold(events)

    async def holding_history(self, tenant_id: UUID, account_id: UUID, symbol: str) -> list[object]:
        """Per-symbol provenance timeline (delegates to the pure kernel)."""
        events = await self._read_events(tenant_id, account_id)
        return list(holding_history(events, symbol))

    async def read_events(self, tenant_id: UUID, account_id: UUID) -> list[LedgerEventLike]:
        """Public alias for reading an account's events (for read-model derivation)."""
        return await self._read_events(tenant_id, account_id)

    async def _read_events(self, tenant_id: UUID, account_id: UUID) -> list[LedgerEventLike]:
        """Event rows as the kernel protocol (ORM rows duck-type it at runtime;
        the cast bridges SQLAlchemy's Mapped descriptors for the type checker)."""
        events = await self._writer.read_account_events(tenant_id, account_id)
        return cast("list[LedgerEventLike]", events)

    async def reconcile_account(
        self,
        tenant_id: UUID,
        account_id: UUID,
        broker_positions: dict[str, Decimal],
    ) -> list[Drift]:
        """Shadow-compare the ledger aggregate against broker truth.

        Returns the (possibly empty) list of drifts. The drift policy then adopts
        external trades into Unmanaged and freezes sleeves the broker
        contradicts (see ``tasks/drift_policy.py``).
        """
        projection = await self.project_account(tenant_id, account_id)
        drifts = reconcile(projection, broker_positions)
        metrics.ledger.vs_broker_mismatch_dollars.set(float(_mismatch_dollars(projection, drifts)))
        if drifts:
            logger.warning(
                "ledger reconciliation drift on account %s: %s",
                account_id,
                [(d.symbol, d.kind.value, str(d.delta)) for d in drifts],
            )
        return drifts
