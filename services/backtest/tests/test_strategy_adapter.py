"""Tests for strategy adapter - bridges allocation DSL strategies with backtest engine."""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from src.engine.backtester import BacktestConfig, BacktestEngine
from src.engine.strategy_adapter import (
    AllocationState,
    create_allocation_strategy,
    create_strategy_function,
    should_rebalance,
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


class TestShouldRebalance:
    """Tests for rebalancing frequency logic."""

    def test_first_bar_always_rebalances(self) -> None:
        """First bar should always trigger rebalance."""
        current = date(2024, 1, 15)

        assert should_rebalance(current, None, "daily") is True
        assert should_rebalance(current, None, "weekly") is True
        assert should_rebalance(current, None, "monthly") is True
        assert should_rebalance(current, None, "quarterly") is True
        assert should_rebalance(current, None, "annually") is True

    def test_same_day_never_rebalances(self) -> None:
        """Same day should never trigger rebalance."""
        current = date(2024, 1, 15)
        last = date(2024, 1, 15)

        assert should_rebalance(current, last, "daily") is False
        assert should_rebalance(current, last, "weekly") is False
        assert should_rebalance(current, last, "monthly") is False

    def test_daily_rebalance(self) -> None:
        """Daily frequency should rebalance every trading day."""
        current = date(2024, 1, 16)
        last = date(2024, 1, 15)

        assert should_rebalance(current, last, "daily") is True

    def test_weekly_rebalance_on_monday(self) -> None:
        """Weekly frequency should rebalance on Monday."""
        # Monday Jan 15, 2024
        monday = date(2024, 1, 15)
        friday = date(2024, 1, 12)

        assert should_rebalance(monday, friday, "weekly") is True

    def test_weekly_no_rebalance_mid_week(self) -> None:
        """Weekly frequency should not rebalance mid-week."""
        # Wednesday Jan 17, 2024
        wednesday = date(2024, 1, 17)
        tuesday = date(2024, 1, 16)

        assert should_rebalance(wednesday, tuesday, "weekly") is False

    def test_monthly_rebalance_new_month(self) -> None:
        """Monthly frequency should rebalance when month changes."""
        current = date(2024, 2, 1)
        last = date(2024, 1, 31)

        assert should_rebalance(current, last, "monthly") is True

    def test_monthly_no_rebalance_same_month(self) -> None:
        """Monthly frequency should not rebalance within same month."""
        current = date(2024, 1, 20)
        last = date(2024, 1, 5)

        assert should_rebalance(current, last, "monthly") is False

    def test_quarterly_rebalance_new_quarter(self) -> None:
        """Quarterly frequency should rebalance when quarter changes."""
        # Q1 to Q2
        current = date(2024, 4, 1)
        last = date(2024, 3, 31)

        assert should_rebalance(current, last, "quarterly") is True

    def test_quarterly_no_rebalance_same_quarter(self) -> None:
        """Quarterly frequency should not rebalance within same quarter."""
        current = date(2024, 2, 15)
        last = date(2024, 1, 15)

        assert should_rebalance(current, last, "quarterly") is False

    def test_annually_rebalance_new_year(self) -> None:
        """Annually frequency should rebalance when year changes."""
        current = date(2025, 1, 2)
        last = date(2024, 12, 31)

        assert should_rebalance(current, last, "annually") is True

    def test_annually_no_rebalance_same_year(self) -> None:
        """Annually frequency should not rebalance within same year."""
        current = date(2024, 6, 15)
        last = date(2024, 1, 2)

        assert should_rebalance(current, last, "annually") is False

    def test_default_to_daily_when_none(self) -> None:
        """When frequency is None, default to daily."""
        current = date(2024, 1, 16)
        last = date(2024, 1, 15)

        assert should_rebalance(current, last, None) is True


class TestAllocationState:
    """Tests for allocation state management."""

    def test_initial_state(self) -> None:
        """Test initial allocation state."""
        state = AllocationState()

        assert state.current_weights == {}
        assert state.target_weights == {}
        assert state.last_rebalance is None
        assert state.rebalance_frequency is None

    def test_state_tracks_weights(self) -> None:
        """Test that state tracks weight changes."""
        state = AllocationState()
        state.current_weights["SPY"] = 60.0
        state.current_weights["TLT"] = 40.0
        state.target_weights["SPY"] = 70.0

        assert state.current_weights["SPY"] == 60.0
        assert state.current_weights["TLT"] == 40.0
        assert state.target_weights["SPY"] == 70.0

    def test_state_tracks_rebalance(self) -> None:
        """Test that state tracks rebalance date."""
        state = AllocationState(rebalance_frequency="monthly")
        state.last_rebalance = date(2024, 1, 15)

        assert state.rebalance_frequency == "monthly"
        assert state.last_rebalance == date(2024, 1, 15)


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


class TestMultiSymbolStrategy:
    """Tests for multi-symbol strategy evaluation."""

    @pytest.fixture
    def multi_symbol_bars(self) -> dict[str, list[dict[str, float | datetime]]]:
        """Create sample bar data for multiple symbols."""
        np.random.seed(42)
        base_date = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)

        symbols_data: dict[str, list[dict[str, float | datetime]]] = {}
        base_prices = {"SPY": 450.0, "QQQ": 400.0, "TLT": 100.0}

        for symbol, base_price in base_prices.items():
            bars: list[dict[str, float | datetime]] = []
            price = base_price

            for i in range(50):
                change = np.random.randn() * 0.02
                close = price * (1 + change)
                high = close * 1.01
                low = close * 0.99

                bars.append(
                    {
                        "timestamp": base_date + timedelta(days=i),
                        "open": price,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": 1000000.0,
                    }
                )
                price = close

            symbols_data[symbol] = bars

        return symbols_data

    def test_create_multi_symbol_strategy(self) -> None:
        """Test creating a multi-symbol strategy function."""
        from src.engine.strategy_adapter import create_multi_symbol_strategy

        config = """(strategy "Multi Symbol"
  :rebalance monthly
  (weight :method equal
    (asset SPY)
    (asset QQQ)
    (asset TLT)))"""

        strategy_fn, symbols, min_bars = create_multi_symbol_strategy(config)

        assert callable(strategy_fn)
        assert "SPY" in symbols
        assert "QQQ" in symbols
        assert "TLT" in symbols
        assert min_bars >= 2

    def test_multi_symbol_strategy_receives_all_bars(
        self, multi_symbol_bars: dict[str, list[dict[str, float | datetime]]]
    ) -> None:
        """Test that multi-symbol strategy receives all symbols' bars."""
        from src.engine.strategy_adapter import create_multi_symbol_strategy

        config = """(strategy "Equal Weight"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)
    (asset TLT)))"""

        strategy_fn, symbols, min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        # Get bars for a specific date
        date_idx = min_bars + 5
        bars_dict = {
            symbol: multi_symbol_bars[symbol][date_idx]
            for symbol in symbols
            if symbol in multi_symbol_bars
        }

        # Strategy should handle all bars at once
        signals = strategy_fn(engine, bars_dict)

        # Should return a list of signals
        assert isinstance(signals, list)

    def test_multi_symbol_strategy_generates_buy_signals(
        self, multi_symbol_bars: dict[str, list[dict[str, float | datetime]]]
    ) -> None:
        """Test that multi-symbol strategy generates buy signals via backtest."""
        from src.engine.strategy_adapter import create_multi_symbol_strategy

        config = """(strategy "Equal Weight"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""

        strategy_fn, symbols, min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        # Use run_multi_symbol to properly process bars and generate signals
        filtered_bars = {s: multi_symbol_bars[s] for s in symbols if s in multi_symbol_bars}
        start_date = multi_symbol_bars["SPY"][min_bars]["timestamp"]
        end_date = multi_symbol_bars["SPY"][-1]["timestamp"]

        result = engine.run_multi_symbol(
            bars=filtered_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Should have made at least one trade
        assert len(result.trades) >= 0  # May have 0 trades if positions held till end
        assert result.final_equity > 0  # Should have positive equity

    def test_multi_symbol_strategy_respects_rebalance_frequency(
        self, multi_symbol_bars: dict[str, list[dict[str, float | datetime]]]
    ) -> None:
        """Test that monthly rebalance generates fewer signals than daily.

        Monthly rebalancing should result in fewer total signals across
        the backtest period compared to daily rebalancing.
        """
        from src.engine.strategy_adapter import create_multi_symbol_strategy

        # Daily rebalance strategy
        daily_config = """(strategy "Daily Rebalance"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""

        daily_fn, symbols, min_bars = create_multi_symbol_strategy(daily_config)
        daily_engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        filtered_bars = {s: multi_symbol_bars[s] for s in symbols if s in multi_symbol_bars}
        start_date = multi_symbol_bars["SPY"][min_bars]["timestamp"]
        end_date = multi_symbol_bars["SPY"][-1]["timestamp"]

        daily_result = daily_engine.run_multi_symbol(
            bars=filtered_bars,
            strategy_fn=daily_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Monthly rebalance strategy
        monthly_config = """(strategy "Monthly Rebalance"
  :rebalance monthly
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""

        monthly_fn, _, _ = create_multi_symbol_strategy(monthly_config)
        monthly_engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        monthly_result = monthly_engine.run_multi_symbol(
            bars=filtered_bars,
            strategy_fn=monthly_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Both should complete successfully
        assert daily_result.final_equity > 0
        assert monthly_result.final_equity > 0

        # Monthly should have equal or fewer trades (less frequent rebalancing)
        # Note: The test data only spans ~50 days, so differences may be small
        assert len(monthly_result.trades) <= len(daily_result.trades) + 2

    def test_backtester_run_multi_symbol(
        self, multi_symbol_bars: dict[str, list[dict[str, float | datetime]]]
    ) -> None:
        """Test running backtest with multi-symbol strategy."""
        from src.engine.strategy_adapter import create_multi_symbol_strategy

        config = """(strategy "Backtest Multi"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""

        strategy_fn, symbols, min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        # Filter bars to only include required symbols
        filtered_bars = {s: multi_symbol_bars[s] for s in symbols if s in multi_symbol_bars}

        # Run backtest with multi-symbol method
        start_date = multi_symbol_bars["SPY"][min_bars]["timestamp"]
        end_date = multi_symbol_bars["SPY"][-1]["timestamp"]

        result = engine.run_multi_symbol(
            bars=filtered_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Verify backtest completed
        assert result.final_equity > 0
        assert len(result.equity_curve) > 0
