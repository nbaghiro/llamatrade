"""Emergency circuit breaker for trading sessions.

The circuit breaker monitors trading activity and automatically pauses
trading when critical conditions are detected:
- Consecutive losing trades
- Daily loss limit breaches
- Maximum drawdown exceeded
- Excessive API/order errors

Once triggered, the circuit breaker enters a cooldown period before
allowing trading to resume (either automatically or manually).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from prometheus_client import Counter

logger = logging.getLogger(__name__)


class CircuitBreakerReason(StrEnum):
    """Reasons for circuit breaker activation."""

    CONSECUTIVE_LOSSES = "consecutive_losses"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DRAWDOWN_LIMIT = "drawdown_limit"
    ORDER_ERRORS = "order_errors"
    API_ERRORS = "api_errors"
    MANUAL = "manual"


class CircuitBreakerState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Triggered, trading paused
    HALF_OPEN = "half_open"  # Cooldown complete, testing


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker thresholds.

    Attributes:
        max_consecutive_losses: Number of consecutive losses before triggering.
        max_daily_loss_percent: Daily loss as percentage of equity to trigger.
        max_drawdown_percent: Maximum drawdown percentage to trigger.
        max_order_errors: Number of order errors in window before triggering.
        max_api_errors: Number of API errors in window before triggering.
        error_window_seconds: Time window for counting errors.
        cooldown_seconds: Time before auto-reset after triggering.
        auto_reset: Whether to automatically reset after cooldown.
    """

    max_consecutive_losses: int = 5
    max_daily_loss_percent: float = 5.0
    max_drawdown_percent: float = 10.0
    max_order_errors: int = 5
    max_api_errors: int = 10
    error_window_seconds: int = 300  # 5 minutes
    cooldown_seconds: int = 300  # 5 minutes
    auto_reset: bool = False  # Require manual reset by default


@dataclass
class CircuitBreakerStatus:
    """Current status of the circuit breaker."""

    state: CircuitBreakerState
    triggered_at: datetime | None = None
    triggered_reason: CircuitBreakerReason | None = None
    triggered_details: dict[str, Any] | None = None
    cooldown_remaining_seconds: int | None = None
    can_resume: bool = True


@dataclass
class ErrorTracker:
    """Tracks errors within a time window."""

    errors: list[float] = field(default_factory=lambda: [])  # Timestamps of errors
    window_seconds: int = 300

    def add_error(self) -> None:
        """Record an error."""
        self.errors.append(time.time())

    def count_recent(self) -> int:
        """Count errors within the window."""
        cutoff = time.time() - self.window_seconds
        self.errors = [t for t in self.errors if t > cutoff]
        return len(self.errors)

    def reset(self) -> None:
        """Clear all errors."""
        self.errors.clear()


class CircuitBreakerCallback(Protocol):
    """Callback protocol for circuit breaker events."""

    async def on_circuit_breaker_triggered(
        self,
        tenant_id: UUID,
        session_id: UUID,
        reason: str,
        details: dict[str, Any],
    ) -> None: ...

    async def on_circuit_breaker_reset(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> None: ...


class CircuitBreaker:
    """Emergency circuit breaker for trading sessions.

    Monitors trading activity and automatically triggers when
    critical thresholds are exceeded. Once triggered, trading
    is paused until the circuit breaker is reset.

    Usage:
        cb = CircuitBreaker(config, tenant_id, session_id)

        # Check before processing signals
        if not cb.can_trade():
            return  # Trading paused

        # Record events
        cb.record_trade(is_win=False)
        cb.record_order_error()

        # Check status
        status = cb.get_status()
        if status.state == CircuitBreakerState.OPEN:
            print(f"Triggered: {status.triggered_reason}")
    """

    def __init__(
        self,
        config: CircuitBreakerConfig,
        tenant_id: UUID,
        session_id: UUID,
        callback: CircuitBreakerCallback | None = None,
        starting_equity: float = 100000.0,
    ):
        self.config = config
        self.tenant_id = tenant_id
        self.session_id = session_id
        self.callback = callback
        self.starting_equity = starting_equity

        # State
        self._state = CircuitBreakerState.CLOSED
        self._triggered_at: datetime | None = None
        self._triggered_reason: CircuitBreakerReason | None = None
        self._triggered_details: dict[str, Any] | None = None

        # Tracking
        self._consecutive_losses = 0
        self._daily_pnl = 0.0
        self._current_equity = starting_equity
        self._peak_equity = starting_equity
        self._order_errors = ErrorTracker(window_seconds=config.error_window_seconds)
        self._api_errors = ErrorTracker(window_seconds=config.error_window_seconds)

        # Cooldown task
        self._cooldown_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._state

    @property
    def is_triggered(self) -> bool:
        """Check if circuit breaker is triggered."""
        return self._state == CircuitBreakerState.OPEN

    def can_trade(self) -> bool:
        """Check if trading is allowed.

        Returns True if circuit breaker is closed or half-open.
        """
        return self._state != CircuitBreakerState.OPEN

    def get_status(self) -> CircuitBreakerStatus:
        """Get detailed circuit breaker status."""
        cooldown_remaining = None
        if self._state == CircuitBreakerState.OPEN and self._triggered_at:
            elapsed = (datetime.now(UTC) - self._triggered_at).total_seconds()
            remaining = self.config.cooldown_seconds - elapsed
            cooldown_remaining = max(0, int(remaining))

        return CircuitBreakerStatus(
            state=self._state,
            triggered_at=self._triggered_at,
            triggered_reason=self._triggered_reason,
            triggered_details=self._triggered_details,
            cooldown_remaining_seconds=cooldown_remaining,
            can_resume=cooldown_remaining == 0 if cooldown_remaining is not None else True,
        )

    async def record_trade(self, is_win: bool, pnl: float = 0.0) -> None:
        """Record a completed trade.

        Args:
            is_win: Whether the trade was profitable.
            pnl: Realized P&L from the trade.
        """
        if is_win:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1

        self._daily_pnl += pnl
        self._current_equity += pnl

        # Update peak equity (only track increases)
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity

        # Check consecutive losses
        if self._consecutive_losses >= self.config.max_consecutive_losses:
            await self._trigger(
                CircuitBreakerReason.CONSECUTIVE_LOSSES,
                {
                    "consecutive_losses": self._consecutive_losses,
                    "threshold": self.config.max_consecutive_losses,
                },
            )
            return

        # Check daily loss
        daily_loss_percent = abs(self._daily_pnl / self.starting_equity * 100)
        if self._daily_pnl < 0 and daily_loss_percent >= self.config.max_daily_loss_percent:
            await self._trigger(
                CircuitBreakerReason.DAILY_LOSS_LIMIT,
                {
                    "daily_loss": self._daily_pnl,
                    "daily_loss_percent": daily_loss_percent,
                    "threshold_percent": self.config.max_daily_loss_percent,
                },
            )
            return

        # Check drawdown
        if self._peak_equity > 0:
            drawdown_percent = (self._peak_equity - self._current_equity) / self._peak_equity * 100
            if drawdown_percent >= self.config.max_drawdown_percent:
                await self._trigger(
                    CircuitBreakerReason.DRAWDOWN_LIMIT,
                    {
                        "current_equity": self._current_equity,
                        "peak_equity": self._peak_equity,
                        "drawdown_percent": drawdown_percent,
                        "threshold_percent": self.config.max_drawdown_percent,
                    },
                )

    async def record_order_error(self, error_message: str | None = None) -> None:
        """Record an order submission error.

        Args:
            error_message: Optional error message for details.
        """
        self._order_errors.add_error()
        error_count = self._order_errors.count_recent()

        if error_count >= self.config.max_order_errors:
            await self._trigger(
                CircuitBreakerReason.ORDER_ERRORS,
                {
                    "error_count": error_count,
                    "threshold": self.config.max_order_errors,
                    "window_seconds": self.config.error_window_seconds,
                    "last_error": error_message,
                },
            )

    async def record_api_error(self, error_message: str | None = None) -> None:
        """Record an API error.

        Args:
            error_message: Optional error message for details.
        """
        self._api_errors.add_error()
        error_count = self._api_errors.count_recent()

        if error_count >= self.config.max_api_errors:
            await self._trigger(
                CircuitBreakerReason.API_ERRORS,
                {
                    "error_count": error_count,
                    "threshold": self.config.max_api_errors,
                    "window_seconds": self.config.error_window_seconds,
                    "last_error": error_message,
                },
            )

    def update_equity(self, equity: float, daily_pnl: float | None = None) -> None:
        """Update current equity and optionally daily P&L.

        Called during equity sync to keep drawdown tracking accurate.
        """
        self._current_equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity
        if daily_pnl is not None:
            self._daily_pnl = daily_pnl

    async def check_thresholds(self) -> bool:
        """Check all thresholds without recording new events.

        Returns True if circuit breaker was triggered.
        Useful for periodic health checks.
        """
        if self._state == CircuitBreakerState.OPEN:
            return True

        # Check drawdown
        if self._peak_equity > 0:
            drawdown_percent = (self._peak_equity - self._current_equity) / self._peak_equity * 100
            if drawdown_percent >= self.config.max_drawdown_percent:
                await self._trigger(
                    CircuitBreakerReason.DRAWDOWN_LIMIT,
                    {
                        "current_equity": self._current_equity,
                        "peak_equity": self._peak_equity,
                        "drawdown_percent": drawdown_percent,
                        "threshold_percent": self.config.max_drawdown_percent,
                    },
                )
                return True

        # Check daily loss
        if self._daily_pnl < 0:
            daily_loss_percent = abs(self._daily_pnl / self.starting_equity * 100)
            if daily_loss_percent >= self.config.max_daily_loss_percent:
                await self._trigger(
                    CircuitBreakerReason.DAILY_LOSS_LIMIT,
                    {
                        "daily_loss": self._daily_pnl,
                        "daily_loss_percent": daily_loss_percent,
                        "threshold_percent": self.config.max_daily_loss_percent,
                    },
                )
                return True

        return False

    async def manual_trigger(self, reason: str | None = None) -> None:
        """Manually trigger the circuit breaker.

        Args:
            reason: Optional reason for manual trigger.
        """
        await self._trigger(
            CircuitBreakerReason.MANUAL,
            {"reason": reason or "Manual emergency stop"},
        )

    async def reset(self, force: bool = False) -> bool:
        """Reset the circuit breaker to allow trading.

        Args:
            force: If True, reset even if cooldown hasn't elapsed.

        Returns:
            True if reset was successful.
        """
        if self._state == CircuitBreakerState.CLOSED:
            return True

        if not force and self._triggered_at:
            elapsed = (datetime.now(UTC) - self._triggered_at).total_seconds()
            if elapsed < self.config.cooldown_seconds:
                logger.warning(
                    f"Cannot reset circuit breaker: cooldown has "
                    f"{self.config.cooldown_seconds - elapsed:.0f}s remaining"
                )
                return False

        # Cancel any pending cooldown task
        if self._cooldown_task:
            self._cooldown_task.cancel()
            try:
                await self._cooldown_task
            except asyncio.CancelledError:
                pass
            self._cooldown_task = None

        # Reset state
        self._state = CircuitBreakerState.CLOSED
        self._triggered_at = None
        self._triggered_reason = None
        self._triggered_details = None

        # Reset error trackers (but not trade tracking)
        self._order_errors.reset()
        self._api_errors.reset()

        logger.info(
            f"Circuit breaker reset for session {self.session_id}",
            extra={"tenant_id": str(self.tenant_id), "session_id": str(self.session_id)},
        )

        # Notify callback
        if self.callback:
            try:
                await self.callback.on_circuit_breaker_reset(
                    tenant_id=self.tenant_id,
                    session_id=self.session_id,
                )
            except Exception as e:
                logger.error(f"Error in circuit breaker reset callback: {e}")

        return True

    def reset_daily_tracking(self, new_starting_equity: float | None = None) -> None:
        """Reset daily tracking at start of new trading day.

        Call this at market open to reset daily loss tracking.
        """
        if new_starting_equity:
            self.starting_equity = new_starting_equity
        self._daily_pnl = 0.0
        self._consecutive_losses = 0
        self._peak_equity = self._current_equity

    async def _trigger(self, reason: CircuitBreakerReason, details: dict[str, Any]) -> None:
        """Trigger the circuit breaker.

        Args:
            reason: Reason for triggering.
            details: Additional details about the trigger.
        """
        if self._state == CircuitBreakerState.OPEN:
            return  # Already triggered

        self._state = CircuitBreakerState.OPEN
        self._triggered_at = datetime.now(UTC)
        self._triggered_reason = reason
        self._triggered_details = details

        logger.warning(
            f"Circuit breaker triggered: {reason.value}",
            extra={
                "tenant_id": str(self.tenant_id),
                "session_id": str(self.session_id),
                "reason": reason.value,
                "details": details,
            },
        )

        # Record metric
        CIRCUIT_BREAKER_TRIGGERED_TOTAL.labels(reason=reason.value).inc()

        # Notify callback
        if self.callback:
            try:
                await self.callback.on_circuit_breaker_triggered(
                    tenant_id=self.tenant_id,
                    session_id=self.session_id,
                    reason=reason.value,
                    details=details,
                )
            except Exception as e:
                logger.error(f"Error in circuit breaker trigger callback: {e}")

        # Start cooldown if auto-reset is enabled
        if self.config.auto_reset:
            self._cooldown_task = asyncio.create_task(self._cooldown_timer())

    async def _cooldown_timer(self) -> None:
        """Wait for cooldown period and then reset."""
        try:
            await asyncio.sleep(self.config.cooldown_seconds)
            if self._state == CircuitBreakerState.OPEN:
                self._state = CircuitBreakerState.HALF_OPEN
                logger.info(
                    "Circuit breaker cooldown complete, entering half-open state",
                    extra={
                        "tenant_id": str(self.tenant_id),
                        "session_id": str(self.session_id),
                    },
                )
                # Auto-reset after cooldown
                await self.reset(force=True)
        except asyncio.CancelledError:
            pass


# Prometheus metrics for circuit breaker events
CIRCUIT_BREAKER_TRIGGERED_TOTAL = Counter(
    "trading_circuit_breaker_triggered_total",
    "Circuit breaker trigger events",
    ["reason"],
)

CIRCUIT_BREAKER_RESETS_TOTAL = Counter(
    "trading_circuit_breaker_resets_total",
    "Circuit breaker reset events",
)


def create_circuit_breaker(
    tenant_id: UUID,
    session_id: UUID,
    callback: CircuitBreakerCallback | None = None,
    starting_equity: float = 100000.0,
    config: CircuitBreakerConfig | None = None,
) -> CircuitBreaker:
    """Factory function to create a circuit breaker with default config.

    Args:
        tenant_id: Tenant identifier.
        session_id: Trading session identifier.
        callback: Optional callback for circuit breaker events.
        starting_equity: Starting equity for percentage calculations.
        config: Optional custom configuration.

    Returns:
        Configured CircuitBreaker instance.
    """
    return CircuitBreaker(
        config=config or CircuitBreakerConfig(),
        tenant_id=tenant_id,
        session_id=session_id,
        callback=callback,
        starting_equity=starting_equity,
    )
