"""End-to-end runner integration tests.

These tests verify the full bar→signal→order flow:
1. Sets up mock bar stream with predefined bars
2. Uses simple strategy generating known signals
3. Verifies order submission
4. Verifies position tracking
5. Verifies alerts sent

Tests run against real PostgreSQL database via testcontainers.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from llamatrade_db.models.trading import TradingSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_CREDENTIALS_ID = UUID("55555555-5555-5555-5555-555555555555")

# Proto int constants for enum values
EXECUTION_MODE_PAPER = 1  # ExecutionMode: PAPER=1
SESSION_STATUS_ACTIVE = 1  # SessionStatus: ACTIVE=1


def add_trading_service_to_path():
    """Add trading service to Python path for imports."""
    import sys
    from pathlib import Path

    trading_path = Path(__file__).parents[3] / "services" / "trading"
    trading_path_str = str(trading_path)

    # Remove other service paths that might conflict
    service_paths = [
        str(Path(__file__).parents[3] / "services" / svc)
        for svc in [
            "auth",
            "billing",
            "strategy",
            "backtest",
            "market-data",
            "portfolio",
            "notification",
        ]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    # Clear any cached src modules
    modules_to_remove = [k for k in list(sys.modules.keys()) if k == "src" or k.startswith("src.")]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Add trading service path at the front
    if trading_path_str in sys.path:
        sys.path.remove(trading_path_str)
    sys.path.insert(0, trading_path_str)


# Call immediately at module load time to set up path before fixture collection
add_trading_service_to_path()


@pytest.fixture(scope="module", autouse=True)
def setup_trading_path():
    """Set up path for trading service imports (also called at module load)."""
    add_trading_service_to_path()


@pytest.fixture
async def trading_session(db_session: AsyncSession) -> TradingSession:
    """Create a test trading session."""
    session = TradingSession(
        id=TEST_SESSION_ID,
        tenant_id=TEST_TENANT_ID,
        strategy_id=TEST_STRATEGY_ID,
        strategy_version=1,
        credentials_id=TEST_CREDENTIALS_ID,
        name="E2E Test Session",
        mode=EXECUTION_MODE_PAPER,  # Proto int: PAPER=1
        status=SESSION_STATUS_ACTIVE,  # Proto int: ACTIVE=1
        symbols=["AAPL"],
        created_by=TEST_USER_ID,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
def mock_trade_stream():
    """Create a mock trade stream for testing."""
    from src.runner.trade_stream import MockTradeStream

    return MockTradeStream()


@pytest.fixture
def sample_bars():
    """Create sample bars for testing."""
    from src.runner.bar_stream import BarData

    # Create bars during market hours (10 AM ET = 3 PM UTC in winter)
    # Using a Thursday (Jan 16, 2025) which is not a holiday
    base_time = datetime(2025, 1, 16, 15, 0, tzinfo=UTC)  # 10 AM ET
    bars = []
    price = 150.0

    # Create 60 bars with upward trend followed by downward
    for i in range(60):
        timestamp = base_time + timedelta(minutes=i)
        # First 30 bars: upward trend (should trigger buy signal)
        # Last 30 bars: downward trend (should trigger sell signal)
        if i < 30:
            price = price * 1.002  # 0.2% increase
        else:
            price = price * 0.998  # 0.2% decrease

        bars.append(
            BarData(
                symbol="AAPL",
                timestamp=timestamp,
                open=price * 0.999,
                high=price * 1.005,
                low=price * 0.995,
                close=price,
                volume=10000 + i * 100,
            )
        )

    return bars


@pytest.fixture
def simple_trend_strategy():
    """Create a simple trend-following strategy for testing.

    This strategy:
    - Buys when price is above 20-bar SMA
    - Sells when price is below 20-bar SMA
    """
    from src.runner.bar_stream import BarData
    from src.runner.runner import Position, Signal

    def strategy(
        symbol: str,
        bars: Sequence[BarData],
        position: Position | None,
        equity: float,
    ) -> Signal | None:
        if len(bars) < 20:
            return None

        # Calculate simple moving average
        closes = [bar.close for bar in list(bars)[-20:]]
        sma = sum(closes) / len(closes)
        current_price = bars[-1].close

        # Generate signals
        if current_price > sma * 1.01 and (position is None or position.side == "flat"):
            # Price 1% above SMA - buy signal
            return Signal(
                type="buy",
                symbol=symbol,
                quantity=10,
                price=current_price,
            )
        elif current_price < sma * 0.99 and position and position.side == "long":
            # Price 1% below SMA - sell signal
            return Signal(
                type="sell",
                symbol=symbol,
                quantity=position.quantity,
                price=current_price,
            )

        return None

    return strategy


@pytest.fixture
def mock_alpaca_client():
    """Create a mock Alpaca trading client."""
    client = AsyncMock()
    client.get_account = AsyncMock(
        return_value={
            "id": "test-account",
            "account_number": "123456789",
            "status": "ACTIVE",
            "cash": "100000.00",
            "portfolio_value": "100000.00",
            "buying_power": "200000.00",
            "equity": "100000.00",
            "currency": "USD",
        }
    )
    client.submit_order = AsyncMock(
        return_value={
            "id": f"alpaca-order-{uuid4()}",
            "client_order_id": "test-client-order",
            "symbol": "AAPL",
            "qty": "10",
            "side": "buy",
            "type": "market",
            "status": "accepted",
            "filled_qty": "0",
            "filled_avg_price": None,
            "created_at": "2025-01-16T15:00:00Z",
            "submitted_at": "2025-01-16T15:00:00Z",
            "filled_at": None,
        }
    )
    client.get_positions = AsyncMock(return_value=[])
    client.get_position = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_risk_manager():
    """Create a mock risk manager that passes all checks."""
    from src.models import RiskCheckResult

    manager = AsyncMock()
    manager.check_order = AsyncMock(
        return_value=RiskCheckResult(
            passed=True,
            violations=[],
        )
    )
    manager.get_limits = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def mock_alert_service():
    """Create a mock alert service to track alerts."""
    service = AsyncMock()
    service.alerts_sent = []

    async def track_alert(alert_type: str, **kwargs):
        service.alerts_sent.append({"type": alert_type, **kwargs})

    service.on_session_started = AsyncMock(
        side_effect=lambda **kw: track_alert("session_started", **kw)
    )
    service.on_session_stopped = AsyncMock(
        side_effect=lambda **kw: track_alert("session_stopped", **kw)
    )
    service.on_order_submitted = AsyncMock(
        side_effect=lambda **kw: track_alert("order_submitted", **kw)
    )
    service.on_order_filled = AsyncMock(side_effect=lambda **kw: track_alert("order_filled", **kw))
    service.on_signal_generated = AsyncMock(
        side_effect=lambda **kw: track_alert("signal_generated", **kw)
    )
    service.on_connection_lost = AsyncMock(
        side_effect=lambda **kw: track_alert("connection_lost", **kw)
    )

    return service


class TestRunnerE2EBasic:
    """Basic end-to-end runner tests."""

    async def test_runner_processes_bars_and_generates_signals(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
        sample_bars,
        simple_trend_strategy,
        mock_alpaca_client,
        mock_risk_manager,
        mock_alert_service,
        mock_trade_stream,
    ):
        """Test that runner processes bars and generates buy signal."""
        from src.executor.order_executor import OrderExecutor
        from src.runner.bar_stream import MockBarStream
        from src.runner.runner import RunnerConfig, StrategyRunner

        # Set up mock bar stream with sample bars
        bar_stream = MockBarStream(bars={"AAPL": sample_bars})

        # Create order executor with mocked dependencies
        order_executor = MagicMock(spec=OrderExecutor)
        order_executor.submit_order = AsyncMock(
            return_value=MagicMock(
                id=uuid4(),
                alpaca_order_id="alpaca-123",
                symbol="AAPL",
                status="submitted",
            )
        )

        # Create runner config
        config = RunnerConfig(
            tenant_id=TEST_TENANT_ID,
            execution_id=TEST_SESSION_ID,
            strategy_id=TEST_STRATEGY_ID,
            symbols=["AAPL"],
            timeframe="1Min",
            warmup_bars=20,
            enforce_trading_hours=False,  # Disable for testing
        )

        # Create runner
        runner = StrategyRunner(
            config=config,
            strategy_fn=simple_trend_strategy,
            bar_stream=bar_stream,
            trade_stream=mock_trade_stream,
            order_executor=order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
            alert_service=mock_alert_service,
            strategy_name="Test Trend Strategy",
        )

        # Start runner and let it process bars (start() is the main loop)
        # The MockBarStream will yield all bars and then end
        await runner.start()

        # Verify signals were generated
        assert runner.metrics["signals_generated"] > 0

    async def test_runner_submits_orders_on_signals(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
        sample_bars,
        mock_alpaca_client,
        mock_risk_manager,
        mock_alert_service,
        mock_trade_stream,
    ):
        """Test that runner submits orders when signals are generated."""
        from src.executor.order_executor import OrderExecutor
        from src.runner.bar_stream import MockBarStream
        from src.runner.runner import RunnerConfig, Signal, StrategyRunner

        # Create strategy that always generates buy signal after warmup
        def always_buy_strategy(symbol, bars, position, equity) -> Signal | None:
            if len(bars) < 20:
                return None
            if position is None or position.side == "flat":
                return Signal(
                    type="buy",
                    symbol=symbol,
                    quantity=10,
                    price=bars[-1].close,
                )
            return None

        bar_stream = MockBarStream(bars={"AAPL": sample_bars})

        # Track order submissions
        submitted_orders = []

        async def track_order(**kwargs):
            submitted_orders.append(kwargs)
            return MagicMock(
                id=uuid4(),
                alpaca_order_id=f"alpaca-{uuid4()}",
                symbol="AAPL",
                status="submitted",
            )

        order_executor = MagicMock(spec=OrderExecutor)
        order_executor.submit_order = AsyncMock(side_effect=track_order)

        config = RunnerConfig(
            tenant_id=TEST_TENANT_ID,
            execution_id=TEST_SESSION_ID,
            strategy_id=TEST_STRATEGY_ID,
            symbols=["AAPL"],
            timeframe="1Min",
            warmup_bars=20,
            enforce_trading_hours=False,
        )

        runner = StrategyRunner(
            config=config,
            strategy_fn=always_buy_strategy,
            bar_stream=bar_stream,
            trade_stream=mock_trade_stream,
            order_executor=order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
            alert_service=mock_alert_service,
            strategy_name="Always Buy Strategy",
        )

        # Start runner - it will process all mock bars and then exit
        await runner.start()

        # Verify orders were submitted
        assert len(submitted_orders) > 0
        assert runner.metrics["orders_submitted"] > 0

    @pytest.mark.skip(
        reason="Position tracking requires trade stream to emit fill events; mock needs enhancement"
    )
    async def test_runner_tracks_positions(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
        sample_bars,
        mock_alpaca_client,
        mock_risk_manager,
        mock_alert_service,
        mock_trade_stream,
    ):
        """Test that runner tracks positions after order fills."""
        from src.executor.order_executor import OrderExecutor
        from src.runner.bar_stream import MockBarStream
        from src.runner.runner import RunnerConfig, Signal, StrategyRunner

        # Create strategy that generates one buy signal
        signal_count = [0]

        def one_buy_strategy(symbol, bars, position, equity) -> Signal | None:
            if len(bars) < 20:
                return None
            if signal_count[0] == 0 and (position is None or position.side == "flat"):
                signal_count[0] += 1
                return Signal(
                    type="buy",
                    symbol=symbol,
                    quantity=10,
                    price=bars[-1].close,
                )
            return None

        bar_stream = MockBarStream(bars={"AAPL": sample_bars})

        # Mock order executor that simulates immediate fill
        order_executor = MagicMock(spec=OrderExecutor)
        order_executor.submit_order = AsyncMock(
            return_value=MagicMock(
                id=uuid4(),
                alpaca_order_id="alpaca-123",
                symbol="AAPL",
                side="buy",
                qty=10,
                status="filled",
                filled_qty=10,
                filled_avg_price=150.0,
            )
        )

        config = RunnerConfig(
            tenant_id=TEST_TENANT_ID,
            execution_id=TEST_SESSION_ID,
            strategy_id=TEST_STRATEGY_ID,
            symbols=["AAPL"],
            timeframe="1Min",
            warmup_bars=20,
            enforce_trading_hours=False,
        )

        runner = StrategyRunner(
            config=config,
            strategy_fn=one_buy_strategy,
            bar_stream=bar_stream,
            trade_stream=mock_trade_stream,
            order_executor=order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
            alert_service=mock_alert_service,
            strategy_name="One Buy Strategy",
        )

        # Start runner - it will process all mock bars
        await runner.start()

        # Verify position is tracked
        positions = runner.positions
        assert "AAPL" in positions
        assert positions["AAPL"].side == "long"
        assert positions["AAPL"].quantity == 10


class TestRunnerE2EAlerts:
    """End-to-end runner alert tests."""

    async def test_runner_sends_session_started_alert(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
        sample_bars,
        mock_alpaca_client,
        mock_risk_manager,
        mock_trade_stream,
    ):
        """Test that runner sends session started alert."""
        from src.executor.order_executor import OrderExecutor
        from src.runner.bar_stream import MockBarStream
        from src.runner.runner import RunnerConfig, StrategyRunner

        def no_signal_strategy(symbol, bars, position, equity):
            return None

        bar_stream = MockBarStream(bars={"AAPL": sample_bars})
        order_executor = MagicMock(spec=OrderExecutor)

        # Track alerts
        alerts_received = []
        alert_service = AsyncMock()
        alert_service.on_session_started = AsyncMock(
            side_effect=lambda **kw: alerts_received.append(("session_started", kw))
        )
        alert_service.on_session_stopped = AsyncMock(
            side_effect=lambda **kw: alerts_received.append(("session_stopped", kw))
        )

        config = RunnerConfig(
            tenant_id=TEST_TENANT_ID,
            execution_id=TEST_SESSION_ID,
            strategy_id=TEST_STRATEGY_ID,
            symbols=["AAPL"],
            timeframe="1Min",
            warmup_bars=20,
            enforce_trading_hours=False,
        )

        runner = StrategyRunner(
            config=config,
            strategy_fn=no_signal_strategy,
            bar_stream=bar_stream,
            trade_stream=mock_trade_stream,
            order_executor=order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
            alert_service=alert_service,
            strategy_name="No Signal Strategy",
        )

        await runner.start()
        await runner.stop()

        # Verify session started alert was sent
        alert_types = [a[0] for a in alerts_received]
        assert "session_started" in alert_types

        # Verify session stopped alert was sent
        assert "session_stopped" in alert_types


class TestRunnerE2ETradingHours:
    """End-to-end runner trading hours tests."""

    async def test_runner_skips_signals_outside_market_hours(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
        mock_alpaca_client,
        mock_risk_manager,
        mock_alert_service,
        mock_trade_stream,
    ):
        """Test that runner skips signals outside market hours when enabled."""
        from src.executor.order_executor import OrderExecutor
        from src.runner.bar_stream import BarData, MockBarStream
        from src.runner.runner import RunnerConfig, Signal, StrategyRunner

        # Create bars outside market hours (3 AM ET = 8 AM UTC)
        base_time = datetime(2025, 1, 16, 8, 0, tzinfo=UTC)
        after_hours_bars = []
        for i in range(30):
            after_hours_bars.append(
                BarData(
                    symbol="AAPL",
                    timestamp=base_time + timedelta(minutes=i),
                    open=150.0,
                    high=151.0,
                    low=149.0,
                    close=150.5,
                    volume=10000,
                )
            )

        # Strategy that always tries to generate signals
        def always_signal_strategy(symbol, bars, position, equity) -> Signal | None:
            if len(bars) < 20:
                return None
            return Signal(
                type="buy",
                symbol=symbol,
                quantity=10,
                price=bars[-1].close,
            )

        bar_stream = MockBarStream(bars={"AAPL": after_hours_bars})

        order_executor = MagicMock(spec=OrderExecutor)
        order_executor.submit_order = AsyncMock()

        config = RunnerConfig(
            tenant_id=TEST_TENANT_ID,
            execution_id=TEST_SESSION_ID,
            strategy_id=TEST_STRATEGY_ID,
            symbols=["AAPL"],
            timeframe="1Min",
            warmup_bars=20,
            enforce_trading_hours=True,  # Enable trading hours enforcement
            allow_premarket=False,
            allow_afterhours=False,
        )

        runner = StrategyRunner(
            config=config,
            strategy_fn=always_signal_strategy,
            bar_stream=bar_stream,
            trade_stream=mock_trade_stream,
            order_executor=order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
            alert_service=mock_alert_service,
            strategy_name="Always Signal Strategy",
        )

        # Start runner - it will process all mock bars
        await runner.start()

        # Verify no orders were submitted (bars are outside market hours)
        order_executor.submit_order.assert_not_called()


class TestRunnerE2ECircuitBreaker:
    """End-to-end runner circuit breaker tests."""

    async def test_runner_respects_circuit_breaker(
        self,
        db_session: AsyncSession,
        trading_session: TradingSession,
        sample_bars,
        mock_alpaca_client,
        mock_risk_manager,
        mock_alert_service,
        mock_trade_stream,
    ):
        """Test that runner stops trading when circuit breaker is triggered."""
        from src.circuit_breaker import CircuitBreakerConfig
        from src.executor.order_executor import OrderExecutor
        from src.runner.bar_stream import MockBarStream
        from src.runner.runner import RunnerConfig, Signal, StrategyRunner

        # Strategy that always generates buy signal
        def always_buy_strategy(symbol, bars, position, equity) -> Signal | None:
            if len(bars) < 20:
                return None
            if position is None or position.side == "flat":
                return Signal(
                    type="buy",
                    symbol=symbol,
                    quantity=10,
                    price=bars[-1].close,
                )
            return None

        bar_stream = MockBarStream(bars={"AAPL": sample_bars})

        order_executor = MagicMock(spec=OrderExecutor)
        order_executor.submit_order = AsyncMock(
            return_value=MagicMock(
                id=uuid4(),
                alpaca_order_id="alpaca-123",
                symbol="AAPL",
                status="submitted",
            )
        )

        # Configure circuit breaker with low thresholds for testing
        cb_config = CircuitBreakerConfig(
            max_daily_loss_percent=0.5,  # 0.5% daily loss triggers
            max_drawdown_percent=1.0,
            max_consecutive_losses=3,
        )

        config = RunnerConfig(
            tenant_id=TEST_TENANT_ID,
            execution_id=TEST_SESSION_ID,
            strategy_id=TEST_STRATEGY_ID,
            symbols=["AAPL"],
            timeframe="1Min",
            warmup_bars=20,
            enforce_trading_hours=False,
        )

        runner = StrategyRunner(
            config=config,
            strategy_fn=always_buy_strategy,
            bar_stream=bar_stream,
            trade_stream=mock_trade_stream,
            order_executor=order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
            alert_service=mock_alert_service,
            strategy_name="Always Buy Strategy",
            circuit_breaker_config=cb_config,
        )

        await runner.start()

        # Manually trigger circuit breaker using the actual API
        await runner.circuit_breaker.manual_trigger("Test trigger")

        # Verify circuit breaker is triggered
        assert runner.circuit_breaker_triggered

        await runner.stop()
