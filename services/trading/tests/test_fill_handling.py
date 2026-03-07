"""Tests for event-driven position updates via trade stream fills."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models import RiskCheckResult
from src.runner.bar_stream import MockBarStream
from src.runner.runner import Position, RunnerConfig, Signal, StrategyRunner
from src.runner.trade_stream import (
    FillData,
    MockTradeStream,
    TradeEvent,
    TradeEventType,
)


@pytest.fixture
def sample_config():
    """Create a sample runner config."""
    return RunnerConfig(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        strategy_id=uuid4(),
        symbols=["AAPL", "GOOGL"],
        timeframe="1Min",
        warmup_bars=20,
        enforce_trading_hours=False,
    )


@pytest.fixture
def mock_alpaca_client():
    """Create a mock Alpaca client."""
    client = AsyncMock()
    client.get_account = AsyncMock(return_value={"equity": "100000.00", "cash": "100000.00"})
    client.get_positions = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_risk_manager():
    """Create a mock risk manager."""
    manager = AsyncMock()
    manager.check_order = AsyncMock(return_value=RiskCheckResult(passed=True, violations=[]))
    return manager


@pytest.fixture
def mock_order_executor():
    """Create a mock order executor."""
    executor = MagicMock()
    executor.submit_order = AsyncMock(
        return_value=MagicMock(
            id=uuid4(),
            client_order_id="test-client-order-123",
            alpaca_order_id="alpaca-123",
            symbol="AAPL",
            status=2,  # SUBMITTED
        )
    )
    return executor


@pytest.fixture
def simple_strategy():
    """Create a simple strategy function that generates no signals."""

    def strategy(symbol, bars, position, equity):
        return None

    return strategy


@pytest.fixture
def runner_with_trade_stream(
    sample_config,
    simple_strategy,
    mock_alpaca_client,
    mock_risk_manager,
    mock_order_executor,
):
    """Create a runner with trade stream enabled."""
    bar_stream = MockBarStream(bars={})
    trade_stream = MockTradeStream()

    return StrategyRunner(
        config=sample_config,
        strategy_fn=simple_strategy,
        bar_stream=bar_stream,
        order_executor=mock_order_executor,
        risk_manager=mock_risk_manager,
        alpaca_client=mock_alpaca_client,
        trade_stream=trade_stream,
    )


class TestRunnerWithTradeStream:
    """Tests for runner with trade stream integration."""

    def test_runner_accepts_trade_stream(self, runner_with_trade_stream):
        """Test that runner accepts trade_stream parameter."""
        assert runner_with_trade_stream.trade_stream is not None

    def test_metrics_include_trade_stream_status(self, runner_with_trade_stream):
        """Test that metrics include trade stream connected status."""
        metrics = runner_with_trade_stream.metrics
        assert "trade_stream_connected" in metrics
        assert metrics["trade_stream_connected"] is False  # Not connected yet

    def test_metrics_include_fills_processed(self, runner_with_trade_stream):
        """Test that metrics include fills processed count."""
        metrics = runner_with_trade_stream.metrics
        assert "fills_processed" in metrics
        assert metrics["fills_processed"] == 0

    def test_metrics_include_pending_orders(self, runner_with_trade_stream):
        """Test that metrics include pending orders count."""
        metrics = runner_with_trade_stream.metrics
        assert "pending_orders" in metrics
        assert metrics["pending_orders"] == 0


class TestFillEventHandling:
    """Tests for fill event handling."""

    async def test_handle_fill_opens_long_position(
        self,
        runner_with_trade_stream,
    ):
        """Test that a buy fill opens a long position."""
        runner = runner_with_trade_stream
        now = datetime.now(UTC)

        # Create fill event
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("10"),
            fill_price=Decimal("150.00"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        event = TradeEvent(
            event_type=TradeEventType.FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("150.00"),
            timestamp=now,
            fill=fill,
        )

        # Process fill
        await runner._handle_fill_event(event)

        # Check position created
        assert "AAPL" in runner._positions
        pos = runner._positions["AAPL"]
        assert pos.side == "long"
        assert pos.quantity == 10.0
        assert pos.entry_price == 150.0

    async def test_handle_fill_closes_long_position(
        self,
        runner_with_trade_stream,
    ):
        """Test that a sell fill closes a long position."""
        runner = runner_with_trade_stream
        now = datetime.now(UTC)

        # Set up existing long position
        runner._positions["AAPL"] = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=145.0,
            entry_date=now,
        )

        # Create sell fill event
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="sell",
            fill_qty=Decimal("10"),
            fill_price=Decimal("155.00"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        event = TradeEvent(
            event_type=TradeEventType.FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="sell",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("155.00"),
            timestamp=now,
            fill=fill,
        )

        # Process fill
        await runner._handle_fill_event(event)

        # Check position closed
        assert "AAPL" not in runner._positions

    async def test_handle_fill_adds_to_long_position(
        self,
        runner_with_trade_stream,
    ):
        """Test that a buy fill adds to existing long position."""
        runner = runner_with_trade_stream
        now = datetime.now(UTC)

        # Set up existing long position
        runner._positions["AAPL"] = Position(
            symbol="AAPL",
            side="long",
            quantity=10.0,
            entry_price=140.0,
            entry_date=now,
        )

        # Create buy fill event to add more
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("10"),
            fill_price=Decimal("160.00"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        event = TradeEvent(
            event_type=TradeEventType.FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("160.00"),
            timestamp=now,
            fill=fill,
        )

        # Process fill
        await runner._handle_fill_event(event)

        # Check position updated
        assert "AAPL" in runner._positions
        pos = runner._positions["AAPL"]
        assert pos.side == "long"
        assert pos.quantity == 20.0
        # Average price: (140 * 10 + 160 * 10) / 20 = 150
        assert pos.entry_price == 150.0

    async def test_handle_fill_opens_short_position(
        self,
        runner_with_trade_stream,
    ):
        """Test that a sell fill opens a short position when no position exists."""
        runner = runner_with_trade_stream
        now = datetime.now(UTC)

        # Create sell fill event (no existing position)
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="sell",
            fill_qty=Decimal("10"),
            fill_price=Decimal("150.00"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        event = TradeEvent(
            event_type=TradeEventType.FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="sell",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("150.00"),
            timestamp=now,
            fill=fill,
        )

        # Process fill
        await runner._handle_fill_event(event)

        # Check short position created
        assert "AAPL" in runner._positions
        pos = runner._positions["AAPL"]
        assert pos.side == "short"
        assert pos.quantity == 10.0

    async def test_handle_fill_covers_short_position(
        self,
        runner_with_trade_stream,
    ):
        """Test that a buy fill covers a short position."""
        runner = runner_with_trade_stream
        now = datetime.now(UTC)

        # Set up existing short position
        runner._positions["AAPL"] = Position(
            symbol="AAPL",
            side="short",
            quantity=10.0,
            entry_price=155.0,
            entry_date=now,
        )

        # Create buy fill event (cover)
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("10"),
            fill_price=Decimal("145.00"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        event = TradeEvent(
            event_type=TradeEventType.FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("145.00"),
            timestamp=now,
            fill=fill,
        )

        # Process fill
        await runner._handle_fill_event(event)

        # Check position closed
        assert "AAPL" not in runner._positions

    async def test_fills_processed_metric_increments(
        self,
        runner_with_trade_stream,
    ):
        """Test that fills_processed counter increments on fill."""
        runner = runner_with_trade_stream
        now = datetime.now(UTC)

        assert runner._fills_processed == 0

        # Process a fill
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("10"),
            fill_price=Decimal("150.00"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        event = TradeEvent(
            event_type=TradeEventType.FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("150.00"),
            timestamp=now,
            fill=fill,
        )

        await runner._handle_fill_event(event)

        assert runner._fills_processed == 1


class TestPendingOrderTracking:
    """Tests for pending order tracking."""

    async def test_pending_order_removed_on_fill(
        self,
        runner_with_trade_stream,
    ):
        """Test that pending orders are removed on fill."""
        runner = runner_with_trade_stream
        now = datetime.now(UTC)

        # Add pending order
        signal = Signal(
            type="buy",
            symbol="AAPL",
            quantity=10.0,
            price=150.0,
        )
        runner._pending_orders["client-456"] = signal

        # Process fill
        fill = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("10"),
            fill_price=Decimal("150.00"),
            total_filled_qty=Decimal("10"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        event = TradeEvent(
            event_type=TradeEventType.FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("10"),
            filled_avg_price=Decimal("150.00"),
            timestamp=now,
            fill=fill,
        )

        await runner._handle_fill_event(event)

        # Check pending order removed
        assert "client-456" not in runner._pending_orders


class TestOrderCancellation:
    """Tests for order cancellation handling."""

    async def test_canceled_order_removed_from_pending(
        self,
        runner_with_trade_stream,
    ):
        """Test that canceled orders are removed from pending."""
        runner = runner_with_trade_stream

        # Add pending order
        signal = Signal(
            type="buy",
            symbol="AAPL",
            quantity=10.0,
            price=150.0,
        )
        runner._pending_orders["client-456"] = signal

        # Process cancellation
        event = TradeEvent(
            event_type=TradeEventType.CANCELED,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            timestamp=datetime.now(UTC),
        )

        await runner._handle_order_canceled(event)

        # Check pending order removed
        assert "client-456" not in runner._pending_orders

    async def test_canceled_order_does_not_affect_position(
        self,
        runner_with_trade_stream,
    ):
        """Test that canceled order doesn't change positions."""
        runner = runner_with_trade_stream

        # No positions initially
        assert len(runner._positions) == 0

        # Process cancellation
        event = TradeEvent(
            event_type=TradeEventType.CANCELED,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            timestamp=datetime.now(UTC),
        )

        await runner._handle_order_canceled(event)

        # Still no positions
        assert len(runner._positions) == 0


class TestOrderRejection:
    """Tests for order rejection handling."""

    async def test_rejected_order_removed_from_pending(
        self,
        runner_with_trade_stream,
    ):
        """Test that rejected orders are removed from pending."""
        runner = runner_with_trade_stream

        # Add pending order
        signal = Signal(
            type="buy",
            symbol="AAPL",
            quantity=10.0,
            price=150.0,
        )
        runner._pending_orders["client-456"] = signal

        # Process rejection
        event = TradeEvent(
            event_type=TradeEventType.REJECTED,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            timestamp=datetime.now(UTC),
        )

        await runner._handle_order_rejected(event)

        # Check pending order removed
        assert "client-456" not in runner._pending_orders

    async def test_rejected_order_increments_rejected_count(
        self,
        runner_with_trade_stream,
    ):
        """Test that rejected orders increment rejected counter."""
        runner = runner_with_trade_stream
        initial_rejected = runner._orders_rejected

        # Add pending order
        signal = Signal(
            type="buy",
            symbol="AAPL",
            quantity=10.0,
            price=150.0,
        )
        runner._pending_orders["client-456"] = signal

        # Process rejection
        event = TradeEvent(
            event_type=TradeEventType.REJECTED,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("10"),
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            timestamp=datetime.now(UTC),
        )

        await runner._handle_order_rejected(event)

        assert runner._orders_rejected == initial_rejected + 1


class TestPartialFills:
    """Tests for partial fill handling."""

    async def test_partial_fill_updates_position(
        self,
        runner_with_trade_stream,
    ):
        """Test that partial fills update position incrementally."""
        runner = runner_with_trade_stream
        now = datetime.now(UTC)

        # First partial fill - 50 of 100 shares
        fill1 = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("50"),
            fill_price=Decimal("150.00"),
            total_filled_qty=Decimal("50"),
            remaining_qty=Decimal("50"),
            timestamp=now,
        )
        event1 = TradeEvent(
            event_type=TradeEventType.PARTIAL_FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("100"),
            filled_qty=Decimal("50"),
            filled_avg_price=Decimal("150.00"),
            timestamp=now,
            fill=fill1,
        )

        await runner._handle_partial_fill_event(event1)

        # Check position partially created
        assert "AAPL" in runner._positions
        pos = runner._positions["AAPL"]
        assert pos.quantity == 50.0

        # Second fill - remaining 50 shares
        fill2 = FillData(
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            fill_qty=Decimal("50"),
            fill_price=Decimal("151.00"),
            total_filled_qty=Decimal("100"),
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        event2 = TradeEvent(
            event_type=TradeEventType.FILL,
            order_id="order-123",
            client_order_id="client-456",
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=Decimal("100"),
            filled_qty=Decimal("100"),
            filled_avg_price=Decimal("150.50"),
            timestamp=now,
            fill=fill2,
        )

        await runner._handle_fill_event(event2)

        # Check full position
        pos = runner._positions["AAPL"]
        assert pos.quantity == 100.0
        # Average: (50 * 150 + 50 * 151) / 100 = 150.5
        assert pos.entry_price == 150.5
