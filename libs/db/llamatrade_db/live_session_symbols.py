"""Read the symbols live execution needs (shared read helper).

The market-data ingest role is the platform's only Alpaca bar consumer, so its
subscription set has to cover every symbol a deployed strategy trades. The query
lives here with the models it reads. Two sources make up that set:

* ``TradingSession.symbols`` — the materialized per-session subscription. A
  session may override the strategy's symbols when it starts, so this column,
  not the strategy version, is what the running runner actually consumes.
* ``StrategyVersion.symbols`` reached through an active ``StrategyExecution`` —
  covers a funded execution whose trading session has not been (re)started yet,
  so the store is already warm when it does start.

This is a cross-tenant operational read for an infrastructure daemon, not a
request path: callers open it under ``system_session`` (audited RLS bypass) and
there is deliberately no tenant filter.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.strategy import StrategyExecution, StrategyVersion
from llamatrade_db.models.trading import TradingSession
from llamatrade_proto.generated import common_pb2

# States whose runner consumes, or resumes consuming, live bars. PAUSED is
# included so a resume does not sit without bars until the next refresh;
# STOPPED / ERROR never resume on their own.
ACTIVE_EXECUTION_STATUSES: tuple[common_pb2.ExecutionStatus.ValueType, ...] = (
    common_pb2.EXECUTION_STATUS_RUNNING,
    common_pb2.EXECUTION_STATUS_PAUSED,
)


def _normalize(symbol_lists: Iterable[Sequence[str]]) -> set[str]:
    """Flatten stored symbol arrays into one trimmed, upper-cased set."""
    return {
        stripped
        for symbols in symbol_lists
        for symbol in symbols
        if (stripped := symbol.strip().upper())
    }


async def get_live_session_symbols(db: AsyncSession) -> frozenset[str]:
    """Every symbol an active live session or execution needs, across all tenants."""
    session_symbols = (
        await db.scalars(
            select(TradingSession.symbols).where(
                TradingSession.status.in_(ACTIVE_EXECUTION_STATUSES)
            )
        )
    ).all()

    execution_symbols = (
        await db.scalars(
            select(StrategyVersion.symbols)
            .join(
                StrategyExecution,
                (StrategyExecution.strategy_id == StrategyVersion.strategy_id)
                & (StrategyExecution.version == StrategyVersion.version)
                & (StrategyExecution.tenant_id == StrategyVersion.tenant_id),
            )
            .where(StrategyExecution.status.in_(ACTIVE_EXECUTION_STATUSES))
        )
    ).all()

    return frozenset(_normalize(session_symbols) | _normalize(execution_symbols))
