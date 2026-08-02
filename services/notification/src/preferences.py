"""Category metadata and preference resolution — the routing single source.

Each category declares its default severity, its default external channels
(the in-app row is always persisted and needs no channel), and the proto
``NotificationType`` the in-app row renders as. Tenant preferences
(per-channel ``notification_channels`` rows) can narrow the category set per
channel, except that CRITICAL and SECURITY severities are pinned: they always
reach email regardless of the matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llamatrade_proto.generated import events_pb2, notification_pb2

Category = int
ChannelType = int

EMAIL: ChannelType = notification_pb2.CHANNEL_TYPE_EMAIL
WEBHOOK: ChannelType = notification_pb2.CHANNEL_TYPE_WEBHOOK

_E = events_pb2
_NT = notification_pb2

_INFO = _E.NOTIFICATION_SEVERITY_INFO
_ACT = _E.NOTIFICATION_SEVERITY_ACTIONABLE
_CRIT = _E.NOTIFICATION_SEVERITY_CRITICAL
_SEC = _E.NOTIFICATION_SEVERITY_SECURITY

_NONE: frozenset[ChannelType] = frozenset()
_W: frozenset[ChannelType] = frozenset({WEBHOOK})
_M: frozenset[ChannelType] = frozenset({EMAIL})
_MW: frozenset[ChannelType] = frozenset({EMAIL, WEBHOOK})


@dataclass(frozen=True)
class CategorySpec:
    severity: int
    channels: frozenset[ChannelType]  # default external channels
    notification_type: notification_pb2.NotificationType.ValueType


CATEGORY_SPECS: dict[Category, CategorySpec] = {
    # Money (portfolio)
    _E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN: CategorySpec(_CRIT, _MW, _NT.NOTIFICATION_TYPE_ERROR),
    _E.NOTIFICATION_CATEGORY_FILL_QUARANTINED: CategorySpec(
        _CRIT, _MW, _NT.NOTIFICATION_TYPE_ERROR
    ),
    _E.NOTIFICATION_CATEGORY_EXTERNAL_TRADE_ADOPTED: CategorySpec(
        _ACT, _W, _NT.NOTIFICATION_TYPE_WARNING
    ),
    _E.NOTIFICATION_CATEGORY_CORPORATE_ACTION_PROPOSED: CategorySpec(
        _ACT, _M, _NT.NOTIFICATION_TYPE_INFO
    ),
    _E.NOTIFICATION_CATEGORY_CORPORATE_ACTION_APPLIED: CategorySpec(
        _INFO, _NONE, _NT.NOTIFICATION_TYPE_INFO
    ),
    # Trading
    _E.NOTIFICATION_CATEGORY_ORDER_FILLED: CategorySpec(_INFO, _W, _NT.NOTIFICATION_TYPE_ORDER),
    _E.NOTIFICATION_CATEGORY_ORDER_REJECTED: CategorySpec(_ACT, _W, _NT.NOTIFICATION_TYPE_ORDER),
    _E.NOTIFICATION_CATEGORY_POSITION_OPENED: CategorySpec(_INFO, _W, _NT.NOTIFICATION_TYPE_TRADE),
    _E.NOTIFICATION_CATEGORY_POSITION_CLOSED: CategorySpec(_INFO, _W, _NT.NOTIFICATION_TYPE_TRADE),
    _E.NOTIFICATION_CATEGORY_POSITION_DRIFT: CategorySpec(_ACT, _MW, _NT.NOTIFICATION_TYPE_WARNING),
    _E.NOTIFICATION_CATEGORY_RISK_BREACH: CategorySpec(_ACT, _W, _NT.NOTIFICATION_TYPE_WARNING),
    _E.NOTIFICATION_CATEGORY_EVALUATION_STALLED: CategorySpec(
        _ACT, _MW, _NT.NOTIFICATION_TYPE_WARNING
    ),
    _E.NOTIFICATION_CATEGORY_SYMBOL_NOT_TRADABLE: CategorySpec(
        _ACT, _MW, _NT.NOTIFICATION_TYPE_WARNING
    ),
    _E.NOTIFICATION_CATEGORY_CONNECTION_LOST: CategorySpec(
        _ACT, _MW, _NT.NOTIFICATION_TYPE_WARNING
    ),
    _E.NOTIFICATION_CATEGORY_STRATEGY_ERROR: CategorySpec(_ACT, _MW, _NT.NOTIFICATION_TYPE_ERROR),
    _E.NOTIFICATION_CATEGORY_SESSION_STARTED: CategorySpec(
        _INFO, _NONE, _NT.NOTIFICATION_TYPE_INFO
    ),
    _E.NOTIFICATION_CATEGORY_SESSION_STOPPED: CategorySpec(
        _INFO, _NONE, _NT.NOTIFICATION_TYPE_INFO
    ),
    _E.NOTIFICATION_CATEGORY_SESSION_ERROR: CategorySpec(_CRIT, _MW, _NT.NOTIFICATION_TYPE_ERROR),
    _E.NOTIFICATION_CATEGORY_CIRCUIT_BREAKER_TRIGGERED: CategorySpec(
        _CRIT, _MW, _NT.NOTIFICATION_TYPE_ERROR
    ),
    _E.NOTIFICATION_CATEGORY_CIRCUIT_BREAKER_RESET: CategorySpec(
        _INFO, _W, _NT.NOTIFICATION_TYPE_INFO
    ),
    _E.NOTIFICATION_CATEGORY_STOP_LOSS_HIT: CategorySpec(_INFO, _W, _NT.NOTIFICATION_TYPE_TRADE),
    _E.NOTIFICATION_CATEGORY_TAKE_PROFIT_HIT: CategorySpec(_INFO, _W, _NT.NOTIFICATION_TYPE_TRADE),
    _E.NOTIFICATION_CATEGORY_RECONCILIATION_DRIFT: CategorySpec(
        _ACT, _MW, _NT.NOTIFICATION_TYPE_WARNING
    ),
    # Strategy lifecycle
    _E.NOTIFICATION_CATEGORY_EXECUTION_STARTED: CategorySpec(
        _INFO, _NONE, _NT.NOTIFICATION_TYPE_SUCCESS
    ),
    _E.NOTIFICATION_CATEGORY_EXECUTION_STOPPED: CategorySpec(
        _INFO, _NONE, _NT.NOTIFICATION_TYPE_INFO
    ),
    _E.NOTIFICATION_CATEGORY_FUNDING_FAILED: CategorySpec(_ACT, _M, _NT.NOTIFICATION_TYPE_ERROR),
    _E.NOTIFICATION_CATEGORY_SLEEVE_RELEASE_DEFERRED: CategorySpec(
        _CRIT, _M, _NT.NOTIFICATION_TYPE_ERROR
    ),
    _E.NOTIFICATION_CATEGORY_EXECUTION_CANCELLED: CategorySpec(
        _INFO, _NONE, _NT.NOTIFICATION_TYPE_INFO
    ),
    _E.NOTIFICATION_CATEGORY_PLAN_LIMIT_REACHED: CategorySpec(
        _INFO, _NONE, _NT.NOTIFICATION_TYPE_INFO
    ),
    # Backtest
    _E.NOTIFICATION_CATEGORY_BACKTEST_COMPLETED: CategorySpec(
        _INFO, _NONE, _NT.NOTIFICATION_TYPE_SUCCESS
    ),
    _E.NOTIFICATION_CATEGORY_BACKTEST_FAILED: CategorySpec(
        _ACT, _NONE, _NT.NOTIFICATION_TYPE_ERROR
    ),
    # Billing
    _E.NOTIFICATION_CATEGORY_PAYMENT_SUCCEEDED: CategorySpec(_INFO, _M, _NT.NOTIFICATION_TYPE_INFO),
    _E.NOTIFICATION_CATEGORY_PAYMENT_FAILED: CategorySpec(_CRIT, _M, _NT.NOTIFICATION_TYPE_ERROR),
    _E.NOTIFICATION_CATEGORY_TRIAL_ENDING: CategorySpec(_ACT, _M, _NT.NOTIFICATION_TYPE_WARNING),
    _E.NOTIFICATION_CATEGORY_SUBSCRIPTION_UPDATED: CategorySpec(
        _INFO, _M, _NT.NOTIFICATION_TYPE_INFO
    ),
    _E.NOTIFICATION_CATEGORY_SUBSCRIPTION_CANCELED: CategorySpec(
        _INFO, _M, _NT.NOTIFICATION_TYPE_INFO
    ),
    # Auth and security
    _E.NOTIFICATION_CATEGORY_WELCOME: CategorySpec(_INFO, _M, _NT.NOTIFICATION_TYPE_INFO),
    _E.NOTIFICATION_CATEGORY_PASSWORD_CHANGED: CategorySpec(_SEC, _M, _NT.NOTIFICATION_TYPE_SYSTEM),
    _E.NOTIFICATION_CATEGORY_ACCOUNT_LOCKED: CategorySpec(_SEC, _M, _NT.NOTIFICATION_TYPE_SYSTEM),
    _E.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION: CategorySpec(
        _SEC, _M, _NT.NOTIFICATION_TYPE_SYSTEM
    ),
    _E.NOTIFICATION_CATEGORY_PASSWORD_RESET: CategorySpec(_SEC, _M, _NT.NOTIFICATION_TYPE_SYSTEM),
    # Agent
    _E.NOTIFICATION_CATEGORY_CONFIRMATION_PENDING: CategorySpec(
        _ACT, _NONE, _NT.NOTIFICATION_TYPE_INFO
    ),
    # Service-generated
    _E.NOTIFICATION_CATEGORY_PRICE_ALERT_TRIGGERED: CategorySpec(
        _INFO, _NONE, _NT.NOTIFICATION_TYPE_ALERT
    ),
    _E.NOTIFICATION_CATEGORY_WEBHOOK_DISABLED: CategorySpec(_ACT, _M, _NT.NOTIFICATION_TYPE_SYSTEM),
}

_FALLBACK = CategorySpec(_INFO, _NONE, _NT.NOTIFICATION_TYPE_SYSTEM)

# Severities whose email delivery cannot be opted out of.
PINNED_SEVERITIES: frozenset[int] = frozenset({_CRIT, _SEC})


def spec_for(category: Category) -> CategorySpec:
    return CATEGORY_SPECS.get(category, _FALLBACK)


def effective_severity(category: Category, event_severity: int) -> int:
    return event_severity or spec_for(category).severity


def channels_for(
    category: Category,
    severity: int,
    channel_prefs: dict[ChannelType, dict[str, Any] | None],
) -> frozenset[ChannelType]:
    """Resolve external target channels: defaults, narrowed by prefs, widened by pins.

    ``channel_prefs`` maps channel type to the ``notification_channels`` row's
    state: ``None`` for a disabled row (drops the channel), a dict for an
    enabled row whose optional ``categories`` list narrows what it receives.
    Channels absent from the dict keep their category defaults.
    """
    targets = set(spec_for(category).channels)
    for channel, prefs in channel_prefs.items():
        if prefs is None:
            targets.discard(channel)
            continue
        allowed = prefs.get("categories")
        if isinstance(allowed, list) and category not in allowed:
            targets.discard(channel)
    if severity in PINNED_SEVERITIES:
        targets.add(EMAIL)
    return frozenset(targets)
