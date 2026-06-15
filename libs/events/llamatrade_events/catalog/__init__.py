"""The event catalog — the lib's public, typed produce/consume surface.

Each family owns one channel + its EventType mapping and registers its payload
proto on import, so importing the catalog wires the codec registry. Services use
these classes directly (no per-service wrapper):

    OrderEvents().publish(session_id, order_update)        # trading → UI
    PositionEvents().tail(session_id)                       # UI consumer
    ProgressEvents().publish(backtest_id, progress_update)  # worker → UI
    FillEvents().publish_fill(ledger_fill)                  # trading → portfolio
    FillEvents().consumer(consumer_name="p1").run(handler)  # portfolio ingest
    BarEvents().publish(bar)                                # market-data → all
"""

from __future__ import annotations

from llamatrade_events.catalog.bars import BarEvents
from llamatrade_events.catalog.fills import (
    PORTFOLIO_GROUP,
    FillEvents,
    LedgerFill,
    LedgerReservation,
)
from llamatrade_events.catalog.orders import OrderEvents, OrderUpdate
from llamatrade_events.catalog.positions import PositionEvents, PositionUpdate
from llamatrade_events.catalog.progress import BacktestProgressUpdate, ProgressEvents

__all__ = [
    "PORTFOLIO_GROUP",
    "BacktestProgressUpdate",
    "BarEvents",
    "FillEvents",
    "LedgerFill",
    "LedgerReservation",
    "OrderEvents",
    "OrderUpdate",
    "PositionEvents",
    "PositionUpdate",
    "ProgressEvents",
]
