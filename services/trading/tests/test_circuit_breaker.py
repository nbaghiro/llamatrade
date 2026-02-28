"""Tests for emergency circuit breaker."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from src.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerReason,
    CircuitBreakerState,
    CircuitBreakerStatus,
    ErrorTracker,
    create_circuit_breaker,
)


class TestErrorTracker:
    """Tests for ErrorTracker."""

    def test_add_and_count_errors(self):
        """Test adding and counting errors."""
        tracker = ErrorTracker(window_seconds=60)

        tracker.add_error()
        tracker.add_error()
        tracker.add_error()

        assert tracker.count_recent() == 3

    def test_errors_expire_outside_window(self):
        """Test that old errors are not counted."""
        tracker = ErrorTracker(window_seconds=1)

        # Add error (will be in the past after sleep)
        tracker.errors = [0]  # Timestamp in the past

        # Should not count old error
        assert tracker.count_recent() == 0

    def test_reset_clears_errors(self):
        """Test reset clears all errors."""
        tracker = ErrorTracker()

        tracker.add_error()
        tracker.add_error()
        assert tracker.count_recent() == 2

        tracker.reset()
        assert tracker.count_recent() == 0


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()

        assert config.max_consecutive_losses == 5
        assert config.max_daily_loss_percent == 5.0
        assert config.max_drawdown_percent == 10.0
        assert config.max_order_errors == 5
        assert config.max_api_errors == 10
        assert config.error_window_seconds == 300
        assert config.cooldown_seconds == 300
        assert config.auto_reset is False

    def test_custom_values(self):
        """Test custom configuration values."""
        config = CircuitBreakerConfig(
            max_consecutive_losses=3,
            max_daily_loss_percent=2.0,
            max_drawdown_percent=5.0,
            cooldown_seconds=600,
            auto_reset=True,
        )

        assert config.max_consecutive_losses == 3
        assert config.max_daily_loss_percent == 2.0
        assert config.max_drawdown_percent == 5.0
        assert config.cooldown_seconds == 600
        assert config.auto_reset is True


class TestCircuitBreakerBasics:
    """Tests for basic CircuitBreaker functionality."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return CircuitBreakerConfig(
            max_consecutive_losses=3,
            max_daily_loss_percent=5.0,
            max_drawdown_percent=10.0,
            max_order_errors=3,
            max_api_errors=5,
            error_window_seconds=60,
            cooldown_seconds=60,
        )

    @pytest.fixture
    def circuit_breaker(self, config):
        """Create circuit breaker for testing."""
        return CircuitBreaker(
            config=config,
            tenant_id=uuid4(),
            session_id=uuid4(),
            starting_equity=100000.0,
        )

    def test_initial_state(self, circuit_breaker):
        """Test circuit breaker starts in closed state."""
        assert circuit_breaker.state == CircuitBreakerState.CLOSED
        assert circuit_breaker.is_triggered is False
        assert circuit_breaker.can_trade() is True

    def test_get_status(self, circuit_breaker):
        """Test getting circuit breaker status."""
        status = circuit_breaker.get_status()

        assert isinstance(status, CircuitBreakerStatus)
        assert status.state == CircuitBreakerState.CLOSED
        assert status.triggered_at is None
        assert status.triggered_reason is None
        assert status.can_resume is True


class TestConsecutiveLosses:
    """Tests for consecutive loss circuit breaker trigger."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker with low consecutive loss threshold."""
        config = CircuitBreakerConfig(max_consecutive_losses=3)
        return CircuitBreaker(
            config=config,
            tenant_id=uuid4(),
            session_id=uuid4(),
            starting_equity=100000.0,
        )

    @pytest.mark.asyncio
    async def test_triggers_on_consecutive_losses(self, circuit_breaker):
        """Test circuit breaker triggers after consecutive losses."""
        # Record winning trade - should reset counter
        await circuit_breaker.record_trade(is_win=True, pnl=100)
        assert circuit_breaker.can_trade() is True

        # Record losing trades
        await circuit_breaker.record_trade(is_win=False, pnl=-50)
        assert circuit_breaker.can_trade() is True

        await circuit_breaker.record_trade(is_win=False, pnl=-50)
        assert circuit_breaker.can_trade() is True

        # Third loss should trigger
        await circuit_breaker.record_trade(is_win=False, pnl=-50)
        assert circuit_breaker.can_trade() is False
        assert circuit_breaker.state == CircuitBreakerState.OPEN

        status = circuit_breaker.get_status()
        assert status.triggered_reason == CircuitBreakerReason.CONSECUTIVE_LOSSES

    @pytest.mark.asyncio
    async def test_win_resets_consecutive_loss_counter(self, circuit_breaker):
        """Test winning trade resets consecutive loss counter."""
        await circuit_breaker.record_trade(is_win=False, pnl=-50)
        await circuit_breaker.record_trade(is_win=False, pnl=-50)
        # Two losses, one more would trigger

        # Win resets counter
        await circuit_breaker.record_trade(is_win=True, pnl=100)

        # Start fresh
        await circuit_breaker.record_trade(is_win=False, pnl=-50)
        await circuit_breaker.record_trade(is_win=False, pnl=-50)

        # Should not trigger yet
        assert circuit_breaker.can_trade() is True


class TestDailyLossLimit:
    """Tests for daily loss limit circuit breaker trigger."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker with daily loss limit."""
        config = CircuitBreakerConfig(
            max_daily_loss_percent=5.0,
            max_consecutive_losses=100,  # Disable consecutive loss trigger
        )
        return CircuitBreaker(
            config=config,
            tenant_id=uuid4(),
            session_id=uuid4(),
            starting_equity=100000.0,
        )

    @pytest.mark.asyncio
    async def test_triggers_on_daily_loss_limit(self, circuit_breaker):
        """Test circuit breaker triggers when daily loss exceeds limit."""
        # 5% of 100000 = 5000
        await circuit_breaker.record_trade(is_win=False, pnl=-2000)
        assert circuit_breaker.can_trade() is True

        await circuit_breaker.record_trade(is_win=False, pnl=-2000)
        assert circuit_breaker.can_trade() is True

        # This should push us over 5%
        await circuit_breaker.record_trade(is_win=False, pnl=-1500)
        assert circuit_breaker.can_trade() is False

        status = circuit_breaker.get_status()
        assert status.triggered_reason == CircuitBreakerReason.DAILY_LOSS_LIMIT


class TestDrawdownLimit:
    """Tests for drawdown limit circuit breaker trigger."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker with drawdown limit."""
        config = CircuitBreakerConfig(
            max_drawdown_percent=10.0,
            max_daily_loss_percent=100.0,  # Disable daily loss trigger
            max_consecutive_losses=100,  # Disable consecutive loss trigger
        )
        return CircuitBreaker(
            config=config,
            tenant_id=uuid4(),
            session_id=uuid4(),
            starting_equity=100000.0,
        )

    @pytest.mark.asyncio
    async def test_triggers_on_drawdown_limit(self, circuit_breaker):
        """Test circuit breaker triggers when drawdown exceeds limit."""
        # First, increase equity to create a peak
        await circuit_breaker.record_trade(is_win=True, pnl=5000)
        # Equity now 105000, peak at 105000

        # Now lose money to create drawdown
        await circuit_breaker.record_trade(is_win=False, pnl=-5000)
        # Equity 100000, drawdown = 5/105 = 4.76%
        assert circuit_breaker.can_trade() is True

        await circuit_breaker.record_trade(is_win=False, pnl=-6000)
        # Equity 94000, drawdown = 11/105 = 10.5%
        assert circuit_breaker.can_trade() is False

        status = circuit_breaker.get_status()
        assert status.triggered_reason == CircuitBreakerReason.DRAWDOWN_LIMIT


class TestOrderErrors:
    """Tests for order error circuit breaker trigger."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker with order error limit."""
        config = CircuitBreakerConfig(
            max_order_errors=3,
            error_window_seconds=60,
        )
        return CircuitBreaker(
            config=config,
            tenant_id=uuid4(),
            session_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_triggers_on_order_errors(self, circuit_breaker):
        """Test circuit breaker triggers after too many order errors."""
        await circuit_breaker.record_order_error("Connection refused")
        assert circuit_breaker.can_trade() is True

        await circuit_breaker.record_order_error("Timeout")
        assert circuit_breaker.can_trade() is True

        await circuit_breaker.record_order_error("Invalid order")
        assert circuit_breaker.can_trade() is False

        status = circuit_breaker.get_status()
        assert status.triggered_reason == CircuitBreakerReason.ORDER_ERRORS


class TestApiErrors:
    """Tests for API error circuit breaker trigger."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker with API error limit."""
        config = CircuitBreakerConfig(
            max_api_errors=3,
            error_window_seconds=60,
        )
        return CircuitBreaker(
            config=config,
            tenant_id=uuid4(),
            session_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_triggers_on_api_errors(self, circuit_breaker):
        """Test circuit breaker triggers after too many API errors."""
        await circuit_breaker.record_api_error("Connection failed")
        await circuit_breaker.record_api_error("Timeout")
        await circuit_breaker.record_api_error("Server error")

        assert circuit_breaker.can_trade() is False

        status = circuit_breaker.get_status()
        assert status.triggered_reason == CircuitBreakerReason.API_ERRORS


class TestManualTriggerAndReset:
    """Tests for manual trigger and reset."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker."""
        config = CircuitBreakerConfig(cooldown_seconds=1)
        return CircuitBreaker(
            config=config,
            tenant_id=uuid4(),
            session_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_manual_trigger(self, circuit_breaker):
        """Test manual circuit breaker trigger."""
        await circuit_breaker.manual_trigger("Emergency stop requested")

        assert circuit_breaker.can_trade() is False
        assert circuit_breaker.state == CircuitBreakerState.OPEN

        status = circuit_breaker.get_status()
        assert status.triggered_reason == CircuitBreakerReason.MANUAL

    @pytest.mark.asyncio
    async def test_reset_after_cooldown(self, circuit_breaker):
        """Test reset after cooldown period."""
        await circuit_breaker.manual_trigger("Test")
        assert circuit_breaker.can_trade() is False

        # Try reset before cooldown - should fail
        success = await circuit_breaker.reset(force=False)
        assert success is False
        assert circuit_breaker.can_trade() is False

        # Wait for cooldown
        await asyncio.sleep(1.1)

        # Now reset should work
        success = await circuit_breaker.reset(force=False)
        assert success is True
        assert circuit_breaker.can_trade() is True

    @pytest.mark.asyncio
    async def test_force_reset(self, circuit_breaker):
        """Test force reset ignores cooldown."""
        await circuit_breaker.manual_trigger("Test")
        assert circuit_breaker.can_trade() is False

        # Force reset should work immediately
        success = await circuit_breaker.reset(force=True)
        assert success is True
        assert circuit_breaker.can_trade() is True


class TestCallbacks:
    """Tests for circuit breaker callbacks."""

    @pytest.mark.asyncio
    async def test_trigger_callback_called(self):
        """Test callback is called when circuit breaker triggers."""
        callback = AsyncMock()
        callback.on_circuit_breaker_triggered = AsyncMock()
        callback.on_circuit_breaker_reset = AsyncMock()

        tenant_id = uuid4()
        session_id = uuid4()

        cb = CircuitBreaker(
            config=CircuitBreakerConfig(max_consecutive_losses=1),
            tenant_id=tenant_id,
            session_id=session_id,
            callback=callback,
        )

        await cb.record_trade(is_win=False, pnl=-100)

        callback.on_circuit_breaker_triggered.assert_called_once()
        call_args = callback.on_circuit_breaker_triggered.call_args
        assert call_args.kwargs["tenant_id"] == tenant_id
        assert call_args.kwargs["session_id"] == session_id
        assert call_args.kwargs["reason"] == "consecutive_losses"

    @pytest.mark.asyncio
    async def test_reset_callback_called(self):
        """Test callback is called when circuit breaker resets."""
        callback = AsyncMock()
        callback.on_circuit_breaker_triggered = AsyncMock()
        callback.on_circuit_breaker_reset = AsyncMock()

        cb = CircuitBreaker(
            config=CircuitBreakerConfig(
                max_consecutive_losses=1,
                cooldown_seconds=0,
            ),
            tenant_id=uuid4(),
            session_id=uuid4(),
            callback=callback,
        )

        await cb.manual_trigger("Test")
        await cb.reset(force=True)

        callback.on_circuit_breaker_reset.assert_called_once()


class TestCheckThresholds:
    """Tests for periodic threshold checking."""

    @pytest.mark.asyncio
    async def test_check_thresholds_triggers_on_drawdown(self):
        """Test check_thresholds can trigger circuit breaker."""
        config = CircuitBreakerConfig(
            max_drawdown_percent=5.0,
            max_consecutive_losses=100,
        )
        cb = CircuitBreaker(
            config=config,
            tenant_id=uuid4(),
            session_id=uuid4(),
            starting_equity=100000.0,
        )

        # Set up drawdown scenario
        cb.update_equity(105000.0)  # Create peak
        cb.update_equity(98000.0)  # Drawdown = 7/105 = 6.7%

        triggered = await cb.check_thresholds()

        assert triggered is True
        assert cb.can_trade() is False


class TestDailyTracking:
    """Tests for daily tracking reset."""

    def test_reset_daily_tracking(self):
        """Test resetting daily tracking."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker(
            config=config,
            tenant_id=uuid4(),
            session_id=uuid4(),
            starting_equity=100000.0,
        )

        # Simulate some trading
        cb._daily_pnl = -2000.0
        cb._consecutive_losses = 3
        cb._current_equity = 98000.0
        cb._peak_equity = 105000.0

        # Reset for new day
        cb.reset_daily_tracking(new_starting_equity=98000.0)

        assert cb.starting_equity == 98000.0
        assert cb._daily_pnl == 0.0
        assert cb._consecutive_losses == 0
        assert cb._peak_equity == 98000.0


class TestFactoryFunction:
    """Tests for create_circuit_breaker factory function."""

    def test_create_circuit_breaker_default_config(self):
        """Test creating circuit breaker with default config."""
        cb = create_circuit_breaker(
            tenant_id=uuid4(),
            session_id=uuid4(),
        )

        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.config.max_consecutive_losses == 5

    def test_create_circuit_breaker_custom_config(self):
        """Test creating circuit breaker with custom config."""
        custom_config = CircuitBreakerConfig(max_consecutive_losses=10)

        cb = create_circuit_breaker(
            tenant_id=uuid4(),
            session_id=uuid4(),
            config=custom_config,
        )

        assert cb.config.max_consecutive_losses == 10


class TestUpdateEquity:
    """Tests for equity update method."""

    def test_update_equity_tracks_peak(self):
        """Test equity update tracks peak correctly."""
        cb = create_circuit_breaker(
            tenant_id=uuid4(),
            session_id=uuid4(),
            starting_equity=100000.0,
        )

        cb.update_equity(105000.0)
        assert cb._peak_equity == 105000.0

        cb.update_equity(103000.0)
        # Peak should stay at 105000
        assert cb._peak_equity == 105000.0

        cb.update_equity(110000.0)
        assert cb._peak_equity == 110000.0

    def test_update_equity_with_daily_pnl(self):
        """Test equity update with daily P&L."""
        cb = create_circuit_breaker(
            tenant_id=uuid4(),
            session_id=uuid4(),
            starting_equity=100000.0,
        )

        cb.update_equity(102000.0, daily_pnl=2000.0)

        assert cb._current_equity == 102000.0
        assert cb._daily_pnl == 2000.0
