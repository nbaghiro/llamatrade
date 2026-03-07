"""Tests for llamatrade_compiler.state module."""

from datetime import UTC, datetime

import numpy as np
import pytest

from llamatrade_compiler.state import EvaluationState, Position
from llamatrade_compiler.types import Bar
from llamatrade_dsl import Indicator, Metric


@pytest.fixture
def sample_bar() -> Bar:
    """Create a sample bar for testing."""
    return Bar(
        timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        open=100.0,
        high=105.0,
        low=98.0,
        close=103.0,
        volume=1000000,
    )


@pytest.fixture
def prev_bar() -> Bar:
    """Create a previous bar for testing."""
    return Bar(
        timestamp=datetime(2024, 1, 15, 10, 29, tzinfo=UTC),
        open=99.0,
        high=102.0,
        low=97.0,
        close=100.0,
        volume=800000,
    )


@pytest.fixture
def bar_history() -> list[Bar]:
    """Create a list of historical bars."""
    base_time = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
    bars = []
    for i in range(10):
        bars.append(
            Bar(
                timestamp=base_time.replace(minute=20 + i),
                open=95.0 + i,
                high=97.0 + i,
                low=94.0 + i,
                close=96.0 + i,
                volume=500000 + i * 10000,
            )
        )
    return bars


@pytest.fixture
def sample_indicators() -> dict[str, float | np.ndarray]:
    """Create sample indicator data."""
    return {
        "sma_AAPL_close_20": np.array([98.0, 99.0, 100.0, 101.0, 102.0]),
        "rsi_AAPL_close_14": np.array([45.0, 48.0, 52.0, 55.0, 58.0]),
        "ema_AAPL_close_10": 101.5,  # Scalar value
    }


class TestPosition:
    """Tests for Position dataclass."""

    def test_position_creation(self) -> None:
        """Test creating a Position."""
        entry_time = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        position = Position(
            symbol="AAPL",
            side="long",
            quantity=100.0,
            entry_price=150.0,
            entry_time=entry_time,
        )

        assert position.symbol == "AAPL"
        assert position.side == "long"
        assert position.quantity == 100.0
        assert position.entry_price == 150.0
        assert position.entry_time == entry_time

    def test_position_short(self) -> None:
        """Test creating a short Position."""
        position = Position(
            symbol="AAPL",
            side="short",
            quantity=50.0,
            entry_price=155.0,
            entry_time=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )

        assert position.side == "short"
        assert position.quantity == 50.0

    def test_position_is_frozen(self) -> None:
        """Test that Position is immutable (frozen dataclass)."""
        position = Position(
            symbol="AAPL",
            side="long",
            quantity=100.0,
            entry_price=150.0,
            entry_time=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )

        with pytest.raises(AttributeError):
            position.quantity = 200.0  # type: ignore[misc]

    def test_position_equality(self) -> None:
        """Test Position equality comparison."""
        entry_time = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)
        pos1 = Position("AAPL", "long", 100.0, 150.0, entry_time)
        pos2 = Position("AAPL", "long", 100.0, 150.0, entry_time)
        pos3 = Position("AAPL", "short", 100.0, 150.0, entry_time)

        assert pos1 == pos2
        assert pos1 != pos3

    def test_position_hashable(self) -> None:
        """Test that Position is hashable (can be used in sets/dicts)."""
        position = Position(
            symbol="AAPL",
            side="long",
            quantity=100.0,
            entry_price=150.0,
            entry_time=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )

        # Should be hashable
        assert hash(position) is not None
        positions_set = {position}
        assert position in positions_set


class TestEvaluationStateGetPrice:
    """Tests for EvaluationState.get_price() method."""

    def test_get_price_close(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test getting close price."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        assert state.get_price("AAPL", "close") == 103.0

    def test_get_price_open(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test getting open price."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        assert state.get_price("AAPL", "open") == 100.0

    def test_get_price_high(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test getting high price."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        assert state.get_price("AAPL", "high") == 105.0

    def test_get_price_low(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test getting low price."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        assert state.get_price("AAPL", "low") == 98.0

    def test_get_price_volume(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test getting volume as float."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        value = state.get_price("AAPL", "volume")
        assert value == 1000000.0
        assert isinstance(value, float)

    def test_get_price_unknown_symbol_raises(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test that unknown symbol raises KeyError."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        with pytest.raises(KeyError, match="No price data"):
            state.get_price("GOOGL", "close")

    def test_get_price_unknown_field_raises(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test that unknown field raises KeyError."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        with pytest.raises(KeyError, match="Unknown price field"):
            state.get_price("AAPL", "invalid_field")


class TestEvaluationStateGetPrevPrice:
    """Tests for EvaluationState.get_prev_price() method."""

    def test_get_prev_price_close(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test getting previous close price."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        assert state.get_prev_price("AAPL", "close") == 100.0

    def test_get_prev_price_open(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test getting previous open price."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        assert state.get_prev_price("AAPL", "open") == 99.0

    def test_get_prev_price_volume(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test getting previous volume as float."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        value = state.get_prev_price("AAPL", "volume")
        assert value == 800000.0
        assert isinstance(value, float)


class TestEvaluationStateIndicators:
    """Tests for EvaluationState indicator methods."""

    def test_get_indicator_value_array(
        self, sample_bar: Bar, prev_bar: Bar, sample_indicators: dict
    ) -> None:
        """Test get_indicator_value with array returns last element."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=sample_indicators,
        )

        indicator = Indicator(name="sma", symbol="AAPL", params=(20,))
        value = state.get_indicator_value(indicator)

        assert value == 102.0  # Last element

    def test_get_indicator_value_scalar(
        self, sample_bar: Bar, prev_bar: Bar, sample_indicators: dict
    ) -> None:
        """Test get_indicator_value with scalar returns the value."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=sample_indicators,
        )

        indicator = Indicator(name="ema", symbol="AAPL", params=(10,))
        value = state.get_indicator_value(indicator)

        assert value == 101.5

    def test_get_prev_indicator_value(
        self, sample_bar: Bar, prev_bar: Bar, sample_indicators: dict
    ) -> None:
        """Test get_prev_indicator_value returns second to last."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=sample_indicators,
        )

        indicator = Indicator(name="sma", symbol="AAPL", params=(20,))
        value = state.get_prev_indicator_value(indicator)

        assert value == 101.0  # Second to last

    def test_get_indicator_array(
        self, sample_bar: Bar, prev_bar: Bar, sample_indicators: dict
    ) -> None:
        """Test get_indicator_array returns full array."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=sample_indicators,
        )

        arr = state.get_indicator_array("sma_AAPL_close_20")
        np.testing.assert_array_equal(arr, [98.0, 99.0, 100.0, 101.0, 102.0])

    def test_get_indicator_array_from_scalar(
        self, sample_bar: Bar, prev_bar: Bar, sample_indicators: dict
    ) -> None:
        """Test get_indicator_array wraps scalar in array."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators=sample_indicators,
        )

        arr = state.get_indicator_array("ema_AAPL_close_10")
        np.testing.assert_array_equal(arr, [101.5])

    def test_get_indicator_not_found_raises(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test get_indicator_value raises KeyError for unknown indicator."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            indicators={},
        )

        indicator = Indicator(name="sma", symbol="AAPL", params=(20,))
        with pytest.raises(KeyError, match="Indicator not computed"):
            state.get_indicator_value(indicator)


class TestEvaluationStateMetrics:
    """Tests for EvaluationState metric methods."""

    def test_get_metric_return(
        self, sample_bar: Bar, prev_bar: Bar, bar_history: list[Bar]
    ) -> None:
        """Test get_metric_value for return metric."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            bar_history={"AAPL": bar_history},
        )

        metric = Metric(name="return", symbol="AAPL", period=5)
        value = state.get_metric_value(metric)

        # Calculate expected return
        start_price = bar_history[-5].close
        end_price = bar_history[-1].close
        expected = (end_price - start_price) / start_price

        assert value == pytest.approx(expected)

    def test_get_metric_drawdown(
        self, sample_bar: Bar, prev_bar: Bar, bar_history: list[Bar]
    ) -> None:
        """Test get_metric_value for drawdown metric."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            bar_history={"AAPL": bar_history},
        )

        metric = Metric(name="drawdown", symbol="AAPL")
        value = state.get_metric_value(metric)

        # Calculate expected drawdown
        closes = [b.close for b in bar_history]
        peak = max(closes)
        current = closes[-1]
        expected = (peak - current) / peak

        assert value == pytest.approx(expected)

    def test_get_metric_volatility(
        self, sample_bar: Bar, prev_bar: Bar, bar_history: list[Bar]
    ) -> None:
        """Test get_metric_value for volatility metric."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            bar_history={"AAPL": bar_history},
        )

        metric = Metric(name="volatility", symbol="AAPL")
        value = state.get_metric_value(metric)

        assert value >= 0  # Volatility should be non-negative


class TestEvaluationStatePosition:
    """Tests for EvaluationState position methods."""

    def test_has_position_true(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test has_position returns True when position exists."""
        position = Position(
            symbol="AAPL",
            side="long",
            quantity=100.0,
            entry_price=150.0,
            entry_time=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            position=position,
        )

        assert state.has_position() is True

    def test_has_position_false(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test has_position returns False when no position."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            position=None,
        )

        assert state.has_position() is False

    def test_position_side_long(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test position_side returns 'long' for long position."""
        position = Position(
            symbol="AAPL",
            side="long",
            quantity=100.0,
            entry_price=150.0,
            entry_time=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )

        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            position=position,
        )

        assert state.position_side() == "long"

    def test_position_side_none(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test position_side returns None when no position."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
            position=None,
        )

        assert state.position_side() is None

    def test_position_pnl_pct_long_profit(self, prev_bar: Bar) -> None:
        """Test position_pnl_pct for profitable long position."""
        # Current bar with higher close than entry
        current_bar = Bar(
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            open=100.0,
            high=115.0,
            low=98.0,
            close=110.0,  # 10% above entry price of 100
            volume=1000000,
        )

        position = Position(
            symbol="AAPL",
            side="long",
            quantity=100.0,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )

        state = EvaluationState(
            current_bars={"AAPL": current_bar},
            prev_bars={"AAPL": prev_bar},
            position=position,
        )

        pnl = state.position_pnl_pct()
        assert pnl is not None
        assert pnl == pytest.approx(10.0)  # 10% profit

    def test_position_pnl_pct_short_profit(self, prev_bar: Bar) -> None:
        """Test position_pnl_pct for profitable short position."""
        current_bar = Bar(
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            open=100.0,
            high=105.0,
            low=88.0,
            close=90.0,  # 10% below entry price
            volume=1000000,
        )

        position = Position(
            symbol="AAPL",
            side="short",
            quantity=100.0,
            entry_price=100.0,
            entry_time=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
        )

        state = EvaluationState(
            current_bars={"AAPL": current_bar},
            prev_bars={"AAPL": prev_bar},
            position=position,
        )

        pnl = state.position_pnl_pct()
        assert pnl is not None
        assert pnl == pytest.approx(10.0)  # 10% profit for short


class TestEvaluationStateLegacyInterface:
    """Tests for legacy single-bar interface."""

    def test_current_bar_property(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test current_bar property returns first bar."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        assert state.current_bar is not None
        assert state.current_bar.close == 103.0

    def test_prev_bar_property(self, sample_bar: Bar, prev_bar: Bar) -> None:
        """Test prev_bar property returns first previous bar."""
        state = EvaluationState(
            current_bars={"AAPL": sample_bar},
            prev_bars={"AAPL": prev_bar},
        )

        assert state.prev_bar is not None
        assert state.prev_bar.close == 100.0

    def test_current_bar_empty_returns_none(self) -> None:
        """Test current_bar returns None when empty."""
        state = EvaluationState()
        assert state.current_bar is None

    def test_prev_bar_empty_returns_none(self) -> None:
        """Test prev_bar returns None when empty."""
        state = EvaluationState()
        assert state.prev_bar is None
