"""Test strategy runner."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_MARKET,
)

from src.models import OrderResponse
from src.runner.bar_stream import BarData, MockBarStream
from src.runner.runner import (
    Position,
    RunnerConfig,
    RunnerManager,
    Signal,
    StrategyRunner,
    get_runner_manager,
)
from src.runner.trade_stream import MockTradeStream


@pytest.fixture
def runner_config(tenant_id, session_id, strategy_id):
    """Create a runner configuration."""
    return RunnerConfig(
        tenant_id=tenant_id,
        execution_id=session_id,
        strategy_id=strategy_id,
        symbols=["AAPL"],
        timeframe="1min",
        warmup_bars=10,
    )


@pytest.fixture
def mock_order_executor():
    """Create a mock order executor."""
    executor = AsyncMock()
    executor.submit_order = AsyncMock(
        return_value=OrderResponse(
            id=UUID("77777777-7777-7777-7777-777777777777"),
            alpaca_order_id="alpaca-order-123",
            symbol="AAPL",
            side=ORDER_SIDE_BUY,
            qty=10.0,
            order_type=ORDER_TYPE_MARKET,
            status=ORDER_STATUS_SUBMITTED,
            filled_qty=0,
            filled_avg_price=None,
            submitted_at=datetime.now(UTC),
            filled_at=None,
        )
    )
    return executor


@pytest.fixture
def mock_strategy_fn():
    """Create a mock strategy function."""
    fn = MagicMock()
    fn.return_value = None  # No signal by default
    return fn


@pytest.fixture
def strategy_runner(
    runner_config,
    mock_strategy_fn,
    mock_order_executor,
    mock_risk_manager,
    sample_bars,
):
    """Create a strategy runner with mocks."""
    mock_bar_stream = MockBarStream(bars={"AAPL": sample_bars})
    mock_trade_stream = MockTradeStream()

    return StrategyRunner(
        config=runner_config,
        strategy_fn=mock_strategy_fn,
        bar_stream=mock_bar_stream,
        trade_stream=mock_trade_stream,
        order_executor=mock_order_executor,
        risk_manager=mock_risk_manager,
    )


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation(self):
        """Test creating a Signal instance."""
        signal = Signal(
            type="buy",
            symbol="AAPL",
            quantity=10.0,
            price=150.0,
        )

        assert signal.type == "buy"
        assert signal.symbol == "AAPL"
        assert signal.quantity == 10.0
        assert signal.price == 150.0
        assert signal.timestamp is not None


class TestPosition:
    """Tests for Position dataclass."""

    def test_position_creation(self):
        """Test creating a Position instance."""
        now = datetime.now(UTC)
        position = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=150.0,
            entry_date=now,
        )

        assert position.symbol == "AAPL"
        assert position.side == "long"
        assert position.quantity == 10.0
        assert position.entry_price == 150.0
        assert position.entry_date == now


class TestRunnerConfig:
    """Tests for RunnerConfig."""

    def test_config_creation(self, tenant_id, session_id, strategy_id):
        """Test creating a RunnerConfig."""
        config = RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=["AAPL", "GOOGL"],
            timeframe="5min",
            warmup_bars=50,
        )

        assert config.tenant_id == tenant_id
        assert config.execution_id == session_id
        assert config.strategy_id == strategy_id
        assert config.symbols == ["AAPL", "GOOGL"]
        assert config.timeframe == "5min"
        assert config.warmup_bars == 50


class TestStrategyRunner:
    """Tests for StrategyRunner."""

    def test_runner_initialization(self, strategy_runner):
        """Test runner initialization."""
        assert strategy_runner.running is False
        assert strategy_runner.paused is False
        assert len(strategy_runner.positions) == 0

    def test_runner_metrics(self, strategy_runner):
        """Test runner metrics."""
        metrics = strategy_runner.metrics

        assert "signals_generated" in metrics
        assert "orders_submitted" in metrics
        assert "orders_rejected" in metrics
        assert "positions" in metrics
        assert "bar_history_sizes" in metrics

    def test_pause_resume(self, strategy_runner):
        """Test pause and resume functionality."""
        assert strategy_runner.paused is False

        strategy_runner.pause()
        assert strategy_runner.paused is True

        strategy_runner.resume()
        assert strategy_runner.paused is False

    def test_set_equity(self, strategy_runner):
        """Test setting equity value."""
        strategy_runner.set_equity(200000.0)
        assert strategy_runner._equity == 200000.0

    def test_sync_position_add(self, strategy_runner):
        """Test syncing a new position."""
        position = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=150.0,
            entry_date=datetime.now(UTC),
        )

        strategy_runner.sync_position("AAPL", position)

        assert "AAPL" in strategy_runner.positions
        assert strategy_runner.positions["AAPL"].quantity == 10.0

    def test_sync_position_remove(self, strategy_runner):
        """Test removing a position via sync."""
        position = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=150.0,
            entry_date=datetime.now(UTC),
        )
        strategy_runner.sync_position("AAPL", position)

        strategy_runner.sync_position("AAPL", None)

        assert "AAPL" not in strategy_runner.positions

    def test_signal_to_order_buy(self, strategy_runner):
        """Test converting buy signal to order."""
        signal = Signal(
            type="buy",
            symbol="AAPL",
            quantity=10.0,
            price=150.0,
        )

        order = strategy_runner._signal_to_order(signal)

        assert order.symbol == "AAPL"
        assert order.side == ORDER_SIDE_BUY
        assert order.qty == 10.0

    def test_signal_to_order_sell(self, strategy_runner):
        """Test converting sell signal to order."""
        signal = Signal(
            type="sell",
            symbol="AAPL",
            quantity=10.0,
            price=155.0,
        )

        order = strategy_runner._signal_to_order(signal)

        assert order.symbol == "AAPL"
        assert order.side == ORDER_SIDE_SELL
        assert order.qty == 10.0

    def test_signal_to_order_cover(self, strategy_runner):
        """Test converting cover signal to order (buy to close short)."""
        signal = Signal(
            type="cover",
            symbol="AAPL",
            quantity=10.0,
            price=145.0,
        )

        order = strategy_runner._signal_to_order(signal)

        assert order.side == ORDER_SIDE_BUY  # Cover = buy to close short

    def test_signal_to_order_short(self, strategy_runner):
        """Test converting short signal to order."""
        signal = Signal(
            type="short",
            symbol="AAPL",
            quantity=10.0,
            price=155.0,
        )

        order = strategy_runner._signal_to_order(signal)

        assert order.side == ORDER_SIDE_SELL  # Short = sell

    async def test_update_position_buy(self, strategy_runner):
        """Test position update on buy signal."""
        signal = Signal(
            type="buy",
            symbol="AAPL",
            quantity=10.0,
            price=150.0,
        )

        await strategy_runner._update_position(signal)

        assert "AAPL" in strategy_runner._positions
        assert strategy_runner._positions["AAPL"].side == "long"
        assert strategy_runner._positions["AAPL"].quantity == 10.0

    async def test_update_position_sell(self, strategy_runner):
        """Test position update on sell signal (close long)."""
        # First create a position
        buy_signal = Signal(type="buy", symbol="AAPL", quantity=10.0, price=150.0)
        await strategy_runner._update_position(buy_signal)

        # Then sell it
        sell_signal = Signal(type="sell", symbol="AAPL", quantity=10.0, price=155.0)
        await strategy_runner._update_position(sell_signal)

        assert "AAPL" not in strategy_runner._positions

    async def test_update_position_short(self, strategy_runner):
        """Test position update on short signal."""
        signal = Signal(
            type="short",
            symbol="AAPL",
            quantity=10.0,
            price=155.0,
        )

        await strategy_runner._update_position(signal)

        assert "AAPL" in strategy_runner._positions
        assert strategy_runner._positions["AAPL"].side == "short"

    async def test_update_position_cover(self, strategy_runner):
        """Test position update on cover signal (close short)."""
        # First create a short position
        short_signal = Signal(type="short", symbol="AAPL", quantity=10.0, price=155.0)
        await strategy_runner._update_position(short_signal)

        # Then cover it
        cover_signal = Signal(type="cover", symbol="AAPL", quantity=10.0, price=150.0)
        await strategy_runner._update_position(cover_signal)

        assert "AAPL" not in strategy_runner._positions


class TestRunnerManager:
    """Tests for RunnerManager."""

    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = RunnerManager()

        assert len(manager.active_runners) == 0

    def test_get_nonexistent_runner(self):
        """Test getting a non-existent runner."""
        manager = RunnerManager()

        runner = manager.get_runner(UUID("00000000-0000-0000-0000-000000000000"))

        assert runner is None

    async def test_stop_all_empty(self):
        """Test stopping all runners when none exist."""
        manager = RunnerManager()

        # Should not raise
        await manager.stop_all()


class TestGetRunnerManager:
    """Tests for get_runner_manager singleton."""

    def test_returns_manager(self):
        """Test that get_runner_manager returns a RunnerManager."""
        manager = get_runner_manager()

        assert isinstance(manager, RunnerManager)

    def test_returns_same_instance(self):
        """Test that get_runner_manager returns the same instance."""
        manager1 = get_runner_manager()
        manager2 = get_runner_manager()

        assert manager1 is manager2


class TestRunnerManagerOperations:
    """Tests for RunnerManager operations."""

    async def test_stop_all_when_empty(self):
        """Test stop_all handles empty runners gracefully."""
        manager = RunnerManager()
        await manager.stop_all()
        assert len(manager.active_runners) == 0

    def test_get_runner_returns_existing_runner(
        self,
        runner_config,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test get_runner returns existing runner."""
        manager = RunnerManager()
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})

        runner = StrategyRunner(
            config=runner_config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )
        # Use internal _runners dict, not active_runners property
        manager._runners[runner_config.execution_id] = runner

        result = manager.get_runner(runner_config.execution_id)

        assert result is runner

    async def test_stop_runner_not_found(self):
        """Test stopping non-existent runner returns False."""
        manager = RunnerManager()
        result = await manager.stop_runner(UUID("00000000-0000-0000-0000-000000000000"))
        assert result is False


class TestStrategyRunnerAdvanced:
    """Advanced tests for StrategyRunner."""

    async def test_process_bar_ignores_untracked_symbols(
        self,
        runner_config,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test that bars for untracked symbols are ignored."""
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})
        runner = StrategyRunner(
            config=runner_config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )

        # Create a bar for an untracked symbol
        untracked_bar = sample_bars[0]
        untracked_bar = BarData(
            symbol="TSLA",  # Not in config.symbols
            timestamp=untracked_bar.timestamp,
            open=untracked_bar.open,
            high=untracked_bar.high,
            low=untracked_bar.low,
            close=untracked_bar.close,
            volume=untracked_bar.volume,
        )

        await runner._process_bar(untracked_bar)

        # Strategy function should not be called
        mock_strategy_fn.assert_not_called()

    async def test_process_bar_warmup_period(
        self,
        runner_config,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test that strategy is not called during warmup period."""
        mock_stream = MockBarStream(bars={"AAPL": sample_bars[:5]})
        runner = StrategyRunner(
            config=runner_config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )

        # Process a bar during warmup
        await runner._process_bar(sample_bars[0])

        # Strategy should not be called during warmup
        mock_strategy_fn.assert_not_called()

    async def test_process_signal_rejected_by_risk(
        self,
        runner_config,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test signal rejection by risk manager."""
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})
        runner = StrategyRunner(
            config=runner_config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )

        # Fill warmup history
        runner._bar_history["AAPL"] = sample_bars[:15]

        # Configure risk manager to reject
        mock_risk_manager.check_order.return_value.passed = False
        mock_risk_manager.check_order.return_value.violations = ["Position too large"]

        signal = Signal(type="buy", symbol="AAPL", quantity=10.0, price=150.0)
        await runner._process_signal(signal)

        # Order should not be submitted
        mock_order_executor.submit_order.assert_not_called()
        assert runner._orders_rejected == 1

    def test_circuit_breaker_property(
        self,
        runner_config,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test circuit breaker property access."""
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})
        runner = StrategyRunner(
            config=runner_config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )

        assert runner.circuit_breaker is not None
        assert runner.circuit_breaker_triggered is False

    async def test_stop_runner(
        self,
        runner_config,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test stopping the runner."""
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})
        mock_stream.disconnect = AsyncMock()

        runner = StrategyRunner(
            config=runner_config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )

        await runner.stop(reason="Test stop")

        assert runner._running is False
        mock_stream.disconnect.assert_called_once()


class TestPositionReconciliation:
    """Tests for position reconciliation with Alpaca."""

    @pytest.fixture
    def mock_alpaca_client(self):
        """Create a mock Alpaca client."""

        client = AsyncMock()
        # Default: return empty positions
        client.get_positions = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def reconciliation_runner(
        self,
        runner_config,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        mock_alpaca_client,
        sample_bars,
    ):
        """Create a runner with position reconciliation enabled."""
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})

        # Enable reconciliation in config
        runner_config.position_reconciliation_enabled = True
        runner_config.position_reconciliation_interval_seconds = 60
        runner_config.position_drift_auto_correct_threshold_pct = 5.0
        runner_config.position_drift_alert_threshold_pct = 10.0

        return StrategyRunner(
            config=runner_config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=mock_alpaca_client,
            alert_service=AsyncMock(),
        )

    async def test_sync_positions_all_match(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test reconciliation when all positions match."""
        from src.models import PositionResponse

        # Set up matching positions
        reconciliation_runner._positions["AAPL"] = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=150.0,
            entry_date=datetime.now(UTC),
        )

        mock_alpaca_client.get_positions.return_value = [
            PositionResponse(
                symbol="AAPL",
                qty=10.0,
                side="long",
                cost_basis=1500.0,
                market_value=1550.0,
                unrealized_pnl=50.0,
                unrealized_pnl_percent=3.33,
                current_price=155.0,
            )
        ]
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # Position should remain unchanged
        assert reconciliation_runner._positions["AAPL"].quantity == 10.0
        # Alert service should not be called for position drift
        reconciliation_runner.alerts.on_position_drift.assert_not_called()

    async def test_sync_positions_missing_at_broker(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test reconciliation when local position is missing at broker."""
        # Local position exists
        reconciliation_runner._positions["AAPL"] = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=150.0,
            entry_date=datetime.now(UTC),
        )

        # Broker has no positions
        mock_alpaca_client.get_positions.return_value = []
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # Alert should be sent for missing broker position
        reconciliation_runner.alerts.on_position_drift.assert_called_once()
        call_args = reconciliation_runner.alerts.on_position_drift.call_args
        assert call_args.kwargs["drift_type"] == "missing_broker"
        assert call_args.kwargs["action"] == "alerted"

    async def test_sync_positions_missing_locally(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test reconciliation when broker has position not tracked locally."""
        from src.models import PositionResponse

        # No local positions
        reconciliation_runner._positions = {}

        # Broker has a position
        mock_alpaca_client.get_positions.return_value = [
            PositionResponse(
                symbol="AAPL",
                qty=10.0,
                side="long",
                cost_basis=1500.0,
                market_value=1550.0,
                unrealized_pnl=50.0,
                unrealized_pnl_percent=3.33,
                current_price=155.0,
            )
        ]
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # Position should be auto-added
        assert "AAPL" in reconciliation_runner._positions
        assert reconciliation_runner._positions["AAPL"].quantity == 10.0
        assert reconciliation_runner._positions["AAPL"].side == "long"

        # Alert should be sent with action="corrected"
        reconciliation_runner.alerts.on_position_drift.assert_called_once()
        call_args = reconciliation_runner.alerts.on_position_drift.call_args
        assert call_args.kwargs["drift_type"] == "missing_local"
        assert call_args.kwargs["action"] == "corrected"

    async def test_sync_positions_small_quantity_drift_auto_corrected(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test that small quantity drift (<5%) is auto-corrected."""
        from src.models import PositionResponse

        # Local position with quantity 10.0
        reconciliation_runner._positions["AAPL"] = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=150.0,
            entry_date=datetime.now(UTC),
        )

        # Broker has 10.4 (4% drift - under 5% threshold)
        mock_alpaca_client.get_positions.return_value = [
            PositionResponse(
                symbol="AAPL",
                qty=10.4,
                side="long",
                cost_basis=1560.0,
                market_value=1612.0,
                unrealized_pnl=52.0,
                unrealized_pnl_percent=3.33,
                current_price=155.0,
            )
        ]
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # Position should be auto-corrected to broker value
        assert reconciliation_runner._positions["AAPL"].quantity == 10.4

        # Alert should be sent with action="corrected"
        reconciliation_runner.alerts.on_position_drift.assert_called_once()
        call_args = reconciliation_runner.alerts.on_position_drift.call_args
        assert call_args.kwargs["drift_type"] == "quantity_mismatch"
        assert call_args.kwargs["action"] == "corrected"

    async def test_sync_positions_large_quantity_drift_alerted(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test that large quantity drift (>=10%) is alerted but not corrected."""
        from src.models import PositionResponse

        # Local position with quantity 10.0
        reconciliation_runner._positions["AAPL"] = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=150.0,
            entry_date=datetime.now(UTC),
        )

        # Broker has 12.0 (20% drift - over 10% threshold)
        mock_alpaca_client.get_positions.return_value = [
            PositionResponse(
                symbol="AAPL",
                qty=12.0,
                side="long",
                cost_basis=1800.0,
                market_value=1860.0,
                unrealized_pnl=60.0,
                unrealized_pnl_percent=3.33,
                current_price=155.0,
            )
        ]
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # Position should NOT be corrected
        assert reconciliation_runner._positions["AAPL"].quantity == 10.0

        # Alert should be sent with action="alerted"
        reconciliation_runner.alerts.on_position_drift.assert_called_once()
        call_args = reconciliation_runner.alerts.on_position_drift.call_args
        assert call_args.kwargs["drift_type"] == "quantity_mismatch"
        assert call_args.kwargs["action"] == "alerted"

    async def test_sync_positions_side_mismatch(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test that side mismatch is alerted."""
        from src.models import PositionResponse

        # Local position is long
        reconciliation_runner._positions["AAPL"] = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=150.0,
            entry_date=datetime.now(UTC),
        )

        # Broker position is short
        mock_alpaca_client.get_positions.return_value = [
            PositionResponse(
                symbol="AAPL",
                qty=10.0,
                side="short",
                cost_basis=1500.0,
                market_value=1550.0,
                unrealized_pnl=50.0,
                unrealized_pnl_percent=3.33,
                current_price=155.0,
            )
        ]
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # Alert should be sent for side mismatch
        reconciliation_runner.alerts.on_position_drift.assert_called_once()
        call_args = reconciliation_runner.alerts.on_position_drift.call_args
        assert call_args.kwargs["drift_type"] == "side_mismatch"
        assert call_args.kwargs["action"] == "alerted"

    async def test_sync_positions_ignores_non_strategy_symbols(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test that positions for non-strategy symbols are ignored."""
        from src.models import PositionResponse

        # Config only has AAPL, but broker has GOOGL position
        mock_alpaca_client.get_positions.return_value = [
            PositionResponse(
                symbol="GOOGL",  # Not in strategy symbols
                qty=5.0,
                side="long",
                cost_basis=5000.0,
                market_value=5100.0,
                unrealized_pnl=100.0,
                unrealized_pnl_percent=2.0,
                current_price=1020.0,
            )
        ]
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # GOOGL should not be added (not in strategy symbols)
        assert "GOOGL" not in reconciliation_runner._positions
        # No alerts should be sent
        reconciliation_runner.alerts.on_position_drift.assert_not_called()

    async def test_sync_positions_handles_api_error(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test graceful handling of Alpaca API errors."""
        # Simulate API error
        mock_alpaca_client.get_positions.side_effect = Exception("API timeout")
        reconciliation_runner.alpaca_client = mock_alpaca_client

        # Should not raise
        await reconciliation_runner._sync_positions()

        # Circuit breaker should record the error
        # (Verified by not crashing and logging the error)

    async def test_sync_positions_no_client(
        self,
        runner_config,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test that sync_positions does nothing without alpaca_client."""
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})
        runner = StrategyRunner(
            config=runner_config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
            alpaca_client=None,  # No client
        )

        # Should return early without error
        await runner._sync_positions()

    async def test_medium_drift_ignored(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test that medium drift (5-10%) is logged but not acted on."""
        from src.models import PositionResponse

        # Local position with quantity 10.0
        reconciliation_runner._positions["AAPL"] = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=150.0,
            entry_date=datetime.now(UTC),
        )

        # Broker has 10.7 (7% drift - between 5% and 10%)
        mock_alpaca_client.get_positions.return_value = [
            PositionResponse(
                symbol="AAPL",
                qty=10.7,
                side="long",
                cost_basis=1605.0,
                market_value=1658.5,
                unrealized_pnl=53.5,
                unrealized_pnl_percent=3.33,
                current_price=155.0,
            )
        ]
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # Position should NOT be corrected (drift too large)
        assert reconciliation_runner._positions["AAPL"].quantity == 10.0

        # No alert should be sent (drift not large enough)
        reconciliation_runner.alerts.on_position_drift.assert_not_called()


class TestTradingHoursIntegration:
    """Tests for trading hours integration in StrategyRunner."""

    @pytest.fixture
    def trading_hours_config(self, tenant_id, session_id, strategy_id):
        """Create a runner config with trading hours enforcement."""
        return RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=["AAPL"],
            timeframe="1min",
            warmup_bars=5,  # Lower warmup for faster tests
            enforce_trading_hours=True,
            allow_premarket=False,
            allow_afterhours=False,
        )

    @pytest.fixture
    def trading_hours_runner(
        self,
        trading_hours_config,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Create a runner with trading hours enforcement enabled."""
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})
        return StrategyRunner(
            config=trading_hours_config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )

    def test_trading_hours_checker_created_when_enabled(
        self,
        trading_hours_runner,
    ):
        """Test that TradingHoursChecker is created when enabled in config."""
        assert trading_hours_runner._trading_hours is not None

    def test_trading_hours_checker_not_created_when_disabled(
        self,
        tenant_id,
        session_id,
        strategy_id,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test that TradingHoursChecker is not created when disabled."""
        config = RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=["AAPL"],
            timeframe="1min",
            warmup_bars=5,
            enforce_trading_hours=False,  # Disabled
        )
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})
        runner = StrategyRunner(
            config=config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )

        assert runner._trading_hours is None

    async def test_process_bar_skips_outside_market_hours(
        self,
        trading_hours_runner,
        mock_strategy_fn,
        sample_bars,
    ):
        """Test that bars outside market hours are skipped."""
        from zoneinfo import ZoneInfo

        # Fill warmup history
        trading_hours_runner._bar_history["AAPL"] = sample_bars[:10]

        # Create a bar at 3:00 AM ET (outside market hours)
        eastern_tz = ZoneInfo("America/New_York")
        outside_hours_bar = BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 3, 0, tzinfo=eastern_tz),  # Monday 3:00 AM
            open=150.0,
            high=152.0,
            low=149.5,
            close=151.5,
            volume=10000,
        )

        await trading_hours_runner._process_bar(outside_hours_bar)

        # Strategy function should NOT be called
        mock_strategy_fn.assert_not_called()

    async def test_process_bar_executes_during_market_hours(
        self,
        trading_hours_runner,
        mock_strategy_fn,
        sample_bars,
    ):
        """Test that bars during market hours are processed."""
        from zoneinfo import ZoneInfo

        # Fill warmup history
        trading_hours_runner._bar_history["AAPL"] = sample_bars[:10]

        # Create a bar at 10:30 AM ET (during regular market hours)
        # Note: Jan 15, 2024 is MLK Day (holiday), so use Jan 16, 2024 (Tuesday)
        eastern_tz = ZoneInfo("America/New_York")
        market_hours_bar = BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 16, 10, 30, tzinfo=eastern_tz),  # Tuesday 10:30 AM
            open=150.0,
            high=152.0,
            low=149.5,
            close=151.5,
            volume=10000,
        )

        await trading_hours_runner._process_bar(market_hours_bar)

        # Strategy function should be called
        mock_strategy_fn.assert_called_once()

    async def test_premarket_skipped_when_disabled(
        self,
        trading_hours_runner,
        mock_strategy_fn,
        sample_bars,
    ):
        """Test that pre-market bars are skipped when allow_premarket=False."""
        from zoneinfo import ZoneInfo

        # Fill warmup history
        trading_hours_runner._bar_history["AAPL"] = sample_bars[:10]

        # Create a bar at 5:00 AM ET (pre-market, but disabled)
        eastern_tz = ZoneInfo("America/New_York")
        premarket_bar = BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 5, 0, tzinfo=eastern_tz),  # Monday 5:00 AM
            open=150.0,
            high=152.0,
            low=149.5,
            close=151.5,
            volume=10000,
        )

        await trading_hours_runner._process_bar(premarket_bar)

        # Strategy function should NOT be called
        mock_strategy_fn.assert_not_called()

    async def test_premarket_processed_when_enabled(
        self,
        tenant_id,
        session_id,
        strategy_id,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test that pre-market bars are processed when allow_premarket=True."""
        from zoneinfo import ZoneInfo

        config = RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=["AAPL"],
            timeframe="1min",
            warmup_bars=5,
            enforce_trading_hours=True,
            allow_premarket=True,  # Enabled
            allow_afterhours=False,
        )
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})
        runner = StrategyRunner(
            config=config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )

        # Fill warmup history
        runner._bar_history["AAPL"] = sample_bars[:10]

        # Create a bar at 5:00 AM ET (pre-market)
        # Note: Jan 15, 2024 is MLK Day (holiday), so use Jan 16, 2024 (Tuesday)
        eastern_tz = ZoneInfo("America/New_York")
        premarket_bar = BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 16, 5, 0, tzinfo=eastern_tz),  # Tuesday 5:00 AM
            open=150.0,
            high=152.0,
            low=149.5,
            close=151.5,
            volume=10000,
        )

        await runner._process_bar(premarket_bar)

        # Strategy function should be called (pre-market enabled)
        mock_strategy_fn.assert_called_once()

    async def test_afterhours_skipped_when_disabled(
        self,
        trading_hours_runner,
        mock_strategy_fn,
        sample_bars,
    ):
        """Test that after-hours bars are skipped when allow_afterhours=False."""
        from zoneinfo import ZoneInfo

        # Fill warmup history
        trading_hours_runner._bar_history["AAPL"] = sample_bars[:10]

        # Create a bar at 5:00 PM ET (after-hours, but disabled)
        eastern_tz = ZoneInfo("America/New_York")
        afterhours_bar = BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 17, 0, tzinfo=eastern_tz),  # Monday 5:00 PM
            open=150.0,
            high=152.0,
            low=149.5,
            close=151.5,
            volume=10000,
        )

        await trading_hours_runner._process_bar(afterhours_bar)

        # Strategy function should NOT be called
        mock_strategy_fn.assert_not_called()

    async def test_afterhours_processed_when_enabled(
        self,
        tenant_id,
        session_id,
        strategy_id,
        mock_strategy_fn,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test that after-hours bars are processed when allow_afterhours=True."""
        from zoneinfo import ZoneInfo

        config = RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=["AAPL"],
            timeframe="1min",
            warmup_bars=5,
            enforce_trading_hours=True,
            allow_premarket=False,
            allow_afterhours=True,  # Enabled
        )
        mock_stream = MockBarStream(bars={"AAPL": sample_bars})
        runner = StrategyRunner(
            config=config,
            strategy_fn=mock_strategy_fn,
            bar_stream=mock_stream,
            trade_stream=MockTradeStream(),
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )

        # Fill warmup history
        runner._bar_history["AAPL"] = sample_bars[:10]

        # Create a bar at 5:00 PM ET (after-hours)
        # Note: Jan 15, 2024 is MLK Day (holiday), so use Jan 16, 2024 (Tuesday)
        eastern_tz = ZoneInfo("America/New_York")
        afterhours_bar = BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 16, 17, 0, tzinfo=eastern_tz),  # Tuesday 5:00 PM
            open=150.0,
            high=152.0,
            low=149.5,
            close=151.5,
            volume=10000,
        )

        await runner._process_bar(afterhours_bar)

        # Strategy function should be called (after-hours enabled)
        mock_strategy_fn.assert_called_once()

    async def test_weekend_bars_skipped(
        self,
        trading_hours_runner,
        mock_strategy_fn,
        sample_bars,
    ):
        """Test that weekend bars are skipped even during normal time."""
        from zoneinfo import ZoneInfo

        # Fill warmup history
        trading_hours_runner._bar_history["AAPL"] = sample_bars[:10]

        # Create a bar on Saturday at 10:30 AM ET (weekend)
        eastern_tz = ZoneInfo("America/New_York")
        weekend_bar = BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 13, 10, 30, tzinfo=eastern_tz),  # Saturday 10:30 AM
            open=150.0,
            high=152.0,
            low=149.5,
            close=151.5,
            volume=10000,
        )

        await trading_hours_runner._process_bar(weekend_bar)

        # Strategy function should NOT be called
        mock_strategy_fn.assert_not_called()

    def test_config_default_values(self, tenant_id, session_id, strategy_id):
        """Test default values for trading hours config."""
        config = RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=["AAPL"],
            timeframe="1min",
        )

        assert config.enforce_trading_hours is True
        assert config.allow_premarket is False
        assert config.allow_afterhours is False
