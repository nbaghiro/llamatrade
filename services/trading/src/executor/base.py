"""Base executor mixin - shared logic for order submission.

This module extracts common functionality between OrderExecutor and
EventSourcedOrderExecutor to reduce code duplication.
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import TradingClient
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_STATUS_ACCEPTED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_SUBMITTED,
    OrderStatus,
)

from src.metrics import record_order_submission
from src.models import (
    OrderCreate,
    RiskCheckResult,
    order_side_to_str,
    order_type_to_str,
    time_in_force_to_str,
)
from src.risk.risk_manager import RiskManager
from src.services.alert_service import AlertService

logger = logging.getLogger(__name__)


class RiskCheckable(Protocol):
    """Protocol for objects that can have risk checks performed."""

    async def check_order(
        self,
        tenant_id: UUID,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        limit_price: float | None = None,
        session_id: UUID | None = None,
    ) -> RiskCheckResult: ...


class AlertNotifier(Protocol):
    """Protocol for objects that can send alerts."""

    async def on_order_rejected(
        self,
        tenant_id: UUID,
        session_id: UUID,
        symbol: str,
        side: str,
        qty: float,
        reason: str,
    ) -> None: ...


@dataclass
class RiskRejection:
    """Result of a risk check rejection."""

    violations: list[str]
    duration: float


@dataclass
class AlpacaSubmitResult:
    """Result of submitting an order to Alpaca."""

    order: AlpacaOrder
    alpaca_order_id: str
    status: str


class OrderSubmissionMixin:
    """Mixin providing shared order submission functionality.

    This mixin extracts common patterns from OrderExecutor and
    EventSourcedOrderExecutor:
    - Risk checking with metrics
    - Alert notifications on rejection
    - Alpaca submission with error handling
    - Status mapping

    Usage:
        class MyExecutor(OrderSubmissionMixin):
            def __init__(
                self,
                alpaca_client: TradingClient,
                risk_manager: RiskManager,
                alert_service: AlertService | None = None,
            ):
                self.alpaca = alpaca_client
                self.risk = risk_manager
                self.alerts = alert_service

            async def submit_order(self, ...):
                # Use mixin methods
                risk_result = await self._run_risk_check(...)
                if not risk_result.passed:
                    await self._handle_risk_rejection(...)
                    raise ValueError(...)
                result = await self._submit_to_alpaca(...)
    """

    # These attributes are expected to be set by the implementing class
    alpaca: TradingClient
    risk: RiskManager
    alerts: AlertService | None

    async def _run_risk_check(
        self,
        tenant_id: UUID,
        order: OrderCreate,
        session_id: UUID | None = None,
    ) -> RiskCheckResult:
        """Run risk checks for an order.

        Args:
            tenant_id: Tenant identifier.
            order: Order to check.
            session_id: Optional session identifier for session-specific limits.

        Returns:
            RiskCheckResult with passed status and any violations.
        """
        return await self.risk.check_order(
            tenant_id=tenant_id,
            symbol=order.symbol,
            side=order_side_to_str(order.side),
            qty=order.qty,
            order_type=order_type_to_str(order.order_type),
            limit_price=order.limit_price,
            session_id=session_id,
        )

    async def _handle_risk_rejection(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderCreate,
        violations: list[str],
        start_time: float,
    ) -> None:
        """Handle a risk check rejection by recording metrics and sending alerts.

        Args:
            tenant_id: Tenant identifier.
            session_id: Trading session identifier.
            order: The rejected order.
            violations: List of risk violations.
            start_time: Time when order processing started (for duration metric).
        """
        # Record rejection metric
        duration = time.perf_counter() - start_time
        record_order_submission(
            side=order_side_to_str(order.side),
            order_type=order_type_to_str(order.order_type),
            status="rejected_risk",
            duration=duration,
        )

        # Send rejection alert
        if self.alerts:
            await self.alerts.on_order_rejected(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=order.symbol,
                side=order_side_to_str(order.side),
                qty=order.qty,
                reason=", ".join(violations),
            )

        logger.warning(
            "Risk check rejected order",
            extra={
                "tenant_id": str(tenant_id),
                "session_id": str(session_id),
                "symbol": order.symbol,
                "side": order_side_to_str(order.side),
                "qty": order.qty,
                "violations": violations,
            },
        )

    async def _submit_to_alpaca(
        self,
        order: OrderCreate,
        client_order_id: str | None = None,
    ) -> AlpacaSubmitResult:
        """Submit an order to Alpaca.

        Args:
            order: Order to submit.
            client_order_id: Optional idempotency key.

        Returns:
            AlpacaSubmitResult with order response and parsed fields.

        Raises:
            Exception: If Alpaca submission fails.
        """
        alpaca_order = await self.alpaca.submit_order(
            symbol=order.symbol,
            qty=order.qty,
            side=order_side_to_str(order.side),
            order_type=order_type_to_str(order.order_type),
            time_in_force=time_in_force_to_str(order.time_in_force),
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            client_order_id=client_order_id,
        )

        return AlpacaSubmitResult(
            order=alpaca_order,
            alpaca_order_id=alpaca_order.id,
            status=alpaca_order.status.value,
        )

    async def _handle_alpaca_rejection(
        self,
        tenant_id: UUID,
        session_id: UUID,
        order: OrderCreate,
        error: Exception,
        start_time: float,
    ) -> None:
        """Handle an Alpaca API rejection by recording metrics and sending alerts.

        Args:
            tenant_id: Tenant identifier.
            session_id: Trading session identifier.
            order: The rejected order.
            error: The exception from Alpaca.
            start_time: Time when order processing started (for duration metric).
        """
        # Record API error metric
        duration = time.perf_counter() - start_time
        record_order_submission(
            side=order_side_to_str(order.side),
            order_type=order_type_to_str(order.order_type),
            status="rejected_api",
            duration=duration,
        )

        # Send rejection alert
        if self.alerts:
            await self.alerts.on_order_rejected(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol=order.symbol,
                side=order_side_to_str(order.side),
                qty=order.qty,
                reason=f"Alpaca API error: {error}",
            )

        logger.error(
            "Alpaca API rejected order",
            extra={
                "tenant_id": str(tenant_id),
                "session_id": str(session_id),
                "symbol": order.symbol,
                "side": order_side_to_str(order.side),
                "qty": order.qty,
                "error": str(error),
            },
        )

    def _record_submission_success(
        self,
        order: OrderCreate,
        start_time: float,
    ) -> None:
        """Record successful order submission metric.

        Args:
            order: The submitted order.
            start_time: Time when order processing started.
        """
        duration = time.perf_counter() - start_time
        record_order_submission(
            side=order_side_to_str(order.side),
            order_type=order_type_to_str(order.order_type),
            status="success",
            duration=duration,
        )

    @staticmethod
    def _map_alpaca_status(alpaca_status: str) -> OrderStatus.ValueType:
        """Map Alpaca order status to OrderStatus proto value.

        Args:
            alpaca_status: Status string from Alpaca API.

        Returns:
            OrderStatus proto value.
        """
        mapping: dict[str, OrderStatus.ValueType] = {
            "new": ORDER_STATUS_SUBMITTED,
            "accepted": ORDER_STATUS_ACCEPTED,
            "pending_new": ORDER_STATUS_PENDING,
            "accepted_for_bidding": ORDER_STATUS_ACCEPTED,
            "stopped": ORDER_STATUS_CANCELLED,
            "rejected": ORDER_STATUS_REJECTED,
            "suspended": ORDER_STATUS_PENDING,
            "calculated": ORDER_STATUS_PENDING,
            "partially_filled": ORDER_STATUS_PARTIAL,
            "filled": ORDER_STATUS_FILLED,
            "done_for_day": ORDER_STATUS_EXPIRED,
            "canceled": ORDER_STATUS_CANCELLED,
            "expired": ORDER_STATUS_EXPIRED,
            "replaced": ORDER_STATUS_CANCELLED,
            "pending_cancel": ORDER_STATUS_PENDING,
            "pending_replace": ORDER_STATUS_PENDING,
        }
        return mapping.get(alpaca_status.lower()) or ORDER_STATUS_PENDING

    def _get_current_utc_time(self) -> datetime:
        """Get current UTC time.

        Extracted as a method for easier testing.
        """
        return datetime.now(UTC)
