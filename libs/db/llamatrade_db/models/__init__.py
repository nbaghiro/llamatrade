"""ORM models for LlamaTrade database."""

from llamatrade_db.models.agent import (
    AgentMemoryEmbedding,
    AgentMemoryFact,
    AgentMessage,
    AgentSession,
    AgentSessionSummary,
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

# NOTE: Enum constants should be imported directly from llamatrade_proto.generated.*_pb2
# e.g., from llamatrade_proto.generated.trading_pb2 import ORDER_SIDE_BUY
from llamatrade_db.models.market_data import (
    Bar,
    Quote,
    Trade,
)
from llamatrade_db.models.notification import (
    Alert,
    Notification,
    NotificationChannel,
    Webhook,
)
from llamatrade_db.models.portfolio import (
    PerformanceMetrics,
    PortfolioHistory,
    PortfolioSummary,
    StrategyPerformanceMetrics,
    StrategyPerformanceSnapshot,
    Transaction,
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
    "AgentMemoryEmbedding",
    "AgentSessionSummary",
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
    # Portfolio
    "PortfolioSummary",
    "Transaction",
    "PortfolioHistory",
    "PerformanceMetrics",
    "StrategyPerformanceSnapshot",
    "StrategyPerformanceMetrics",
    # Market Data
    "Bar",
    "Quote",
    "Trade",
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
