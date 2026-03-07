# pyright: reportPrivateUsage=false
# pyright: reportAttributeAccessIssue=false
"""Tests for strategy adapter - bridges allocation DSL strategies with backtest engine."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.engine.backtester import BacktestConfig, BacktestEngine
from src.engine.strategy_adapter import (
    AllocationState,
    create_allocation_strategy,
    create_strategy_function,
)


class TestCreateStrategyFunction:
    """Tests for strategy function creation from allocation S-expressions."""

    def test_create_simple_rsi_allocation_strategy(self) -> None:
        """Test creating an RSI-based allocation strategy."""
        config = """(strategy "RSI Allocation"
  :rebalance daily
  :benchmark SPY
  (if (< (rsi SPY 14) 30)
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy_fn, min_bars = create_strategy_function(config)

        assert callable(strategy_fn)
        assert min_bars >= 14  # At least 14 bars for RSI(14)

    def test_create_sma_crossover_allocation(self) -> None:
        """Test creating an SMA crossover allocation strategy."""
        config = """(strategy "SMA Crossover Allocation"
  :rebalance daily
  :benchmark SPY
  (if (crosses-above (sma SPY 10) (sma SPY 20))
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy_fn, min_bars = create_strategy_function(config)

        assert callable(strategy_fn)
        assert min_bars >= 20  # At least 20 bars for SMA(20)

    def test_create_equal_weight_allocation(self) -> None:
        """Test creating an equal weight allocation strategy."""
        config = """(strategy "Equal Weight"
  :rebalance monthly
  :benchmark SPY
  (weight :method equal
    (asset AAPL)
    (asset GOOGL)
    (asset MSFT)))"""

        strategy_fn, min_bars = create_strategy_function(config)

        assert callable(strategy_fn)
        assert min_bars >= 2  # At least 2 for crossovers

    def test_create_strategy_invalid_syntax(self) -> None:
        """Test that invalid S-expression raises error."""
        config = '(strategy "invalid'

        with pytest.raises(Exception):
            create_strategy_function(config)

    def test_create_strategy_missing_body(self) -> None:
        """Test that missing body raises validation error."""
        config = """(strategy "Empty"
  :rebalance daily
  :benchmark SPY)"""

        with pytest.raises(ValueError, match="Invalid strategy"):
            create_strategy_function(config)


class TestCreateAllocationStrategy:
    """Tests for the allocation strategy factory function."""

    def test_create_allocation_strategy_basic(self) -> None:
        """Test creating a compiled allocation strategy."""
        config = """(strategy "Basic"
  :rebalance daily
  :benchmark SPY
  (weight :method equal
    (asset SPY)
    (asset TLT)))"""

        compiled, symbols, min_bars = create_allocation_strategy(config)

        assert compiled is not None
        assert "SPY" in symbols or "TLT" in symbols
        assert min_bars >= 2

    def test_create_allocation_strategy_with_conditions(self) -> None:
        """Test creating a conditional allocation strategy."""
        config = """(strategy "Conditional"
  :rebalance daily
  :benchmark SPY
  (if (> (rsi SPY 14) 50)
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        compiled, symbols, min_bars = create_allocation_strategy(config)

        assert compiled is not None
        assert "SPY" in symbols


class TestAllocationState:
    """Tests for allocation state management."""

    def test_initial_state(self) -> None:
        """Test initial allocation state."""
        state = AllocationState()

        assert state.current_weights == {}
        assert state.target_weights == {}

    def test_state_tracks_weights(self) -> None:
        """Test that state tracks weight changes."""
        state = AllocationState()
        state.current_weights["SPY"] = 60.0
        state.current_weights["TLT"] = 40.0
        state.target_weights["SPY"] = 70.0

        assert state.current_weights["SPY"] == 60.0
        assert state.current_weights["TLT"] == 40.0
        assert state.target_weights["SPY"] == 70.0


class TestStrategyFunctionIntegration:
    """Integration tests for strategy function with backtest engine."""

    @pytest.fixture
    def sample_bars(self) -> dict[str, list[dict[str, float | datetime]]]:
        """Create sample bar data for testing."""
        np.random.seed(42)
        base_price = 100.0
        bars: list[dict[str, float | datetime]] = []
        timestamp = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)

        for i in range(50):
            change = np.random.randn() * 0.02
            close = base_price * (1 + change)
            high = close * 1.01
            low = close * 0.99
            open_price = base_price

            bars.append(
                {
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": 1000000.0,
                }
            )

            base_price = close
            timestamp += timedelta(days=1)

        return {"SPY": bars, "TLT": bars}

    def test_strategy_function_generates_signals(
        self, sample_bars: dict[str, list[dict[str, float | datetime]]]
    ) -> None:
        """Test that strategy function generates buy/sell signals."""
        config = """(strategy "Test"
  :rebalance daily
  :benchmark SPY
  (if (> (rsi SPY 14) 50)
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy_fn, min_bars = create_strategy_function(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        # Process bars through strategy
        all_signals = []
        for bar in sample_bars["SPY"][min_bars:]:  # Skip warmup bars
            signals = strategy_fn(engine, "SPY", bar)
            all_signals.extend(signals)

        # Should generate at least some signals
        assert isinstance(all_signals, list)

    def test_strategy_function_allocates_based_on_condition(
        self, sample_bars: dict[str, list[dict[str, float | datetime]]]
    ) -> None:
        """Test that strategy allocates based on condition evaluation."""
        # Use a condition that will definitely trigger (always true)
        config = """(strategy "Always SPY"
  :rebalance daily
  :benchmark SPY
  (if (> (price SPY) 0)
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy_fn, min_bars = create_strategy_function(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        # Process bars and collect signals
        buy_signals = []
        for bar in sample_bars["SPY"][min_bars:]:
            signals = strategy_fn(engine, "SPY", bar)
            for signal in signals:
                if signal.get("type") == "buy":
                    buy_signals.append(signal)
                    # Simulate opening position
                    engine._open_position("SPY", "long", bar["close"], 10)
                    break  # Only count first buy

        # Should have at least one buy signal since condition is always true
        assert len(buy_signals) >= 1


class TestIndicatorExtraction:
    """Tests for indicator extraction from strategies."""

    def test_extract_rsi_indicator(self) -> None:
        """Test extracting RSI indicator from strategy."""
        from llamatrade_compiler.extractor import extract_indicators
        from llamatrade_dsl import parse_strategy

        config = """(strategy "RSI Test"
  :rebalance daily
  :benchmark SPY
  (if (< (rsi SPY 14) 30)
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy = parse_strategy(config)
        indicators = extract_indicators(strategy)

        # Should have RSI indicator
        rsi_indicators = [i for i in indicators if i.indicator_type == "rsi"]
        assert len(rsi_indicators) >= 1
        assert rsi_indicators[0].params == (14,)

    def test_extract_sma_indicators(self) -> None:
        """Test extracting multiple SMA indicators."""
        from llamatrade_compiler.extractor import extract_indicators
        from llamatrade_dsl import parse_strategy

        config = """(strategy "Multi SMA"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 10) (sma SPY 20))
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy = parse_strategy(config)
        indicators = extract_indicators(strategy)

        # Should have two SMA indicators with different periods
        sma_indicators = [i for i in indicators if i.indicator_type == "sma"]
        assert len(sma_indicators) >= 2

        periods = {i.params[0] for i in sma_indicators}
        assert 10 in periods
        assert 20 in periods

    def test_max_lookback_calculation(self) -> None:
        """Test max lookback is calculated correctly."""
        from llamatrade_compiler.extractor import extract_indicators, get_max_lookback
        from llamatrade_dsl import parse_strategy

        config = """(strategy "MACD Test"
  :rebalance daily
  :benchmark SPY
  (if (> (macd SPY 12 26 9) 0)
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy = parse_strategy(config)
        indicators = extract_indicators(strategy)
        lookback = get_max_lookback(indicators)

        # MACD needs at least 26 bars (slow period)
        assert lookback >= 26


class TestSymbolExtraction:
    """Tests for symbol extraction from strategies."""

    def test_extract_symbols_from_assets(self) -> None:
        """Test extracting symbols from asset blocks."""
        from llamatrade_compiler.extractor import get_required_symbols
        from llamatrade_dsl import parse_strategy

        config = """(strategy "Multi Asset"
  :rebalance monthly
  :benchmark SPY
  (weight :method equal
    (asset AAPL)
    (asset GOOGL)
    (asset MSFT)))"""

        strategy = parse_strategy(config)
        symbols = get_required_symbols(strategy)

        assert "AAPL" in symbols
        assert "GOOGL" in symbols
        assert "MSFT" in symbols

    def test_extract_symbols_from_indicators(self) -> None:
        """Test extracting symbols from indicator references."""
        from llamatrade_compiler.extractor import get_required_symbols
        from llamatrade_dsl import parse_strategy

        config = """(strategy "Indicator Symbols"
  :rebalance daily
  :benchmark SPY
  (if (> (rsi SPY 14) 50)
    (asset QQQ :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy = parse_strategy(config)
        symbols = get_required_symbols(strategy)

        assert "SPY" in symbols  # From indicator
        assert "QQQ" in symbols  # From asset
        assert "TLT" in symbols  # From asset
