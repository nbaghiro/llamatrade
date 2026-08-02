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
import os
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_telemetry import metrics

from src.ledger import checkpoint_store
from src.ledger.projection import (
    AccountLotBook,
    AccountProjection,
    LedgerEventLike,
    Lot,
    ReservationState,
    copy_lot_book,
    fold,
    fold_into,
    fold_lots_into,
    holding_history,
)
from src.ledger.reconciliation import Drift, cash_drift, ledger_cash, reconcile
from src.ledger.writer import LedgerWriter

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")


@dataclass
class _Checkpoint:
    """A folded projection at a sequence, plus the reservation fold state
    (pending + terminal ids) and the per-(sleeve, symbol) FIFO lot book needed to
    resume both folds — together they are the full fold state, so a resumed fold
    equals a fold from zero."""

    as_of_sequence: int
    projection: AccountProjection
    reservations: ReservationState
    lots: AccountLotBook


# Process-level incremental-projection cache — the FIRST-level checkpoint cache
# (the persisted ``checkpoint_store`` rows are the second, surviving restarts).
# Populated ONLY from committed reads (a fresh read-only session): folding the
# delta since a checkpoint onto a deep copy of it equals a full fold by
# construction (shared ``fold_into`` + the split-invariance property test).
# In-transaction writers must NOT use the incremental path — a mid-transaction
# (uncommitted) read would seed a checkpoint with events that may roll back.
# Keyed by (tenant_id, account_id). Bounded LRU so a long-lived process can't
# retain a checkpoint per account forever; the least-recently-projected
# accounts fall out and simply re-fold.
_MAX_CACHED_ACCOUNTS = 2048
_INCREMENTAL_CACHE: OrderedDict[tuple[str, str], _Checkpoint] = OrderedDict()

# Cash reconciliation alerts above this |broker_cash − ledger_cash| ($): small drifts are rounding, material drift means a missing ledger event.
_CASH_DRIFT_ALERT_DOLLARS = Decimal("1")

# A checkpoint must never advance onto an event still inside this window. The
# ``sequence`` identity is assigned at INSERT but the row commits later, so
# commit order is not sequence order: a fill that takes a low sequence and holds
# its transaction open can commit AFTER a higher-sequence event a reconciliation
# pass already checkpointed past, and would then be folded once and never again.
# Advancing only past events older than the window makes that safe as long as no
# ledger write transaction outlives the window: ``idle_in_transaction_session_timeout``
# (enforced engine-wide in libs/db, 120s default) is the backstop that force-closes
# a stuck transaction, so the window must be >= that timeout for an event older
# than it to be guaranteed durably committed. The recent tail is re-folded each
# pass (cheap, bounded).
_CHECKPOINT_SAFETY_WINDOW = timedelta(
    seconds=float(os.getenv("LEDGER_CHECKPOINT_SAFETY_WINDOW_SECONDS", "120"))
)


def _partition_at_window(
    delta: list[LedgerEventLike], cutoff: datetime
) -> tuple[list[LedgerEventLike], list[LedgerEventLike]]:
    """Split ``delta`` (ledger order) into (safe-to-checkpoint, recent tail).

    An event is in the tail once its ``created_at`` is at or after ``cutoff``;
    everything from the first such event on is the tail, so the checkpoint never
    advances past a row that might still be committing out of order. A row with no
    ``created_at`` (a plain test event) is treated as safe. ``created_at`` is the
    transaction-start time (``func.now()``), not the commit time, so it does not
    rise monotonically with ``sequence``; the cut stays safe because an out-of-order
    commit only ever moves the cutoff EARLIER (a recent-``created_at`` row with a
    low sequence shrinks the safe prefix, re-folding more of the tail), never later
    into an in-flight row. Everything in the safe prefix is older than the window,
    which (per ``_CHECKPOINT_SAFETY_WINDOW``) exceeds the engine's
    ``idle_in_transaction_session_timeout``, so it is durably committed.
    """
    for index, event in enumerate(delta):
        created = getattr(event, "created_at", None)
        if created is not None and created >= cutoff:
            return delta[:index], delta[index:]
    return delta, []


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
        # High-sev: a skipped persisted event leaves this account's projection incomplete until fixed; the event stays recoverable by id and the ERROR log is the operator's pointer.
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
        self, tenant_id: UUID, account_id: UUID, *, persist: bool = True
    ) -> AccountProjection:
        """Project from the latest checkpoint + only the delta since it.

        Equivalent to :meth:`project_account` by construction (same ``fold_into``),
        but O(new events) instead of O(all events). The process-local LRU is the
        first-level checkpoint cache; on a miss (fresh process) the persisted
        checkpoint row seeds the fold, so a restart replays only the delta — an
        absent or unreadable row degrades to a full fold, never an error.

        With ``persist=True`` (the reconciliation loop): the checkpoint is
        advanced only past events older than :data:`_CHECKPOINT_SAFETY_WINDOW` and
        the recent tail is re-folded each pass, then persisted and COMMITTED (its
        only write on this path). This preserves replay-from-zero equivalence even
        though commit order is not sequence order.

        With ``persist=False`` (an in-transaction caller, e.g. the fill path):
        the whole delta is folded onto a copy of the committed checkpoint seed and
        returned; nothing is cached or persisted. The caller's session sees its own
        uncommitted writes in the delta read, so the returned projection is the
        full committed state plus the caller's pending event — safe because the
        seed is always a committed checkpoint behind the safety window.

        **Caller contract for ``persist=True``:** the session must read COMMITTED
        state (a fresh read-only session), or the checkpoint commit would also
        commit the caller's pending writes. Deep copies guard the shared cache
        from mutation/torn reads.
        """
        key = (str(tenant_id), str(account_id))
        from_cache = key in _INCREMENTAL_CACHE
        seed = await self._seed(tenant_id, account_id)

        after = seed.as_of_sequence if seed is not None else 0
        delta = cast(
            "list[LedgerEventLike]",
            await self._writer.read_account_events_since(tenant_id, account_id, after),
        )
        if seed is not None and from_cache and not delta:
            return seed.projection  # nothing new since the in-process checkpoint

        projection = seed.projection if seed is not None else AccountProjection()
        reservations = seed.reservations if seed is not None else ReservationState()
        lots = seed.lots if seed is not None else {}

        if not persist:
            # In-transaction read-only caller: fold the whole delta and return, never seeding the shared cache or committing from this session.
            with metrics.ledger.projection_fold_duration.time():
                fold_into(projection, reservations, delta, on_error=self._on_poison)
            return projection

        # Split the delta at the safety window: older events are durably committed and safe to checkpoint; the recent tail is re-folded each pass (rows may still commit out of sequence order).
        cutoff = datetime.now(UTC) - _CHECKPOINT_SAFETY_WINDOW
        safe, tail = _partition_at_window(delta, cutoff)
        with metrics.ledger.projection_fold_duration.time():
            safe_seq = fold_into(projection, reservations, safe, on_error=self._on_poison)
            # Advance the lot book over the SAME safe events so projection, reservations, and FIFO lots are all at ``checkpoint_seq``.
            fold_lots_into(lots, safe)
        checkpoint_seq = safe_seq if safe else after

        # Advance the checkpoint forward-only; replacement is atomic so concurrent readers never see a torn projection (worst case is a redundant re-fold).
        current = _INCREMENTAL_CACHE.get(key)
        if current is None or checkpoint_seq >= current.as_of_sequence:
            _INCREMENTAL_CACHE[key] = _Checkpoint(checkpoint_seq, projection, reservations, lots)
            _INCREMENTAL_CACHE.move_to_end(key)
            while len(_INCREMENTAL_CACHE) > _MAX_CACHED_ACCOUNTS:
                _INCREMENTAL_CACHE.popitem(last=False)
        # Persist only when the checkpoint advanced past its seed, and never a poisoned projection (a restart must re-fold to pick up a corrected event).
        if checkpoint_seq > after and projection.is_complete:
            await self._persist_checkpoint(
                tenant_id, account_id, checkpoint_seq, projection, reservations, lots
            )

        if not tail:
            return copy.deepcopy(projection)
        # Return the full projection: checkpoint state (at the safe sequence) plus the re-folded recent tail, on a private copy.
        ret_projection = copy.deepcopy(projection)
        ret_reservations = reservations.copy()
        with metrics.ledger.projection_fold_duration.time():
            fold_into(ret_projection, ret_reservations, tail, on_error=self._on_poison)
        return ret_projection

    async def open_lots_incremental(
        self, tenant_id: UUID, account_id: UUID, sleeve_id: UUID, symbol: str
    ) -> list[Lot]:
        """FIFO open lots for one (sleeve, symbol): the checkpoint lot book + the delta.

        The read-only counterpart of ``project_account_incremental(persist=False)``
        for the FIFO lot book. It seeds from the committed checkpoint (or a full
        fold on a cold cache / fresh account), folds the whole delta read in THIS
        session, and returns the requested slice — O(delta) rather than folding
        the account's full history on every basis-less sell. Never caches or
        commits (an in-transaction caller, e.g. the fill-ingestion path). Safe
        because the seed lot book is always a committed checkpoint behind the
        safety window; the delta re-reads everything since it.
        """
        seed = await self._seed(tenant_id, account_id)
        after = seed.as_of_sequence if seed is not None else 0
        delta = cast(
            "list[LedgerEventLike]",
            await self._writer.read_account_events_since(tenant_id, account_id, after),
        )
        book = seed.lots if seed is not None else {}
        with metrics.ledger.projection_fold_duration.time():
            fold_lots_into(book, delta)
        return book.get(str(sleeve_id), {}).get(symbol, [])

    async def _seed(self, tenant_id: UUID, account_id: UUID) -> _Checkpoint | None:
        """A private, mutation-safe fold seed from the in-process cache or the row.

        A cache hit is deep-copied (projection, reservations, and lot book) so a
        caller folding onto the seed never mutates the shared cache; a miss loads
        the persisted checkpoint (also a fresh object). Read-only for the caller.
        """
        cached = _INCREMENTAL_CACHE.get((str(tenant_id), str(account_id)))
        if cached is not None:
            return _Checkpoint(
                cached.as_of_sequence,
                copy.deepcopy(cached.projection),
                cached.reservations.copy(),
                copy_lot_book(cached.lots),
            )
        return await self._load_persisted_checkpoint(tenant_id, account_id)

    async def _load_persisted_checkpoint(
        self, tenant_id: UUID, account_id: UUID
    ) -> _Checkpoint | None:
        """Second-level (restart) checkpoint seed; absent or unreadable → None."""
        loaded = await checkpoint_store.load(self.db, tenant_id, account_id)
        if loaded is None:
            return None
        sequence, projection, reservations, lots = loaded
        return _Checkpoint(sequence, projection, reservations, lots)

    async def _persist_checkpoint(
        self,
        tenant_id: UUID,
        account_id: UUID,
        as_of_sequence: int,
        projection: AccountProjection,
        reservations: ReservationState,
        lots: AccountLotBook,
    ) -> None:
        """Persist the advanced checkpoint and commit it (best-effort).

        A failed persist costs a re-fold after the next restart, never the
        projection itself; the session is rolled back so it stays usable.
        """
        try:
            await checkpoint_store.save(
                self.db, tenant_id, account_id, as_of_sequence, projection, reservations, lots
            )
            await self.db.commit()
        except SQLAlchemyError:
            logger.warning(
                "failed to persist ledger projection checkpoint for account %s (seq=%s)",
                account_id,
                as_of_sequence,
                exc_info=True,
            )
            with suppress(SQLAlchemyError):
                await self.db.rollback()

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
        broker_cash: Decimal | None = None,
    ) -> tuple[list[Drift], Decimal | None]:
        """Shadow-compare the ledger aggregate against broker truth.

        Returns ``(position drifts, cash drift)``. The drift policy adopts
        external trades into Unmanaged and freezes sleeves the broker contradicts
        (see ``tasks/drift_policy.py``). When ``broker_cash`` is supplied, the
        ``Σ sleeve_cash == broker_cash`` invariant is also recorded (gauge +
        warning) and the ``broker − ledger`` cash drift is returned so the
        reconciliation loop can act on a sustained cash divergence; it is ``None``
        when broker cash was unreadable this pass.

        Uses the incremental projection — reconciliation runs on a fresh
        per-account session (committed reads), so the checkpoint is sound, and
        every cycle then folds only the events since the last one.
        """
        projection = await self.project_account_incremental(tenant_id, account_id)
        drifts = reconcile(projection, broker_positions)
        metrics.ledger.vs_broker_mismatch_dollars.set(float(_mismatch_dollars(projection, drifts)))
        cash_delta: Decimal | None = None
        if broker_cash is not None:
            cash_delta = cash_drift(projection, broker_cash)
            metrics.ledger.vs_broker_cash_mismatch_dollars.set(float(abs(cash_delta)))
            if abs(cash_delta) > _CASH_DRIFT_ALERT_DOLLARS:
                logger.warning(
                    "ledger cash reconciliation drift on account %s: broker=%s ledger=%s drift=%s",
                    account_id,
                    broker_cash,
                    ledger_cash(projection),
                    cash_delta,
                )
        if drifts:
            logger.warning(
                "ledger reconciliation drift on account %s: %s",
                account_id,
                [(d.symbol, d.kind.value, str(d.delta)) for d in drifts],
            )
        return drifts, cash_delta
