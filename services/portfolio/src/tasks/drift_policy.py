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
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.ledger import (
    Account,
    LedgerEventType,
    SleeveStatus,
    SleeveType,
)
from llamatrade_db.models.trading import Order
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_REJECTED,
)
from llamatrade_telemetry import metrics

from src.alerts import LedgerIncident
from src.ledger.ids import deterministic_event_id
from src.ledger.reconciliation import Drift, DriftKind

if TYPE_CHECKING:
    from src.ports import BrokerSnapshot, BrokerSnapshotProvider, LedgerStore, SleeveRepository

logger = logging.getLogger(__name__)

# Bounded retry for the broker snapshot during adoption: a transient broker hiccup shouldn't skip a real external trade for a whole pass.
_SNAPSHOT_ATTEMPTS = 3
_SNAPSHOT_BASE_DELAY = 0.5

# Drift kinds that contradict the ledger's own record → freeze, never correct.
_FREEZE_KINDS = {DriftKind.MISSING_AT_BROKER, DriftKind.QTY_MISMATCH}

_TERMINAL_ORDER_STATUSES = (
    ORDER_STATUS_FILLED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_EXPIRED,
)
# A terminal order this recent may have a fill still in flight to the ledger.
_RECENT_TERMINAL_WINDOW = timedelta(minutes=10)


class OrderActivityLookup(Protocol):
    """Reads recent order activity for (account, symbol) — the adoption guard."""

    async def has_recent_activity(self, tenant_id: UUID, account_id: UUID, symbol: str) -> bool: ...


class AlertSink(Protocol):
    """Dispatches ledger incidents (see ``src.alerts``); implementations never raise."""

    async def dispatch(self, tenant_id: UUID, incident: LedgerIncident) -> None: ...


class SqlOrderActivityLookup:
    """``OrderActivityLookup`` over the shared orders table."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def has_recent_activity(self, tenant_id: UUID, account_id: UUID, symbol: str) -> bool:
        cutoff = datetime.now(UTC) - _RECENT_TERMINAL_WINDOW
        stmt = (
            select(Order.id)
            .where(Order.tenant_id == tenant_id)
            .where(Order.account_id == account_id)
            .where(Order.symbol == symbol)
            .where(
                or_(
                    Order.status.not_in(_TERMINAL_ORDER_STATUSES),
                    Order.updated_at >= cutoff,
                )
            )
            .limit(1)
        )
        return await self._db.scalar(stmt) is not None


_QTY_SCALE = Decimal("0.00000001")


def _q(value: Decimal) -> str:
    """Scale-normalized quantity, so ``20`` and ``20.0`` key identically."""
    return str(value.quantize(_QTY_SCALE))


def _drift_event_id(account_id: UUID, drift: Drift, kind: str, *, on_date: date) -> UUID:
    """Deterministic id so a drift re-detected within one pass day never double-appends.

    Quantities are quantized (``"20"`` and ``"20.0"`` must not key twice) and the
    pass date is part of the key, so a genuinely recurring identical drift on a
    later day books again rather than being swallowed forever.
    """
    key = (
        f"{account_id}:{kind}:{drift.symbol}:"
        f"{_q(drift.ledger_qty)}:{_q(drift.broker_qty)}:{on_date.isoformat()}"
    )
    return deterministic_event_id(key)


async def apply_drift_action(
    *,
    repo: SleeveRepository,
    store: LedgerStore,
    broker: BrokerSnapshotProvider,
    account: Account,
    drift: Drift,
    orders: OrderActivityLookup | None = None,
    alerts: AlertSink | None = None,
) -> str:
    """Apply the policy for one material drift; returns the action taken."""
    if drift.kind is DriftKind.MISSING_IN_LEDGER:
        return await _adopt_external_trade(repo, store, broker, account, drift, orders, alerts)
    if drift.kind in _FREEZE_KINDS:
        return await _freeze_holding_sleeves(repo, store, account, drift, alerts)
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
    orders: OrderActivityLookup | None,
    alerts: AlertSink | None = None,
) -> str:
    """Attribute a broker-only holding to the Unmanaged sleeve."""
    if orders is not None and await orders.has_recent_activity(
        account.tenant_id, account.id, drift.symbol
    ):
        # An in-flight (or just-terminal) order's fill may not be folded yet; adopting now would double-count once the fill lands. Retry next pass.
        logger.info(
            "deferring adoption of %s (account=%s): recent order activity",
            drift.symbol,
            account.id,
        )
        return "deferred"
    unmanaged = await repo.get_sleeve_by_type(account.tenant_id, account.id, SleeveType.UNMANAGED)
    if unmanaged is None:
        logger.error(
            "no Unmanaged sleeve for account %s; cannot adopt %s", account.id, drift.symbol
        )
        return "skipped"

    snapshot = await _snapshot_with_retry(broker, account)
    if snapshot is None:
        # Broker unavailable after retries — leave the drift for the next pass rather than guessing a price (detection is idempotent).
        logger.warning(
            "broker snapshot unavailable for adoption of %s (account=%s); retry next pass",
            drift.symbol,
            account.id,
        )
        return "skipped"
    holding = next((h for h in snapshot.holdings if h.symbol == drift.symbol), None)
    if holding is None:
        # The position vanished between reconciliation and now — let the next pass re-classify rather than guess a price.
        logger.warning("broker holding %s vanished before adoption; skipping", drift.symbol)
        return "skipped"

    _event, inserted = await store.append(
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
        event_id=_drift_event_id(account.id, drift, "adopt", on_date=datetime.now(UTC).date()),
    )
    if not inserted:
        # A drift with these exact quantities was already adopted this pass day (deterministic id deduped it); report the no-op so telemetry isn't counting a fresh adoption.
        logger.info(
            "external-trade adoption deduped (already booked this pass): account=%s symbol=%s",
            account.id,
            drift.symbol,
        )
        return "deduped"
    logger.warning(
        "adopted external trade into Unmanaged: account=%s symbol=%s qty=%s @ %s",
        account.id,
        drift.symbol,
        drift.delta,
        holding.avg_price,
    )
    if alerts is not None:
        await alerts.dispatch(
            account.tenant_id,
            LedgerIncident(
                kind="external_trade_adopted",
                message=f"{drift.delta} {drift.symbol} adopted at {holding.avg_price}",
                context={
                    "account_id": str(account.id),
                    "symbol": drift.symbol,
                    "qty": str(drift.delta),
                    "price": str(holding.avg_price),
                },
            ),
        )
    return "adopted"


async def _freeze_holding_sleeves(
    repo: SleeveRepository,
    store: LedgerStore,
    account: Account,
    drift: Drift,
    alerts: AlertSink | None,
) -> str:
    """Freeze every active sleeve holding the drifted symbol (manual review)."""
    projection = await store.project_account(account.tenant_id, account.id)
    reason = f"{drift.kind}: {drift.symbol} ledger={drift.ledger_qty} broker={drift.broker_qty}"
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
                "reason": reason,
            },
            sleeve_id=sleeve.id,
            event_id=_drift_event_id(sleeve.id, drift, "freeze", on_date=datetime.now(UTC).date()),
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
        if alerts is not None:
            await _dispatch_freeze_alert(alerts, account, sleeve.id, drift, reason)
    return f"froze:{frozen}"


async def _dispatch_freeze_alert(
    alerts: AlertSink,
    account: Account,
    sleeve_id: UUID,
    drift: Drift,
    reason: str,
) -> None:
    """Best-effort webhook alert for a freeze; a sink fault never blocks the policy."""
    try:
        await alerts.dispatch(
            account.tenant_id,
            LedgerIncident(
                kind="sleeve_frozen",
                message=f"Sleeve {sleeve_id} frozen: {reason}. Trading on it is halted.",
                context={
                    "sleeve_id": str(sleeve_id),
                    "account_id": str(account.id),
                    "symbol": drift.symbol,
                    "drift_kind": str(drift.kind),
                    "ledger_qty": str(drift.ledger_qty),
                    "broker_qty": str(drift.broker_qty),
                },
            ),
        )
    except Exception:
        logger.exception("sleeve-freeze alert dispatch failed (sleeve=%s)", sleeve_id)


def _cash_freeze_event_id(sleeve_id: UUID, on_date: date) -> UUID:
    """Deterministic id for a cash-drift sleeve freeze (idempotent within a day)."""
    return deterministic_event_id(f"{sleeve_id}:cash_drift_freeze:{on_date.isoformat()}")


async def freeze_account_for_cash_drift(
    *,
    repo: SleeveRepository,
    store: LedgerStore,
    account: Account,
    cash_drift: Decimal,
    alerts: AlertSink | None = None,
) -> int:
    """Freeze every active sleeve on an account after sustained cash drift.

    Cash drift carries no symbol to attribute, so the whole account is halted:
    every strategy sizing against a wrong free-cash figure is stopped until an
    operator reconciles. Reuses the position-drift freeze machinery (status flip,
    ``SLEEVE_FROZEN`` audit event, alert). Idempotent within a pass day via the
    deterministic freeze event id; an already-frozen sleeve is left alone.
    """
    on_date = datetime.now(UTC).date()
    reason = f"sustained cash drift: broker − ledger = {cash_drift}"
    frozen = 0
    for sleeve in await repo.list_sleeves(account.tenant_id, account.id):
        if sleeve.status == SleeveStatus.FROZEN.value:
            continue
        await repo.set_sleeve_status(sleeve, SleeveStatus.FROZEN.value)
        await store.append(
            tenant_id=account.tenant_id,
            account_id=account.id,
            event_type=LedgerEventType.SLEEVE_FROZEN,
            data={"sleeve_id": str(sleeve.id), "reason": reason},
            sleeve_id=sleeve.id,
            event_id=_cash_freeze_event_id(sleeve.id, on_date),
        )
        metrics.ledger.sleeve_frozen()
        frozen += 1
        logger.critical(
            "froze sleeve %s (account=%s): sustained cash drift %s — manual review required",
            sleeve.id,
            account.id,
            cash_drift,
        )
    if frozen and alerts is not None:
        await _dispatch_cash_drift_alert(alerts, account, cash_drift, reason)
    return frozen


async def _dispatch_cash_drift_alert(
    alerts: AlertSink, account: Account, cash_drift: Decimal, reason: str
) -> None:
    """Best-effort webhook alert for a cash-drift freeze; a sink fault never blocks it."""
    try:
        await alerts.dispatch(
            account.tenant_id,
            LedgerIncident(
                kind="sleeve_frozen",
                message=(
                    f"Account {account.id} sleeves frozen: {reason}. Trading is halted "
                    "until the cash discrepancy is reconciled."
                ),
                context={"account_id": str(account.id), "cash_drift": str(cash_drift)},
            ),
        )
    except Exception:
        logger.exception("cash-drift freeze alert dispatch failed (account=%s)", account.id)


def make_cash_drift_freezer(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[Account, Decimal], Awaitable[None]]:
    """Bind :func:`freeze_account_for_cash_drift` to a session factory for the loop."""
    from src.alerts import LedgerAlertDispatcher
    from src.repositories import SqlLedgerStore, SqlSleeveRepository

    alerts = LedgerAlertDispatcher()

    async def freeze(account: Account, cash_drift: Decimal) -> None:
        async with tenant_session(account.tenant_id, session_factory) as db:
            await freeze_account_for_cash_drift(
                repo=SqlSleeveRepository(db),
                store=SqlLedgerStore(db),
                account=account,
                cash_drift=cash_drift,
                alerts=alerts,
            )
            await db.commit()

    return freeze


def make_drift_handler(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[Account, Drift], Awaitable[None]]:
    """Bind the policy to a session factory for ``run_reconciliation_pass``.

    Each drift gets its own short transaction so one failed action never
    poisons the pass (the pass already isolates handler exceptions too).
    """
    from src.alerts import LedgerAlertDispatcher
    from src.clients.alpaca import AlpacaBrokerPositions
    from src.repositories import SqlLedgerStore, SqlSleeveRepository

    alerts = LedgerAlertDispatcher()

    async def handle(account: Account, drift: Drift) -> None:
        from src.metrics import record_drift_action

        async with tenant_session(account.tenant_id, session_factory) as db:
            action = await apply_drift_action(
                repo=SqlSleeveRepository(db),
                store=SqlLedgerStore(db),
                broker=AlpacaBrokerPositions(db),
                account=account,
                drift=drift,
                orders=SqlOrderActivityLookup(db),
                alerts=alerts,
            )
            await db.commit()
        record_drift_action(action)

    return handle
