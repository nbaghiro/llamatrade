"""The leader-elected market-condition loop: tail live bars, fire price alerts.

One pod holds a Postgres advisory lock and tails ``lt.market.bars.1m``,
filtered to the symbols of active market alerts (set refreshed periodically,
cross-tenant). Replicas without the lock poll for it, so failover is
automatic; the deterministic trigger id makes a torn-leader overlap harmless.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from llamatrade_db import system_session
from llamatrade_db.advisory import advisory_unlock, try_advisory_lock
from llamatrade_db.models.notification import Alert
from llamatrade_events.catalog.bars import Bar, BarEvents
from llamatrade_proto.generated import notification_pb2

from src.alerts.engine import (
    MARKET_CONDITION_TYPES,
    SymbolWindow,
    alert_is_live,
    evaluate_market,
    trigger_alert,
)
from src.pipeline import Dispatcher

logger = logging.getLogger(__name__)

_C = notification_pb2

# Stable advisory-lock key for the single market-evaluation leader.
MARKET_LOOP_LOCK_KEY = 0x6E6F7469  # "noti"

SYMBOL_REFRESH_SECONDS = 30.0
LEADERSHIP_RETRY_SECONDS = 15.0


async def try_acquire_leadership(engine: AsyncEngine) -> AsyncConnection | None:
    """Take the market-loop advisory lock on a dedicated connection, or None.

    Session-level lock semantics (see llamatrade_db.advisory): the holder keeps
    this connection and must release via :func:`release_leadership` — handing a
    pooled connection back still holds the lock. A dead backend releases it
    server-side, which is the crash-failover path.
    """
    conn = await engine.connect()
    if await try_advisory_lock(conn, MARKET_LOOP_LOCK_KEY):
        return conn
    await conn.close()
    return None


async def release_leadership(conn: AsyncConnection) -> None:
    await advisory_unlock(conn, MARKET_LOOP_LOCK_KEY)
    await conn.close()


async def active_market_alerts(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, list[tuple[UUID, UUID]]]:
    """Symbol -> [(alert_id, tenant_id)] for live market alerts, cross-tenant."""
    now = datetime.now(UTC)
    by_symbol: dict[str, list[tuple[UUID, UUID]]] = defaultdict(list)
    async with system_session(
        session_factory, reason="notification market-alert symbol sweep"
    ) as db:
        rows = await db.scalars(
            select(Alert).where(
                Alert.status == _C.ALERT_STATUS_ACTIVE,
                Alert.alert_type.in_(list(MARKET_CONDITION_TYPES)),
                Alert.symbol.is_not(None),
            )
        )
        for alert in rows:
            if alert.symbol and alert_is_live(alert, now):
                by_symbol[alert.symbol].append((alert.id, alert.tenant_id))
    return dict(by_symbol)


async def run_market_loop(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    dispatcher: Dispatcher,
    *,
    bars: BarEvents | None = None,
    stop_event: asyncio.Event,
) -> None:
    """Acquire leadership, then evaluate market alerts against the bar tail."""
    lock_conn: AsyncConnection | None = None
    while not stop_event.is_set() and lock_conn is None:
        lock_conn = await try_acquire_leadership(engine)
        if lock_conn is None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=LEADERSHIP_RETRY_SECONDS)
            except TimeoutError:
                continue
    if lock_conn is None:
        return
    logger.info("notification market loop: leadership acquired")

    bar_events = bars or BarEvents()
    windows: dict[str, SymbolWindow] = defaultdict(SymbolWindow)
    watched = await active_market_alerts(session_factory)
    last_refresh = asyncio.get_running_loop().time()
    try:
        async for _cursor, bar in bar_events.tail():
            if stop_event.is_set():
                return
            now = asyncio.get_running_loop().time()
            if now - last_refresh >= SYMBOL_REFRESH_SECONDS:
                watched = await active_market_alerts(session_factory)
                last_refresh = now
            targets = watched.get(bar.symbol)
            if not targets:
                continue
            close = _decimal_value(bar.close.value)
            if close is None:
                continue
            window = windows[bar.symbol]
            window.push(float(close), bar.volume)
            await _evaluate_symbol(session_factory, dispatcher, bar.symbol, window, targets, bar)
    finally:
        await release_leadership(lock_conn)
        if bars is None:
            await bar_events.close()


async def _evaluate_symbol(
    session_factory: async_sessionmaker[AsyncSession],
    dispatcher: Dispatcher,
    symbol: str,
    window: SymbolWindow,
    targets: list[tuple[UUID, UUID]],
    bar: Bar,
) -> None:
    bucket = _bar_bucket(bar)
    now = datetime.now(UTC)
    async with system_session(session_factory, reason="notification market-alert evaluation") as db:
        rows = list(await db.scalars(select(Alert).where(Alert.id.in_([a for a, _ in targets]))))
    tenant_by_alert = dict(targets)
    for alert in rows:
        if not alert_is_live(alert, now):
            continue
        hit, detail = evaluate_market(alert, window)
        if not hit:
            continue
        await trigger_alert(
            session_factory,
            dispatcher,
            alert_id=alert.id,
            tenant_id=tenant_by_alert[alert.id],
            reason=detail,
            bucket=f"bar:{symbol}:{bucket}",
        )


def _decimal_value(raw: str) -> Decimal | None:
    try:
        return Decimal(raw) if raw else None
    except InvalidOperation:
        return None


def _bar_bucket(bar: Bar) -> str:
    return str(bar.timestamp.seconds // 60)
