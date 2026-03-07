"""Tests for compiler_adapter module - allocation-based strategy adapter."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.compiler_adapter import (
    StrategyAdapter,
    load_strategy_adapter,
)
from src.runner.bar_stream import BarData
from src.runner.runner import Position


@pytest.fixture
def sample_bar_data() -> BarData:
    """Create sample bar data for testing."""
    return BarData(
        symbol="SPY",
        timestamp=datetime(2024, 1, 15, 9, 30, 0, tzinfo=UTC),
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume=10000,
    )


@pytest.fixture
def sample_bars(sample_bar_data: BarData) -> list[BarData]:
    """Create a list of sample bars."""
    return [
        BarData(
            symbol="SPY",
            timestamp=datetime(2024, 1, 15, 9, 29, 0, tzinfo=UTC),
            open=149.0,
            high=150.0,
            low=148.0,
            close=149.5,
            volume=8000,
        ),
        sample_bar_data,
    ]


@pytest.fixture
def sample_position() -> Position:
    """Create a sample position."""
    return Position(
        symbol="SPY",
        side="long",
        quantity=100.0,
        entry_price=149.0,
        entry_date=datetime(2024, 1, 15, 9, 25, 0, tzinfo=UTC),
    )


@pytest.fixture
def mock_compiled_strategy() -> MagicMock:
    """Create a mock compiled strategy for allocation-based testing."""
    mock = MagicMock()
    mock.name = "Test Strategy"
    mock.min_bars = 5
    mock.indicators = []
    mock.rebalance_frequency = "daily"
    mock.compute_allocation.return_value = {"weights": {}}
    mock.reset = MagicMock()
    mock.add_bars = MagicMock()
    return mock


@pytest.fixture
def mock_ast() -> MagicMock:
    """Create a mock AST."""
    mock = MagicMock()
    mock.rebalance = "daily"
    return mock


@pytest.fixture
def mock_validation() -> MagicMock:
    """Create a mock validation result."""
    mock = MagicMock()
    mock.valid = True
    mock.errors = []
    return mock


class TestStrategyAdapterInit:
    """Tests for StrategyAdapter initialization."""

    def test_init_parses_validates_and_compiles(
        self, mock_ast: MagicMock, mock_compiled_strategy: MagicMock, mock_validation: MagicMock
    ) -> None:
        """Test that init parses, validates, and compiles the strategy."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast) as mock_parse,
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY", "TLT"}),
        ):
            adapter = StrategyAdapter('(strategy "test" :rebalance daily)')

            mock_parse.assert_called_once()
            assert adapter._ast is mock_ast
            assert adapter._template is mock_compiled_strategy
            assert len(adapter._per_symbol) == 0
            assert len(adapter._initialized_symbols) == 0

    def test_init_raises_on_parse_error(self) -> None:
        """Test that init raises ValueError on parse error."""
        with patch("src.compiler_adapter.parse_strategy", side_effect=Exception("Parse failed")):
            with pytest.raises(ValueError, match="Failed to parse strategy"):
                StrategyAdapter("(invalid)")

    def test_init_raises_on_validation_error(self, mock_ast: MagicMock) -> None:
        """Test that init raises ValueError on validation error."""
        mock_validation = MagicMock()
        mock_validation.valid = False
        mock_validation.errors = ["Missing body"]

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
        ):
            with pytest.raises(ValueError, match="Invalid strategy"):
                StrategyAdapter('(strategy "test")')

    def test_init_raises_on_compile_error(
        self, mock_ast: MagicMock, mock_validation: MagicMock
    ) -> None:
        """Test that init raises ValueError on compile error."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", side_effect=Exception("Compile failed")),
        ):
            with pytest.raises(ValueError, match="Failed to compile strategy"):
                StrategyAdapter('(strategy "test")')


class TestStrategyAdapterCall:
    """Tests for StrategyAdapter.__call__ method with allocation-based behavior."""

    def test_call_returns_none_for_empty_bars(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test that calling with empty bars returns None."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            result = adapter(symbol="SPY", bars=[], position=None, equity=100000.0)
            assert result is None

    def test_call_creates_per_symbol_compiled_strategy(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
        sample_bars: list[BarData],
    ) -> None:
        """Test that calling creates a per-symbol compiled strategy."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            adapter(symbol="SPY", bars=sample_bars, position=None, equity=100000.0)
            assert "SPY" in adapter._per_symbol

    def test_call_initializes_with_historical_bars(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
        sample_bars: list[BarData],
    ) -> None:
        """Test that first call adds historical bars."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            adapter(symbol="SPY", bars=sample_bars, position=None, equity=100000.0)

            # Should have initialized and marked symbol as initialized
            assert "SPY" in adapter._initialized_symbols
            # add_bars should be called for historical bars
            assert mock_compiled_strategy.add_bars.call_count >= 1

    def test_call_does_not_reinitialize(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
        sample_bars: list[BarData],
    ) -> None:
        """Test that subsequent calls don't reinitialize."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')

            # First call
            adapter(symbol="SPY", bars=sample_bars, position=None, equity=100000.0)

            # Second call should not reinitialize
            adapter(symbol="SPY", bars=sample_bars, position=None, equity=100000.0)

            # add_bars for historical should not be called again
            assert "SPY" in adapter._initialized_symbols

    def test_call_returns_none_when_no_weight(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
        sample_bars: list[BarData],
    ) -> None:
        """Test that no allocation returns None."""
        mock_compiled_strategy.compute_allocation.return_value = {"weights": {}}

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            result = adapter(symbol="SPY", bars=sample_bars, position=None, equity=100000.0)
            assert result is None

    def test_call_returns_buy_signal_on_positive_weight(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
        sample_bars: list[BarData],
    ) -> None:
        """Test that positive weight with no position generates buy signal."""
        mock_compiled_strategy.compute_allocation.return_value = {"weights": {"SPY": 100.0}}

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            result = adapter(symbol="SPY", bars=sample_bars, position=None, equity=100000.0)

            assert result is not None
            assert result.type == "buy"
            assert result.symbol == "SPY"
            assert result.quantity > 0
            assert result.price == 150.5  # close price

    def test_call_returns_sell_signal_on_zero_weight_with_position(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
        sample_bars: list[BarData],
        sample_position: Position,
    ) -> None:
        """Test that zero weight with position generates sell signal."""
        mock_compiled_strategy.compute_allocation.return_value = {"weights": {"SPY": 0.0}}

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            result = adapter(
                symbol="SPY", bars=sample_bars, position=sample_position, equity=100000.0
            )

            assert result is not None
            assert result.type == "sell"
            assert result.symbol == "SPY"
            assert result.quantity == sample_position.quantity

    def test_call_returns_none_when_already_in_position(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
        sample_bars: list[BarData],
        sample_position: Position,
    ) -> None:
        """Test that positive weight with existing position returns None."""
        mock_compiled_strategy.compute_allocation.return_value = {"weights": {"SPY": 100.0}}

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            result = adapter(
                symbol="SPY", bars=sample_bars, position=sample_position, equity=100000.0
            )

            # Should not generate duplicate buy when already in position
            assert result is None

    def test_call_handles_zero_price(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test handling of zero price edge case."""
        mock_compiled_strategy.compute_allocation.return_value = {"weights": {"SPY": 100.0}}

        zero_price_bar = BarData(
            symbol="SPY",
            timestamp=datetime(2024, 1, 15, 9, 30, 0, tzinfo=UTC),
            open=0.0,
            high=0.0,
            low=0.0,
            close=0.0,
            volume=0,
        )

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            result = adapter(symbol="SPY", bars=[zero_price_bar], position=None, equity=100000.0)

            # Should not generate signal with zero quantity
            assert result is None

    def test_call_handles_allocation_error(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
        sample_bars: list[BarData],
    ) -> None:
        """Test that allocation errors are caught and return None."""
        mock_compiled_strategy.compute_allocation.side_effect = Exception("Evaluation failed")

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            result = adapter(symbol="SPY", bars=sample_bars, position=None, equity=100000.0)
            assert result is None


class TestStrategyAdapterMultiSymbol:
    """Tests for multi-symbol support."""

    def test_call_creates_separate_instances_per_symbol(
        self, mock_ast: MagicMock, mock_validation: MagicMock, sample_bars: list[BarData]
    ) -> None:
        """Test that each symbol gets its own compiled strategy instance."""
        mock_template = MagicMock()
        mock_template.name = "Test Strategy"
        mock_template.min_bars = 5
        mock_template.indicators = []
        mock_template.rebalance_frequency = "daily"

        mock_compiled_1 = MagicMock()
        mock_compiled_1.compute_allocation.return_value = {"weights": {}}
        mock_compiled_1.add_bars = MagicMock()

        mock_compiled_2 = MagicMock()
        mock_compiled_2.compute_allocation.return_value = {"weights": {}}
        mock_compiled_2.add_bars = MagicMock()

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch(
                "src.compiler_adapter.compile_strategy",
                side_effect=[mock_template, mock_compiled_1, mock_compiled_2],
            ),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY", "QQQ"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')

            # Call for SPY
            adapter(symbol="SPY", bars=sample_bars, position=None, equity=100000.0)

            # Call for QQQ
            qqq_bars = [
                BarData(
                    symbol="QQQ",
                    timestamp=datetime(2024, 1, 15, 9, 30, 0, tzinfo=UTC),
                    open=140.0,
                    high=141.0,
                    low=139.0,
                    close=140.5,
                    volume=5000,
                )
            ]
            adapter(symbol="QQQ", bars=qqq_bars, position=None, equity=100000.0)

            # Should have two separate instances
            assert "SPY" in adapter._per_symbol
            assert "QQQ" in adapter._per_symbol
            assert "SPY" in adapter._initialized_symbols
            assert "QQQ" in adapter._initialized_symbols


class TestStrategyAdapterReset:
    """Tests for reset method."""

    def test_reset_all_clears_state(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test that reset clears all state."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            adapter._per_symbol["SPY"] = mock_compiled_strategy
            adapter._initialized_symbols.add("SPY")
            adapter._current_weights["SPY"] = 100.0

            adapter.reset()

            assert len(adapter._per_symbol) == 0
            assert len(adapter._initialized_symbols) == 0
            assert len(adapter._current_weights) == 0

    def test_reset_single_symbol(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test that reset can clear a single symbol."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY", "QQQ"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            adapter._per_symbol["SPY"] = mock_compiled_strategy
            adapter._per_symbol["QQQ"] = MagicMock()
            adapter._initialized_symbols.add("SPY")
            adapter._initialized_symbols.add("QQQ")
            adapter._current_weights["SPY"] = 100.0
            adapter._current_weights["QQQ"] = 50.0

            adapter.reset("SPY")

            # SPY should be reset, QQQ should remain
            mock_compiled_strategy.reset.assert_called_once()
            assert "SPY" not in adapter._initialized_symbols
            assert "QQQ" in adapter._initialized_symbols
            assert "SPY" not in adapter._current_weights
            assert "QQQ" in adapter._current_weights


class TestStrategyAdapterProperties:
    """Tests for property accessors."""

    def test_name_property(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test name property returns template name."""
        mock_compiled_strategy.name = "My Strategy"

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            assert adapter.name == "My Strategy"

    def test_min_bars_property(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test min_bars property returns template min_bars."""
        mock_compiled_strategy.min_bars = 20

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            assert adapter.min_bars == 20

    def test_symbols_property(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test symbols property returns extracted symbols."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY", "TLT"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            symbols = adapter.symbols
            assert "SPY" in symbols
            assert "TLT" in symbols

    def test_rebalance_frequency_property(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test rebalance_frequency property returns template rebalance_frequency."""
        mock_compiled_strategy.rebalance_frequency = "monthly"

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            assert adapter.rebalance_frequency == "monthly"


class TestGetCurrentWeights:
    """Tests for get_current_weights method."""

    def test_get_current_weights_returns_copy(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test that get_current_weights returns a copy of weights."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY", "TLT"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            adapter._current_weights["SPY"] = 60.0
            adapter._current_weights["TLT"] = 40.0

            weights = adapter.get_current_weights()

            assert weights["SPY"] == 60.0
            assert weights["TLT"] == 40.0
            # Should be a copy
            weights["SPY"] = 100.0
            assert adapter._current_weights["SPY"] == 60.0


class TestGetIndicatorValues:
    """Tests for get_indicator_values method."""

    def test_get_indicator_values_returns_empty_for_unknown_symbol(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test that unknown symbol returns empty dict."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            result = adapter.get_indicator_values("UNKNOWN")
            assert result == {}


class TestLoadStrategyAdapter:
    """Tests for load_strategy_adapter factory function."""

    def test_load_creates_adapter(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test that load_strategy_adapter creates an adapter."""
        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = load_strategy_adapter('(strategy "test")')
            assert isinstance(adapter, StrategyAdapter)

    def test_load_raises_on_invalid_strategy(self) -> None:
        """Test that load raises on invalid strategy."""
        with patch("src.compiler_adapter.parse_strategy", side_effect=Exception("Parse error")):
            with pytest.raises(ValueError):
                load_strategy_adapter("(invalid)")


class TestStrategyAdapterRepr:
    """Tests for __repr__ method."""

    def test_repr(
        self,
        mock_ast: MagicMock,
        mock_compiled_strategy: MagicMock,
        mock_validation: MagicMock,
    ) -> None:
        """Test repr output."""
        mock_compiled_strategy.name = "Test Strategy"
        mock_compiled_strategy.min_bars = 10

        with (
            patch("src.compiler_adapter.parse_strategy", return_value=mock_ast),
            patch("src.compiler_adapter.validate_strategy", return_value=mock_validation),
            patch("src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy),
            patch("src.compiler_adapter.get_required_symbols", return_value={"SPY"}),
        ):
            adapter = StrategyAdapter('(strategy "test")')
            result = repr(adapter)

            assert "StrategyAdapter" in result
            assert "Test Strategy" in result
            assert "min_bars=10" in result
            assert "SPY" in result
