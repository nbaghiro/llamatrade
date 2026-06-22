"""DB-backed projector + reconciliation service.

Thin async wrappers around the pure kernel: read an account's events from the
ledger, fold them into an :class:`AccountProjection`, and reconcile the
aggregate against broker truth. The projection is computed on-read from the
event log (the source of truth); materializing it into ``Sleeve``/``Lot`` rows
is a later optimization (``SleeveSnapshot`` already backs the equity curve).
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_telemetry import metrics

from src.ledger.projection import (
    AccountProjection,
    LedgerEventLike,
    _fold_into,
    fold,
    holding_history,
)
from src.ledger.reconciliation import Drift, reconcile
from src.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


@dataclass
class _Checkpoint:
    """A folded projection at a sequence, plus the open-reservation map needed to
    resume the fold (the two together are the full ``fold`` state)."""

    as_of_sequence: int
    projection: AccountProjection
    pending: dict[str, tuple[str, Decimal]]


# Process-level incremental-projection cache. Populated ONLY from committed reads
# (a fresh read-only session): folding the delta since a checkpoint onto a deep
# copy of it equals a full fold by construction (shared ``_fold_into`` + the
# split-invariance property test). In-transaction writers must NOT use the
# incremental path — a mid-transaction (uncommitted) read would seed a checkpoint
# with events that may roll back. Keyed by (tenant_id, account_id).
_INCREMENTAL_CACHE: dict[tuple[str, str], _Checkpoint] = {}


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

    @staticmethod
    def _on_poison(event_id: str | None, exc: Exception) -> None:
        metrics.ledger.poison_event()
        # High-sev alert: a persisted event was skipped, so this account's
        # projection is incomplete until fixed. The event stays recoverable from
        # the ledger by its id (it's a row); the ERROR log is the actionable
        # pointer for operator review.
        logger.error(
            "poison ledger event skipped during projection (event_id=%s): %s; "
            "account projection is incomplete until corrected",
            event_id,
            exc,
        )

    async def project_account(self, tenant_id: UUID, account_id: UUID) -> AccountProjection:
        """Fold the account's full event history into a projection.

        Folds from zero every call — safe for in-transaction callers (fund ops,
        the post-fill invariant freeze, close) whose session may hold uncommitted
        events. Read-only, committed-state callers should prefer
        :meth:`project_account_incremental`.
        """
        events = await self._read_events(tenant_id, account_id)
        with metrics.ledger.projection_fold_duration.time():
            return fold(events, on_error=self._on_poison)

    async def project_account_incremental(
        self, tenant_id: UUID, account_id: UUID
    ) -> AccountProjection:
        """Project from the latest cached checkpoint + only the delta since it.

        Equivalent to :meth:`project_account` by construction (same ``_fold_into``),
        but O(new events) instead of O(all events). **Caller contract:** the
        session must read COMMITTED state (a fresh read-only session) — a
        mid-transaction caller could seed the checkpoint with events that later
        roll back. The reconciliation loop (fresh per-account sessions) is the
        caller. Deep copies guard the shared cache from mutation/torn reads.
        """
        key = (str(tenant_id), str(account_id))
        cp = _INCREMENTAL_CACHE.get(key)
        after = cp.as_of_sequence if cp is not None else 0
        delta = cast(
            "list[LedgerEventLike]",
            await self._writer.read_account_events_since(tenant_id, account_id, after),
        )
        if cp is not None and not delta:
            return copy.deepcopy(cp.projection)  # nothing new since the checkpoint

        projection = copy.deepcopy(cp.projection) if cp is not None else AccountProjection()
        pending = dict(cp.pending) if cp is not None else {}
        with metrics.ledger.projection_fold_duration.time():
            last_seq = _fold_into(projection, pending, delta, on_error=self._on_poison)

        new_seq = last_seq if delta else after
        # Advance the checkpoint forward-only; replacement is atomic so concurrent
        # readers never see a torn projection (worst case is a redundant re-fold).
        current = _INCREMENTAL_CACHE.get(key)
        if current is None or new_seq >= current.as_of_sequence:
            _INCREMENTAL_CACHE[key] = _Checkpoint(new_seq, projection, pending)
        return copy.deepcopy(projection)

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

        Uses the incremental projection — reconciliation runs on a fresh
        per-account session (committed reads), so the checkpoint is sound, and
        every cycle then folds only the events since the last one.
        """
        projection = await self.project_account_incremental(tenant_id, account_id)
        drifts = reconcile(projection, broker_positions)
        metrics.ledger.vs_broker_mismatch_dollars.set(float(_mismatch_dollars(projection, drifts)))
        if drifts:
            logger.warning(
                "ledger reconciliation drift on account %s: %s",
                account_id,
                [(d.symbol, d.kind.value, str(d.delta)) for d in drifts],
            )
        return drifts
