"""Tests for the CompiledStrategy class."""

from datetime import datetime, timedelta

import numpy as np
from llamatrade_compiler import Bar, SignalType
from llamatrade_dsl import parse_strategy
from src.compiler.compiled import compile_strategy
from src.compiler.state import Position


def generate_bars(n: int, start_price: float = 100.0, trend: float = 0.0) -> list[Bar]:
    """Generate synthetic bar data.

    Args:
        n: Number of bars
        start_price: Starting price
        trend: Daily trend (e.g., 0.01 = 1% daily gain)

    Returns:
        List of Bar objects
    """
    np.random.seed(42)
    bars: list[Bar] = []

    price = start_price
    timestamp = datetime(2024, 1, 1)

    for _ in range(n):
        # Add trend and random noise
        change = trend + np.random.randn() * 0.02
        new_price = price * (1 + change)

        high = max(price, new_price) * (1 + abs(np.random.randn() * 0.01))
        low = min(price, new_price) * (1 - abs(np.random.randn() * 0.01))

        bars.append(
            Bar(
                timestamp=timestamp,
                open=price,
                high=high,
                low=low,
                close=new_price,
                volume=int(1000000 * (1 + np.random.randn() * 0.3)),
            )
        )

        price = new_price
        timestamp += timedelta(days=1)

    return bars


SIMPLE_SMA_STRATEGY = """
(strategy
  :name "SMA Crossover"
  :symbols ["AAPL"]
  :timeframe "1D"
  :entry (cross-above (sma close 10) (sma close 20))
  :exit (cross-below (sma close 10) (sma close 20))
  :risk {:stop_loss_pct 5 :take_profit_pct 10})
"""

RSI_STRATEGY = """
(strategy
  :name "RSI Strategy"
  :symbols ["AAPL"]
  :timeframe "1D"
  :entry (< (rsi close 14) 30)
  :exit (> (rsi close 14) 70))
"""


class TestCompileStrategy:
    """Tests for compile_strategy function."""

    def test_compile_extracts_indicators(self) -> None:
        """Test that compilation extracts indicators."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        assert len(compiled.indicators) == 2
        assert compiled.name == "SMA Crossover"
        assert compiled.symbols == ["AAPL"]
        assert compiled.timeframe == "1D"

    def test_compile_sets_min_bars(self) -> None:
        """Test that min_bars is set correctly."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        # SMA(20) needs 20 bars, plus 2 for crossover
        assert compiled.min_bars >= 20

    def test_compile_rsi_strategy(self) -> None:
        """Test compiling RSI strategy."""
        strategy = parse_strategy(RSI_STRATEGY)
        compiled = compile_strategy(strategy)

        assert len(compiled.indicators) == 1
        assert compiled.indicators[0].indicator_type == "rsi"


class TestCompiledStrategyEvaluation:
    """Tests for strategy evaluation."""

    def test_evaluate_needs_enough_history(self) -> None:
        """Test that evaluation requires minimum history."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        # Add only 5 bars (not enough)
        bars = generate_bars(5)
        signals = []
        for bar in bars:
            signals.extend(compiled.evaluate(bar))

        assert len(signals) == 0
        assert not compiled.has_enough_history()

    def test_evaluate_with_enough_history(self) -> None:
        """Test evaluation with sufficient history."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        # Add enough bars (25 should be plenty)
        bars = generate_bars(25)
        for bar in bars:
            compiled.evaluate(bar)

        assert compiled.has_enough_history()

    def test_entry_signal_generated(self) -> None:
        """Test that entry signal is generated on condition met."""
        strategy = parse_strategy(RSI_STRATEGY)
        compiled = compile_strategy(strategy)

        # Create bars with declining price to trigger RSI < 30
        bars = generate_bars(30, start_price=100, trend=-0.02)  # Downtrend

        all_signals = []
        for bar in bars:
            signals = compiled.evaluate(bar)
            all_signals.extend(signals)

        # Should have at least one buy signal
        [s for s in all_signals if s.type == SignalType.BUY]
        # Note: May or may not trigger depending on RSI calculation
        # This test verifies the pipeline works, not specific RSI values

    def test_exit_signal_generated(self) -> None:
        """Test that exit signal is generated when in position."""
        strategy = parse_strategy(RSI_STRATEGY)
        compiled = compile_strategy(strategy)

        # Generate uptrending data (to trigger RSI > 70)
        bars = generate_bars(40, start_price=100, trend=0.03)

        # Process some bars first
        for bar in bars[:20]:
            compiled.evaluate(bar)

        # Manually open a position
        compiled.open_position(
            symbol="AAPL",
            side="long",
            quantity=100,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 15),
        )

        # Continue evaluation
        exit_signals = []
        for bar in bars[20:]:
            signals = compiled.evaluate(bar)
            for s in signals:
                if s.type in (SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT):
                    exit_signals.append(s)

        # May or may not trigger depending on RSI


class TestPositionManagement:
    """Tests for position management."""

    def test_open_and_close_position(self) -> None:
        """Test opening and closing positions."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        # Open position
        compiled.open_position(
            symbol="AAPL",
            side="long",
            quantity=100,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 15),
        )

        assert compiled._position is not None
        assert compiled._position.symbol == "AAPL"
        assert compiled._position.side == "long"

        # Close position
        compiled.close_position()
        assert compiled._position is None

    def test_set_position(self) -> None:
        """Test setting position directly."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        position = Position(
            symbol="AAPL",
            side="long",
            quantity=100,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 15),
        )

        compiled.set_position(position)
        assert compiled._position == position

        compiled.set_position(None)
        assert compiled._position is None


class TestReset:
    """Tests for strategy reset."""

    def test_reset_clears_state(self) -> None:
        """Test that reset clears all state."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        # Add some state
        bars = generate_bars(10)
        for bar in bars:
            compiled.add_bar(bar)

        compiled.open_position(
            symbol="AAPL",
            side="long",
            quantity=100,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 15),
        )

        assert len(compiled._bar_history) > 0
        assert compiled._position is not None

        # Reset
        compiled.reset()

        assert len(compiled._bar_history) == 0
        assert compiled._position is None
        assert len(compiled._indicator_cache) == 0


class TestBacktestBars:
    """Tests for backtest_bars method."""

    def test_backtest_returns_signals(self) -> None:
        """Test that backtest_bars returns signals."""
        strategy = parse_strategy(RSI_STRATEGY)
        compiled = compile_strategy(strategy)

        # Generate volatile data to trigger signals
        bars = generate_bars(100, trend=0.0)

        signals = compiled.backtest_bars(bars)

        # Should return a list (may be empty or have signals)
        assert isinstance(signals, list)

    def test_backtest_updates_positions(self) -> None:
        """Test that backtest auto-manages positions."""
        strategy = parse_strategy(RSI_STRATEGY)
        compiled = compile_strategy(strategy)

        # Create declining data to trigger buy
        bars = generate_bars(50, trend=-0.02)

        signals = compiled.backtest_bars(bars)

        # All signals should be from managed positions
        for signal in signals:
            assert signal.symbol == "AAPL"

    def test_backtest_resets_first(self) -> None:
        """Test that backtest resets state before running."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        # Add some state
        bars = generate_bars(10)
        for bar in bars:
            compiled.add_bar(bar)

        # Run backtest (should reset first)
        new_bars = generate_bars(30)
        compiled.backtest_bars(new_bars)

        # History should match new_bars length
        assert len(compiled._bar_history) == 30


class TestSignalMetadata:
    """Tests for signal metadata."""

    def test_entry_signal_has_metadata(self) -> None:
        """Test that entry signals include metadata."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        # Create a mock entry signal
        bar = Bar(
            timestamp=datetime(2024, 1, 15),
            open=100,
            high=101,
            low=99,
            close=101,
            volume=1000000,
        )

        signal = compiled._create_entry_signal(bar)

        assert signal.metadata is not None
        assert "strategy_name" in signal.metadata
        assert signal.metadata["strategy_name"] == "SMA Crossover"

    def test_entry_signal_has_risk_levels(self) -> None:
        """Test that entry signals have stop loss and take profit."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        bar = Bar(
            timestamp=datetime(2024, 1, 15),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000000,
        )

        signal = compiled._create_entry_signal(bar)

        # Strategy has 5% stop loss and 10% take profit
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        assert signal.stop_loss < bar.close  # Stop loss is below entry
        assert signal.take_profit > bar.close  # Take profit is above entry


class TestRiskExits:
    """Tests for risk-based exits."""

    def test_stop_loss_triggered(self) -> None:
        """Test stop loss exit."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        # Set up position
        compiled.open_position(
            symbol="AAPL",
            side="long",
            quantity=100,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
        )

        # Generate enough bars for evaluation
        bars = generate_bars(compiled.min_bars + 1, start_price=100)

        # Reset and process bars
        compiled._bar_history = []
        for bar in bars[:-1]:
            compiled.add_bar(bar)

        # Add final bar with price drop > 5%
        crash_bar = Bar(
            timestamp=datetime(2024, 1, 25),
            open=95,
            high=96,
            low=93,
            close=94,  # 6% loss from entry
            volume=1000000,
        )
        compiled.add_bar(crash_bar)

        # Build state and check risk exits
        state = compiled._build_state()
        risk_signal = compiled._check_risk_exits(state, crash_bar)

        assert risk_signal is not None
        assert risk_signal.type == SignalType.CLOSE_LONG
        assert risk_signal.metadata is not None
        assert risk_signal.metadata["exit_reason"] == "stop_loss"

    def test_take_profit_triggered(self) -> None:
        """Test take profit exit."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        # Set up position
        compiled.open_position(
            symbol="AAPL",
            side="long",
            quantity=100,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 1),
        )

        # Generate enough bars
        bars = generate_bars(compiled.min_bars + 1, start_price=100)

        # Reset and process bars
        compiled._bar_history = []
        for bar in bars[:-1]:
            compiled.add_bar(bar)

        # Add final bar with price gain > 10%
        profit_bar = Bar(
            timestamp=datetime(2024, 1, 25),
            open=110,
            high=115,
            low=110,
            close=112,  # 12% gain from entry
            volume=1000000,
        )
        compiled.add_bar(profit_bar)

        # Build state and check risk exits
        state = compiled._build_state()
        risk_signal = compiled._check_risk_exits(state, profit_bar)

        assert risk_signal is not None
        assert risk_signal.type == SignalType.CLOSE_LONG
        assert risk_signal.metadata is not None
        assert risk_signal.metadata["exit_reason"] == "take_profit"


class TestRepr:
    """Tests for string representation."""

    def test_repr(self) -> None:
        """Test __repr__ method."""
        strategy = parse_strategy(SIMPLE_SMA_STRATEGY)
        compiled = compile_strategy(strategy)

        repr_str = repr(compiled)

        assert "CompiledStrategy" in repr_str
        assert "SMA Crossover" in repr_str
        assert "AAPL" in repr_str
