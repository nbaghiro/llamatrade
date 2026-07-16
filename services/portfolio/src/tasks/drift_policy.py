"""Drift policy: what reconciliation DOES about material ledger/broker drift.

The ledger is authoritative, so material drift always gets an action:

- ``MISSING_IN_LEDGER`` (broker holds something the ledger doesn't): an
  externally originated trade — attribute it to the **Unmanaged** sleeve via
  an ``EXTERNAL_TRADE_DETECTED`` event so the invariant heals. Priced at the
  broker's average entry (the only honest cost we have).
- ``MISSING_AT_BROKER`` / ``QTY_MISMATCH``: the ledger believes something the
  broker contradicts — never auto-corrected. **Freeze** every sleeve holding
  the symbol (orders on frozen sleeves are rejected by trading's risk check)
  and record a ``SLEEVE_FROZEN`` event for the audit trail; a human unfreezes
  after review.

``apply_drift_action`` is the unit-tested core; ``make_drift_handler`` binds it
to a session factory for the reconciliation loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.ledger import (
    Account,
    LedgerEventType,
    SleeveStatus,
    SleeveType,
)
from llamatrade_telemetry import metrics

from src.ledger.reconciliation import Drift, DriftKind

if TYPE_CHECKING:
    from src.ports import BrokerSnapshot, BrokerSnapshotProvider, LedgerStore, SleeveRepository

logger = logging.getLogger(__name__)

# Bounded retry for the broker snapshot during adoption: a transient broker
# hiccup shouldn't make us skip a real external trade for a whole pass.
_SNAPSHOT_ATTEMPTS = 3
_SNAPSHOT_BASE_DELAY = 0.5

# Drift kinds that contradict the ledger's own record → freeze, never correct.
_FREEZE_KINDS = {DriftKind.MISSING_AT_BROKER, DriftKind.QTY_MISMATCH}


def _drift_event_id(account_id: UUID, drift: Drift, kind: str) -> UUID:
    """Deterministic id so re-detecting the same drift never double-appends."""
    digest = hashlib.sha256(
        f"{account_id}:{kind}:{drift.symbol}:{drift.ledger_qty}:{drift.broker_qty}".encode()
    ).digest()
    return UUID(bytes=digest[:16])


async def apply_drift_action(
    *,
    repo: SleeveRepository,
    store: LedgerStore,
    broker: BrokerSnapshotProvider,
    account: Account,
    drift: Drift,
) -> str:
    """Apply the policy for one material drift; returns the action taken."""
    if drift.kind is DriftKind.MISSING_IN_LEDGER:
        return await _adopt_external_trade(repo, store, broker, account, drift)
    if drift.kind in _FREEZE_KINDS:
        return await _freeze_holding_sleeves(repo, store, account, drift)
    return "observed"


async def _snapshot_with_retry(
    broker: BrokerSnapshotProvider, account: Account
) -> BrokerSnapshot | None:
    """Fetch the broker snapshot with bounded exponential backoff.

    Returns None if it never succeeds — a transient broker outage shouldn't make
    us skip a real external trade; the next pass retries (detection is idempotent).
    """
    for attempt in range(_SNAPSHOT_ATTEMPTS):
        try:
            return await broker.snapshot(account.tenant_id, account)
        except Exception as e:  # broker faults are opaque; retry then defer
            if attempt == _SNAPSHOT_ATTEMPTS - 1:
                logger.warning(
                    "broker snapshot failed after %d attempts (account=%s): %s",
                    _SNAPSHOT_ATTEMPTS,
                    account.id,
                    e,
                )
                return None
            await asyncio.sleep(_SNAPSHOT_BASE_DELAY * (2**attempt))
    return None


async def _adopt_external_trade(
    repo: SleeveRepository,
    store: LedgerStore,
    broker: BrokerSnapshotProvider,
    account: Account,
    drift: Drift,
) -> str:
    """Attribute a broker-only holding to the Unmanaged sleeve."""
    unmanaged = await repo.get_sleeve_by_type(account.tenant_id, account.id, SleeveType.UNMANAGED)
    if unmanaged is None:
        logger.error(
            "no Unmanaged sleeve for account %s; cannot adopt %s", account.id, drift.symbol
        )
        return "skipped"

    snapshot = await _snapshot_with_retry(broker, account)
    if snapshot is None:
        # Broker unavailable after retries — leave the drift for the next pass
        # rather than guessing a price (the detection is idempotent).
        logger.warning(
            "broker snapshot unavailable for adoption of %s (account=%s); retry next pass",
            drift.symbol,
            account.id,
        )
        return "skipped"
    holding = next((h for h in snapshot.holdings if h.symbol == drift.symbol), None)
    if holding is None:
        # The position vanished between reconciliation and now — let the next
        # pass re-classify rather than guess a price.
        logger.warning("broker holding %s vanished before adoption; skipping", drift.symbol)
        return "skipped"

    await store.append(
        tenant_id=account.tenant_id,
        account_id=account.id,
        event_type=LedgerEventType.EXTERNAL_TRADE_DETECTED,
        data={
            "sleeve_id": str(unmanaged.id),
            "symbol": drift.symbol,
            "qty": str(drift.delta),  # broker − ledger: the unaccounted quantity
            "price": str(holding.avg_price),
        },
        sleeve_id=unmanaged.id,
        event_id=_drift_event_id(account.id, drift, "adopt"),
    )
    logger.warning(
        "adopted external trade into Unmanaged: account=%s symbol=%s qty=%s @ %s",
        account.id,
        drift.symbol,
        drift.delta,
        holding.avg_price,
    )
    return "adopted"


async def _freeze_holding_sleeves(
    repo: SleeveRepository,
    store: LedgerStore,
    account: Account,
    drift: Drift,
) -> str:
    """Freeze every active sleeve holding the drifted symbol (manual review)."""
    projection = await store.project_account(account.tenant_id, account.id)
    frozen = 0
    for sleeve in await repo.list_sleeves(account.tenant_id, account.id):
        position = projection.sleeve(str(sleeve.id)).positions.get(drift.symbol)
        if position is None or position.qty == 0:
            continue
        if sleeve.status == SleeveStatus.FROZEN.value:
            continue
        await repo.set_sleeve_status(sleeve, SleeveStatus.FROZEN.value)
        await store.append(
            tenant_id=account.tenant_id,
            account_id=account.id,
            event_type=LedgerEventType.SLEEVE_FROZEN,
            data={
                "sleeve_id": str(sleeve.id),
                "reason": f"{drift.kind}: {drift.symbol} ledger={drift.ledger_qty} "
                f"broker={drift.broker_qty}",
            },
            sleeve_id=sleeve.id,
            event_id=_drift_event_id(sleeve.id, drift, "freeze"),
        )
        metrics.ledger.sleeve_frozen()
        frozen += 1
        logger.critical(
            "froze sleeve %s (account=%s): %s drift on %s — manual review required",
            sleeve.id,
            account.id,
            drift.kind,
            drift.symbol,
        )
    return f"froze:{frozen}"


def make_drift_handler(session_factory: async_sessionmaker[AsyncSession]):
    """Bind the policy to a session factory for ``run_reconciliation_pass``.

    Each drift gets its own short transaction so one failed action never
    poisons the pass (the pass already isolates handler exceptions too).
    """
    from src.clients.alpaca import AlpacaBrokerPositions
    from src.repositories import SqlLedgerStore, SqlSleeveRepository

    async def handle(account: Account, drift: Drift) -> None:
        from src.metrics import record_drift_action

        async with tenant_session(account.tenant_id, session_factory) as db:
            action = await apply_drift_action(
                repo=SqlSleeveRepository(db),
                store=SqlLedgerStore(db),
                broker=AlpacaBrokerPositions(db),
                account=account,
                drift=drift,
            )
            await db.commit()
        record_drift_action(action)

    return handle
