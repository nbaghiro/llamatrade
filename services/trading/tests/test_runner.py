"""Test strategy runner."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from src.models import OrderResponse, OrderStatus
from src.runner.bar_stream import MockBarStream
from src.runner.runner import (
    Position,
    RunnerConfig,
    RunnerManager,
    Signal,
    StrategyRunner,
    get_runner_manager,
)


@pytest.fixture
def runner_config(tenant_id, session_id, strategy_id):
    """Create a runner configuration."""
    return RunnerConfig(
        tenant_id=tenant_id,
        deployment_id=session_id,
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
            side="buy",
            qty=10.0,
            order_type="market",
            status=OrderStatus.SUBMITTED,
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
    mock_stream = MockBarStream(bars={"AAPL": sample_bars})

    return StrategyRunner(
        config=runner_config,
        strategy_fn=mock_strategy_fn,
        bar_stream=mock_stream,
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
            deployment_id=session_id,
            strategy_id=strategy_id,
            symbols=["AAPL", "GOOGL"],
            timeframe="5min",
            warmup_bars=50,
        )

        assert config.tenant_id == tenant_id
        assert config.deployment_id == session_id
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
        assert order.side.value == "buy"
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
        assert order.side.value == "sell"
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

        assert order.side.value == "buy"

    def test_signal_to_order_short(self, strategy_runner):
        """Test converting short signal to order."""
        signal = Signal(
            type="short",
            symbol="AAPL",
            quantity=10.0,
            price=155.0,
        )

        order = strategy_runner._signal_to_order(signal)

        assert order.side.value == "sell"

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
            order_executor=mock_order_executor,
            risk_manager=mock_risk_manager,
        )
        # Use internal _runners dict, not active_runners property
        manager._runners[runner_config.deployment_id] = runner

        result = manager.get_runner(runner_config.deployment_id)

        assert result is runner
