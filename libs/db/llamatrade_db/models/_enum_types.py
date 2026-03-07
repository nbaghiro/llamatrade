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
        status: Mapped[int] = mapped_column(OrderStatusType(), nullable=False)
"""

from enum import StrEnum

from sqlalchemy import Dialect, Enum
from sqlalchemy.types import TypeDecorator

# Import proto constants from generated modules
from llamatrade_proto.generated import (
    backtest_pb2,
    billing_pb2,
    common_pb2,
    notification_pb2,
    portfolio_pb2,
    strategy_pb2,
    trading_pb2,
)

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
    """Invoice status (DB-only, no proto)."""

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


class _ProtoEnumType(TypeDecorator):
    """Base TypeDecorator for proto int <-> PostgreSQL ENUM conversion."""

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

    def process_bind_param(self, value: int | None, dialect: Dialect) -> str | None:
        """Convert proto int to PostgreSQL enum string value."""
        return self._convert_to_db_value(value)

    def process_result_value(self, value: str | StrEnum | None, dialect: Dialect) -> int | None:
        """Convert PostgreSQL enum string to proto int."""
        if value is None:
            return None
        # Handle both string and enum member
        if isinstance(value, str):
            # Find the enum member with this value
            for member in self._str_enum:
                if member.value == value:
                    return self._str_to_int.get(member, 0)
            return 0
        return self._str_to_int.get(value, 0)

    def coerce_compared_value(self, op: object, value: object) -> TypeDecorator | None:
        """Ensure comparison values are coerced through this TypeDecorator."""
        # Return self to ensure the value goes through process_bind_param
        return self


# =============================================================================
# Public TypeDecorators (used by DB models)
# =============================================================================


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """Extract lowercase values from StrEnum for SQLAlchemy Enum impl."""
    return [e.value for e in enum_cls]


class OrderSideType(_ProtoEnumType):
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


class OrderTypeType(_ProtoEnumType):
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


class OrderStatusType(_ProtoEnumType):
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


class TimeInForceType(_ProtoEnumType):
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


class PositionSideType(_ProtoEnumType):
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


class ExecutionModeType(_ProtoEnumType):
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


class ExecutionStatusType(_ProtoEnumType):
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


class SessionStatusType(_ProtoEnumType):
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


class StrategyStatusType(_ProtoEnumType):
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


class BacktestStatusType(_ProtoEnumType):
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


class SubscriptionStatusType(_ProtoEnumType):
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


class PlanTierType(_ProtoEnumType):
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


class BillingIntervalType(_ProtoEnumType):
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


class InvoiceStatusType(_ProtoEnumType):
    """InvoiceStatus is DB-only (no proto), uses manual int mapping."""

    impl = Enum(
        _InvoiceStatus,
        name="invoice_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _InvoiceStatus
    _int_to_str = {
        1: _InvoiceStatus.DRAFT,
        2: _InvoiceStatus.OPEN,
        3: _InvoiceStatus.PAID,
        4: _InvoiceStatus.VOID,
        5: _InvoiceStatus.UNCOLLECTIBLE,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class NotificationTypeType(_ProtoEnumType):
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


class ChannelTypeType(_ProtoEnumType):
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


class AlertConditionTypeType(_ProtoEnumType):
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


class AlertStatusType(_ProtoEnumType):
    """AlertStatus is DB-only (no proto), uses manual int mapping."""

    impl = Enum(
        _AlertStatus,
        name="alert_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _AlertStatus
    _int_to_str = {
        1: _AlertStatus.ACTIVE,
        2: _AlertStatus.TRIGGERED,
        3: _AlertStatus.DISABLED,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class NotificationStatusType(_ProtoEnumType):
    """NotificationStatus is DB-only (no proto), uses manual int mapping."""

    impl = Enum(
        _NotificationStatus,
        name="notification_status",
        create_type=False,
        values_callable=_enum_values,
    )
    _str_enum = _NotificationStatus
    _int_to_str = {
        1: _NotificationStatus.PENDING,
        2: _NotificationStatus.SENT,
        3: _NotificationStatus.FAILED,
        4: _NotificationStatus.READ,
    }
    _str_to_int = {v: k for k, v in _int_to_str.items()}


class TransactionTypeType(_ProtoEnumType):
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
