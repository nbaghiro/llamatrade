"""Test strategy runner."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from llamatrade_alpaca import MockBarStream, MockTradeStream
from llamatrade_alpaca import StreamBar as BarData
from llamatrade_alpaca.models.trading import Position as AlpacaPosition
from llamatrade_alpaca.models.trading import PositionSide as AlpacaPositionSide
from llamatrade_db.models.trading import Order
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_MARKET,
)
from llamatrade_runtime import StrategySession
from tests.session_util import CountingSession, hold_session

from src.runner.runner import (
    RunnerConfig,
    RunnerManager,
    RunnerPosition,
    Signal,
    StrategyRunner,
    get_runner_manager,
)

EASTERN = ZoneInfo("America/New_York")


def _broker_position(
    symbol: str,
    qty: Decimal,
    side: str,
    cost_basis: Decimal,
    market_value: Decimal = Decimal("0"),
    unrealized_pnl: Decimal = Decimal("0"),
    unrealized_pnl_percent: Decimal = Decimal("0"),
    current_price: Decimal = Decimal("0"),
) -> AlpacaPosition:
    """A broker position as ``alpaca_client.get_positions()`` returns (Alpaca Position)."""
    return AlpacaPosition(
        symbol=symbol,
        qty=qty,
        side=AlpacaPositionSide(side),
        avg_entry_price=cost_basis / qty if qty else Decimal("0"),
        market_value=market_value,
        cost_basis=cost_basis,
        unrealized_pl=unrealized_pnl,
        unrealized_plpc=unrealized_pnl_percent,
        current_price=current_price,
    )


def _bar_at(ts: datetime, symbol: str = "AAPL", close: float = 150.0) -> BarData:
    return BarData(
        symbol=symbol,
        timestamp=ts,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=10000,
    )


def _build_runner(
    config: RunnerConfig,
    session: StrategySession,
    order_executor: AsyncMock,
    risk_manager: AsyncMock,
    bars: dict[str, list[BarData]] | None = None,
    alpaca_client: AsyncMock | None = None,
    alert_service: AsyncMock | None = None,
) -> StrategyRunner:
    return StrategyRunner(
        config=config,
        session=session,
        bar_stream=MockBarStream(bars=bars if bars is not None else {"AAPL": []}),
        trade_stream=MockTradeStream(),
        order_executor=order_executor,
        risk_manager=risk_manager,
        alpaca_client=alpaca_client,
        alert_service=alert_service,
    )


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
        return_value=Order(
            id=UUID("77777777-7777-7777-7777-777777777777"),
            alpaca_order_id="alpaca-order-123",
            symbol="AAPL",
            side=ORDER_SIDE_BUY,
            qty=Decimal("10.0"),
            order_type=ORDER_TYPE_MARKET,
            status=ORDER_STATUS_SUBMITTED,
            filled_qty=Decimal("0"),
            filled_avg_price=None,
            submitted_at=datetime.now(UTC),
            filled_at=None,
        )
    )
    return executor


@pytest.fixture
def strategy_runner(
    runner_config,
    mock_order_executor,
    mock_risk_manager,
    sample_bars,
):
    """Create a session-backed strategy runner with mocked I/O."""
    return _build_runner(
        runner_config,
        hold_session("AAPL"),
        mock_order_executor,
        mock_risk_manager,
        bars={"AAPL": sample_bars},
    )


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation(self):
        """Test creating a Signal instance."""
        signal = Signal(
            type="buy",
            symbol="AAPL",
            quantity=Decimal("10.0"),
            price=Decimal("150.0"),
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
        position = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10.0"),
            entry_price=Decimal("150.0"),
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
        strategy_runner.set_equity(Decimal("200000"))
        assert strategy_runner._equity == Decimal("200000")

    def test_sync_position_add(self, strategy_runner):
        """Test syncing a new position."""
        position = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10.0"),
            entry_price=Decimal("150.0"),
            entry_date=datetime.now(UTC),
        )

        strategy_runner.sync_position("AAPL", position)

        assert "AAPL" in strategy_runner.positions
        assert strategy_runner.positions["AAPL"].quantity == 10.0

    def test_sync_position_remove(self, strategy_runner):
        """Test removing a position via sync."""
        position = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10.0"),
            entry_price=Decimal("150.0"),
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
            quantity=Decimal("10.0"),
            price=Decimal("150.0"),
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
            quantity=Decimal("10.0"),
            price=Decimal("155.0"),
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
            quantity=Decimal("10.0"),
            price=Decimal("145.0"),
        )

        order = strategy_runner._signal_to_order(signal)

        assert order.side == ORDER_SIDE_BUY  # Cover = buy to close short

    def test_signal_to_order_short(self, strategy_runner):
        """Test converting short signal to order."""
        signal = Signal(
            type="short",
            symbol="AAPL",
            quantity=Decimal("10.0"),
            price=Decimal("155.0"),
        )

        order = strategy_runner._signal_to_order(signal)

        assert order.side == ORDER_SIDE_SELL  # Short = sell

    def test_circuit_breaker_property(self, strategy_runner):
        """Test circuit breaker property access."""
        assert strategy_runner.circuit_breaker is not None
        assert strategy_runner.circuit_breaker_triggered is False


class TestRunnerManager:
    """Tests for RunnerManager registry operations."""

    def test_manager_initialization(self):
        """Test manager initialization."""
        manager = RunnerManager()

        assert len(manager.active_runners) == 0

    def test_get_nonexistent_runner(self):
        """Test getting a non-existent runner."""
        manager = RunnerManager()

        runner = manager.get_runner(UUID("00000000-0000-0000-0000-000000000000"))

        assert runner is None

    async def test_stop_all_when_empty(self):
        """Test stop_all handles empty runners gracefully."""
        manager = RunnerManager()
        await manager.stop_all()
        assert len(manager.active_runners) == 0

    def test_get_runner_returns_existing_runner(
        self,
        runner_config,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test get_runner returns existing runner."""
        manager = RunnerManager()
        runner = _build_runner(
            runner_config,
            hold_session("AAPL"),
            mock_order_executor,
            mock_risk_manager,
            bars={"AAPL": sample_bars},
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
        mock_order_executor,
        mock_risk_manager,
        mock_alpaca_client,
        sample_bars,
    ):
        """Create a runner with position reconciliation enabled."""
        # Enable reconciliation in config
        runner_config.position_reconciliation_enabled = True
        runner_config.position_reconciliation_interval_seconds = 60
        runner_config.position_drift_auto_correct_threshold_pct = 5.0
        runner_config.position_drift_alert_threshold_pct = 10.0

        return _build_runner(
            runner_config,
            hold_session("AAPL"),
            mock_order_executor,
            mock_risk_manager,
            bars={"AAPL": sample_bars},
            alpaca_client=mock_alpaca_client,
            alert_service=AsyncMock(),
        )

    async def test_sync_positions_all_match(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test reconciliation when all positions match."""

        # Set up matching positions
        reconciliation_runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10.0"),
            entry_price=Decimal("150.0"),
            entry_date=datetime.now(UTC),
        )

        mock_alpaca_client.get_positions.return_value = [
            _broker_position(
                symbol="AAPL",
                qty=Decimal("10.0"),
                side="long",
                cost_basis=Decimal("1500.0"),
                market_value=Decimal("1550.0"),
                unrealized_pnl=Decimal("50.0"),
                unrealized_pnl_percent=Decimal("3.33"),
                current_price=Decimal("155.0"),
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
        reconciliation_runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10.0"),
            entry_price=Decimal("150.0"),
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

        # No local positions
        reconciliation_runner._positions = {}

        # Broker has a position
        mock_alpaca_client.get_positions.return_value = [
            _broker_position(
                symbol="AAPL",
                qty=Decimal("10.0"),
                side="long",
                cost_basis=Decimal("1500.0"),
                market_value=Decimal("1550.0"),
                unrealized_pnl=Decimal("50.0"),
                unrealized_pnl_percent=Decimal("3.33"),
                current_price=Decimal("155.0"),
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

        # Local position with quantity 10.0
        reconciliation_runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10.0"),
            entry_price=Decimal("150.0"),
            entry_date=datetime.now(UTC),
        )

        # Broker has 10.4 (4% drift - under 5% threshold)
        mock_alpaca_client.get_positions.return_value = [
            _broker_position(
                symbol="AAPL",
                qty=Decimal("10.4"),
                side="long",
                cost_basis=Decimal("1560.0"),
                market_value=Decimal("1612.0"),
                unrealized_pnl=Decimal("52.0"),
                unrealized_pnl_percent=Decimal("3.33"),
                current_price=Decimal("155.0"),
            )
        ]
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # Position should be auto-corrected to broker value
        assert reconciliation_runner._positions["AAPL"].quantity == Decimal("10.4")

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

        # Local position with quantity 10.0
        reconciliation_runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10.0"),
            entry_price=Decimal("150.0"),
            entry_date=datetime.now(UTC),
        )

        # Broker has 12.0 (20% drift - over 10% threshold)
        mock_alpaca_client.get_positions.return_value = [
            _broker_position(
                symbol="AAPL",
                qty=Decimal("12.0"),
                side="long",
                cost_basis=Decimal("1800.0"),
                market_value=Decimal("1860.0"),
                unrealized_pnl=Decimal("60.0"),
                unrealized_pnl_percent=Decimal("3.33"),
                current_price=Decimal("155.0"),
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

        # Local position is long
        reconciliation_runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10.0"),
            entry_price=Decimal("150.0"),
            entry_date=datetime.now(UTC),
        )

        # Broker position is short
        mock_alpaca_client.get_positions.return_value = [
            _broker_position(
                symbol="AAPL",
                qty=Decimal("10.0"),
                side="short",
                cost_basis=Decimal("1500.0"),
                market_value=Decimal("1550.0"),
                unrealized_pnl=Decimal("50.0"),
                unrealized_pnl_percent=Decimal("3.33"),
                current_price=Decimal("155.0"),
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

        # Config only has AAPL, but broker has GOOGL position
        mock_alpaca_client.get_positions.return_value = [
            _broker_position(
                symbol="GOOGL",  # Not in strategy symbols
                qty=Decimal("5.0"),
                side="long",
                cost_basis=Decimal("5000.0"),
                market_value=Decimal("5100.0"),
                unrealized_pnl=Decimal("100.0"),
                unrealized_pnl_percent=Decimal("2.0"),
                current_price=Decimal("1020.0"),
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
        """A broker failure is contained and counted as a reconciliation error."""
        mock_alpaca_client.get_positions.side_effect = Exception("API timeout")
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        assert reconciliation_runner.reconciliation_error_count == 1
        assert reconciliation_runner.last_reconciliation_time is None

    async def test_sync_positions_no_client(
        self,
        runner_config,
        mock_order_executor,
        mock_risk_manager,
        sample_bars,
    ):
        """Test that sync_positions does nothing without alpaca_client."""
        runner = _build_runner(
            runner_config,
            hold_session("AAPL"),
            mock_order_executor,
            mock_risk_manager,
            bars={"AAPL": sample_bars},
            alpaca_client=None,
        )

        # Should return early without error
        await runner._sync_positions()

    async def test_medium_drift_ignored(
        self,
        reconciliation_runner,
        mock_alpaca_client,
    ):
        """Test that medium drift (5-10%) is logged but not acted on."""

        # Local position with quantity 10.0
        reconciliation_runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10.0"),
            entry_price=Decimal("150.0"),
            entry_date=datetime.now(UTC),
        )

        # Broker has 10.7 (7% drift - between 5% and 10%)
        mock_alpaca_client.get_positions.return_value = [
            _broker_position(
                symbol="AAPL",
                qty=Decimal("10.7"),
                side="long",
                cost_basis=Decimal("1605.0"),
                market_value=Decimal("1658.5"),
                unrealized_pnl=Decimal("53.5"),
                unrealized_pnl_percent=Decimal("3.33"),
                current_price=Decimal("155.0"),
            )
        ]
        reconciliation_runner.alpaca_client = mock_alpaca_client

        await reconciliation_runner._sync_positions()

        # Position should NOT be corrected (drift too large)
        assert reconciliation_runner._positions["AAPL"].quantity == 10.0

        # No alert should be sent (drift not large enough)
        reconciliation_runner.alerts.on_position_drift.assert_not_called()


class TestSessionEvaluationGates:
    """The production gates in ``_evaluate_session``: market hours + breaker.

    Every runner evaluates through the merged-symbol session, so these tests
    pin the skip behavior with a real ``CountingSession`` (no strategy doubles).
    """

    def _runner(
        self,
        mock_order_executor: AsyncMock,
        mock_risk_manager: AsyncMock,
        tenant_id: UUID,
        session_id: UUID,
        strategy_id: UUID,
        **config_overrides: object,
    ) -> tuple[StrategyRunner, CountingSession]:
        config = RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=["AAPL"],
            timeframe="1min",
            warmup_bars=5,
            enforce_trading_hours=True,
            allow_premarket=False,
            allow_afterhours=False,
        )
        for key, value in config_overrides.items():
            setattr(config, key, value)
        session = CountingSession('(strategy "Hold" :rebalance daily (asset AAPL :weight 100))')
        runner = _build_runner(config, session, mock_order_executor, mock_risk_manager)
        return runner, session

    async def test_bar_outside_market_hours_is_not_evaluated(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner, session = self._runner(
            mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
        )

        # Monday 3:00 AM ET is outside every session.
        await runner._process_bar(_bar_at(datetime(2024, 1, 15, 3, 0, tzinfo=EASTERN)))

        assert session.evaluate_calls == 0
        mock_order_executor.submit_order.assert_not_awaited()

    async def test_bar_during_market_hours_is_evaluated(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner, session = self._runner(
            mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
        )

        # Tuesday Jan 16 2024, 10:30 AM ET (Jan 15 is MLK day).
        await runner._process_bar(_bar_at(datetime(2024, 1, 16, 10, 30, tzinfo=EASTERN)))

        assert session.evaluate_calls == 1

    async def test_premarket_bar_skipped_when_disabled(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner, session = self._runner(
            mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
        )

        await runner._process_bar(_bar_at(datetime(2024, 1, 16, 5, 0, tzinfo=EASTERN)))

        assert session.evaluate_calls == 0

    async def test_premarket_bar_evaluated_when_enabled(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner, session = self._runner(
            mock_order_executor,
            mock_risk_manager,
            tenant_id,
            session_id,
            strategy_id,
            allow_premarket=True,
        )

        await runner._process_bar(_bar_at(datetime(2024, 1, 16, 5, 0, tzinfo=EASTERN)))

        assert session.evaluate_calls == 1

    async def test_afterhours_bar_skipped_when_disabled(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner, session = self._runner(
            mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
        )

        await runner._process_bar(_bar_at(datetime(2024, 1, 16, 17, 0, tzinfo=EASTERN)))

        assert session.evaluate_calls == 0

    async def test_afterhours_bar_evaluated_when_enabled(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner, session = self._runner(
            mock_order_executor,
            mock_risk_manager,
            tenant_id,
            session_id,
            strategy_id,
            allow_afterhours=True,
        )

        await runner._process_bar(_bar_at(datetime(2024, 1, 16, 17, 0, tzinfo=EASTERN)))

        assert session.evaluate_calls == 1

    async def test_weekend_bar_is_not_evaluated(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner, session = self._runner(
            mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
        )

        # Saturday Jan 13 2024, 10:30 AM ET.
        await runner._process_bar(_bar_at(datetime(2024, 1, 13, 10, 30, tzinfo=EASTERN)))

        assert session.evaluate_calls == 0

    async def test_triggered_breaker_skips_evaluation(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner, session = self._runner(
            mock_order_executor,
            mock_risk_manager,
            tenant_id,
            session_id,
            strategy_id,
            enforce_trading_hours=False,
        )
        await runner._circuit_breaker.manual_trigger("halt")

        await runner._process_bar(_bar_at(datetime(2024, 1, 16, 10, 30, tzinfo=EASTERN)))

        assert session.evaluate_calls == 0
        mock_order_executor.submit_order.assert_not_awaited()

    async def test_untracked_symbol_is_ignored(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner, session = self._runner(
            mock_order_executor,
            mock_risk_manager,
            tenant_id,
            session_id,
            strategy_id,
            enforce_trading_hours=False,
        )

        await runner._process_bar(
            _bar_at(datetime(2024, 1, 16, 10, 30, tzinfo=EASTERN), symbol="TSLA")
        )

        assert session.evaluate_calls == 0
        mock_order_executor.submit_order.assert_not_awaited()


class TestLiveGate:
    """The runtime-loop gate ``_live_gate``: pause / market-open / breaker."""

    def _runner(
        self,
        mock_order_executor: AsyncMock,
        mock_risk_manager: AsyncMock,
        tenant_id: UUID,
        session_id: UUID,
        strategy_id: UUID,
        *,
        enforce_trading_hours: bool = True,
    ) -> StrategyRunner:
        config = RunnerConfig(
            tenant_id=tenant_id,
            execution_id=session_id,
            strategy_id=strategy_id,
            symbols=["AAPL"],
            timeframe="1min",
            warmup_bars=5,
            enforce_trading_hours=enforce_trading_hours,
        )
        return _build_runner(config, hold_session("AAPL"), mock_order_executor, mock_risk_manager)

    async def test_gate_open_during_market_hours(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner = self._runner(
            mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
        )

        assert runner._live_gate(datetime(2024, 1, 16, 10, 30, tzinfo=EASTERN)) is True

    async def test_gate_shut_while_paused(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner = self._runner(
            mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
        )
        runner.pause()

        assert runner._live_gate(datetime(2024, 1, 16, 10, 30, tzinfo=EASTERN)) is False

        runner.resume()
        assert runner._live_gate(datetime(2024, 1, 16, 10, 30, tzinfo=EASTERN)) is True

    async def test_gate_shut_outside_market_hours(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner = self._runner(
            mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
        )

        assert runner._live_gate(datetime(2024, 1, 16, 3, 0, tzinfo=EASTERN)) is False

    async def test_gate_ignores_market_hours_when_not_enforced(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner = self._runner(
            mock_order_executor,
            mock_risk_manager,
            tenant_id,
            session_id,
            strategy_id,
            enforce_trading_hours=False,
        )

        assert runner._live_gate(datetime(2024, 1, 16, 3, 0, tzinfo=EASTERN)) is True

    async def test_gate_shut_when_breaker_triggered(
        self, mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
    ):
        runner = self._runner(
            mock_order_executor, mock_risk_manager, tenant_id, session_id, strategy_id
        )
        await runner._circuit_breaker.manual_trigger("halt")

        assert runner._live_gate(datetime(2024, 1, 16, 10, 30, tzinfo=EASTERN)) is False
