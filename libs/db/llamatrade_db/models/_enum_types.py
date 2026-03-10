"""Internal: SQLAlchemy TypeDecorators for proto int <-> PostgreSQL ENUM conversion.

This module is internal to the DB layer. Service code should import enum constants
directly from llamatrade_proto.generated.

Architecture:
- Service layer uses proto constants (e.g., ORDER_SIDE_BUY = 1)
- Database stores PostgreSQL native ENUMs (e.g., 'buy', 'sell')
- TypeDecorators convert automatically: 1 <-> 'buy'

Usage in DB models:
    from llamatrade_db.models._enum_types import OrderStatusType

    class Order(Base):
        status: Mapped[OrderStatus.ValueType] = mapped_column(OrderStatusType(), nullable=False)
"""

from enum import StrEnum
from typing import Generic, TypeVar, cast

from sqlalchemy import Dialect, Enum
from sqlalchemy.types import TypeDecorator

from llamatrade_proto.generated import (
    backtest_pb2,
    billing_pb2,
    common_pb2,
    notification_pb2,
    portfolio_pb2,
    strategy_pb2,
    trading_pb2,
)

# Generic type variable for proto ValueType
T = TypeVar("T", bound=int)

# =============================================================================
# PostgreSQL StrEnums (internal - maps to DB ENUM types)
# =============================================================================


class _OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class _OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class _OrderStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class _TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    OPG = "opg"
    CLS = "cls"


class _PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class _ExecutionMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class _ExecutionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class _SessionStatus(StrEnum):
    """Trading session status (subset of ExecutionStatus)."""

    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class _StrategyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class _BacktestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class _SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    TRIALING = "trialing"
    PAUSED = "paused"


class _PlanTier(StrEnum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"


class _BillingInterval(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class _InvoiceStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class _NotificationType(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    ALERT = "alert"
    ORDER = "order"
    TRADE = "trade"
    SYSTEM = "system"


class _ChannelType(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"


class _AlertConditionType(StrEnum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_CHANGE_PERCENT = "price_change_percent"
    VOLUME_ABOVE = "volume_above"
    RSI_ABOVE = "rsi_above"
    RSI_BELOW = "rsi_below"
    ORDER_FILLED = "order_filled"
    STRATEGY_SIGNAL = "strategy_signal"


class _AlertStatus(StrEnum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    DISABLED = "disabled"


class _NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class _NotificationPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class _TemplateCategory(StrEnum):
    BUY_AND_HOLD = "buy-and-hold"
    TACTICAL = "tactical"
    FACTOR = "factor"
    INCOME = "income"
    TREND = "trend"
    MEAN_REVERSION = "mean-reversion"
    ALTERNATIVES = "alternatives"


class _AssetClass(StrEnum):
    EQUITY = "equity"
    FIXED_INCOME = "fixed-income"
    MULTI_ASSET = "multi-asset"
    CRYPTO = "crypto"
    COMMODITY = "commodity"
    OPTIONS = "options"


class _IndicatorType(StrEnum):
    SMA = "sma"
    EMA = "ema"
    MACD = "macd"
    ADX = "adx"
    RSI = "rsi"
    STOCHASTIC = "stochastic"
    CCI = "cci"
    WILLIAMS_R = "williams-r"
    BOLLINGER_BANDS = "bollinger-bands"
    ATR = "atr"
    KELTNER_CHANNEL = "keltner-channel"
    OBV = "obv"
    MFI = "mfi"
    VWAP = "vwap"
    DONCHIAN_CHANNEL = "donchian-channel"


class _TemplateDifficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class _TransactionType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    FEE = "fee"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"


# =============================================================================
# TypeDecorator Infrastructure
# =============================================================================


class _ProtoEnumType(TypeDecorator[T], Generic[T]):
    """Base TypeDecorator for proto int <-> PostgreSQL ENUM conversion.

    Generic over T which should be the proto enum's ValueType.
    This ensures pyright knows the correct return type when reading from DB.
    """

    cache_ok = True
    _int_to_str: dict[int, StrEnum]
    _str_to_int: dict[StrEnum, int]
    _str_enum: type[StrEnum]

    def _convert_to_db_value(self, value: int | str | StrEnum | None) -> str | None:
        """Convert any value type to the PostgreSQL enum string."""
        if value is None:
            return None
        if isinstance(value, self._str_enum):
            return value.value  # Return the string value
        if isinstance(value, str):
            # Already a string, ensure lowercase
            return value.lower()
        # Integer value - convert via mapping
        int_val = int(value)
        enum_member = self._int_to_str.get(int_val)
        if enum_member is not None:
            return enum_member.value
        # Fallback to first enum member
        return next(iter(self._str_enum)).value

    def process_bind_param(self, value: T | None, dialect: Dialect) -> str | None:
        """Convert proto ValueType to PostgreSQL enum string value."""
        return self._convert_to_db_value(value)

    def process_result_value(self, value: str | StrEnum | None, dialect: Dialect) -> T | None:
        """Convert PostgreSQL enum string to proto ValueType."""
        if value is None:
            return None
        # StrEnum is a subclass of str, so we can treat both the same way
        # Get the string value (works for both str and StrEnum)
        str_value = value.value if isinstance(value, StrEnum) else value
        # Find the enum member with this value
        for member in self._str_enum:
            if member.value == str_value:
                # Cast to T since we know the mapping produces valid proto values
                return cast(T, self._str_to_int.get(member, 0))
        return cast(T, 0)

    def coerce_compared_value(self, op: object, value: object) -> TypeDecorator[T] | None:
        """Ensure comparison values are coerced through this TypeDecorator."""
        # Return self to ensure the value goes through process_bind_param
        return self


# =============================================================================
# Public TypeDecorators (used by DB models)
# =============================================================================


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """Extract lowercase values from StrEnum for SQLAlchemy Enum impl."""
    return [e.value for e in enum_cls]


class OrderSideType(_ProtoEnumType[trading_pb2.OrderSide.ValueType]):
    impl = Enum(
        _OrderSide,
        name="order_side",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _OrderSide
    _int_to_str = {
        trading_pb2.ORDER_SIDE_BUY: _OrderSide.BUY,
        trading_pb2.ORDER_SIDE_SELL: _OrderSide.SELL,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class OrderTypeType(_ProtoEnumType[trading_pb2.OrderType.ValueType]):
    impl = Enum(
        _OrderType,
        name="order_type",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _OrderType
    _int_to_str = {
        trading_pb2.ORDER_TYPE_MARKET: _OrderType.MARKET,
        trading_pb2.ORDER_TYPE_LIMIT: _OrderType.LIMIT,
        trading_pb2.ORDER_TYPE_STOP: _OrderType.STOP,
        trading_pb2.ORDER_TYPE_STOP_LIMIT: _OrderType.STOP_LIMIT,
        trading_pb2.ORDER_TYPE_TRAILING_STOP: _OrderType.TRAILING_STOP,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class OrderStatusType(_ProtoEnumType[trading_pb2.OrderStatus.ValueType]):
    impl = Enum(
        _OrderStatus,
        name="order_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _OrderStatus
    _int_to_str = {
        trading_pb2.ORDER_STATUS_PENDING: _OrderStatus.PENDING,
        trading_pb2.ORDER_STATUS_SUBMITTED: _OrderStatus.SUBMITTED,
        trading_pb2.ORDER_STATUS_ACCEPTED: _OrderStatus.ACCEPTED,
        trading_pb2.ORDER_STATUS_PARTIAL: _OrderStatus.PARTIAL,
        trading_pb2.ORDER_STATUS_FILLED: _OrderStatus.FILLED,
        trading_pb2.ORDER_STATUS_CANCELLED: _OrderStatus.CANCELLED,
        trading_pb2.ORDER_STATUS_REJECTED: _OrderStatus.REJECTED,
        trading_pb2.ORDER_STATUS_EXPIRED: _OrderStatus.EXPIRED,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class TimeInForceType(_ProtoEnumType[trading_pb2.TimeInForce.ValueType]):
    impl = Enum(
        _TimeInForce,
        name="time_in_force",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _TimeInForce
    _int_to_str = {
        trading_pb2.TIME_IN_FORCE_DAY: _TimeInForce.DAY,
        trading_pb2.TIME_IN_FORCE_GTC: _TimeInForce.GTC,
        trading_pb2.TIME_IN_FORCE_IOC: _TimeInForce.IOC,
        trading_pb2.TIME_IN_FORCE_FOK: _TimeInForce.FOK,
        trading_pb2.TIME_IN_FORCE_OPG: _TimeInForce.OPG,
        trading_pb2.TIME_IN_FORCE_CLS: _TimeInForce.CLS,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class PositionSideType(_ProtoEnumType[trading_pb2.PositionSide.ValueType]):
    impl = Enum(
        _PositionSide,
        name="position_side",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _PositionSide
    _int_to_str = {
        trading_pb2.POSITION_SIDE_LONG: _PositionSide.LONG,
        trading_pb2.POSITION_SIDE_SHORT: _PositionSide.SHORT,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class ExecutionModeType(_ProtoEnumType[common_pb2.ExecutionMode.ValueType]):
    impl = Enum(
        _ExecutionMode,
        name="execution_mode",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _ExecutionMode
    _int_to_str = {
        common_pb2.EXECUTION_MODE_PAPER: _ExecutionMode.PAPER,
        common_pb2.EXECUTION_MODE_LIVE: _ExecutionMode.LIVE,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class ExecutionStatusType(_ProtoEnumType[common_pb2.ExecutionStatus.ValueType]):
    impl = Enum(
        _ExecutionStatus,
        name="execution_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _ExecutionStatus
    _int_to_str = {
        common_pb2.EXECUTION_STATUS_PENDING: _ExecutionStatus.PENDING,
        common_pb2.EXECUTION_STATUS_RUNNING: _ExecutionStatus.RUNNING,
        common_pb2.EXECUTION_STATUS_PAUSED: _ExecutionStatus.PAUSED,
        common_pb2.EXECUTION_STATUS_STOPPED: _ExecutionStatus.STOPPED,
        common_pb2.EXECUTION_STATUS_ERROR: _ExecutionStatus.ERROR,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class SessionStatusType(_ProtoEnumType[common_pb2.ExecutionStatus.ValueType]):
    """SessionStatus maps ExecutionStatus int values to session-specific string values."""

    impl = Enum(
        _SessionStatus,
        name="session_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _SessionStatus
    _int_to_str = {
        # ACTIVE (1) maps to RUNNING in ExecutionStatus
        common_pb2.EXECUTION_STATUS_RUNNING: _SessionStatus.ACTIVE,
        common_pb2.EXECUTION_STATUS_PAUSED: _SessionStatus.PAUSED,
        common_pb2.EXECUTION_STATUS_STOPPED: _SessionStatus.STOPPED,
        common_pb2.EXECUTION_STATUS_ERROR: _SessionStatus.ERROR,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class StrategyStatusType(_ProtoEnumType[strategy_pb2.StrategyStatus.ValueType]):
    impl = Enum(
        _StrategyStatus,
        name="strategy_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _StrategyStatus
    _int_to_str = {
        strategy_pb2.STRATEGY_STATUS_DRAFT: _StrategyStatus.DRAFT,
        strategy_pb2.STRATEGY_STATUS_ACTIVE: _StrategyStatus.ACTIVE,
        strategy_pb2.STRATEGY_STATUS_PAUSED: _StrategyStatus.PAUSED,
        strategy_pb2.STRATEGY_STATUS_ARCHIVED: _StrategyStatus.ARCHIVED,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class BacktestStatusType(_ProtoEnumType[backtest_pb2.BacktestStatus.ValueType]):
    impl = Enum(
        _BacktestStatus,
        name="backtest_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _BacktestStatus
    _int_to_str = {
        backtest_pb2.BACKTEST_STATUS_PENDING: _BacktestStatus.PENDING,
        backtest_pb2.BACKTEST_STATUS_RUNNING: _BacktestStatus.RUNNING,
        backtest_pb2.BACKTEST_STATUS_COMPLETED: _BacktestStatus.COMPLETED,
        backtest_pb2.BACKTEST_STATUS_FAILED: _BacktestStatus.FAILED,
        backtest_pb2.BACKTEST_STATUS_CANCELLED: _BacktestStatus.CANCELLED,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class SubscriptionStatusType(_ProtoEnumType[billing_pb2.SubscriptionStatus.ValueType]):
    impl = Enum(
        _SubscriptionStatus,
        name="subscription_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _SubscriptionStatus
    _int_to_str = {
        billing_pb2.SUBSCRIPTION_STATUS_ACTIVE: _SubscriptionStatus.ACTIVE,
        billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE: _SubscriptionStatus.PAST_DUE,
        billing_pb2.SUBSCRIPTION_STATUS_CANCELED: _SubscriptionStatus.CANCELED,
        billing_pb2.SUBSCRIPTION_STATUS_TRIALING: _SubscriptionStatus.TRIALING,
        billing_pb2.SUBSCRIPTION_STATUS_PAUSED: _SubscriptionStatus.PAUSED,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class PlanTierType(_ProtoEnumType[billing_pb2.PlanTier.ValueType]):
    impl = Enum(
        _PlanTier,
        name="plan_tier",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _PlanTier
    _int_to_str = {
        billing_pb2.PLAN_TIER_FREE: _PlanTier.FREE,
        billing_pb2.PLAN_TIER_STARTER: _PlanTier.STARTER,
        billing_pb2.PLAN_TIER_PRO: _PlanTier.PRO,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class BillingIntervalType(_ProtoEnumType[billing_pb2.BillingInterval.ValueType]):
    impl = Enum(
        _BillingInterval,
        name="billing_interval",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _BillingInterval
    _int_to_str = {
        billing_pb2.BILLING_INTERVAL_MONTHLY: _BillingInterval.MONTHLY,
        billing_pb2.BILLING_INTERVAL_YEARLY: _BillingInterval.YEARLY,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class InvoiceStatusType(_ProtoEnumType[billing_pb2.InvoiceStatus.ValueType]):
    impl = Enum(
        _InvoiceStatus,
        name="invoice_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _InvoiceStatus
    _int_to_str = {
        billing_pb2.INVOICE_STATUS_DRAFT: _InvoiceStatus.DRAFT,
        billing_pb2.INVOICE_STATUS_OPEN: _InvoiceStatus.OPEN,
        billing_pb2.INVOICE_STATUS_PAID: _InvoiceStatus.PAID,
        billing_pb2.INVOICE_STATUS_VOID: _InvoiceStatus.VOID,
        billing_pb2.INVOICE_STATUS_UNCOLLECTIBLE: _InvoiceStatus.UNCOLLECTIBLE,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class NotificationTypeType(_ProtoEnumType[notification_pb2.NotificationType.ValueType]):
    impl = Enum(
        _NotificationType,
        name="notification_type",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _NotificationType
    _int_to_str = {
        notification_pb2.NOTIFICATION_TYPE_INFO: _NotificationType.INFO,
        notification_pb2.NOTIFICATION_TYPE_SUCCESS: _NotificationType.SUCCESS,
        notification_pb2.NOTIFICATION_TYPE_WARNING: _NotificationType.WARNING,
        notification_pb2.NOTIFICATION_TYPE_ERROR: _NotificationType.ERROR,
        notification_pb2.NOTIFICATION_TYPE_ALERT: _NotificationType.ALERT,
        notification_pb2.NOTIFICATION_TYPE_ORDER: _NotificationType.ORDER,
        notification_pb2.NOTIFICATION_TYPE_TRADE: _NotificationType.TRADE,
        notification_pb2.NOTIFICATION_TYPE_SYSTEM: _NotificationType.SYSTEM,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class ChannelTypeType(_ProtoEnumType[notification_pb2.ChannelType.ValueType]):
    impl = Enum(
        _ChannelType,
        name="channel_type",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _ChannelType
    _int_to_str = {
        notification_pb2.CHANNEL_TYPE_EMAIL: _ChannelType.EMAIL,
        notification_pb2.CHANNEL_TYPE_SMS: _ChannelType.SMS,
        notification_pb2.CHANNEL_TYPE_PUSH: _ChannelType.PUSH,
        notification_pb2.CHANNEL_TYPE_WEBHOOK: _ChannelType.WEBHOOK,
        notification_pb2.CHANNEL_TYPE_SLACK: _ChannelType.SLACK,
        notification_pb2.CHANNEL_TYPE_DISCORD: _ChannelType.DISCORD,
        notification_pb2.CHANNEL_TYPE_TELEGRAM: _ChannelType.TELEGRAM,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class AlertConditionTypeType(_ProtoEnumType[notification_pb2.AlertConditionType.ValueType]):
    impl = Enum(
        _AlertConditionType,
        name="alert_condition_type",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _AlertConditionType
    _int_to_str = {
        notification_pb2.ALERT_CONDITION_TYPE_PRICE_ABOVE: _AlertConditionType.PRICE_ABOVE,
        notification_pb2.ALERT_CONDITION_TYPE_PRICE_BELOW: _AlertConditionType.PRICE_BELOW,
        notification_pb2.ALERT_CONDITION_TYPE_PRICE_CHANGE_PERCENT: _AlertConditionType.PRICE_CHANGE_PERCENT,
        notification_pb2.ALERT_CONDITION_TYPE_VOLUME_ABOVE: _AlertConditionType.VOLUME_ABOVE,
        notification_pb2.ALERT_CONDITION_TYPE_RSI_ABOVE: _AlertConditionType.RSI_ABOVE,
        notification_pb2.ALERT_CONDITION_TYPE_RSI_BELOW: _AlertConditionType.RSI_BELOW,
        notification_pb2.ALERT_CONDITION_TYPE_ORDER_FILLED: _AlertConditionType.ORDER_FILLED,
        notification_pb2.ALERT_CONDITION_TYPE_STRATEGY_SIGNAL: _AlertConditionType.STRATEGY_SIGNAL,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class AlertStatusType(_ProtoEnumType[notification_pb2.AlertStatus.ValueType]):
    impl = Enum(
        _AlertStatus,
        name="alert_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _AlertStatus
    _int_to_str = {
        notification_pb2.ALERT_STATUS_ACTIVE: _AlertStatus.ACTIVE,
        notification_pb2.ALERT_STATUS_TRIGGERED: _AlertStatus.TRIGGERED,
        notification_pb2.ALERT_STATUS_DISABLED: _AlertStatus.DISABLED,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class NotificationStatusType(_ProtoEnumType[notification_pb2.NotificationStatus.ValueType]):
    impl = Enum(
        _NotificationStatus,
        name="notification_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _NotificationStatus
    _int_to_str = {
        notification_pb2.NOTIFICATION_STATUS_PENDING: _NotificationStatus.PENDING,
        notification_pb2.NOTIFICATION_STATUS_SENT: _NotificationStatus.SENT,
        notification_pb2.NOTIFICATION_STATUS_FAILED: _NotificationStatus.FAILED,
        notification_pb2.NOTIFICATION_STATUS_READ: _NotificationStatus.READ,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class TransactionTypeType(_ProtoEnumType[portfolio_pb2.TransactionType.ValueType]):
    impl = Enum(
        _TransactionType,
        name="transaction_type",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _TransactionType
    _int_to_str = {
        portfolio_pb2.TRANSACTION_TYPE_DEPOSIT: _TransactionType.DEPOSIT,
        portfolio_pb2.TRANSACTION_TYPE_WITHDRAWAL: _TransactionType.WITHDRAWAL,
        portfolio_pb2.TRANSACTION_TYPE_DIVIDEND: _TransactionType.DIVIDEND,
        portfolio_pb2.TRANSACTION_TYPE_INTEREST: _TransactionType.INTEREST,
        portfolio_pb2.TRANSACTION_TYPE_FEE: _TransactionType.FEE,
        portfolio_pb2.TRANSACTION_TYPE_TRANSFER_IN: _TransactionType.TRANSFER_IN,
        portfolio_pb2.TRANSACTION_TYPE_TRANSFER_OUT: _TransactionType.TRANSFER_OUT,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class NotificationPriorityType(_ProtoEnumType[notification_pb2.NotificationPriority.ValueType]):
    impl = Enum(
        _NotificationPriority,
        name="notification_priority",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _NotificationPriority
    _int_to_str = {
        notification_pb2.NOTIFICATION_PRIORITY_LOW: _NotificationPriority.LOW,
        notification_pb2.NOTIFICATION_PRIORITY_MEDIUM: _NotificationPriority.MEDIUM,
        notification_pb2.NOTIFICATION_PRIORITY_HIGH: _NotificationPriority.HIGH,
        notification_pb2.NOTIFICATION_PRIORITY_CRITICAL: _NotificationPriority.CRITICAL,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class TemplateCategoryType(_ProtoEnumType[strategy_pb2.TemplateCategory.ValueType]):
    impl = Enum(
        _TemplateCategory,
        name="template_category",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _TemplateCategory
    _int_to_str = {
        strategy_pb2.TEMPLATE_CATEGORY_BUY_AND_HOLD: _TemplateCategory.BUY_AND_HOLD,
        strategy_pb2.TEMPLATE_CATEGORY_TACTICAL: _TemplateCategory.TACTICAL,
        strategy_pb2.TEMPLATE_CATEGORY_FACTOR: _TemplateCategory.FACTOR,
        strategy_pb2.TEMPLATE_CATEGORY_INCOME: _TemplateCategory.INCOME,
        strategy_pb2.TEMPLATE_CATEGORY_TREND: _TemplateCategory.TREND,
        strategy_pb2.TEMPLATE_CATEGORY_MEAN_REVERSION: _TemplateCategory.MEAN_REVERSION,
        strategy_pb2.TEMPLATE_CATEGORY_ALTERNATIVES: _TemplateCategory.ALTERNATIVES,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class AssetClassType(_ProtoEnumType[strategy_pb2.AssetClass.ValueType]):
    impl = Enum(
        _AssetClass,
        name="asset_class",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _AssetClass
    _int_to_str = {
        strategy_pb2.ASSET_CLASS_EQUITY: _AssetClass.EQUITY,
        strategy_pb2.ASSET_CLASS_FIXED_INCOME: _AssetClass.FIXED_INCOME,
        strategy_pb2.ASSET_CLASS_MULTI_ASSET: _AssetClass.MULTI_ASSET,
        strategy_pb2.ASSET_CLASS_CRYPTO: _AssetClass.CRYPTO,
        strategy_pb2.ASSET_CLASS_COMMODITY: _AssetClass.COMMODITY,
        strategy_pb2.ASSET_CLASS_OPTIONS: _AssetClass.OPTIONS,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class IndicatorTypeType(_ProtoEnumType[strategy_pb2.IndicatorType.ValueType]):
    impl = Enum(
        _IndicatorType,
        name="indicator_type",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _IndicatorType
    _int_to_str = {
        strategy_pb2.INDICATOR_TYPE_SMA: _IndicatorType.SMA,
        strategy_pb2.INDICATOR_TYPE_EMA: _IndicatorType.EMA,
        strategy_pb2.INDICATOR_TYPE_MACD: _IndicatorType.MACD,
        strategy_pb2.INDICATOR_TYPE_ADX: _IndicatorType.ADX,
        strategy_pb2.INDICATOR_TYPE_RSI: _IndicatorType.RSI,
        strategy_pb2.INDICATOR_TYPE_STOCHASTIC: _IndicatorType.STOCHASTIC,
        strategy_pb2.INDICATOR_TYPE_CCI: _IndicatorType.CCI,
        strategy_pb2.INDICATOR_TYPE_WILLIAMS_R: _IndicatorType.WILLIAMS_R,
        strategy_pb2.INDICATOR_TYPE_BOLLINGER_BANDS: _IndicatorType.BOLLINGER_BANDS,
        strategy_pb2.INDICATOR_TYPE_ATR: _IndicatorType.ATR,
        strategy_pb2.INDICATOR_TYPE_KELTNER_CHANNEL: _IndicatorType.KELTNER_CHANNEL,
        strategy_pb2.INDICATOR_TYPE_OBV: _IndicatorType.OBV,
        strategy_pb2.INDICATOR_TYPE_MFI: _IndicatorType.MFI,
        strategy_pb2.INDICATOR_TYPE_VWAP: _IndicatorType.VWAP,
        strategy_pb2.INDICATOR_TYPE_DONCHIAN_CHANNEL: _IndicatorType.DONCHIAN_CHANNEL,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class TemplateDifficultyType(_ProtoEnumType[strategy_pb2.TemplateDifficulty.ValueType]):
    impl = Enum(
        _TemplateDifficulty,
        name="template_difficulty",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _TemplateDifficulty
    _int_to_str = {
        strategy_pb2.TEMPLATE_DIFFICULTY_BEGINNER: _TemplateDifficulty.BEGINNER,
        strategy_pb2.TEMPLATE_DIFFICULTY_INTERMEDIATE: _TemplateDifficulty.INTERMEDIATE,
        strategy_pb2.TEMPLATE_DIFFICULTY_ADVANCED: _TemplateDifficulty.ADVANCED,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}
