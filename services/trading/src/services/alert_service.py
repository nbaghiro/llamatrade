"""Alert service - publishes trading events onto the notification stream.

A thin producer facade: each ``on_*`` keeps its call-site signature and maps
the event to a ``NotificationCategory`` with machine-readable fields. Delivery
(in-app row, email, webhooks) is the notification service's job; publishes are
fire-and-forget and never raise into the trading path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from llamatrade_events.catalog.notifications import (
    NotificationEvent,
    NotificationEvents,
    shared_notification_events,
)
from llamatrade_proto.generated import events_pb2

from src.models import order_side_to_str

if TYPE_CHECKING:
    from llamatrade_db.models.trading import Order

logger = logging.getLogger(__name__)

_E = events_pb2


class AlertPriority(StrEnum):
    """Priority levels for alerts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(StrEnum):
    """Types of alerts."""

    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_DRIFT = "position_drift"
    RECONCILIATION_DRIFT = "reconciliation_drift"
    SLEEVE_FROZEN = "sleeve_frozen"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    RISK_BREACH = "risk_breach"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DRAWDOWN_LIMIT = "drawdown_limit"
    STRATEGY_ERROR = "strategy_error"
    EVALUATION_STALLED = "evaluation_stalled"
    SYMBOL_NOT_TRADABLE = "symbol_not_tradable"
    SESSION_STARTED = "session_started"
    SESSION_STOPPED = "session_stopped"
    SESSION_ERROR = "session_error"
    CONNECTION_LOST = "connection_lost"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker_triggered"
    CIRCUIT_BREAKER_RESET = "circuit_breaker_reset"


CATEGORY_BY_ALERT_TYPE: dict[AlertType, events_pb2.NotificationCategory.ValueType] = {
    AlertType.ORDER_FILLED: _E.NOTIFICATION_CATEGORY_ORDER_FILLED,
    AlertType.ORDER_REJECTED: _E.NOTIFICATION_CATEGORY_ORDER_REJECTED,
    AlertType.POSITION_OPENED: _E.NOTIFICATION_CATEGORY_POSITION_OPENED,
    AlertType.POSITION_CLOSED: _E.NOTIFICATION_CATEGORY_POSITION_CLOSED,
    AlertType.POSITION_DRIFT: _E.NOTIFICATION_CATEGORY_POSITION_DRIFT,
    AlertType.RECONCILIATION_DRIFT: _E.NOTIFICATION_CATEGORY_RECONCILIATION_DRIFT,
    AlertType.SLEEVE_FROZEN: _E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN,
    AlertType.STOP_LOSS_HIT: _E.NOTIFICATION_CATEGORY_STOP_LOSS_HIT,
    AlertType.TAKE_PROFIT_HIT: _E.NOTIFICATION_CATEGORY_TAKE_PROFIT_HIT,
    AlertType.RISK_BREACH: _E.NOTIFICATION_CATEGORY_RISK_BREACH,
    AlertType.DAILY_LOSS_LIMIT: _E.NOTIFICATION_CATEGORY_RISK_BREACH,
    AlertType.DRAWDOWN_LIMIT: _E.NOTIFICATION_CATEGORY_RISK_BREACH,
    AlertType.STRATEGY_ERROR: _E.NOTIFICATION_CATEGORY_STRATEGY_ERROR,
    AlertType.EVALUATION_STALLED: _E.NOTIFICATION_CATEGORY_EVALUATION_STALLED,
    AlertType.SYMBOL_NOT_TRADABLE: _E.NOTIFICATION_CATEGORY_SYMBOL_NOT_TRADABLE,
    AlertType.SESSION_STARTED: _E.NOTIFICATION_CATEGORY_SESSION_STARTED,
    AlertType.SESSION_STOPPED: _E.NOTIFICATION_CATEGORY_SESSION_STOPPED,
    AlertType.SESSION_ERROR: _E.NOTIFICATION_CATEGORY_SESSION_ERROR,
    AlertType.CONNECTION_LOST: _E.NOTIFICATION_CATEGORY_CONNECTION_LOST,
    AlertType.CIRCUIT_BREAKER_TRIGGERED: _E.NOTIFICATION_CATEGORY_CIRCUIT_BREAKER_TRIGGERED,
    AlertType.CIRCUIT_BREAKER_RESET: _E.NOTIFICATION_CATEGORY_CIRCUIT_BREAKER_RESET,
}


@dataclass
class Alert:
    """One trading event on its way to the notification stream."""

    tenant_id: UUID
    alert_type: AlertType
    priority: AlertPriority
    session_id: UUID | None = None
    symbol: str | None = None
    reason: str | None = None
    amount: str | None = None
    metadata: dict[str, Any] = field(default_factory=lambda: {})
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class AlertService:
    """Publishes trading alerts onto the ``notifications`` stream."""

    def __init__(self, events: NotificationEvents | None = None) -> None:
        self._events = events or shared_notification_events()

    async def send(self, alert: Alert) -> bool:
        """Publish one alert; fire-and-forget, returns False on publish failure."""
        event = NotificationEvent(
            category=CATEGORY_BY_ALERT_TYPE[alert.alert_type],
            severity=(
                _E.NOTIFICATION_SEVERITY_CRITICAL
                if alert.priority is AlertPriority.CRITICAL
                else _E.NOTIFICATION_SEVERITY_UNSPECIFIED
            ),
            session_id=str(alert.session_id) if alert.session_id else "",
            symbol=alert.symbol or "",
            reason=alert.reason or "",
            amount=alert.amount or "",
            extra={k: str(v) for k, v in alert.metadata.items() if v is not None},
        )
        cursor = await self._events.publish_safe(
            event,
            tenant_id=str(alert.tenant_id),
            # Each call is one occurrence; uniqueness comes from the envelope id.
            event_id=None if _is_deterministic(alert) else _occurrence_id(),
            dedup_parts=_dedup_parts(alert) if _is_deterministic(alert) else (),
        )
        return cursor is not None

    async def on_order_filled(self, tenant_id: UUID, session_id: UUID, order: Order) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.ORDER_FILLED,
                priority=AlertPriority.LOW,
                symbol=order.symbol,
                reason=f"{order_side_to_str(order.side)} {order.filled_qty} {order.symbol}",
                amount=str(order.filled_avg_price) if order.filled_avg_price else None,
                metadata={"order_id": str(order.id), "client_order_id": order.client_order_id},
            )
        )

    async def on_order_rejected(
        self, tenant_id: UUID, session_id: UUID, symbol: str, side: str, qty: float, reason: str
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.ORDER_REJECTED,
                priority=AlertPriority.MEDIUM,
                symbol=symbol,
                reason=reason,
                metadata={"side": side, "qty": qty},
            )
        )

    async def on_stop_loss_hit(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        qty: float,
        stop_price: float,
        filled_price: float,
        pnl: float | None = None,
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.STOP_LOSS_HIT,
                priority=AlertPriority.HIGH,
                symbol=symbol,
                amount=str(filled_price),
                metadata={"qty": qty, "stop_price": stop_price, "pnl": pnl},
            )
        )

    async def on_take_profit_hit(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        qty: float,
        target_price: float,
        filled_price: float,
        pnl: float | None = None,
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.TAKE_PROFIT_HIT,
                priority=AlertPriority.MEDIUM,
                symbol=symbol,
                amount=str(filled_price),
                metadata={"qty": qty, "target_price": target_price, "pnl": pnl},
            )
        )

    async def on_position_opened(
        self, tenant_id: UUID, session_id: UUID, symbol: str, side: str, qty: float, price: float
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.POSITION_OPENED,
                priority=AlertPriority.LOW,
                symbol=symbol,
                amount=str(price),
                metadata={"side": side, "qty": qty},
            )
        )

    async def on_position_closed(
        self, tenant_id: UUID, session_id: UUID, symbol: str, qty: float, pnl: float
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.POSITION_CLOSED,
                priority=AlertPriority.LOW,
                symbol=symbol,
                amount=f"{pnl:.2f}",
                metadata={"qty": qty, "pnl": pnl},
            )
        )

    async def on_position_drift(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        drift_type: str,
        local_qty: float,
        broker_qty: float,
        action: str,
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.POSITION_DRIFT,
                priority=(
                    AlertPriority.CRITICAL if drift_type == "side_mismatch" else AlertPriority.HIGH
                ),
                symbol=symbol,
                reason=f"{drift_type}: local {local_qty} vs broker {broker_qty} ({action})",
                metadata={
                    "drift_type": drift_type,
                    "local_qty": local_qty,
                    "broker_qty": broker_qty,
                    "action": action,
                },
            )
        )

    async def on_reconciliation_drift(
        self,
        tenant_id: UUID,
        account_id: UUID,
        symbol: str,
        drift_kind: str,
        ledger_qty: float,
        broker_qty: float,
        session_id: UUID | None = None,
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.RECONCILIATION_DRIFT,
                priority=(
                    AlertPriority.CRITICAL
                    if drift_kind == "missing_at_broker"
                    else AlertPriority.HIGH
                ),
                symbol=symbol,
                reason=f"{drift_kind}: ledger {ledger_qty} vs broker {broker_qty}",
                metadata={
                    "account_id": str(account_id),
                    "drift_kind": drift_kind,
                    "ledger_qty": ledger_qty,
                    "broker_qty": broker_qty,
                },
            )
        )

    async def on_sleeve_frozen(
        self, tenant_id: UUID, sleeve_id: UUID, reason: str, session_id: UUID | None = None
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.SLEEVE_FROZEN,
                priority=AlertPriority.CRITICAL,
                reason=reason,
                metadata={"sleeve_id": str(sleeve_id)},
            )
        )

    async def on_risk_breach(
        self, tenant_id: UUID, session_id: UUID, breach_type: str, details: dict[str, Any]
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.RISK_BREACH,
                priority=AlertPriority.HIGH,
                symbol=str(details.get("symbol") or "") or None,
                reason=breach_type,
                metadata=details,
            )
        )

    async def on_daily_loss_limit(
        self, tenant_id: UUID, session_id: UUID, current_loss: float, limit: float
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.DAILY_LOSS_LIMIT,
                priority=AlertPriority.CRITICAL,
                reason=f"daily loss ${current_loss:.2f} reached the ${limit:.2f} limit",
                metadata={"current_loss": current_loss, "limit": limit},
            )
        )

    async def on_drawdown_limit(
        self, tenant_id: UUID, session_id: UUID, current_drawdown: float, limit: float
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.DRAWDOWN_LIMIT,
                priority=AlertPriority.CRITICAL,
                reason=f"drawdown {current_drawdown:.1f}% reached the {limit:.1f}% limit",
                metadata={"current_drawdown": current_drawdown, "limit": limit},
            )
        )

    async def on_strategy_error(self, tenant_id: UUID, session_id: UUID, error: str) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.STRATEGY_ERROR,
                priority=AlertPriority.HIGH,
                reason=error,
            )
        )

    async def on_evaluation_stalled(
        self, tenant_id: UUID, session_id: UUID, symbols: list[str], stale_seconds: float
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.EVALUATION_STALLED,
                priority=AlertPriority.HIGH,
                reason=f"no complete bar set for {stale_seconds:.0f}s"
                + (f" (waiting on {', '.join(symbols)})" if symbols else ""),
                metadata={"symbols": ",".join(symbols), "stale_seconds": stale_seconds},
            )
        )

    async def on_symbol_not_tradable(
        self, tenant_id: UUID, session_id: UUID, symbol: str, reason: str, description: str
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.SYMBOL_NOT_TRADABLE,
                priority=AlertPriority.HIGH,
                symbol=symbol,
                reason=description or reason,
                metadata={"status": reason},
            )
        )

    async def on_session_started(
        self, tenant_id: UUID, session_id: UUID, strategy_name: str, mode: str
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.SESSION_STARTED,
                priority=AlertPriority.LOW,
                reason=f"{strategy_name} ({mode})",
                metadata={"strategy_name": strategy_name, "mode": mode},
            )
        )

    async def on_session_stopped(
        self, tenant_id: UUID, session_id: UUID, reason: str | None = None
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.SESSION_STOPPED,
                priority=AlertPriority.LOW,
                reason=reason,
            )
        )

    async def on_session_error(self, tenant_id: UUID, session_id: UUID, error: str) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.SESSION_ERROR,
                priority=AlertPriority.CRITICAL,
                reason=error,
            )
        )

    async def on_connection_lost(self, tenant_id: UUID, session_id: UUID, service: str) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.CONNECTION_LOST,
                priority=AlertPriority.HIGH,
                reason=service,
                metadata={"service": service},
            )
        )

    async def on_circuit_breaker_triggered(
        self, tenant_id: UUID, session_id: UUID, reason: str, details: dict[str, Any]
    ) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.CIRCUIT_BREAKER_TRIGGERED,
                priority=AlertPriority.CRITICAL,
                reason=reason,
                metadata=details,
            )
        )

    async def on_circuit_breaker_reset(self, tenant_id: UUID, session_id: UUID) -> None:
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.CIRCUIT_BREAKER_RESET,
                priority=AlertPriority.MEDIUM,
            )
        )


# Alert types where one logical episode may be re-reported (stall/symbol-halt latching): a deterministic id collapses repeats platform-wide.
_DETERMINISTIC_TYPES = frozenset(
    {AlertType.EVALUATION_STALLED, AlertType.SYMBOL_NOT_TRADABLE, AlertType.SLEEVE_FROZEN}
)


def _is_deterministic(alert: Alert) -> bool:
    return alert.alert_type in _DETERMINISTIC_TYPES


def _dedup_parts(alert: Alert) -> tuple[str, ...]:
    parts = [alert.alert_type.value]
    if alert.session_id:
        parts.append(str(alert.session_id))
    if alert.symbol:
        parts.append(alert.symbol)
    if sleeve := alert.metadata.get("sleeve_id"):
        parts.append(str(sleeve))
    return tuple(parts)


def _occurrence_id() -> str:
    return uuid4().hex


def get_alert_service() -> AlertService:
    """FastAPI dependency: a publisher over the shared notification stream."""
    return AlertService()
