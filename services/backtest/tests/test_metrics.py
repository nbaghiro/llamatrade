"""Golden-value tests for the shared metrics module.

These are the authoritative tests for backtest metric math. Values are
hand-computed for small fixed series so a regression in any formula fails
against a constant, not against a re-implementation of the same formula.
"""

from datetime import UTC, datetime

import numpy as np
import pytest

from src.engine.metrics import (
    calculate_max_drawdown,
    calculate_monthly_returns,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_trade_statistics,
)


class _FakeTrade:
    def __init__(self, pnl: float):
        self._pnl = pnl

    @property
    def pnl(self) -> float:
        return self._pnl


class TestSharpeRatio:
    def test_empty_returns_zero(self):
        assert calculate_sharpe_ratio(np.array([])) == 0.0

    def test_constant_returns_zero(self):
        """Zero variance means Sharpe is undefined; we report 0."""
        assert calculate_sharpe_ratio(np.array([0.01, 0.01, 0.01])) == 0.0

    def test_known_value(self):
        """returns [0.2, 0.0], rf=0: mean=0.1, std=0.1 → sqrt(252)*1."""
        result = calculate_sharpe_ratio(np.array([0.2, 0.0]), risk_free_rate=0.0)
        assert result == pytest.approx(np.sqrt(252), rel=1e-9)

    def test_risk_free_rate_reduces_sharpe(self):
        with_rf = calculate_sharpe_ratio(np.array([0.2, 0.0]), risk_free_rate=0.02)
        without_rf = calculate_sharpe_ratio(np.array([0.2, 0.0]), risk_free_rate=0.0)
        assert with_rf < without_rf


class TestSortinoRatio:
    def test_empty_returns_zero(self):
        assert calculate_sortino_ratio(np.array([])) == 0.0

    def test_no_negative_returns_zero(self):
        """No downside deviation → undefined → 0."""
        assert calculate_sortino_ratio(np.array([0.01, 0.02])) == 0.0

    def test_known_value(self):
        """returns [0.1, -0.1, -0.3]: mean=-0.1; downside std=0.1 → sqrt(252)*-1."""
        result = calculate_sortino_ratio(np.array([0.1, -0.1, -0.3]))
        assert result == pytest.approx(-np.sqrt(252), rel=1e-9)


class TestMaxDrawdown:
    def test_empty_equity(self):
        assert calculate_max_drawdown(np.array([])) == (0.0, 0)

    def test_monotonic_rise_has_no_drawdown(self):
        dd, duration = calculate_max_drawdown(np.array([100.0, 110.0, 120.0]))
        assert dd == 0.0
        assert duration == 0

    def test_known_value(self):
        """Peak 120 → trough 90 is a 25% drawdown lasting 2 bars."""
        equity = np.array([100.0, 120.0, 90.0, 100.0, 130.0])
        dd, duration = calculate_max_drawdown(equity)
        assert dd == pytest.approx(0.25)
        assert duration == 2


class TestMonthlyReturns:
    def test_empty_curve(self):
        assert calculate_monthly_returns([], 100000) == {}

    def test_known_values(self):
        """Jan: 100 → 110 (+10%); Feb: 110 → 99 (−10%)."""
        curve = [
            (datetime(2024, 1, 10, tzinfo=UTC), 105.0),
            (datetime(2024, 1, 31, tzinfo=UTC), 110.0),
            (datetime(2024, 2, 15, tzinfo=UTC), 120.0),
            (datetime(2024, 2, 28, tzinfo=UTC), 99.0),
        ]
        result = calculate_monthly_returns(curve, initial_capital=100.0)
        assert result["2024-01"] == pytest.approx(0.10)
        assert result["2024-02"] == pytest.approx(-0.10)


class TestTradeStatistics:
    def test_no_trades_profit_factor_undefined(self):
        win_rate, pf = calculate_trade_statistics([])
        assert win_rate == 0.0
        assert pf is None

    def test_no_losses_profit_factor_undefined(self):
        """All-winning trades must not report PF=0 — that's 'undefined'."""
        win_rate, pf = calculate_trade_statistics([_FakeTrade(10.0), _FakeTrade(5.0)])
        assert win_rate == 1.0
        assert pf is None

    def test_known_values(self):
        """Wins 10+20=30, losses 10 → PF=3.0, win rate 2/3."""
        trades = [_FakeTrade(10.0), _FakeTrade(20.0), _FakeTrade(-10.0)]
        win_rate, pf = calculate_trade_statistics(trades)
        assert win_rate == pytest.approx(2 / 3)
        assert pf == pytest.approx(3.0)


class TestReturns:
    def test_empty_equity(self):
        assert calculate_returns(np.array([]), 100000, 0) == (0.0, 0.0, [])

    def test_known_values(self):
        """100 → 121 over a full year (252 days) is 21% total and annual."""
        equity = np.array([100.0, 110.0, 121.0])
        total, annual, daily = calculate_returns(equity, 100.0, num_days=252)
        assert total == pytest.approx(0.21)
        assert annual == pytest.approx(0.21)
        assert daily == pytest.approx([0.1, 0.1])

    def test_annualization_compounds_short_periods(self):
        """+10% over half a year (126 days) annualizes to (1.1)^2 − 1 = 21%."""
        equity = np.array([100.0, 110.0])
        _, annual, _ = calculate_returns(equity, 100.0, num_days=126)
        assert annual == pytest.approx(0.21)


class TestResampleDaily:
    def test_empty(self):
        from src.engine.metrics import resample_daily

        assert resample_daily([]) == []

    def test_daily_curve_is_identity(self):
        from src.engine.metrics import resample_daily

        curve = [
            (datetime(2024, 1, 1, 16, tzinfo=UTC), 100.0),
            (datetime(2024, 1, 2, 16, tzinfo=UTC), 101.0),
        ]
        assert resample_daily(curve) == curve

    def test_intraday_collapses_to_last_point_per_day(self):
        from src.engine.metrics import resample_daily

        curve = [
            (datetime(2024, 1, 1, 10, tzinfo=UTC), 100.0),
            (datetime(2024, 1, 1, 12, tzinfo=UTC), 105.0),
            (datetime(2024, 1, 1, 16, tzinfo=UTC), 102.0),
            (datetime(2024, 1, 2, 10, tzinfo=UTC), 103.0),
            (datetime(2024, 1, 2, 16, tzinfo=UTC), 104.0),
        ]
        result = resample_daily(curve)
        assert result == [
            (datetime(2024, 1, 1, 16, tzinfo=UTC), 102.0),
            (datetime(2024, 1, 2, 16, tzinfo=UTC), 104.0),
        ]


class TestTimeframeInvariance:
    """Annualized metrics must not depend on bar resolution.

    Regression: metrics were annualized with 252 periods/year regardless of
    timeframe, inflating intraday Sharpe by ~sqrt(bars per day).
    """

    def test_hourly_and_daily_curves_yield_same_metrics(self):
        from src.engine.backtester import BacktestConfig, BacktestEngine

        rng = np.random.default_rng(7)
        daily_closes = [100.0]
        for _ in range(59):
            daily_closes.append(daily_closes[-1] * (1 + float(rng.normal(0, 0.01))))

        def run(bars_per_day: int):
            bars = {
                "SPY": [
                    {
                        "timestamp": datetime(2024, 1, 1, tzinfo=UTC)
                        + __import__("datetime").timedelta(days=day, hours=h),
                        "open": close,
                        "high": close * 1.01,
                        "low": close * 0.99,
                        # intermediate intraday bars wiggle, last bar = daily close
                        "close": close * (1.001 if h < bars_per_day - 1 else 1.0),
                        "volume": 1000,
                    }
                    for day, close in enumerate(daily_closes)
                    for h in range(bars_per_day)
                ]
            }
            engine = BacktestEngine(BacktestConfig(initial_capital=100000))

            def buy_and_hold(eng, bars_dict, warm_up):
                symbol, bar = next(iter(bars_dict.items()))
                if not eng.has_position(symbol):
                    qty = eng.get_cash() * 0.9 / bar["close"]
                    return [{"type": "buy", "symbol": symbol, "quantity": qty}]
                return []

            return engine.run(
                bars=bars,
                strategy_fn=buy_and_hold,
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 3, 31, tzinfo=UTC),
            )

        daily_result = run(bars_per_day=1)
        hourly_result = run(bars_per_day=7)

        # Same daily closes → same daily grid → near-identical annual metrics
        assert hourly_result.annual_return == pytest.approx(daily_result.annual_return, rel=0.05)
        assert hourly_result.sharpe_ratio == pytest.approx(
            daily_result.sharpe_ratio, rel=0.10, abs=0.2
        )
        assert len(hourly_result.daily_equity_curve) == len(daily_result.daily_equity_curve)


class TestAlignDailyReturns:
    """Date-joined benchmark alignment (replaces positional truncation)."""

    def test_missing_benchmark_date_does_not_shift_series(self):
        from src.engine.benchmarks import align_daily_returns

        base = datetime(2024, 1, 1, 16, tzinfo=UTC)
        day = __import__("datetime").timedelta(days=1)

        strategy_curve = [(base + i * day, 100.0 * (1.01**i)) for i in range(5)]
        # Benchmark missing day 2
        bench_bars = [
            {"timestamp": base + i * day, "close": 50.0 * (1.02**i)} for i in (0, 1, 3, 4)
        ]

        strat, bench = align_daily_returns(strategy_curve, bench_bars)

        # Joined on days 1 and 4 only (day-over-day returns need consecutive
        # points within each series; benchmark day 3's return spans the gap)
        assert len(strat) == len(bench)
        assert len(strat) >= 2
        # Strategy returns are exactly 1% on every kept date — no shift
        assert all(abs(r - 0.01) < 1e-9 for r in strat)

    def test_identical_series_have_identical_returns(self):
        from src.engine.benchmarks import align_daily_returns

        base = datetime(2024, 1, 1, 16, tzinfo=UTC)
        day = __import__("datetime").timedelta(days=1)
        points = [(base + i * day, 100.0 * (1.01**i)) for i in range(10)]
        bars = [{"timestamp": dt, "close": eq} for dt, eq in points]

        strat, bench = align_daily_returns(points, bars)
        assert np.allclose(strat, bench)


class TestDegenerateEquityGuards:
    """7A: degenerate equity (zero/negative) must never yield inf/nan metrics."""

    def test_max_drawdown_with_zero_equity_is_finite(self):
        equity = np.array([100.0, 0.0, 50.0])
        max_dd, duration = calculate_max_drawdown(equity)
        assert np.isfinite(max_dd)
        assert max_dd >= 0.0
        assert isinstance(duration, int)

    def test_max_drawdown_all_zero_is_finite(self):
        equity = np.array([0.0, 0.0, 0.0])
        max_dd, _ = calculate_max_drawdown(equity)
        assert np.isfinite(max_dd)

    def test_daily_returns_skip_nonpositive_denominators(self):
        # Equity touches zero then recovers — the division must not produce inf.
        equity = np.array([100.0, 0.0, 10.0])
        _total, _annual, daily = calculate_returns(equity, initial_capital=100.0, num_days=3)
        assert all(np.isfinite(r) for r in daily)

    def test_annual_return_finite_when_portfolio_wiped_out(self):
        # Final equity below zero would make (1 + total_return) negative and a
        # fractional power complex/nan; it must clamp to a finite value.
        equity = np.array([100.0, 50.0, -10.0])
        total, annual, daily = calculate_returns(equity, initial_capital=100.0, num_days=3)
        assert isinstance(annual, float) and np.isfinite(annual)
        assert isinstance(total, float) and np.isfinite(total)
        assert all(np.isfinite(r) for r in daily)
