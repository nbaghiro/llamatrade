"""Tests for base strategy class."""

from datetime import UTC, datetime

import numpy as np
import pytest

from llamatrade_compiler import Bar, Signal, SignalType

from src.strategies.base import BaseStrategy

# ===================
# Test Strategy Implementation
# ===================


class TestStrategy(BaseStrategy):
    """Concrete test implementation of BaseStrategy."""

    name = "Test Strategy"
    description = "A strategy for testing"

    def on_bar(self, symbol: str, bar: Bar) -> list[Signal]:
        """Simple test implementation that generates buy signal above MA."""
        self.add_bar(symbol, bar)
        prices = self.get_prices(symbol)

        if len(prices) < 5:
            return []

        ma = np.mean(prices[-5:])
        if bar.close > ma and not self.has_position(symbol):
            return [
                Signal(
                    type=SignalType.BUY,
                    symbol=symbol,
                    price=bar.close,
                    timestamp=bar.timestamp,
                    stop_loss=self.calculate_stop_loss(bar.close),
                    take_profit=self.calculate_take_profit(bar.close),
                )
            ]

        return []


# ===================
# Fixtures
# ===================


@pytest.fixture
def strategy() -> TestStrategy:
    """Create a test strategy with default config."""
    return TestStrategy(
        config={
            "symbols": ["AAPL", "GOOGL"],
            "timeframe": "1D",
            "risk": {
                "stop_loss_percent": 5.0,
                "take_profit_percent": 10.0,
            },
        }
    )


@pytest.fixture
def bar() -> Bar:
    """Create a sample bar."""
    return Bar(
        timestamp=datetime.now(UTC),
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=10000,
    )


# ===================
# Bar Tests
# ===================


class TestBar:
    """Tests for Bar dataclass."""

    def test_bar_creation(self, bar: Bar) -> None:
        """Test bar creation with all fields."""
        assert bar.open == 100.0
        assert bar.high == 105.0
        assert bar.low == 99.0
        assert bar.close == 103.0
        assert bar.volume == 10000
        assert bar.timestamp is not None

    def test_bar_to_dict(self, bar: Bar) -> None:
        """Test bar to_dict method."""
        d = bar.to_dict()

        assert d["open"] == 100.0
        assert d["high"] == 105.0
        assert d["low"] == 99.0
        assert d["close"] == 103.0
        assert d["volume"] == 10000
        assert "timestamp" in d


# ===================
# Signal Tests
# ===================


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation(self) -> None:
        """Test signal creation with required fields."""
        signal = Signal(
            type=SignalType.BUY,
            symbol="AAPL",
            price=150.0,
            timestamp=datetime.now(UTC),
        )

        assert signal.type == SignalType.BUY
        assert signal.symbol == "AAPL"
        assert signal.price == 150.0
        assert signal.confidence == 1.0  # Default
        assert signal.quantity_percent == 100.0  # Default
        assert signal.stop_loss is None  # Default
        assert signal.take_profit is None  # Default

    def test_signal_with_optional_fields(self) -> None:
        """Test signal creation with optional fields."""
        signal = Signal(
            type=SignalType.SELL,
            symbol="GOOGL",
            price=2800.0,
            timestamp=datetime.now(UTC),
            confidence=0.8,
            quantity_percent=50.0,
            stop_loss=2850.0,
            take_profit=2700.0,
            metadata={"reason": "RSI oversold"},
        )

        assert signal.confidence == 0.8
        assert signal.quantity_percent == 50.0
        assert signal.stop_loss == 2850.0
        assert signal.take_profit == 2700.0
        assert signal.metadata is not None
        assert signal.metadata.get("reason") == "RSI oversold"


class TestSignalType:
    """Tests for SignalType enum."""

    def test_signal_types_exist(self) -> None:
        """Test all signal types exist."""
        assert SignalType.BUY.value == "buy"
        assert SignalType.SELL.value == "sell"
        assert SignalType.CLOSE_LONG.value == "close_long"
        assert SignalType.CLOSE_SHORT.value == "close_short"
        assert SignalType.HOLD.value == "hold"


# ===================
# BaseStrategy Tests
# ===================


class TestBaseStrategy:
    """Tests for BaseStrategy class."""

    def test_strategy_initialization(self, strategy: TestStrategy) -> None:
        """Test strategy initialization with config."""
        assert strategy.symbols == ["AAPL", "GOOGL"]
        assert strategy.timeframe == "1D"
        assert strategy.risk_config["stop_loss_percent"] == 5.0
        assert strategy.risk_config["take_profit_percent"] == 10.0

    def test_strategy_default_initialization(self) -> None:
        """Test strategy initialization without config."""
        strategy = TestStrategy()

        assert strategy.symbols == []
        assert strategy.timeframe == "1D"
        assert strategy.risk_config == {}
        assert strategy.indicators == {}
        assert strategy.positions == {}
        assert strategy.bars == {}

    def test_strategy_name_and_description(self, strategy: TestStrategy) -> None:
        """Test strategy has name and description."""
        assert strategy.name == "Test Strategy"
        assert strategy.description == "A strategy for testing"

    def test_validate_config_valid(self, strategy: TestStrategy) -> None:
        """Test config validation with valid config."""
        errors = strategy.validate_config()
        assert errors == []

    def test_validate_config_missing_symbols(self) -> None:
        """Test config validation without symbols."""
        strategy = TestStrategy(config={"timeframe": "1D"})
        errors = strategy.validate_config()

        assert "At least one symbol is required" in errors

    def test_validate_config_invalid_timeframe(self) -> None:
        """Test config validation with invalid timeframe."""
        strategy = TestStrategy(
            config={
                "symbols": ["AAPL"],
                "timeframe": "invalid",
            }
        )
        errors = strategy.validate_config()

        assert any("Invalid timeframe" in e for e in errors)

    def test_add_bar(self, strategy: TestStrategy, bar: Bar) -> None:
        """Test adding bars to strategy."""
        strategy.add_bar("AAPL", bar)

        assert "AAPL" in strategy.bars
        assert len(strategy.bars["AAPL"]) == 1
        assert strategy.bars["AAPL"][0] == bar

    def test_add_multiple_bars(self, strategy: TestStrategy) -> None:
        """Test adding multiple bars."""
        for i in range(5):
            bar = Bar(
                timestamp=datetime.now(UTC),
                open=100.0 + i,
                high=105.0 + i,
                low=99.0 + i,
                close=103.0 + i,
                volume=10000,
            )
            strategy.add_bar("AAPL", bar)

        assert len(strategy.bars["AAPL"]) == 5

    def test_get_prices(self, strategy: TestStrategy) -> None:
        """Test getting prices from bars."""
        for i in range(5):
            bar = Bar(
                timestamp=datetime.now(UTC),
                open=100.0,
                high=105.0,
                low=99.0,
                close=100.0 + i,
                volume=10000,
            )
            strategy.add_bar("AAPL", bar)

        prices = strategy.get_prices("AAPL")

        assert len(prices) == 5
        assert prices[0] == 100.0
        assert prices[4] == 104.0

    def test_get_prices_different_fields(self, strategy: TestStrategy, bar: Bar) -> None:
        """Test getting different price fields."""
        strategy.add_bar("AAPL", bar)

        assert strategy.get_prices("AAPL", "open")[0] == 100.0
        assert strategy.get_prices("AAPL", "high")[0] == 105.0
        assert strategy.get_prices("AAPL", "low")[0] == 99.0
        assert strategy.get_prices("AAPL", "close")[0] == 103.0

    def test_get_prices_empty_symbol(self, strategy: TestStrategy) -> None:
        """Test getting prices for unknown symbol."""
        prices = strategy.get_prices("UNKNOWN")

        assert len(prices) == 0
        assert isinstance(prices, np.ndarray)

    def test_get_volumes(self, strategy: TestStrategy, bar: Bar) -> None:
        """Test getting volumes from bars."""
        strategy.add_bar("AAPL", bar)
        volumes = strategy.get_volumes("AAPL")

        assert len(volumes) == 1
        assert volumes[0] == 10000

    def test_get_volumes_empty_symbol(self, strategy: TestStrategy) -> None:
        """Test getting volumes for unknown symbol."""
        volumes = strategy.get_volumes("UNKNOWN")

        assert len(volumes) == 0
        assert isinstance(volumes, np.ndarray)

    def test_calculate_stop_loss(self, strategy: TestStrategy) -> None:
        """Test stop loss calculation."""
        stop_loss = strategy.calculate_stop_loss(100.0)

        assert stop_loss == 95.0  # 100 * (1 - 5/100)

    def test_calculate_stop_loss_not_configured(self) -> None:
        """Test stop loss when not configured."""
        strategy = TestStrategy()
        stop_loss = strategy.calculate_stop_loss(100.0)

        assert stop_loss is None

    def test_calculate_take_profit(self, strategy: TestStrategy) -> None:
        """Test take profit calculation."""
        take_profit = strategy.calculate_take_profit(100.0)

        assert take_profit is not None
        assert abs(take_profit - 110.0) < 0.01  # 100 * (1 + 10/100)

    def test_calculate_take_profit_not_configured(self) -> None:
        """Test take profit when not configured."""
        strategy = TestStrategy()
        take_profit = strategy.calculate_take_profit(100.0)

        assert take_profit is None

    def test_position_tracking(self, strategy: TestStrategy) -> None:
        """Test position tracking."""
        assert strategy.get_position("AAPL") == 0
        assert not strategy.has_position("AAPL")

        strategy.on_order_filled("AAPL", "buy", 100, 150.0)

        assert strategy.get_position("AAPL") == 100
        assert strategy.has_position("AAPL")

        strategy.on_order_filled("AAPL", "sell", 50, 155.0)

        assert strategy.get_position("AAPL") == 50
        assert strategy.has_position("AAPL")

        strategy.on_order_filled("AAPL", "sell", 50, 160.0)

        assert strategy.get_position("AAPL") == 0
        assert not strategy.has_position("AAPL")

    def test_on_bar_generates_signals(self, strategy: TestStrategy) -> None:
        """Test on_bar method generates signals."""
        # Add enough bars to trigger signal
        signals: list[Signal] = []
        for i in range(10):
            bar = Bar(
                timestamp=datetime.now(UTC),
                open=100.0,
                high=105.0,
                low=99.0,
                close=100.0 + i,  # Rising prices
                volume=10000,
            )
            signals = strategy.on_bar("AAPL", bar)

        # Last bar should trigger buy signal (close > MA)
        assert len(signals) == 1
        assert signals[0].type == SignalType.BUY
        assert signals[0].symbol == "AAPL"
        assert signals[0].stop_loss is not None
        assert signals[0].take_profit is not None

    def test_on_bar_no_signal_when_has_position(self, strategy: TestStrategy) -> None:
        """Test on_bar doesn't generate signal when already has position."""
        # Add bars
        for i in range(10):
            bar = Bar(
                timestamp=datetime.now(UTC),
                open=100.0,
                high=105.0,
                low=99.0,
                close=100.0 + i,
                volume=10000,
            )
            strategy.on_bar("AAPL", bar)

        # Simulate position
        strategy.on_order_filled("AAPL", "buy", 100, 105.0)

        # Next bar should not generate signal
        bar = Bar(
            timestamp=datetime.now(UTC),
            open=110.0,
            high=115.0,
            low=109.0,
            close=112.0,
            volume=10000,
        )
        signals = strategy.on_bar("AAPL", bar)

        assert len(signals) == 0


class TestAbstractMethodEnforcement:
    """Tests for abstract method enforcement."""

    def test_cannot_instantiate_base_strategy(self) -> None:
        """Test that BaseStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseStrategy()
