"""Tests for llamatrade_compiler.types module."""

from datetime import UTC, datetime

import pytest

from llamatrade_compiler.types import Bar, Signal, SignalMetadata, SignalType


class TestSignalType:
    """Tests for SignalType enum."""

    def test_signal_type_buy_value(self) -> None:
        """Test BUY signal type has correct value."""
        assert SignalType.BUY == "buy"
        assert SignalType.BUY.value == "buy"

    def test_signal_type_sell_value(self) -> None:
        """Test SELL signal type has correct value."""
        assert SignalType.SELL == "sell"
        assert SignalType.SELL.value == "sell"

    def test_signal_type_close_long_value(self) -> None:
        """Test CLOSE_LONG signal type has correct value."""
        assert SignalType.CLOSE_LONG == "close_long"
        assert SignalType.CLOSE_LONG.value == "close_long"

    def test_signal_type_close_short_value(self) -> None:
        """Test CLOSE_SHORT signal type has correct value."""
        assert SignalType.CLOSE_SHORT == "close_short"
        assert SignalType.CLOSE_SHORT.value == "close_short"

    def test_signal_type_hold_value(self) -> None:
        """Test HOLD signal type has correct value."""
        assert SignalType.HOLD == "hold"
        assert SignalType.HOLD.value == "hold"

    def test_signal_type_is_string_enum(self) -> None:
        """Test that SignalType values can be used as strings."""
        signal_type = SignalType.BUY
        assert f"Signal: {signal_type}" == "Signal: buy"
        assert str(signal_type) == "buy"


class TestBar:
    """Tests for Bar dataclass."""

    def test_bar_creation_with_valid_data(self) -> None:
        """Test creating a Bar with valid OHLCV data."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        bar = Bar(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        assert bar.timestamp == timestamp
        assert bar.open == 100.0
        assert bar.high == 105.0
        assert bar.low == 98.0
        assert bar.close == 103.0
        assert bar.volume == 1000000

    def test_bar_to_dict(self) -> None:
        """Test Bar.to_dict() method."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        bar = Bar(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        d = bar.to_dict()

        assert d["timestamp"] == timestamp
        assert d["open"] == 100.0
        assert d["high"] == 105.0
        assert d["low"] == 98.0
        assert d["close"] == 103.0
        assert d["volume"] == 1000000

    def test_bar_to_dict_round_trip(self) -> None:
        """Test that to_dict() output can recreate equivalent Bar."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        original = Bar(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        d = original.to_dict()
        recreated = Bar(**d)

        assert recreated == original

    def test_bar_with_zero_volume(self) -> None:
        """Test Bar with zero volume (valid but unusual)."""
        bar = Bar(
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=0,
        )

        assert bar.volume == 0
        d = bar.to_dict()
        assert d["volume"] == 0

    def test_bar_with_float_prices(self) -> None:
        """Test Bar with precise float prices."""
        bar = Bar(
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            open=123.456789,
            high=124.987654,
            low=122.111111,
            close=123.999999,
            volume=100,
        )

        assert bar.open == pytest.approx(123.456789)
        assert bar.high == pytest.approx(124.987654)
        assert bar.low == pytest.approx(122.111111)
        assert bar.close == pytest.approx(123.999999)

    def test_bar_with_negative_prices(self) -> None:
        """Test Bar allows negative prices (no validation at type level)."""
        # This tests that the dataclass doesn't validate - validation happens elsewhere
        bar = Bar(
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            open=-10.0,
            high=-5.0,
            low=-15.0,
            close=-8.0,
            volume=100,
        )

        assert bar.open == -10.0


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation_minimal(self) -> None:
        """Test creating a Signal with only required fields."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        signal = Signal(
            type=SignalType.BUY,
            symbol="AAPL",
            price=150.0,
            timestamp=timestamp,
        )

        assert signal.type == SignalType.BUY
        assert signal.symbol == "AAPL"
        assert signal.price == 150.0
        assert signal.timestamp == timestamp
        # Check defaults
        assert signal.confidence == 1.0
        assert signal.quantity_percent == 100.0
        assert signal.stop_loss is None
        assert signal.take_profit is None
        assert signal.metadata is None

    def test_signal_with_all_fields(self) -> None:
        """Test creating a Signal with all fields specified."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        metadata: SignalMetadata = {
            "indicator_values": {"rsi": 65.5, "sma_20": 148.0},
            "reason": "RSI crossover",
            "strategy_name": "RSI Strategy",
        }

        signal = Signal(
            type=SignalType.BUY,
            symbol="AAPL",
            price=150.0,
            timestamp=timestamp,
            confidence=0.85,
            quantity_percent=50.0,
            stop_loss=145.0,
            take_profit=160.0,
            metadata=metadata,
        )

        assert signal.confidence == 0.85
        assert signal.quantity_percent == 50.0
        assert signal.stop_loss == 145.0
        assert signal.take_profit == 160.0
        assert signal.metadata == metadata
        assert signal.metadata["strategy_name"] == "RSI Strategy"

    def test_signal_with_metadata_indicator_values(self) -> None:
        """Test Signal metadata with indicator values."""
        metadata: SignalMetadata = {
            "indicator_values": {"rsi": 30.5, "macd_line": 0.5, "macd_signal": 0.3},
        }

        signal = Signal(
            type=SignalType.BUY,
            symbol="AAPL",
            price=150.0,
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            metadata=metadata,
        )

        assert signal.metadata is not None
        assert signal.metadata["indicator_values"]["rsi"] == 30.5
        assert signal.metadata["indicator_values"]["macd_line"] == 0.5

    def test_signal_exit_with_pnl_metadata(self) -> None:
        """Test exit Signal with P&L in metadata."""
        metadata: SignalMetadata = {
            "exit_reason": "stop_loss",
            "pnl_pct": -2.5,
            "strategy_name": "Test Strategy",
        }

        signal = Signal(
            type=SignalType.CLOSE_LONG,
            symbol="AAPL",
            price=147.0,
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            quantity_percent=100.0,
            metadata=metadata,
        )

        assert signal.type == SignalType.CLOSE_LONG
        assert signal.metadata is not None
        assert signal.metadata["exit_reason"] == "stop_loss"
        assert signal.metadata["pnl_pct"] == -2.5

    def test_signal_different_types(self) -> None:
        """Test creating signals of each type."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)

        for signal_type in SignalType:
            signal = Signal(
                type=signal_type,
                symbol="AAPL",
                price=150.0,
                timestamp=timestamp,
            )
            assert signal.type == signal_type


class TestSignalMetadata:
    """Tests for SignalMetadata TypedDict."""

    def test_signal_metadata_with_all_fields(self) -> None:
        """Test SignalMetadata with all optional fields."""
        metadata: SignalMetadata = {
            "indicator_values": {"rsi": 45.0},
            "reason": "Entry condition met",
            "strategy_version": 2,
            "strategy_name": "RSI Strategy",
            "strategy_type": "momentum",
            "exit_reason": "take_profit",
            "pnl_pct": 5.5,
        }

        assert metadata["indicator_values"] == {"rsi": 45.0}
        assert metadata["reason"] == "Entry condition met"
        assert metadata["strategy_version"] == 2
        assert metadata["strategy_name"] == "RSI Strategy"
        assert metadata["strategy_type"] == "momentum"
        assert metadata["exit_reason"] == "take_profit"
        assert metadata["pnl_pct"] == 5.5

    def test_signal_metadata_partial(self) -> None:
        """Test SignalMetadata with partial fields (all are optional)."""
        metadata: SignalMetadata = {
            "strategy_name": "Test",
        }

        assert metadata["strategy_name"] == "Test"
        assert "indicator_values" not in metadata
