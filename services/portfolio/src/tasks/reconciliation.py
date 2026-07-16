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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import system_session, tenant_session
from llamatrade_db.models.ledger import Account

from src.clients.alpaca import AlpacaBrokerPositions
from src.ledger.projector import LedgerProjector
from src.ledger.reconciliation import DriftKind
from src.ports import BrokerUnavailableError

if TYPE_CHECKING:
    from src.ledger.reconciliation import Drift
    from src.ports import BrokerPositions

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 300.0
# Per-account work fans out concurrently so a pass scales with concurrency, not
# account count; the per-account timeout keeps one slow broker from stalling the
# rest. Concurrency is capped to respect the Alpaca rate limiter in the lib.
DEFAULT_CONCURRENCY = 8
DEFAULT_PER_ACCOUNT_TIMEOUT_SECONDS = 30.0

# Drift classifications that warrant an alert (vs. log-only noise).
MATERIAL_DRIFT_KINDS = {
    DriftKind.QTY_MISMATCH,
    DriftKind.MISSING_AT_BROKER,
    DriftKind.MISSING_IN_LEDGER,
}

# Called for each material drift: (account, drift). The default handler applies
# the drift policy; it can also be wired to the alert pathway (webhooks /
# notification service).
MaterialDriftHandler = Callable[[Account, "Drift"], Awaitable[None]]


class ReconcilingProjector(Protocol):
    """The slice of ``LedgerProjector`` the pass needs."""

    async def reconcile_account(
        self, tenant_id: UUID, account_id: UUID, broker_positions: dict[str, Decimal]
    ) -> list[Drift]: ...


@dataclass(frozen=True)
class AccountReconResult:
    """Outcome of reconciling a single account during a pass."""

    account_id: UUID
    drifts: list[Drift]
    error: str | None = None
    skipped: bool = False  # broker truth unreadable this pass — not reconciled

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
                drifts = await projector.reconcile_account(
                    account.tenant_id, account.id, broker_positions
                )
                await _surface_drifts(account, drifts, on_material_drift)
                return AccountReconResult(account_id=account.id, drifts=drifts)
            except BrokerUnavailableError as e:
                # Broker truth is unreadable — skip (do NOT reconcile against an
                # empty map, which would freeze every sleeve). Retry next pass.
                logger.info("skipping reconciliation for account %s: %s", account.id, e)
                return AccountReconResult(account_id=account.id, drifts=[], skipped=True)
            except TimeoutError:
                logger.warning("reconciliation timed out for account %s", account.id)
                return AccountReconResult(account_id=account.id, drifts=[], error="timeout")
            except Exception as e:  # isolate per-account failures
                logger.exception("reconciliation failed for account %s", account.id)
                return AccountReconResult(account_id=account.id, drifts=[], error=str(e))

    return list(await asyncio.gather(*(_reconcile_one(a) for a in accounts)))


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
        self, tenant_id: UUID, account_id: UUID, broker_positions: dict[str, Decimal]
    ) -> list[Drift]:
        async with tenant_session(tenant_id, self._sf) as db:
            return await LedgerProjector(db).reconcile_account(
                tenant_id, account_id, broker_positions
            )


class _SessionPerCallBroker:
    """``BrokerPositions`` that opens a fresh session per call (see above)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def positions(self, tenant_id: UUID, account: Account) -> dict[str, Decimal]:
        async with tenant_session(tenant_id, self._sf) as db:
            return await AlpacaBrokerPositions(db).positions(tenant_id, account)


async def reconciliation_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    stop_event: asyncio.Event,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> None:  # pragma: no cover - scheduler shell, logic covered via run_reconciliation_pass
    """Run reconciliation passes until ``stop_event`` is set.

    Accounts are loaded in one session, then reconciled concurrently via
    session-per-account adapters. Material drifts are routed to the drift policy
    (adopt external trades into Unmanaged / freeze contradicted sleeves — see
    ``tasks/drift_policy.py``).
    """
    from src.tasks.drift_policy import make_drift_handler

    on_material_drift = make_drift_handler(session_factory)
    projector = _SessionPerCallProjector(session_factory)
    broker = _SessionPerCallBroker(session_factory)
    logger.info("ledger reconciliation loop started (interval=%ss)", interval_seconds)
    while not stop_event.is_set():
        try:
            async with system_session(session_factory) as db:
                accounts = await _load_accounts(db)
            if accounts:
                await run_reconciliation_pass(
                    projector=projector,
                    broker=broker,
                    accounts=accounts,
                    on_material_drift=on_material_drift,
                    concurrency=concurrency,
                )
        except Exception:  # never let a bad pass kill the loop
            logger.exception("reconciliation pass errored")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
    logger.info("ledger reconciliation loop stopped")
