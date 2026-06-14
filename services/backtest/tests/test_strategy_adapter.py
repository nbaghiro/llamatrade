"""Tests for strategy adapter - bridges allocation DSL strategies with backtest engine.

The adapter is multi-symbol only: all symbols' bars are evaluated together on
each date, so cross-symbol conditions work and every symbol can trade on a
shared rebalance day.
"""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from src.engine.backtester import BacktestConfig, BacktestEngine, BarData
from src.engine.strategy_adapter import (
    create_multi_symbol_strategy,
    should_rebalance,
)


def make_bars(
    closes_by_symbol: dict[str, list[float]],
    start: datetime | None = None,
) -> dict[str, list[BarData]]:
    """Build daily bars from per-symbol close series."""
    start = start or datetime(2024, 1, 1, 10, 0, tzinfo=UTC)
    bars: dict[str, list[BarData]] = {}
    for symbol, closes in closes_by_symbol.items():
        bars[symbol] = [
            {
                "timestamp": start + timedelta(days=i),
                "open": close * 0.999,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1_000_000,
            }
            for i, close in enumerate(closes)
        ]
    return bars


class TestCreateMultiSymbolStrategy:
    """Tests for strategy function creation from allocation S-expressions."""

    def test_create_simple_rsi_allocation_strategy(self) -> None:
        """Test creating an RSI-based allocation strategy."""
        config = """(strategy "RSI Allocation"
  :rebalance daily
  :benchmark SPY
  (if (< (rsi SPY 14) 30)
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy_fn, symbols, min_bars = create_multi_symbol_strategy(config)

        assert callable(strategy_fn)
        assert "SPY" in symbols
        assert "TLT" in symbols
        assert min_bars >= 14  # At least 14 bars for RSI(14)

    def test_create_sma_crossover_allocation(self) -> None:
        """Test creating an SMA crossover allocation strategy."""
        config = """(strategy "SMA Crossover Allocation"
  :rebalance daily
  :benchmark SPY
  (if (crosses-above (sma SPY 10) (sma SPY 20))
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

        strategy_fn, _symbols, min_bars = create_multi_symbol_strategy(config)

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

        strategy_fn, symbols, min_bars = create_multi_symbol_strategy(config)

        assert callable(strategy_fn)
        assert symbols == {"AAPL", "GOOGL", "MSFT"}
        assert min_bars >= 2  # At least 2 for crossovers

    def test_create_strategy_invalid_syntax(self) -> None:
        """Test that invalid S-expression raises error."""
        config = '(strategy "invalid'

        with pytest.raises(Exception):
            create_multi_symbol_strategy(config)

    def test_create_strategy_missing_body(self) -> None:
        """Test that missing body raises validation error."""
        config = """(strategy "Empty"
  :rebalance daily
  :benchmark SPY)"""

        with pytest.raises(ValueError, match="Invalid strategy"):
            create_multi_symbol_strategy(config)


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


class TestMultiSymbolRegressions:
    """Named regression tests for the bugs that motivated the adapter rewrite."""

    def test_all_symbols_trade_on_shared_rebalance_day(self) -> None:
        """Every allocated symbol must trade on the same rebalance day.

        Regression: the old per-symbol adapter advanced last_rebalance after
        the first symbol of the day, so only one symbol ever traded per
        rebalance.
        """
        config = """(strategy "Equal Weight"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""

        strategy_fn, _symbols, min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        n = min_bars + 10
        bars = make_bars({"SPY": [400.0] * n, "QQQ": [300.0] * n})
        start_date = bars["SPY"][min_bars]["timestamp"]
        end_date = bars["SPY"][-1]["timestamp"]

        result = engine.run(
            bars=bars, strategy_fn=strategy_fn, start_date=start_date, end_date=end_date
        )

        traded_symbols = {t.symbol for t in result.trades}
        assert traded_symbols == {"SPY", "QQQ"}
        first_entries = {t.symbol: t.entry_date for t in result.trades}
        assert first_entries["SPY"] == first_entries["QQQ"] == start_date

    def test_cross_symbol_condition_evaluates(self) -> None:
        """A condition on one symbol must drive allocation of another.

        Regression: the old per-symbol adapter passed only one symbol's bar to
        compute_allocation, so RSI(SPY) could never gate a TLT allocation.

        SPY rises monotonically → RSI(SPY) is ~100 → the strategy must hold
        TLT and never buy SPY.
        """
        config = """(strategy "Risk Off"
  :rebalance daily
  (if (> (rsi SPY 14) 70)
    (asset TLT :weight 100)
    (else (asset SPY :weight 100))))"""

        strategy_fn, _symbols, min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        n = min_bars + 15
        spy_closes = [400.0 + 2.0 * i for i in range(n)]  # monotonic rise → RSI 100
        tlt_closes = [100.0] * n
        bars = make_bars({"SPY": spy_closes, "TLT": tlt_closes})
        start_date = bars["SPY"][min_bars]["timestamp"]
        end_date = bars["SPY"][-1]["timestamp"]

        result = engine.run(
            bars=bars, strategy_fn=strategy_fn, start_date=start_date, end_date=end_date
        )

        traded_symbols = {t.symbol for t in result.trades}
        assert traded_symbols == {"TLT"}, (
            f"Expected only TLT trades (RSI(SPY) > 70), got {traded_symbols}"
        )

    def test_bars_feed_indicators_on_non_rebalance_days(self) -> None:
        """Indicators must see every bar, not just rebalance-day bars.

        Regression: bars were only added to the compiled strategy's history on
        rebalance days, so a monthly-rebalance RSI(14) strategy needed 14
        months instead of 14 days of history.

        With ~3 weeks of warm-up and monthly rebalancing, the first trading
        day must still produce an allocation.
        """
        config = """(strategy "Monthly RSI"
  :rebalance monthly
  (if (> (rsi SPY 14) 70)
    (asset TLT :weight 100)
    (else (asset SPY :weight 100))))"""

        strategy_fn, _symbols, min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        n = min_bars + 10
        bars = make_bars({"SPY": [400.0 - i * 0.5 for i in range(n)], "TLT": [100.0] * n})
        start_date = bars["SPY"][min_bars]["timestamp"]
        end_date = bars["SPY"][-1]["timestamp"]

        result = engine.run(
            bars=bars, strategy_fn=strategy_fn, start_date=start_date, end_date=end_date
        )

        # Falling SPY → RSI low → hold SPY; the allocation must happen on the
        # FIRST trading day because daily bars warmed the indicators up.
        assert result.trades, "Expected an initial allocation on the first rebalance day"
        assert min(t.entry_date for t in result.trades) == start_date

    def test_warm_up_does_not_advance_rebalance_state(self) -> None:
        """A warm-up call must not consume the rebalance schedule.

        If warm-up advanced last_rebalance, a monthly strategy starting
        mid-month would silently skip its initial allocation.
        """
        config = """(strategy "Monthly Equal"
  :rebalance monthly
  (weight :method equal
    (asset SPY)))"""

        strategy_fn, _symbols, min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        # Warm-up and trading window are in the SAME month
        n = min_bars + 8
        bars = make_bars({"SPY": [400.0] * n}, start=datetime(2024, 3, 1, 10, 0, tzinfo=UTC))
        start_date = bars["SPY"][min_bars]["timestamp"]
        end_date = bars["SPY"][-1]["timestamp"]

        result = engine.run(
            bars=bars, strategy_fn=strategy_fn, start_date=start_date, end_date=end_date
        )

        assert result.trades, "Initial allocation must happen despite same-month warm-up"
        assert min(t.entry_date for t in result.trades) == start_date


class TestIndicatorExtraction:
    """Tests for indicator extraction from strategies."""

    def test_extract_rsi_indicator(self) -> None:
        """Test extracting RSI indicator from strategy."""
        from llamatrade_compiler import extract_indicators
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
        from llamatrade_compiler import extract_indicators
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
        from llamatrade_compiler import extract_indicators, get_max_lookback
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
        from llamatrade_compiler import get_required_symbols
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
        from llamatrade_compiler import get_required_symbols
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


class TestMultiSymbolIntegration:
    """Integration tests for multi-symbol strategy with the backtest engine."""

    @pytest.fixture
    def multi_symbol_bars(self) -> dict[str, list[BarData]]:
        """Create sample random-walk bar data for multiple symbols."""
        np.random.seed(42)
        base_prices = {"SPY": 450.0, "QQQ": 400.0, "TLT": 100.0}
        closes: dict[str, list[float]] = {}

        for symbol, base_price in base_prices.items():
            price = base_price
            series: list[float] = []
            for _ in range(50):
                price = price * (1 + float(np.random.randn()) * 0.02)
                series.append(price)
            closes[symbol] = series

        return make_bars(closes)

    def test_strategy_function_direct_call(
        self, multi_symbol_bars: dict[str, list[BarData]]
    ) -> None:
        """Calling the strategy function directly returns a signal list."""
        config = """(strategy "Equal Weight"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)
    (asset TLT)))"""

        strategy_fn, symbols, min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        date_idx = min_bars + 5
        bars_dict = {symbol: multi_symbol_bars[symbol][date_idx] for symbol in symbols}

        signals = strategy_fn(engine, bars_dict, False)
        assert isinstance(signals, list)

    def test_warm_up_call_returns_no_signals(
        self, multi_symbol_bars: dict[str, list[BarData]]
    ) -> None:
        """Warm-up calls accumulate history and never emit signals."""
        config = """(strategy "Equal Weight"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""

        strategy_fn, symbols, _min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        for i in range(30):
            bars_dict = {symbol: multi_symbol_bars[symbol][i] for symbol in symbols}
            assert strategy_fn(engine, bars_dict, True) == []

    def test_multi_symbol_strategy_generates_trades(
        self, multi_symbol_bars: dict[str, list[BarData]]
    ) -> None:
        """An equal-weight strategy run end-to-end produces trades and equity."""
        config = """(strategy "Equal Weight"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""

        strategy_fn, symbols, min_bars = create_multi_symbol_strategy(config)
        engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        filtered_bars = {s: multi_symbol_bars[s] for s in symbols}
        start_date = multi_symbol_bars["SPY"][min_bars]["timestamp"]
        end_date = multi_symbol_bars["SPY"][-1]["timestamp"]

        result = engine.run(
            bars=filtered_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        assert result.final_equity > 0
        assert len(result.equity_curve) > 0
        assert {t.symbol for t in result.trades} == {"SPY", "QQQ"}

    def test_monthly_rebalance_trades_less_than_daily(
        self, multi_symbol_bars: dict[str, list[BarData]]
    ) -> None:
        """Monthly rebalancing should not trade more than daily rebalancing."""
        daily_config = """(strategy "Daily Rebalance"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""

        daily_fn, symbols, min_bars = create_multi_symbol_strategy(daily_config)
        daily_engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        filtered_bars = {s: multi_symbol_bars[s] for s in symbols}
        start_date = multi_symbol_bars["SPY"][min_bars]["timestamp"]
        end_date = multi_symbol_bars["SPY"][-1]["timestamp"]

        daily_result = daily_engine.run(
            bars=filtered_bars,
            strategy_fn=daily_fn,
            start_date=start_date,
            end_date=end_date,
        )

        monthly_config = """(strategy "Monthly Rebalance"
  :rebalance monthly
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""

        monthly_fn, _, _ = create_multi_symbol_strategy(monthly_config)
        monthly_engine = BacktestEngine(BacktestConfig(initial_capital=100000))

        monthly_result = monthly_engine.run(
            bars=filtered_bars,
            strategy_fn=monthly_fn,
            start_date=start_date,
            end_date=end_date,
        )

        assert daily_result.final_equity > 0
        assert monthly_result.final_equity > 0
        assert len(monthly_result.trades) <= len(daily_result.trades)
