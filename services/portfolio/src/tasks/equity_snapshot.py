"""Equity-curve snapshot task.

Periodically marks every account + sleeve to market and writes a
``SleeveSnapshot`` row per sleeve. These rows ARE the equity-curve time series
the read layer serves: account/tenant performance groups them by
``as_of_sequence``; strategy performance reads the strategy sleeve's rows
directly. This is the sole equity-curve feed (no separate history tables).

``compute_snapshot_values`` is the pure, unit-tested core (projection + prices →
snapshot rows); ``snapshot_account`` persists them; ``snapshot_loop`` is the
thin scheduler. Decimals in the lots JSONB are stored as strings (JSONB is not
Decimal-aware).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import system_session, tenant_session
from llamatrade_db.models.ledger import (
    SNAPSHOT_DAY_EXPRESSION,
    Account,
    LedgerEvent,
    SleeveSnapshot,
)

from src.ledger.performance import account_pnl
from src.ledger.projection import AccountProjection
from src.ledger.projector import LedgerProjector
from src.ports import PriceProvider
from src.tasks.supervisor import LeadershipProbe

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_INTERVAL_SECONDS = 3600.0


@dataclass(frozen=True)
class SnapshotValue:
    """Pure, persistence-ready snapshot of one sleeve at a sequence."""

    sleeve_id: str
    as_of_sequence: int
    cash_balance: Decimal
    reserved_cash: Decimal
    equity: Decimal
    lots: list[dict[str, str]] = field(default_factory=list)


def projection_symbols(projection: AccountProjection) -> list[str]:
    """Every symbol held by any sleeve (for a single price fetch)."""
    return sorted({sym for s in projection.sleeves.values() for sym in s.positions})


def compute_snapshot_values(
    projection: AccountProjection,
    prices: dict[str, Decimal],
    sequence: int,
) -> list[SnapshotValue]:
    """Mark each sleeve to market into a persistence-ready snapshot list.

    Empty sleeves (no cash, no positions) are skipped. A sleeve holding a symbol
    with no price is also skipped: persisting a cost-valued point during a
    market-data gap permanently distorts the immutable equity curve.
    """
    out: list[SnapshotValue] = []
    for pnl in account_pnl(projection, prices):
        sleeve = projection.sleeves[pnl.sleeve_id]
        if pnl.equity == Decimal("0") and not sleeve.positions:
            continue
        held = {sym for sym, pos in sleeve.positions.items() if pos.qty != Decimal("0")}
        if held - prices.keys():
            continue
        lots = [
            {"symbol": sym, "qty": str(pos.qty), "cost_basis": str(pos.cost_basis)}
            for sym, pos in sorted(sleeve.positions.items())
            if pos.qty != Decimal("0")
        ]
        out.append(
            SnapshotValue(
                sleeve_id=pnl.sleeve_id,
                as_of_sequence=sequence,
                cash_balance=sleeve.cash,
                reserved_cash=sleeve.reserved,
                equity=pnl.equity,
                lots=lots,
            )
        )
    return out


async def _latest_sequence(db: AsyncSession, account_id: UUID) -> int:
    """Highest event sequence for the account (0 if it has no events yet)."""
    seq = await db.scalar(
        select(func.max(LedgerEvent.sequence)).where(LedgerEvent.account_id == account_id)
    )
    return int(seq) if seq is not None else 0


async def _add_snapshot_rows(
    db: AsyncSession, tenant_id: UUID, values: list[SnapshotValue]
) -> None:
    """Insert one ``SleeveSnapshot`` per computed value. The caller commits.

    ``(sleeve_id, as_of_sequence, UTC day)`` is unique: a repeat within a day at
    one ledger sequence — a re-mark, a re-run, a leader fenced a moment too late —
    is not a second curve point but a fresher mark of the same one. On conflict
    the row is UPDATED when the incoming ``created_at`` is newer, so the day's
    LAST mark wins (equity-curve freshness) rather than the first.
    """
    if not values:
        return
    now = datetime.now(UTC)
    rows = [
        {
            "tenant_id": tenant_id,
            "sleeve_id": UUID(v.sleeve_id),
            "as_of_sequence": v.as_of_sequence,
            "cash_balance": v.cash_balance,
            "reserved_cash": v.reserved_cash,
            "equity": v.equity,
            "lots": v.lots,
            "created_at": now,
        }
        for v in values
    ]
    stmt = pg_insert(SleeveSnapshot).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            SleeveSnapshot.sleeve_id,
            SleeveSnapshot.as_of_sequence,
            text(SNAPSHOT_DAY_EXPRESSION),
        ],
        set_={
            "cash_balance": stmt.excluded.cash_balance,
            "reserved_cash": stmt.excluded.reserved_cash,
            "equity": stmt.excluded.equity,
            "lots": stmt.excluded.lots,
            "created_at": stmt.excluded.created_at,
            "updated_at": func.now(),
        },
        where=SleeveSnapshot.created_at < stmt.excluded.created_at,
    )
    await db.execute(stmt)


async def snapshot_account(
    db: AsyncSession,
    projector: LedgerProjector,
    prices_provider: PriceProvider,
    account: Account,
) -> int:
    """Project the account, mark to market, and persist sleeve snapshots.

    Returns the number of snapshot rows written. The caller commits.
    """
    projection = await projector.project_account(account.tenant_id, account.id)
    symbols = projection_symbols(projection)
    prices: dict[str, Decimal] = {}
    if symbols:
        try:
            prices = await prices_provider.get_prices(symbols)
        except Exception:
            logger.exception("equity snapshot price fetch failed for account %s", account.id)
    sequence = await _latest_sequence(db, account.id)
    values = compute_snapshot_values(projection, prices, sequence)
    await _add_snapshot_rows(db, account.tenant_id, values)
    return len(values)


async def run_snapshot_pass(
    session_factory: async_sessionmaker[AsyncSession],
    prices_provider: PriceProvider,
    *,
    is_leader: LeadershipProbe | None = None,
) -> int:
    """One snapshot pass over all accounts, fetching prices in a SINGLE batch.

    Projects every account, unions their held symbols, and fetches all prices in
    one ``get_prices`` call (vs. one per account); then persists each account's
    sleeve snapshots in its own transaction so one failure is isolated. Returns
    the total rows written.

    ``is_leader`` fences the write half: leadership is re-checked immediately
    before the first commit, after the read-and-price phase that dominates the
    pass, so a leader torn mid-pass abandons its writes instead of duplicating
    the successor's.
    """
    plans: list[tuple[Account, AccountProjection, int]] = []
    symbols: set[str] = set()
    # Cross-tenant sweep: enumerate + project every account under the RLS bypass.
    async with system_session(session_factory, reason="equity snapshot pass") as db:
        projector = LedgerProjector(db)
        for account in await _load_accounts(db):
            try:
                projection = await projector.project_account(account.tenant_id, account.id)
                sequence = await _latest_sequence(db, account.id)
            except Exception:
                logger.exception("equity snapshot projection failed for account %s", account.id)
                continue
            plans.append((account, projection, sequence))
            symbols.update(projection_symbols(projection))

    try:
        prices = await prices_provider.get_prices(sorted(symbols)) if symbols else {}
    except Exception:
        logger.exception("equity snapshot price fetch failed; skipping priced sleeves this pass")
        prices = {}

    if is_leader is not None and not await is_leader():
        logger.warning("no longer the ledger writer; discarding this equity-snapshot pass")
        return 0

    total = 0
    for account, projection, sequence in plans:
        values = compute_snapshot_values(projection, prices, sequence)
        if not values:
            continue
        async with tenant_session(account.tenant_id, session_factory) as db:
            try:
                await _add_snapshot_rows(db, account.tenant_id, values)
                await db.commit()
                total += len(values)
            except Exception:
                await db.rollback()
                logger.exception("equity snapshot persist failed for account %s", account.id)
    return total


async def _load_accounts(db: AsyncSession) -> list[Account]:
    result = await db.scalars(select(Account))
    return list(result.all())


async def snapshot_loop(
    session_factory: async_sessionmaker[AsyncSession],
    prices_provider: PriceProvider,
    *,
    stop_event: asyncio.Event,
    interval_seconds: float = DEFAULT_SNAPSHOT_INTERVAL_SECONDS,
    is_leader: LeadershipProbe | None = None,
) -> None:  # pragma: no cover - scheduler shell, logic covered via snapshot_account
    """Write equity snapshots for every account until ``stop_event`` is set.

    Each account gets its own short transaction so one failure never aborts the
    pass; a bad pass never kills the loop. The loop returns as soon as
    ``is_leader`` says this pod no longer holds the writer lock, so the caller
    can re-enter election instead of sweeping against the new leader.
    """
    logger.info("ledger equity-snapshot loop started (interval=%ss)", interval_seconds)
    while not stop_event.is_set():
        if is_leader is not None and not await is_leader():
            break
        try:
            n = await run_snapshot_pass(session_factory, prices_provider, is_leader=is_leader)
            logger.debug("equity-snapshot pass wrote %d rows", n)
        except Exception:
            logger.exception("equity-snapshot pass errored")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
    logger.info("ledger equity-snapshot loop stopped")
