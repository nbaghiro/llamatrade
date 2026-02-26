"""Tests for compiler state module."""

from datetime import UTC, datetime

import numpy as np
import pytest
from llamatrade_compiler import Bar
from src.compiler.state import EvaluationState, Position

# ===================
# Fixtures
# ===================


@pytest.fixture
def bar():
    """Create a sample bar."""
    return Bar(
        timestamp=datetime.now(UTC),
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=10000,
    )


@pytest.fixture
def prev_bar():
    """Create a sample previous bar."""
    return Bar(
        timestamp=datetime.now(UTC),
        open=98.0,
        high=102.0,
        low=97.0,
        close=100.0,
        volume=8000,
    )


@pytest.fixture
def state(bar, prev_bar):
    """Create a basic evaluation state."""
    return EvaluationState(
        current_bar=bar,
        prev_bar=prev_bar,
        indicators={
            "sma_20": np.array([98.0, 99.0, 100.0, 101.0, 102.0]),
            "rsi_14": np.array([30.0, 35.0, 40.0, 45.0, 50.0]),
            "scalar_value": 75.0,
        },
        bar_history=[
            Bar(
                timestamp=datetime.now(UTC), open=95.0, high=98.0, low=94.0, close=97.0, volume=5000
            ),
            Bar(
                timestamp=datetime.now(UTC), open=96.0, high=99.0, low=95.0, close=98.0, volume=6000
            ),
            Bar(
                timestamp=datetime.now(UTC),
                open=97.0,
                high=100.0,
                low=96.0,
                close=99.0,
                volume=7000,
            ),
            prev_bar,
            bar,
        ],
    )


@pytest.fixture
def position():
    """Create a sample position."""
    return Position(
        symbol="AAPL",
        side="long",
        quantity=100.0,
        entry_price=100.0,
        entry_time=datetime.now(UTC),
    )


# ===================
# Position Tests
# ===================


class TestPosition:
    """Tests for Position dataclass."""

    def test_position_creation(self, position):
        """Test position creation."""
        assert position.symbol == "AAPL"
        assert position.side == "long"
        assert position.quantity == 100.0
        assert position.entry_price == 100.0
        assert position.entry_time is not None

    def test_position_immutable(self, position):
        """Test position is immutable (frozen)."""
        with pytest.raises(AttributeError):
            position.quantity = 200.0


# ===================
# EvaluationState get_value Tests
# ===================


class TestEvaluationStateGetValue:
    """Tests for EvaluationState.get_value()."""

    def test_get_close(self, state):
        """Test getting close price."""
        assert state.get_value("close") == 103.0

    def test_get_open(self, state):
        """Test getting open price."""
        assert state.get_value("open") == 100.0

    def test_get_high(self, state):
        """Test getting high price."""
        assert state.get_value("high") == 105.0

    def test_get_low(self, state):
        """Test getting low price."""
        assert state.get_value("low") == 99.0

    def test_get_volume(self, state):
        """Test getting volume."""
        assert state.get_value("volume") == 10000.0

    def test_get_timestamp(self, state):
        """Test getting timestamp as float."""
        value = state.get_value("timestamp")
        assert isinstance(value, float)
        assert value > 0

    def test_get_indicator_array(self, state):
        """Test getting indicator value from array (last value)."""
        assert state.get_value("sma_20") == 102.0

    def test_get_indicator_scalar(self, state):
        """Test getting scalar indicator value."""
        assert state.get_value("scalar_value") == 75.0

    def test_get_unknown_raises(self, state):
        """Test getting unknown value raises KeyError."""
        with pytest.raises(KeyError, match="Unknown value"):
            state.get_value("nonexistent")


# ===================
# EvaluationState get_prev_value Tests
# ===================


class TestEvaluationStateGetPrevValue:
    """Tests for EvaluationState.get_prev_value()."""

    def test_get_prev_close(self, state):
        """Test getting previous close price."""
        assert state.get_prev_value("close") == 100.0

    def test_get_prev_open(self, state):
        """Test getting previous open price."""
        assert state.get_prev_value("open") == 98.0

    def test_get_prev_high(self, state):
        """Test getting previous high price."""
        assert state.get_prev_value("high") == 102.0

    def test_get_prev_low(self, state):
        """Test getting previous low price."""
        assert state.get_prev_value("low") == 97.0

    def test_get_prev_volume(self, state):
        """Test getting previous volume."""
        assert state.get_prev_value("volume") == 8000.0

    def test_get_prev_indicator_array(self, state):
        """Test getting previous indicator value from array."""
        assert state.get_prev_value("sma_20") == 101.0  # Second to last

    def test_get_prev_indicator_scalar(self, state):
        """Test getting previous scalar indicator (returns same value)."""
        assert state.get_prev_value("scalar_value") == 75.0

    def test_get_prev_unknown_raises(self, state):
        """Test getting unknown previous value raises KeyError."""
        with pytest.raises(KeyError, match="Unknown value"):
            state.get_prev_value("nonexistent")


# ===================
# EvaluationState get_value_at_offset Tests
# ===================


class TestEvaluationStateGetValueAtOffset:
    """Tests for EvaluationState.get_value_at_offset()."""

    def test_offset_zero_returns_current(self, state):
        """Test offset 0 returns current value."""
        assert state.get_value_at_offset("close", 0) == 103.0

    def test_offset_price_field(self, state):
        """Test getting price at historical offset."""
        # offset 1 = prev_bar (close=100.0)
        assert state.get_value_at_offset("close", 1) == 100.0
        # offset 2 = third from end (close=99.0)
        assert state.get_value_at_offset("close", 2) == 99.0

    def test_offset_volume(self, state):
        """Test getting volume at historical offset."""
        assert state.get_value_at_offset("volume", 1) == 8000.0

    def test_offset_indicator_array(self, state):
        """Test getting indicator at historical offset."""
        # Array: [98.0, 99.0, 100.0, 101.0, 102.0]
        # offset 0 = 102.0, offset 1 = 101.0, offset 2 = 100.0
        assert state.get_value_at_offset("sma_20", 1) == 101.0
        assert state.get_value_at_offset("sma_20", 2) == 100.0

    def test_offset_indicator_scalar(self, state):
        """Test getting scalar indicator at offset (returns same value)."""
        assert state.get_value_at_offset("scalar_value", 1) == 75.0

    def test_offset_negative_raises(self, state):
        """Test negative offset raises ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            state.get_value_at_offset("close", -1)

    def test_offset_too_large_raises(self, state):
        """Test offset larger than history raises IndexError."""
        with pytest.raises(IndexError, match="Not enough history"):
            state.get_value_at_offset("close", 100)

    def test_offset_indicator_too_large_raises(self, state):
        """Test indicator offset larger than array raises IndexError."""
        with pytest.raises(IndexError, match="Not enough indicator history"):
            state.get_value_at_offset("sma_20", 100)

    def test_offset_unknown_raises(self, state):
        """Test unknown value raises KeyError."""
        with pytest.raises(KeyError, match="Unknown value"):
            state.get_value_at_offset("nonexistent", 1)


# ===================
# EvaluationState get_indicator Tests
# ===================


class TestEvaluationStateGetIndicator:
    """Tests for EvaluationState.get_indicator()."""

    def test_get_indicator_array(self, state):
        """Test getting indicator from array."""
        assert state.get_indicator("sma_20") == 102.0

    def test_get_indicator_scalar(self, state):
        """Test getting scalar indicator."""
        assert state.get_indicator("scalar_value") == 75.0

    def test_get_indicator_not_found(self, state):
        """Test getting non-existent indicator raises KeyError."""
        with pytest.raises(KeyError, match="Indicator not found"):
            state.get_indicator("nonexistent")


# ===================
# EvaluationState get_indicator_array Tests
# ===================


class TestEvaluationStateGetIndicatorArray:
    """Tests for EvaluationState.get_indicator_array()."""

    def test_get_indicator_array_returns_array(self, state):
        """Test getting indicator as array."""
        arr = state.get_indicator_array("sma_20")
        assert isinstance(arr, np.ndarray)
        assert len(arr) == 5

    def test_get_indicator_array_scalar_wraps(self, state):
        """Test scalar indicator is wrapped in array."""
        arr = state.get_indicator_array("scalar_value")
        assert isinstance(arr, np.ndarray)
        assert len(arr) == 1
        assert arr[0] == 75.0

    def test_get_indicator_array_not_found(self, state):
        """Test getting non-existent indicator raises KeyError."""
        with pytest.raises(KeyError, match="Indicator not found"):
            state.get_indicator_array("nonexistent")


# ===================
# EvaluationState Position Tests
# ===================


class TestEvaluationStatePosition:
    """Tests for EvaluationState position methods."""

    def test_has_position_false(self, state):
        """Test has_position when no position."""
        assert not state.has_position()

    def test_has_position_true(self, state, position):
        """Test has_position when position exists."""
        state.position = position
        assert state.has_position()

    def test_position_side_none(self, state):
        """Test position_side when no position."""
        assert state.position_side() is None

    def test_position_side_long(self, state, position):
        """Test position_side returns 'long'."""
        state.position = position
        assert state.position_side() == "long"

    def test_position_side_short(self, state):
        """Test position_side returns 'short'."""
        short_position = Position(
            symbol="AAPL",
            side="short",
            quantity=100.0,
            entry_price=100.0,
            entry_time=datetime.now(UTC),
        )
        state.position = short_position
        assert state.position_side() == "short"

    def test_position_pnl_pct_none(self, state):
        """Test position_pnl_pct when no position."""
        assert state.position_pnl_pct() is None

    def test_position_pnl_pct_long_profit(self, state, position):
        """Test position_pnl_pct for long position with profit."""
        # Entry at 100, current close at 103 = 3% profit
        state.position = position
        pnl = state.position_pnl_pct()
        assert pnl == pytest.approx(3.0)

    def test_position_pnl_pct_long_loss(self, state):
        """Test position_pnl_pct for long position with loss."""
        # Entry at 110, current close at 103 = loss
        position = Position(
            symbol="AAPL",
            side="long",
            quantity=100.0,
            entry_price=110.0,
            entry_time=datetime.now(UTC),
        )
        state.position = position
        pnl = state.position_pnl_pct()
        assert pnl == pytest.approx(-6.363636, rel=0.001)

    def test_position_pnl_pct_short_profit(self, state):
        """Test position_pnl_pct for short position with profit."""
        # Entry at 110, current close at 103 = 6.36% profit for short
        position = Position(
            symbol="AAPL",
            side="short",
            quantity=100.0,
            entry_price=110.0,
            entry_time=datetime.now(UTC),
        )
        state.position = position
        pnl = state.position_pnl_pct()
        assert pnl == pytest.approx(6.363636, rel=0.001)

    def test_position_pnl_pct_short_loss(self, state):
        """Test position_pnl_pct for short position with loss."""
        # Entry at 100, current close at 103 = -3% for short
        position = Position(
            symbol="AAPL",
            side="short",
            quantity=100.0,
            entry_price=100.0,
            entry_time=datetime.now(UTC),
        )
        state.position = position
        pnl = state.position_pnl_pct()
        assert pnl == pytest.approx(-3.0)


# ===================
# EvaluationState Edge Cases
# ===================


class TestEvaluationStateEdgeCases:
    """Edge case tests for EvaluationState."""

    def test_indicator_single_element_array(self, bar, prev_bar):
        """Test indicator with single element array."""
        state = EvaluationState(
            current_bar=bar,
            prev_bar=prev_bar,
            indicators={"single": np.array([42.0])},
        )
        assert state.get_value("single") == 42.0
        # get_prev_value should return the same value for single element
        assert state.get_prev_value("single") == 42.0

    def test_empty_bar_history(self, bar, prev_bar):
        """Test state with empty bar history."""
        state = EvaluationState(
            current_bar=bar,
            prev_bar=prev_bar,
            indicators={},
            bar_history=[],
        )
        assert state.get_value("close") == 103.0
        # Offset should raise for empty history
        with pytest.raises(IndexError):
            state.get_value_at_offset("close", 1)

    def test_no_indicators(self, bar, prev_bar):
        """Test state with no indicators."""
        state = EvaluationState(
            current_bar=bar,
            prev_bar=prev_bar,
            indicators={},
        )
        assert state.get_value("close") == 103.0
        with pytest.raises(KeyError):
            state.get_value("sma_20")
