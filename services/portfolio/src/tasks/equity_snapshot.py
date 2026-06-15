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
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db.models.ledger import Account, LedgerEvent, SleeveSnapshot

from src.ledger.performance import account_pnl
from src.ledger.projection import AccountProjection
from src.ledger.projector import LedgerProjector
from src.ports import PriceProvider

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

    Positions without a price are valued at cost (see ``sleeve_pnl``). Empty
    sleeves (no cash, no positions) are skipped — nothing to chart.
    """
    out: list[SnapshotValue] = []
    for pnl in account_pnl(projection, prices):
        sleeve = projection.sleeves[pnl.sleeve_id]
        if pnl.equity == Decimal("0") and not sleeve.positions:
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
        prices = await prices_provider.get_prices(symbols)
    sequence = await _latest_sequence(db, account.id)
    values = compute_snapshot_values(projection, prices, sequence)
    for v in values:
        db.add(
            SleeveSnapshot(
                tenant_id=account.tenant_id,
                sleeve_id=UUID(v.sleeve_id),
                as_of_sequence=v.as_of_sequence,
                cash_balance=v.cash_balance,
                reserved_cash=v.reserved_cash,
                equity=v.equity,
                lots=v.lots,
            )
        )
    return len(values)


async def _load_accounts(db: AsyncSession) -> list[Account]:
    result = await db.scalars(select(Account))
    return list(result.all())


async def snapshot_loop(
    session_factory: async_sessionmaker[AsyncSession],
    prices_provider: PriceProvider,
    *,
    stop_event: asyncio.Event,
    interval_seconds: float = DEFAULT_SNAPSHOT_INTERVAL_SECONDS,
) -> None:  # pragma: no cover - scheduler shell, logic covered via snapshot_account
    """Write equity snapshots for every account until ``stop_event`` is set.

    Each account gets its own short transaction so one failure never aborts the
    pass; a bad pass never kills the loop.
    """
    logger.info("ledger equity-snapshot loop started (interval=%ss)", interval_seconds)
    while not stop_event.is_set():
        try:
            async with session_factory() as db:
                accounts = await _load_accounts(db)
                for account in accounts:
                    try:
                        n = await snapshot_account(
                            db, LedgerProjector(db), prices_provider, account
                        )
                        await db.commit()
                        logger.debug("equity snapshot: account=%s rows=%d", account.id, n)
                    except Exception:
                        await db.rollback()
                        logger.exception("equity snapshot failed for account %s", account.id)
        except Exception:
            logger.exception("equity-snapshot pass errored")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
    logger.info("ledger equity-snapshot loop stopped")
