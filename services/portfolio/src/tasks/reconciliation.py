"""Reconciliation task: keep the ledger aggregate matching broker truth.

Periodically compares each account's ledger projection against broker truth,
classifies any drift, and routes material drift to the drift policy (adopt
external trades into Unmanaged; freeze sleeves the broker contradicts).

``run_reconciliation_pass`` is the pure orchestration (one pass over a given set
of accounts) and is unit-tested with fakes; ``reconciliation_loop`` is the thin
scheduler that builds a DB session, loads accounts, and sleeps between passes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import bind_tenant_guc, system_session, tenant_session
from llamatrade_db.models.ledger import Account

from src.clients.alpaca import AlpacaBrokerPositions
from src.ledger.projector import LedgerProjector
from src.ledger.reconciliation import DriftKind
from src.ports import BrokerUnavailableError
from src.tasks.supervisor import LeadershipProbe

if TYPE_CHECKING:
    from src.ledger.reconciliation import Drift
    from src.ports import BrokerPositions

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300.0
# Per-account work fans out concurrently so a pass scales with concurrency, not account count; the per-account timeout keeps one slow broker from stalling the rest. Concurrency capped to respect the Alpaca rate limiter.
DEFAULT_CONCURRENCY = 8
DEFAULT_PER_ACCOUNT_TIMEOUT_SECONDS = 30.0
# An account is stale when no successful reconcile landed within this many intervals (skips and failures leave its clock running).
STALE_AFTER_INTERVALS = 3.0

# Cash drift is observed every pass (dividends/fees/interest legitimately move broker cash without a ledger event, so a single pass never acts); drift above this dollar threshold persisting this many consecutive passes freezes the account's sleeves and dispatches an incident (a strategy sizing against phantom free cash). No cause attribution.
CASH_DRIFT_FREEZE_DOLLARS = Decimal(os.getenv("LEDGER_CASH_DRIFT_FREEZE_DOLLARS", "1"))
CASH_DRIFT_FREEZE_PASSES = int(os.getenv("LEDGER_CASH_DRIFT_FREEZE_PASSES", "3"))

# Drift classifications that warrant an alert (vs. log-only noise).
MATERIAL_DRIFT_KINDS = {
    DriftKind.QTY_MISMATCH,
    DriftKind.MISSING_AT_BROKER,
    DriftKind.MISSING_IN_LEDGER,
}

# Called for each material drift: (account, drift). The default handler applies the drift policy; it can also be wired to the alert pathway.
MaterialDriftHandler = Callable[[Account, "Drift"], Awaitable[None]]


class ReconcilingProjector(Protocol):
    """The slice of ``LedgerProjector`` the pass needs."""

    async def reconcile_account(
        self,
        tenant_id: UUID,
        account_id: UUID,
        broker_positions: dict[str, Decimal],
        broker_cash: Decimal | None = None,
    ) -> tuple[list[Drift], Decimal | None]: ...


@dataclass(frozen=True)
class AccountReconResult:
    """Outcome of reconciling a single account during a pass."""

    account_id: UUID
    drifts: list[Drift]
    error: str | None = None
    skipped: bool = False  # broker truth unreadable this pass — not reconciled
    cash_drift: Decimal | None = None  # broker − ledger cash (None when unread)

    @property
    def ok(self) -> bool:
        return self.error is None and not self.drifts and not self.skipped


async def run_reconciliation_pass(
    *,
    projector: ReconcilingProjector,
    broker: BrokerPositions,
    accounts: list[Account],
    on_material_drift: MaterialDriftHandler | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    per_account_timeout: float = DEFAULT_PER_ACCOUNT_TIMEOUT_SECONDS,
) -> list[AccountReconResult]:
    """Reconcile accounts concurrently (bounded). A failure or timeout on one
    account never aborts the pass — it is captured on that account's result so
    the rest still run; results preserve account order.

    Material drifts (qty mismatch / missing either side) are logged at WARNING
    and forwarded to ``on_material_drift`` when wired; dust is debug-only. The
    semaphore caps in-flight broker reads so the pass scales with concurrency
    while respecting the broker rate limiter.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _reconcile_one(account: Account) -> AccountReconResult:
        async with sem:
            try:
                broker_positions = await asyncio.wait_for(
                    broker.positions(account.tenant_id, account), per_account_timeout
                )
                broker_cash = await _read_broker_cash(broker, account, per_account_timeout)
                drifts, cash_drift = await projector.reconcile_account(
                    account.tenant_id, account.id, broker_positions, broker_cash
                )
                await _surface_drifts(account, drifts, on_material_drift)
                return AccountReconResult(
                    account_id=account.id, drifts=drifts, cash_drift=cash_drift
                )
            except BrokerUnavailableError as e:
                # Broker truth is unreadable — skip (do NOT reconcile against an empty map, which would freeze every sleeve). Retry next pass.
                logger.info("skipping reconciliation for account %s: %s", account.id, e)
                return AccountReconResult(account_id=account.id, drifts=[], skipped=True)
            except TimeoutError:
                logger.warning("reconciliation timed out for account %s", account.id)
                return AccountReconResult(account_id=account.id, drifts=[], error="timeout")
            except Exception as e:  # isolate per-account failures
                logger.exception("reconciliation failed for account %s", account.id)
                return AccountReconResult(account_id=account.id, drifts=[], error=str(e))

    return list(await asyncio.gather(*(_reconcile_one(a) for a in accounts)))


def update_staleness(
    results: list[AccountReconResult],
    last_success: dict[UUID, float],
    *,
    interval_seconds: float,
    now: float,
) -> list[UUID]:
    """Fold one pass's results into per-account last-success times and publish the
    stale-accounts gauge, so an account that keeps skipping (e.g. broken
    credentials) can never stay silent.

    ``results`` must cover every account in the pass — accounts absent from it
    are treated as deleted and pruned. A first sighting starts the clock; only a
    successful reconcile (not skipped, no error) resets it. Stale account ids are
    logged by name since the gauge is an aggregate count (no per-account labels).
    Returns the stale account ids.
    """
    from src.metrics import set_reconcile_stale_accounts

    seen = {r.account_id for r in results}
    for account_id in [a for a in last_success if a not in seen]:
        del last_success[account_id]
    for result in results:
        if result.error is None and not result.skipped:
            last_success[result.account_id] = now
        else:
            last_success.setdefault(result.account_id, now)
    threshold = STALE_AFTER_INTERVALS * interval_seconds
    stale = [account_id for account_id, ts in last_success.items() if now - ts > threshold]
    set_reconcile_stale_accounts(len(stale))
    if stale:
        logger.warning(
            "reconciliation stale accounts (no successful reconcile in >%.0fs): %s",
            threshold,
            sorted(str(account_id) for account_id in stale),
        )
    return stale


def update_cash_drift_streaks(
    results: list[AccountReconResult],
    streaks: dict[UUID, int],
    *,
    threshold: Decimal,
    sustained_passes: int,
) -> list[UUID]:
    """Fold one pass's cash drifts into per-account streaks; return freeze candidates.

    A pass whose cash drift exceeds ``threshold`` (dollars) increments the
    account's streak; a pass at or below it resets the streak. A pass that could
    not read broker cash (``cash_drift is None`` — skip/error) leaves the streak
    unchanged, so a transient broker outage neither triggers nor clears it. When
    a streak reaches ``sustained_passes`` the account is returned as a freeze
    candidate and its streak reset (the freeze is idempotent; a still-persisting
    drift needs a human, not a re-freeze every pass). Accounts absent from
    ``results`` are pruned (treated as deleted).
    """
    seen = {r.account_id for r in results}
    for account_id in [a for a in streaks if a not in seen]:
        del streaks[account_id]
    candidates: list[UUID] = []
    for result in results:
        if result.cash_drift is None:
            continue
        if abs(result.cash_drift) > threshold:
            streaks[result.account_id] = streaks.get(result.account_id, 0) + 1
        else:
            streaks[result.account_id] = 0
        if streaks[result.account_id] >= sustained_passes:
            candidates.append(result.account_id)
            streaks[result.account_id] = 0
    return candidates


async def _freeze_sustained_cash_drift(
    results: list[AccountReconResult],
    accounts: list[Account],
    streaks: dict[UUID, int],
    freeze: Callable[[Account, Decimal], Awaitable[None]],
) -> None:  # pragma: no cover - thin orchestration over update_cash_drift_streaks
    """Freeze accounts whose cash drift has persisted past the sustained threshold."""
    candidates = update_cash_drift_streaks(
        results,
        streaks,
        threshold=CASH_DRIFT_FREEZE_DOLLARS,
        sustained_passes=CASH_DRIFT_FREEZE_PASSES,
    )
    if not candidates:
        return
    account_by_id = {a.id: a for a in accounts}
    drift_by_id = {r.account_id: r.cash_drift for r in results}
    for account_id in candidates:
        account = account_by_id.get(account_id)
        cash_drift = drift_by_id.get(account_id)
        if account is None or cash_drift is None:
            continue
        try:
            await freeze(account, cash_drift)
        except Exception:  # a freeze fault must not abort the pass
            logger.exception("cash-drift freeze failed (account=%s)", account_id)


async def _read_broker_cash(
    broker: BrokerPositions, account: Account, timeout: float
) -> Decimal | None:
    """Best-effort broker cash; None (skip cash reconciliation) on any failure — a
    cash-read hiccup must not drop the account's position reconciliation."""
    try:
        return await asyncio.wait_for(broker.cash(account.tenant_id, account), timeout)
    except Exception:
        logger.debug("broker cash read failed for account %s; skipping cash check", account.id)
        return None


async def _surface_drifts(
    account: Account,
    drifts: list[Drift],
    on_material_drift: MaterialDriftHandler | None,
) -> None:
    """Log every drift by severity and forward material ones to the handler.

    A handler failure is logged and never aborts the pass — alerting is
    best-effort, the reconciliation record itself is what matters.
    """
    from src.metrics import record_drift

    for drift in drifts:
        record_drift(str(drift.kind))
        if drift.kind not in MATERIAL_DRIFT_KINDS:
            logger.debug(
                "reconciliation dust: account=%s symbol=%s delta=%s",
                account.id,
                drift.symbol,
                drift.delta,
            )
            continue
        logger.warning(
            "reconciliation drift: account=%s symbol=%s kind=%s ledger=%s broker=%s",
            account.id,
            drift.symbol,
            drift.kind,
            drift.ledger_qty,
            drift.broker_qty,
        )
        if on_material_drift is not None:
            try:
                await on_material_drift(account, drift)
            except Exception:  # alerting is best-effort
                logger.exception(
                    "material-drift handler failed (account=%s symbol=%s)",
                    account.id,
                    drift.symbol,
                )


async def _load_accounts(db: AsyncSession) -> list[Account]:
    result = await db.scalars(select(Account))
    return list(result.all())


class _SessionPerCallProjector:
    """``ReconcilingProjector`` that opens a fresh session per call.

    The pass reconciles accounts concurrently, and an ``AsyncSession`` is not safe
    for concurrent use — so each account gets its own short-lived session.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def reconcile_account(
        self,
        tenant_id: UUID,
        account_id: UUID,
        broker_positions: dict[str, Decimal],
        broker_cash: Decimal | None = None,
    ) -> tuple[list[Drift], Decimal | None]:
        async with tenant_session(tenant_id, self._sf) as db:
            # The projector persists+commits the checkpoint mid-session, clearing the one-shot tenant GUC; bind it durably so post-commit reads stay tenant-scoped under the RLS role.
            bind_tenant_guc(db, tenant_id)
            return await LedgerProjector(db).reconcile_account(
                tenant_id, account_id, broker_positions, broker_cash
            )


class _SessionPerCallBroker:
    """``BrokerPositions`` that opens a fresh session per call (see above)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def positions(self, tenant_id: UUID, account: Account) -> dict[str, Decimal]:
        async with tenant_session(tenant_id, self._sf) as db:
            return await AlpacaBrokerPositions(db).positions(tenant_id, account)

    async def cash(self, tenant_id: UUID, account: Account) -> Decimal:
        async with tenant_session(tenant_id, self._sf) as db:
            return await AlpacaBrokerPositions(db).cash(tenant_id, account)


async def reconcile_accounts_once(
    session_factory: async_sessionmaker[AsyncSession],
    accounts: list[Account],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[AccountReconResult]:
    """Run one reconciliation pass over ``accounts`` (on-demand sync).

    Same session-per-account adapters and drift policy the background loop uses;
    safe to run concurrently with it (drift events are idempotent).
    """
    from src.tasks.drift_policy import make_drift_handler

    return await run_reconciliation_pass(
        projector=_SessionPerCallProjector(session_factory),
        broker=_SessionPerCallBroker(session_factory),
        accounts=accounts,
        on_material_drift=make_drift_handler(session_factory),
        concurrency=concurrency,
    )


async def reconciliation_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    stop_event: asyncio.Event,
    concurrency: int = DEFAULT_CONCURRENCY,
    is_leader: LeadershipProbe | None = None,
) -> None:  # pragma: no cover - scheduler shell, logic covered via run_reconciliation_pass
    """Run reconciliation passes until ``stop_event`` is set.

    Accounts are loaded in one session, then reconciled concurrently via
    session-per-account adapters. Material drifts are routed to the drift policy
    (adopt external trades into Unmanaged / freeze contradicted sleeves — see
    ``tasks/drift_policy.py``). The loop returns as soon as ``is_leader`` says
    this pod no longer holds the writer lock, so the caller can re-elect.
    """
    from src.tasks.drift_policy import make_cash_drift_freezer, make_drift_handler

    on_material_drift = make_drift_handler(session_factory)
    freeze_for_cash_drift = make_cash_drift_freezer(session_factory)
    projector = _SessionPerCallProjector(session_factory)
    broker = _SessionPerCallBroker(session_factory)
    last_success: dict[UUID, float] = {}
    cash_drift_streaks: dict[UUID, int] = {}
    logger.info("ledger reconciliation loop started (interval=%ss)", interval_seconds)
    while not stop_event.is_set():
        if is_leader is not None and not await is_leader():
            break
        try:
            async with system_session(session_factory, reason="reconciliation account sweep") as db:
                accounts = await _load_accounts(db)
            if accounts:
                results = await run_reconciliation_pass(
                    projector=projector,
                    broker=broker,
                    accounts=accounts,
                    on_material_drift=on_material_drift,
                    concurrency=concurrency,
                )
                update_staleness(
                    results,
                    last_success,
                    interval_seconds=interval_seconds,
                    now=time.monotonic(),
                )
                await _freeze_sustained_cash_drift(
                    results, accounts, cash_drift_streaks, freeze_for_cash_drift
                )
        except Exception:  # never let a bad pass kill the loop
            logger.exception("reconciliation pass errored")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
    logger.info("ledger reconciliation loop stopped")
