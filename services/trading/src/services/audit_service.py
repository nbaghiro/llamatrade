"""Audit service - records all trading events for compliance and debugging."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import get_db
from llamatrade_db.models.audit import AuditEventType, AuditLog

from src.models import OrderResponse, RiskCheckResult
from src.runner.runner import Signal


class AuditService:
    """Records all trading events for compliance and debugging."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_signal(
        self,
        tenant_id: UUID,
        session_id: UUID,
        signal: Signal,
    ) -> None:
        """Log signal generation."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.SIGNAL_GENERATED,
            symbol=signal.symbol,
            data={
                "signal_type": signal.type,
                "symbol": signal.symbol,
                "quantity": signal.quantity,
                "price": signal.price,
                "timestamp": signal.timestamp.isoformat(),
            },
            summary=f"Generated {signal.type} signal for {signal.quantity} {signal.symbol} @ ${signal.price:.2f}",
        )

    async def log_signal_rejected(
        self,
        tenant_id: UUID,
        session_id: UUID,
        signal: Signal,
        reason: str,
    ) -> None:
        """Log signal rejection."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.SIGNAL_REJECTED,
            symbol=signal.symbol,
            data={
                "signal_type": signal.type,
                "symbol": signal.symbol,
                "quantity": signal.quantity,
                "price": signal.price,
                "rejection_reason": reason,
            },
            summary=f"Rejected {signal.type} signal for {signal.symbol}: {reason}",
        )

    async def log_order_submitted(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderResponse,
    ) -> None:
        """Log order submission."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.ORDER_SUBMITTED,
            symbol=order.symbol,
            order_id=order.id,
            data={
                "order_id": str(order.id),
                "alpaca_order_id": order.alpaca_order_id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.qty,
                "order_type": order.order_type,
                "limit_price": order.limit_price,
                "stop_price": order.stop_price,
                "status": order.status,
            },
            summary=f"Submitted {order.side} order for {order.qty} {order.symbol}",
        )

    async def log_order_filled(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderResponse,
    ) -> None:
        """Log order fill."""
        event_type = (
            AuditEventType.ORDER_PARTIAL_FILL
            if order.filled_qty < order.qty
            else AuditEventType.ORDER_FILLED
        )

        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=event_type,
            symbol=order.symbol,
            order_id=order.id,
            data={
                "order_id": str(order.id),
                "symbol": order.symbol,
                "side": order.side,
                "filled_qty": order.filled_qty,
                "total_qty": order.qty,
                "filled_avg_price": order.filled_avg_price,
                "status": order.status,
            },
            summary=f"Filled {order.filled_qty}/{order.qty} {order.symbol} @ ${order.filled_avg_price:.2f}"
            if order.filled_avg_price
            else f"Filled {order.filled_qty}/{order.qty} {order.symbol}",
        )

    async def log_order_cancelled(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderResponse,
        reason: str | None = None,
    ) -> None:
        """Log order cancellation."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.ORDER_CANCELLED,
            symbol=order.symbol,
            order_id=order.id,
            data={
                "order_id": str(order.id),
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.qty,
                "filled_qty": order.filled_qty,
                "reason": reason,
            },
            summary=f"Cancelled {order.side} order for {order.symbol}"
            + (f": {reason}" if reason else ""),
        )

    async def log_order_rejected(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        side: str,
        qty: float,
        reason: str,
    ) -> None:
        """Log order rejection."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.ORDER_REJECTED,
            symbol=symbol,
            data={
                "symbol": symbol,
                "side": side,
                "quantity": qty,
                "rejection_reason": reason,
            },
            summary=f"Rejected {side} order for {qty} {symbol}: {reason}",
        )

    async def log_risk_check(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        result: RiskCheckResult,
    ) -> None:
        """Log risk check result."""
        event_type = (
            AuditEventType.RISK_CHECK_PASSED if result.passed else AuditEventType.RISK_CHECK_FAILED
        )

        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=event_type,
            symbol=symbol,
            data={
                "symbol": symbol,
                "passed": result.passed,
                "violations": result.violations,
            },
            summary=f"Risk check {'passed' if result.passed else 'failed'} for {symbol}"
            + (f": {', '.join(result.violations)}" if result.violations else ""),
        )

    async def log_risk_breach(
        self,
        tenant_id: UUID,
        session_id: UUID,
        breach_type: str,
        details: dict[str, Any],
    ) -> None:
        """Log risk limit breach."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.RISK_LIMIT_BREACH,
            data={
                "breach_type": breach_type,
                **details,
            },
            summary=f"Risk limit breach: {breach_type}",
        )

    async def log_position_opened(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
    ) -> None:
        """Log position opened."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.POSITION_OPENED,
            symbol=symbol,
            data={
                "symbol": symbol,
                "side": side,
                "quantity": qty,
                "entry_price": entry_price,
            },
            summary=f"Opened {side} position: {qty} {symbol} @ ${entry_price:.2f}",
        )

    async def log_position_closed(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        qty: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
    ) -> None:
        """Log position closed."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.POSITION_CLOSED,
            symbol=symbol,
            data={
                "symbol": symbol,
                "quantity": qty,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
            },
            summary=f"Closed position: {qty} {symbol}, P&L: ${pnl:+.2f}",
        )

    async def log_session_started(
        self,
        tenant_id: UUID,
        session_id: UUID,
        strategy_id: UUID,
        mode: str,
        symbols: list[str],
    ) -> None:
        """Log session start."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.SESSION_STARTED,
            data={
                "strategy_id": str(strategy_id),
                "mode": mode,
                "symbols": symbols,
            },
            summary=f"Started {mode} trading session for {', '.join(symbols)}",
        )

    async def log_session_stopped(
        self,
        tenant_id: UUID,
        session_id: UUID,
        reason: str | None = None,
    ) -> None:
        """Log session stop."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.SESSION_STOPPED,
            data={
                "reason": reason,
            },
            summary="Stopped trading session" + (f": {reason}" if reason else ""),
        )

    async def log_session_paused(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> None:
        """Log session pause."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.SESSION_PAUSED,
            data={},
            summary="Paused trading session",
        )

    async def log_session_resumed(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> None:
        """Log session resume."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.SESSION_RESUMED,
            data={},
            summary="Resumed trading session",
        )

    async def log_session_error(
        self,
        tenant_id: UUID,
        session_id: UUID,
        error: str,
    ) -> None:
        """Log session error."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.SESSION_ERROR,
            data={
                "error": error,
            },
            summary=f"Session error: {error}",
        )

    async def log_strategy_error(
        self,
        tenant_id: UUID,
        session_id: UUID,
        error: str,
        symbol: str | None = None,
    ) -> None:
        """Log strategy execution error."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.STRATEGY_ERROR,
            symbol=symbol,
            data={
                "error": error,
            },
            summary=f"Strategy error: {error}",
        )

    async def log_connection_lost(
        self,
        tenant_id: UUID,
        session_id: UUID,
        service: str,
    ) -> None:
        """Log connection loss."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.CONNECTION_LOST,
            data={
                "service": service,
            },
            summary=f"Lost connection to {service}",
        )

    async def log_connection_restored(
        self,
        tenant_id: UUID,
        session_id: UUID,
        service: str,
    ) -> None:
        """Log connection restoration."""
        await self._log(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=AuditEventType.CONNECTION_RESTORED,
            data={
                "service": service,
            },
            summary=f"Restored connection to {service}",
        )

    # ===================
    # Private helpers
    # ===================

    async def _log(
        self,
        tenant_id: UUID,
        event_type: AuditEventType,
        data: dict[str, Any],
        session_id: UUID | None = None,
        symbol: str | None = None,
        order_id: UUID | None = None,
        summary: str | None = None,
        source: str = "trading-service",
    ) -> None:
        """Create an audit log entry."""
        log = AuditLog(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=event_type.value,
            timestamp=datetime.now(UTC),
            symbol=symbol,
            order_id=order_id,
            data=data,
            summary=summary,
            source=source,
        )
        self.db.add(log)
        await self.db.commit()


async def get_audit_service(
    db: AsyncSession = Depends(get_db),
) -> AuditService:
    """Dependency to get audit service."""
    return AuditService(db=db)
