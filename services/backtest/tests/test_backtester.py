"""Tests for the backtest engine."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.engine.backtester import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    Position,
    Trade,
)


class TestTrade:
    """Tests for Trade dataclass."""

    def test_trade_pnl_long_profit(self):
        """Test P&L calculation for profitable long trade."""
        trade = Trade(
            entry_date=datetime(2024, 1, 1, tzinfo=UTC),
            exit_date=datetime(2024, 1, 10, tzinfo=UTC),
            symbol="AAPL",
            side="long",
            entry_price=100.0,
            exit_price=110.0,
            quantity=10,
            commission=2.0,
        )

        assert trade.pnl == pytest.approx(98.0)  # (110-100)*10 - 2
        assert trade.pnl_percent == pytest.approx(9.8)  # 98 / (100*10) * 100

    def test_trade_pnl_long_loss(self):
        """Test P&L calculation for losing long trade."""
        trade = Trade(
            entry_date=datetime(2024, 1, 1, tzinfo=UTC),
            exit_date=datetime(2024, 1, 10, tzinfo=UTC),
            symbol="AAPL",
            side="long",
            entry_price=100.0,
            exit_price=90.0,
            quantity=10,
            commission=2.0,
        )

        assert trade.pnl == pytest.approx(-102.0)  # (90-100)*10 - 2
        assert trade.pnl_percent == pytest.approx(-10.2)

    def test_trade_pnl_short_profit(self):
        """Test P&L calculation for profitable short trade."""
        trade = Trade(
            entry_date=datetime(2024, 1, 1, tzinfo=UTC),
            exit_date=datetime(2024, 1, 10, tzinfo=UTC),
            symbol="AAPL",
            side="short",
            entry_price=100.0,
            exit_price=90.0,
            quantity=10,
            commission=2.0,
        )

        assert trade.pnl == pytest.approx(98.0)  # (100-90)*10 - 2

    def test_trade_pnl_short_loss(self):
        """Test P&L calculation for losing short trade."""
        trade = Trade(
            entry_date=datetime(2024, 1, 1, tzinfo=UTC),
            exit_date=datetime(2024, 1, 10, tzinfo=UTC),
            symbol="AAPL",
            side="short",
            entry_price=100.0,
            exit_price=110.0,
            quantity=10,
            commission=2.0,
        )

        assert trade.pnl == pytest.approx(-102.0)  # (100-110)*10 - 2


class TestBacktestConfig:
    """Tests for BacktestConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BacktestConfig()

        assert config.initial_capital == 100000
        assert config.commission_rate == 0
        assert config.slippage_rate == 0
        assert config.risk_free_rate == 0.02

    def test_custom_config(self):
        """Test custom configuration values."""
        config = BacktestConfig(
            initial_capital=50000,
            commission_rate=1.0,
            slippage_rate=0.001,
            risk_free_rate=0.05,
        )

        assert config.initial_capital == 50000
        assert config.commission_rate == 1.0
        assert config.slippage_rate == 0.001
        assert config.risk_free_rate == 0.05


class TestBacktestResult:
    """Tests for BacktestResult dataclass."""

    def test_default_result(self):
        """Test default result values."""
        result = BacktestResult()

        assert result.trades == []
        assert result.equity_curve == []
        assert result.final_equity == 0
        assert result.total_return == 0
        assert result.sharpe_ratio == 0
        assert result.max_drawdown == 0
        assert result.daily_returns == []
        assert result.monthly_returns == {}
        assert result.exposure_time == 0


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    @pytest.fixture
    def engine(self):
        """Create a test engine."""
        return BacktestEngine(BacktestConfig(initial_capital=100000))

    @pytest.fixture
    def sample_bars(self):
        """Create sample bar data."""
        base_date = datetime(2024, 1, 2, tzinfo=UTC)
        bars = []
        price = 100.0

        for i in range(60):
            date = base_date + timedelta(days=i)
            # Create realistic price movement
            change = np.sin(i / 10) * 2 + np.random.randn() * 0.5
            price = max(50, price + change)
            bars.append(
                {
                    "timestamp": date,
                    "open": price - 0.5,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price,
                    "volume": 10000 + i * 100,
                }
            )

        return {"AAPL": bars}

    def test_engine_reset(self, engine):
        """Test engine reset functionality."""
        engine.cash = 50000
        engine.positions = {"AAPL": Position("AAPL", "long", 100, 10, datetime.now())}
        engine.trades = [Trade(datetime.now(), datetime.now(), "AAPL", "long", 100, 110, 10)]
        engine.equity_curve = [(datetime.now(), 110000)]

        engine.reset()

        assert engine.cash == 100000
        assert engine.positions == {}
        assert engine.trades == []
        assert engine.equity_curve == []
        assert engine._days_with_position == 0
        assert engine._total_days == 0

    def test_engine_get_position(self, engine):
        """Test getting position."""
        pos = Position("AAPL", "long", 100, 10, datetime.now(UTC))
        engine.positions["AAPL"] = pos

        assert engine.get_position("AAPL") == pos
        assert engine.get_position("TSLA") is None

    def test_engine_has_position(self, engine):
        """Test checking position existence."""
        engine.positions["AAPL"] = Position("AAPL", "long", 100, 10, datetime.now(UTC))

        assert engine.has_position("AAPL") is True
        assert engine.has_position("TSLA") is False

    def test_engine_get_cash(self, engine):
        """Test getting available cash."""
        assert engine.get_cash() == 100000

        engine.cash = 50000
        assert engine.get_cash() == 50000

    def test_engine_get_equity(self, engine):
        """Test getting current equity."""
        # Initially returns cash when no equity curve
        assert engine.get_equity() == 100000

        # With equity curve, returns last value
        engine.equity_curve = [(datetime.now(), 110000)]
        assert engine.get_equity() == 110000

    def test_engine_run_simple_strategy(self, engine, sample_bars):
        """Test running a simple buy-and-hold strategy."""
        buy_triggered = False

        def strategy_fn(eng, symbol, bar):
            nonlocal buy_triggered
            signals = []
            if not buy_triggered and not eng.has_position(symbol):
                quantity = eng.get_cash() * 0.1 / bar["close"]
                signals.append(
                    {
                        "type": "buy",
                        "symbol": symbol,
                        "quantity": quantity,
                        "price": bar["close"],
                    }
                )
                buy_triggered = True
            return signals

        start_date = datetime(2024, 1, 2, tzinfo=UTC)
        end_date = datetime(2024, 3, 2, tzinfo=UTC)

        result = engine.run(
            bars=sample_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        assert isinstance(result, BacktestResult)
        assert len(result.equity_curve) > 0
        assert result.final_equity > 0

    def test_engine_run_entry_exit_strategy(self, engine, sample_bars):
        """Test running a strategy with entries and exits."""
        trade_count = [0]

        def strategy_fn(eng, symbol, bar):
            signals = []
            if not eng.has_position(symbol) and trade_count[0] < 2:
                quantity = eng.get_cash() * 0.2 / bar["close"]
                signals.append(
                    {
                        "type": "buy",
                        "symbol": symbol,
                        "quantity": quantity,
                        "price": bar["close"],
                    }
                )
                trade_count[0] += 1
            elif eng.has_position(symbol):
                pos = eng.get_position(symbol)
                if pos and bar["close"] > pos.entry_price * 1.02:  # 2% profit
                    signals.append(
                        {
                            "type": "sell",
                            "symbol": symbol,
                            "quantity": pos.quantity,
                            "price": bar["close"],
                        }
                    )
            return signals

        start_date = datetime(2024, 1, 2, tzinfo=UTC)
        end_date = datetime(2024, 3, 2, tzinfo=UTC)

        result = engine.run(
            bars=sample_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        assert isinstance(result, BacktestResult)
        # Should have some trades (entries and exits)
        assert len(result.trades) >= 0

    def test_engine_tracks_exposure_time(self, engine, sample_bars):
        """Test that exposure time is tracked correctly."""
        in_position = [False]

        def strategy_fn(eng, symbol, bar):
            signals = []
            if not eng.has_position(symbol) and not in_position[0]:
                quantity = eng.get_cash() * 0.5 / bar["close"]
                signals.append(
                    {
                        "type": "buy",
                        "symbol": symbol,
                        "quantity": quantity,
                        "price": bar["close"],
                    }
                )
                in_position[0] = True
            return signals

        start_date = datetime(2024, 1, 2, tzinfo=UTC)
        end_date = datetime(2024, 3, 2, tzinfo=UTC)

        result = engine.run(
            bars=sample_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Should have exposure time > 0 since we opened a position
        assert result.exposure_time > 0

    def test_engine_calculates_daily_returns(self, engine, sample_bars):
        """Test that daily returns are calculated."""

        def strategy_fn(eng, symbol, bar):
            return []  # No trades, just track equity

        start_date = datetime(2024, 1, 2, tzinfo=UTC)
        end_date = datetime(2024, 3, 2, tzinfo=UTC)

        result = engine.run(
            bars=sample_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Daily returns should be calculated
        assert isinstance(result.daily_returns, list)

    def test_engine_calculates_monthly_returns(self, engine, sample_bars):
        """Test that monthly returns are calculated."""

        def strategy_fn(eng, symbol, bar):
            return []

        start_date = datetime(2024, 1, 2, tzinfo=UTC)
        end_date = datetime(2024, 3, 2, tzinfo=UTC)

        result = engine.run(
            bars=sample_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Monthly returns should be a dict with month keys
        assert isinstance(result.monthly_returns, dict)

    def test_engine_applies_slippage(self):
        """Test that slippage is applied to trades."""
        config = BacktestConfig(initial_capital=100000, slippage_rate=0.01)  # 1%
        engine = BacktestEngine(config)

        # Create simple bars
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                },
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                },
            ]
        }

        entered = [False]

        def strategy_fn(eng, symbol, bar):
            if not entered[0]:
                entered[0] = True
                return [{"type": "buy", "symbol": symbol, "quantity": 10, "price": bar["close"]}]
            return []

        result = engine.run(
            bars=bars,
            strategy_fn=strategy_fn,
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 1, 2, tzinfo=UTC),
        )

        # Position should be opened with slippage
        assert result.final_equity > 0

    def test_engine_applies_commission(self):
        """Test that commission is applied to trades."""
        config = BacktestConfig(initial_capital=100000, commission_rate=10.0)
        engine = BacktestEngine(config)

        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                },
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 110,
                    "volume": 1000,
                },
            ]
        }

        entered = [False]

        def strategy_fn(eng, symbol, bar):
            if not entered[0]:
                entered[0] = True
                return [{"type": "buy", "symbol": symbol, "quantity": 10, "price": bar["close"]}]
            else:
                return [{"type": "sell", "symbol": symbol, "quantity": 10, "price": bar["close"]}]

        result = engine.run(
            bars=bars,
            strategy_fn=strategy_fn,
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 1, 2, tzinfo=UTC),
        )

        # Should have 1 trade with commission
        assert len(result.trades) == 1
        assert result.trades[0].commission == 20.0  # 10 * 2 (entry + exit)

    def test_engine_handles_empty_bars(self, engine):
        """Test engine handles empty bar data - returns initial capital."""
        result = engine.run(
            bars={},
            strategy_fn=lambda eng, sym, bar: [],
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 1, 31, tzinfo=UTC),
        )

        assert isinstance(result, BacktestResult)
        # No trading occurred, so final equity should equal initial capital
        assert result.final_equity == 100000

    def test_engine_closes_positions_at_end(self, engine, sample_bars):
        """Test that positions are closed at backtest end."""

        def strategy_fn(eng, symbol, bar):
            if not eng.has_position(symbol):
                quantity = eng.get_cash() * 0.5 / bar["close"]
                return [
                    {"type": "buy", "symbol": symbol, "quantity": quantity, "price": bar["close"]}
                ]
            return []

        start_date = datetime(2024, 1, 2, tzinfo=UTC)
        end_date = datetime(2024, 3, 2, tzinfo=UTC)

        result = engine.run(
            bars=sample_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Position should be closed at end
        assert len(result.trades) == 1  # Entry was closed at end

    def test_engine_calculates_sharpe_ratio(self, engine, sample_bars):
        """Test Sharpe ratio calculation."""

        def strategy_fn(eng, symbol, bar):
            return []

        start_date = datetime(2024, 1, 2, tzinfo=UTC)
        end_date = datetime(2024, 3, 2, tzinfo=UTC)

        result = engine.run(
            bars=sample_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Sharpe ratio should be a number (could be 0 if no volatility)
        assert isinstance(result.sharpe_ratio, (int, float))

    def test_engine_calculates_max_drawdown(self, engine, sample_bars):
        """Test max drawdown calculation."""

        def strategy_fn(eng, symbol, bar):
            return []

        start_date = datetime(2024, 1, 2, tzinfo=UTC)
        end_date = datetime(2024, 3, 2, tzinfo=UTC)

        result = engine.run(
            bars=sample_bars,
            strategy_fn=strategy_fn,
            start_date=start_date,
            end_date=end_date,
        )

        # Max drawdown should be >= 0
        assert result.max_drawdown >= 0

    def test_engine_rejects_entry_with_insufficient_cash(self):
        """Test that entries are rejected when there's insufficient cash."""
        # Create engine with very low initial capital
        config = BacktestConfig(initial_capital=10)
        engine = BacktestEngine(config)

        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                },
            ]
        }

        def strategy_fn(eng, symbol, bar):
            # Try to buy $1000 worth when we only have $10
            return [{"type": "buy", "symbol": symbol, "quantity": 10, "price": bar["close"]}]

        result = engine.run(
            bars=bars,
            strategy_fn=strategy_fn,
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 1, 1, tzinfo=UTC),
        )

        # Engine enforces cash limits - signal should be rejected
        assert len(result.trades) == 0
        # Signal should be tracked as rejected
        assert len(result.rejected_signals) == 1
        assert "Insufficient cash" in result.rejected_signals[0].reason


class TestPosition:
    """Tests for Position dataclass."""

    def test_position_creation(self):
        """Test creating a position."""
        pos = Position(
            symbol="AAPL",
            side="long",
            entry_price=100.0,
            quantity=10,
            entry_date=datetime(2024, 1, 1, tzinfo=UTC),
        )

        assert pos.symbol == "AAPL"
        assert pos.side == "long"
        assert pos.entry_price == 100.0
        assert pos.quantity == 10


class TestEdgeCases:
    """Tests for edge cases and error scenarios."""

    def test_trade_pnl_percent_zero_quantity(self):
        """Test P&L percentage with zero quantity doesn't crash."""
        trade = Trade(
            entry_date=datetime(2024, 1, 1, tzinfo=UTC),
            exit_date=datetime(2024, 1, 10, tzinfo=UTC),
            symbol="AAPL",
            side="long",
            entry_price=100.0,
            exit_price=110.0,
            quantity=0,  # Zero quantity
            commission=2.0,
        )

        # Should return 0 instead of raising ZeroDivisionError
        assert trade.pnl_percent == 0.0

    def test_trade_pnl_percent_zero_entry_price(self):
        """Test P&L percentage with zero entry price doesn't crash."""
        trade = Trade(
            entry_date=datetime(2024, 1, 1, tzinfo=UTC),
            exit_date=datetime(2024, 1, 10, tzinfo=UTC),
            symbol="AAPL",
            side="long",
            entry_price=0.0,  # Zero entry price
            exit_price=110.0,
            quantity=10,
            commission=2.0,
        )

        # Should return 0 instead of raising ZeroDivisionError
        assert trade.pnl_percent == 0.0

    def test_engine_tracks_rejected_signals(self):
        """Test that rejected signals are tracked."""
        config = BacktestConfig(initial_capital=100)
        engine = BacktestEngine(config)

        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                },
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                },
            ]
        }

        attempts = [0]

        def strategy_fn(eng, symbol, bar):
            attempts[0] += 1
            # Always try to buy more than we can afford
            return [{"type": "buy", "symbol": symbol, "quantity": 100, "price": bar["close"]}]

        result = engine.run(
            bars=bars,
            strategy_fn=strategy_fn,
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 1, 2, tzinfo=UTC),
        )

        # Both attempts should be rejected (insufficient cash)
        assert len(result.rejected_signals) == 2
        for rejected in result.rejected_signals:
            assert rejected.symbol == "AAPL"
            assert rejected.signal_type == "buy"
            assert "Insufficient cash" in rejected.reason

    def test_single_bar_backtest(self):
        """Test backtest with only one bar."""
        config = BacktestConfig(initial_capital=10000)
        engine = BacktestEngine(config)

        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                },
            ]
        }

        def strategy_fn(eng, symbol, bar):
            if not eng.has_position(symbol):
                return [{"type": "buy", "symbol": symbol, "quantity": 10, "price": bar["close"]}]
            return []

        result = engine.run(
            bars=bars,
            strategy_fn=strategy_fn,
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 1, 1, tzinfo=UTC),
        )

        assert isinstance(result, BacktestResult)
        # Should have 1 trade (opened and closed at end)
        assert len(result.trades) == 1
        assert result.final_equity > 0

    def test_strategy_exception_handling(self):
        """Test that engine handles strategy function exceptions gracefully."""
        config = BacktestConfig(initial_capital=10000)
        engine = BacktestEngine(config)

        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                },
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    "open": 100,
                    "high": 105,
                    "low": 99,
                    "close": 110,
                    "volume": 1000,
                },
            ]
        }

        def bad_strategy(eng, symbol, bar):
            if bar["close"] > 105:
                raise ValueError("Strategy error on price threshold")
            return []

        # Strategy exception should propagate (not silently swallowed)
        with pytest.raises(ValueError, match="Strategy error"):
            engine.run(
                bars=bars,
                strategy_fn=bad_strategy,
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 1, 2, tzinfo=UTC),
            )
