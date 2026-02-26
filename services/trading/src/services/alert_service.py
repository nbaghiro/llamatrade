"""Alert service - sends notifications for important trading events."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

import httpx
from fastapi import Depends
from llamatrade_db import get_db
from llamatrade_db.models.notification import Webhook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import OrderResponse

logger = logging.getLogger(__name__)


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
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    RISK_BREACH = "risk_breach"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DRAWDOWN_LIMIT = "drawdown_limit"
    STRATEGY_ERROR = "strategy_error"
    SESSION_STARTED = "session_started"
    SESSION_STOPPED = "session_stopped"
    SESSION_ERROR = "session_error"
    CONNECTION_LOST = "connection_lost"


@dataclass
class Alert:
    """Alert notification."""

    tenant_id: UUID
    alert_type: AlertType
    priority: AlertPriority
    title: str
    message: str
    session_id: UUID | None = None
    symbol: str | None = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class AlertService:
    """Sends notifications for important trading events."""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db
        self._http_client: httpx.AsyncClient | None = None

    async def send(self, alert: Alert) -> bool:
        """Send alert via configured channels."""
        success = True

        # Get webhooks for tenant
        webhooks = await self._get_webhooks(alert.tenant_id)

        for webhook in webhooks:
            if not self._should_send(alert, webhook):
                continue

            try:
                await self._send_webhook(webhook, alert)
            except Exception as e:
                logger.error(f"Failed to send webhook alert: {e}")
                success = False

        return success

    async def on_order_filled(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderResponse,
    ) -> None:
        """Send alert for order fill."""
        price_str = f" @ ${order.filled_avg_price:.2f}" if order.filled_avg_price else ""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.ORDER_FILLED,
                priority=AlertPriority.LOW,
                title=f"Order Filled: {order.side.upper()} {order.symbol}",
                message=f"Filled {order.filled_qty} {order.symbol}{price_str}",
                symbol=order.symbol,
                metadata={
                    "order_id": str(order.id),
                    "filled_qty": order.filled_qty,
                    "filled_price": order.filled_avg_price,
                },
            )
        )

    async def on_order_rejected(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        side: str,
        qty: float,
        reason: str,
    ) -> None:
        """Send alert for order rejection."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.ORDER_REJECTED,
                priority=AlertPriority.MEDIUM,
                title=f"Order Rejected: {side.upper()} {symbol}",
                message=f"Order for {qty} {symbol} rejected: {reason}",
                symbol=symbol,
                metadata={
                    "side": side,
                    "qty": qty,
                    "reason": reason,
                },
            )
        )

    async def on_position_opened(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        side: str,
        qty: float,
        price: float,
    ) -> None:
        """Send alert for position opened."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.POSITION_OPENED,
                priority=AlertPriority.LOW,
                title=f"Position Opened: {side.upper()} {symbol}",
                message=f"Opened {side} position: {qty} {symbol} @ ${price:.2f}",
                symbol=symbol,
                metadata={
                    "side": side,
                    "qty": qty,
                    "price": price,
                },
            )
        )

    async def on_position_closed(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        qty: float,
        pnl: float,
    ) -> None:
        """Send alert for position closed."""
        priority = AlertPriority.MEDIUM if pnl < 0 else AlertPriority.LOW
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.POSITION_CLOSED,
                priority=priority,
                title=f"Position Closed: {symbol}",
                message=f"Closed {qty} {symbol}, P&L: ${pnl:+.2f}",
                symbol=symbol,
                metadata={
                    "qty": qty,
                    "pnl": pnl,
                },
            )
        )

    async def on_risk_breach(
        self,
        tenant_id: UUID,
        session_id: UUID,
        breach_type: str,
        details: dict,
    ) -> None:
        """Send alert for risk limit breach."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.RISK_BREACH,
                priority=AlertPriority.HIGH,
                title="Risk Limit Breached",
                message=f"Risk breach: {breach_type}",
                metadata={
                    "breach_type": breach_type,
                    **details,
                },
            )
        )

    async def on_daily_loss_limit(
        self,
        tenant_id: UUID,
        session_id: UUID,
        current_loss: float,
        limit: float,
    ) -> None:
        """Send alert for daily loss limit exceeded."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.DAILY_LOSS_LIMIT,
                priority=AlertPriority.CRITICAL,
                title="Daily Loss Limit Exceeded",
                message=f"Daily loss ${abs(current_loss):.2f} exceeds limit ${limit:.2f}. Trading paused.",
                metadata={
                    "current_loss": current_loss,
                    "limit": limit,
                },
            )
        )

    async def on_drawdown_limit(
        self,
        tenant_id: UUID,
        session_id: UUID,
        current_drawdown: float,
        limit: float,
    ) -> None:
        """Send alert for drawdown limit exceeded."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.DRAWDOWN_LIMIT,
                priority=AlertPriority.CRITICAL,
                title="Drawdown Limit Exceeded",
                message=f"Drawdown {current_drawdown:.1f}% exceeds limit {limit:.1f}%. Trading paused.",
                metadata={
                    "current_drawdown": current_drawdown,
                    "limit": limit,
                },
            )
        )

    async def on_strategy_error(
        self,
        tenant_id: UUID,
        session_id: UUID,
        error: str,
    ) -> None:
        """Send alert for strategy error."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.STRATEGY_ERROR,
                priority=AlertPriority.CRITICAL,
                title="Strategy Error",
                message=f"Strategy execution error: {error}",
                metadata={
                    "error": error,
                },
            )
        )

    async def on_session_started(
        self,
        tenant_id: UUID,
        session_id: UUID,
        strategy_name: str,
        mode: str,
    ) -> None:
        """Send alert for session start."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.SESSION_STARTED,
                priority=AlertPriority.LOW,
                title="Trading Session Started",
                message=f"Started {mode} trading with strategy: {strategy_name}",
                metadata={
                    "strategy_name": strategy_name,
                    "mode": mode,
                },
            )
        )

    async def on_session_stopped(
        self,
        tenant_id: UUID,
        session_id: UUID,
        reason: str | None = None,
    ) -> None:
        """Send alert for session stop."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.SESSION_STOPPED,
                priority=AlertPriority.MEDIUM,
                title="Trading Session Stopped",
                message="Trading session stopped" + (f": {reason}" if reason else ""),
                metadata={
                    "reason": reason,
                },
            )
        )

    async def on_session_error(
        self,
        tenant_id: UUID,
        session_id: UUID,
        error: str,
    ) -> None:
        """Send alert for session error."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.SESSION_ERROR,
                priority=AlertPriority.CRITICAL,
                title="Trading Session Error",
                message=f"Session error: {error}",
                metadata={
                    "error": error,
                },
            )
        )

    async def on_connection_lost(
        self,
        tenant_id: UUID,
        session_id: UUID,
        service: str,
    ) -> None:
        """Send alert for connection loss."""
        await self.send(
            Alert(
                tenant_id=tenant_id,
                session_id=session_id,
                alert_type=AlertType.CONNECTION_LOST,
                priority=AlertPriority.HIGH,
                title="Connection Lost",
                message=f"Lost connection to {service}",
                metadata={
                    "service": service,
                },
            )
        )

    # ===================
    # Private helpers
    # ===================

    async def _get_webhooks(self, tenant_id: UUID) -> list[Webhook]:
        """Get active webhooks for tenant."""
        if not self.db:
            return []

        stmt = (
            select(Webhook).where(Webhook.tenant_id == tenant_id).where(Webhook.is_active == True)  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _should_send(self, alert: Alert, webhook: Webhook) -> bool:
        """Check if alert should be sent to this webhook."""
        # Check if webhook is configured for this alert type
        if webhook.events:
            if alert.alert_type.value not in webhook.events:
                return False

        return True

    async def _send_webhook(self, webhook: Webhook, alert: Alert) -> None:
        """Send alert to webhook URL."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=10.0)

        payload = {
            "type": alert.alert_type.value,
            "priority": alert.priority.value,
            "title": alert.title,
            "message": alert.message,
            "timestamp": alert.timestamp.isoformat(),
            "metadata": {
                "tenant_id": str(alert.tenant_id),
                "session_id": str(alert.session_id) if alert.session_id else None,
                "symbol": alert.symbol,
                **alert.metadata,
            },
        }

        headers = {"Content-Type": "application/json"}
        if webhook.secret:
            # In production, add HMAC signature
            headers["X-Webhook-Secret"] = webhook.secret

        response = await self._http_client.post(
            webhook.url,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

        logger.info(f"Sent webhook alert to {webhook.url}: {alert.alert_type.value}")

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


async def get_alert_service(
    db: AsyncSession = Depends(get_db),
) -> AlertService:
    """Dependency to get alert service."""
    return AlertService(db=db)
