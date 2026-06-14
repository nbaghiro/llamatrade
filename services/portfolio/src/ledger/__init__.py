"""Portfolio ledger: event-sourced book of record.

Pure kernel (no IO):
- ``postings``        — double-entry expansion + conservation check
- ``projection``      — fold events into sleeve cash / positions / P&L + holdings
- ``reconciliation``  — shadow compare of ledger aggregate vs broker truth

IO adapter:
- ``writer``          — append-only, idempotent, balance-checked event writer
"""

from src.ledger.backfill import BrokerPosition, PlannedEvent, plan_backfill
from src.ledger.corporate import (
    PlannedCorporateEvent,
    plan_split,
    plan_symbol_change,
    split_dividend,
)
from src.ledger.desired_state import SleeveDesired, plan_rebalance
from src.ledger.funds import (
    FundError,
    PlannedFundEvent,
    RaiseCashSell,
    TransferPlan,
    check_admission,
    plan_allocate,
    plan_deposit,
    plan_transfer,
    plan_withdraw,
)
from src.ledger.ingestion import (
    LedgerAppend,
    fill_to_append,
)
from src.ledger.netting import (
    BrokerOrder,
    NettingResult,
    SleeveAllocation,
    net_orders,
)
from src.ledger.performance import SleevePnL, account_pnl, sleeve_pnl
from src.ledger.postings import (
    Bucket,
    Posting,
    UnbalancedEventError,
    assert_balanced,
    build_postings,
)
from src.ledger.projection import (
    AccountProjection,
    HoldingHistoryEntry,
    PositionState,
    SleeveProjection,
    fold,
    holding_history,
)
from src.ledger.projector import LedgerProjector
from src.ledger.reconciliation import (
    DEFAULT_DUST_TOLERANCE,
    Drift,
    DriftKind,
    reconcile,
)
from src.ledger.sizing import (
    DEFAULT_DRIFT_TOLERANCE,
    FifoResult,
    IntendedOrder,
    Lot,
    fit_to_free_cash,
    select_lots_fifo,
    sleeve_equity,
    target_orders,
)
from src.ledger.writer import LedgerWriter

__all__ = [
    # postings
    "Bucket",
    "Posting",
    "UnbalancedEventError",
    "assert_balanced",
    "build_postings",
    # projection
    "AccountProjection",
    "SleeveProjection",
    "PositionState",
    "HoldingHistoryEntry",
    "fold",
    "holding_history",
    # reconciliation
    "Drift",
    "DriftKind",
    "DEFAULT_DUST_TOLERANCE",
    "reconcile",
    # writer
    "LedgerWriter",
    # ingestion
    "LedgerAppend",
    "fill_to_append",
    # backfill
    "BrokerPosition",
    "PlannedEvent",
    "plan_backfill",
    # corporate actions
    "PlannedCorporateEvent",
    "plan_split",
    "plan_symbol_change",
    "split_dividend",
    # projector
    "LedgerProjector",
    # funds
    "FundError",
    "PlannedFundEvent",
    "RaiseCashSell",
    "TransferPlan",
    "check_admission",
    "plan_allocate",
    "plan_deposit",
    "plan_transfer",
    "plan_withdraw",
    # sizing
    "IntendedOrder",
    "Lot",
    "FifoResult",
    "DEFAULT_DRIFT_TOLERANCE",
    "sleeve_equity",
    "target_orders",
    "fit_to_free_cash",
    "select_lots_fifo",
    # desired-state
    "SleeveDesired",
    "plan_rebalance",
    # netting
    "BrokerOrder",
    "SleeveAllocation",
    "NettingResult",
    "net_orders",
    # performance
    "SleevePnL",
    "sleeve_pnl",
    "account_pnl",
]
