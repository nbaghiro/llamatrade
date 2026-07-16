"""ORM models for LlamaTrade database."""

from llamatrade_db.models.agent import (
    AgentMemoryFact,
    AgentMessage,
    AgentSession,
    MemoryFactCategory,
    PendingArtifact,
    ToolCallLog,
)
from llamatrade_db.models.audit import (
    AuditEventType,
    AuditLog,
    DailyPnL,
    RiskConfig,
)
from llamatrade_db.models.auth import (
    AlpacaCredentials,
    APIKey,
    Tenant,
    User,
)
from llamatrade_db.models.backtest import (
    Backtest,
    BacktestResult,
)
from llamatrade_db.models.billing import (
    Invoice,
    PaymentMethod,
    Plan,
    Subscription,
    UsageRecord,
)
from llamatrade_db.models.ledger import (
    Account,
    LedgerEvent,
    LedgerEventType,
    Lot,
    LotSide,
    Sleeve,
    SleeveSnapshot,
    SleeveStatus,
    SleeveType,
)

# NOTE: Enum constants should be imported directly from llamatrade_proto.generated.*_pb2
# e.g., from llamatrade_proto.generated.trading_pb2 import ORDER_SIDE_BUY
# Market-data bars/quotes/trades live in the market-data service's Timescale store, not here.
from llamatrade_db.models.notification import (
    Alert,
    Notification,
    NotificationChannel,
    Webhook,
)
from llamatrade_db.models.strategy import (
    Strategy,
    StrategyExecution,
    StrategyTemplate,
    StrategyVersion,
)
from llamatrade_db.models.trading import (
    Order,
    Position,
    TradingSession,
)

__all__ = [
    # Agent
    "AgentSession",
    "AgentMessage",
    "PendingArtifact",
    "ToolCallLog",
    "AgentMemoryFact",
    "MemoryFactCategory",
    # Audit
    "AuditLog",
    "AuditEventType",
    "RiskConfig",
    "DailyPnL",
    # Auth
    "Tenant",
    "User",
    "AlpacaCredentials",
    "APIKey",
    # Strategy
    "Strategy",
    "StrategyVersion",
    "StrategyTemplate",
    "StrategyExecution",
    # Backtest
    "Backtest",
    "BacktestResult",
    # Trading
    "TradingSession",
    "Order",
    "Position",
    # Portfolio Ledger
    "Account",
    "Sleeve",
    "Lot",
    "LedgerEvent",
    "SleeveSnapshot",
    "SleeveType",
    "SleeveStatus",
    "LotSide",
    "LedgerEventType",
    # Notification
    "Alert",
    "Notification",
    "NotificationChannel",
    "Webhook",
    # Billing
    "Plan",
    "Subscription",
    "UsageRecord",
    "Invoice",
    "PaymentMethod",
]
