"""Tests for compiler_adapter module."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from src.compiler_adapter import (
    StrategyAdapter,
    fetch_strategy_and_create_adapter,
    load_strategy_adapter,
)
from src.runner.bar_stream import BarData
from src.runner.runner import Position


@pytest.fixture
def sample_bar_data():
    """Create sample bar data for testing."""
    return BarData(
        symbol="AAPL",
        timestamp=datetime(2024, 1, 15, 9, 30, 0),
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume=10000,
    )


@pytest.fixture
def sample_bars(sample_bar_data):
    """Create a list of sample bars."""
    return [
        BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 9, 29, 0),
            open=149.0,
            high=150.0,
            low=148.0,
            close=149.5,
            volume=8000,
        ),
        sample_bar_data,
    ]


@pytest.fixture
def sample_position():
    """Create a sample position."""
    return Position(
        symbol="AAPL",
        side="long",
        quantity=100.0,
        entry_price=149.0,
        entry_date=datetime(2024, 1, 15, 9, 25, 0),
    )


@pytest.fixture
def mock_compiled_strategy():
    """Create a mock compiled strategy."""
    mock = MagicMock()
    mock.name = "Test Strategy"
    mock.min_bars = 5
    mock.evaluate.return_value = []
    mock.reset = MagicMock()
    mock.set_position = MagicMock()
    mock.close_position = MagicMock()
    mock.add_bar = MagicMock()
    return mock


@pytest.fixture
def mock_ast():
    """Create a mock AST."""
    return MagicMock()


class TestStrategyAdapterInit:
    """Tests for StrategyAdapter initialization."""

    def test_init_parses_and_compiles(self, mock_ast, mock_compiled_strategy):
        """Test that init parses and compiles the strategy."""
        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast) as mock_parse:
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ) as mock_compile:
                adapter = StrategyAdapter("(strategy test)")

                mock_parse.assert_called_once_with("(strategy test)")
                mock_compile.assert_called_once_with(mock_ast)
                assert adapter.ast is mock_ast
                assert adapter.compiled is mock_compiled_strategy
                assert adapter._initialized is False


class TestStrategyAdapterCall:
    """Tests for StrategyAdapter.__call__ method."""

    def test_call_returns_none_for_empty_bars(self, mock_ast, mock_compiled_strategy):
        """Test that calling with empty bars returns None."""
        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                result = adapter(symbol="AAPL", bars=[], position=None, equity=100000.0)

                assert result is None

    def test_call_without_position_closes_position(
        self, mock_ast, mock_compiled_strategy, sample_bars
    ):
        """Test that calling without position closes compiled position."""
        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                adapter(symbol="AAPL", bars=sample_bars, position=None, equity=100000.0)

                mock_compiled_strategy.close_position.assert_called_once()

    def test_call_with_position_sets_position(
        self, mock_ast, mock_compiled_strategy, sample_bars, sample_position
    ):
        """Test that calling with position syncs to compiled strategy."""
        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                adapter(symbol="AAPL", bars=sample_bars, position=sample_position, equity=100000.0)

                mock_compiled_strategy.set_position.assert_called_once()

    def test_call_initializes_with_historical_bars(
        self, mock_ast, mock_compiled_strategy, sample_bars
    ):
        """Test that first call adds historical bars."""
        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                # First call should add historical bars
                adapter(symbol="AAPL", bars=sample_bars, position=None, equity=100000.0)

                # Should have added the first bar (not the last one which is processed separately)
                assert mock_compiled_strategy.add_bar.call_count == 1
                assert adapter._initialized is True

    def test_call_does_not_reinitialize(self, mock_ast, mock_compiled_strategy, sample_bars):
        """Test that subsequent calls don't add historical bars again."""
        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                # First call
                adapter(symbol="AAPL", bars=sample_bars, position=None, equity=100000.0)
                mock_compiled_strategy.add_bar.reset_mock()

                # Second call should not add historical bars
                adapter(symbol="AAPL", bars=sample_bars, position=None, equity=100000.0)

                mock_compiled_strategy.add_bar.assert_not_called()

    def test_call_returns_none_when_no_signals(self, mock_ast, mock_compiled_strategy, sample_bars):
        """Test that no signals returns None."""
        mock_compiled_strategy.evaluate.return_value = []

        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                result = adapter(symbol="AAPL", bars=sample_bars, position=None, equity=100000.0)

                assert result is None

    def test_call_returns_buy_signal(self, mock_ast, mock_compiled_strategy, sample_bars):
        """Test that buy signal is returned with quantity."""
        mock_signal = MagicMock()
        mock_signal.type.value = "buy"
        mock_signal.quantity_percent = 10.0
        mock_compiled_strategy.evaluate.return_value = [mock_signal]

        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                result = adapter(symbol="AAPL", bars=sample_bars, position=None, equity=100000.0)

                assert result is not None
                assert result.type == "buy"
                assert result.symbol == "AAPL"
                # 10% of 100000 / 150.5 (close price) = ~66.45
                assert result.quantity > 0
                assert result.price == 150.5

    def test_call_returns_sell_signal(self, mock_ast, mock_compiled_strategy, sample_bars):
        """Test that sell signal is returned with quantity."""
        mock_signal = MagicMock()
        mock_signal.type.value = "sell"
        mock_signal.quantity_percent = 5.0
        mock_compiled_strategy.evaluate.return_value = [mock_signal]

        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                result = adapter(symbol="AAPL", bars=sample_bars, position=None, equity=100000.0)

                assert result is not None
                assert result.type == "sell"

    def test_call_returns_close_long_signal_with_position_quantity(
        self, mock_ast, mock_compiled_strategy, sample_bars, sample_position
    ):
        """Test that close_long uses position quantity."""
        mock_signal = MagicMock()
        mock_signal.type.value = "close_long"
        mock_signal.quantity_percent = 100.0
        mock_compiled_strategy.evaluate.return_value = [mock_signal]

        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                result = adapter(
                    symbol="AAPL", bars=sample_bars, position=sample_position, equity=100000.0
                )

                assert result is not None
                assert result.type == "close_long"
                assert result.quantity == sample_position.quantity

    def test_call_handles_zero_price(self, mock_ast, mock_compiled_strategy):
        """Test handling of zero price edge case."""
        mock_signal = MagicMock()
        mock_signal.type.value = "buy"
        mock_signal.quantity_percent = 10.0
        mock_compiled_strategy.evaluate.return_value = [mock_signal]

        zero_price_bar = BarData(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 9, 30, 0),
            open=0.0,
            high=0.0,
            low=0.0,
            close=0.0,
            volume=0,
        )

        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                result = adapter(
                    symbol="AAPL", bars=[zero_price_bar], position=None, equity=100000.0
                )

                assert result is not None
                assert result.quantity == 0


class TestStrategyAdapterReset:
    """Tests for reset method."""

    def test_reset_resets_compiled_and_flag(self, mock_ast, mock_compiled_strategy):
        """Test that reset clears state."""
        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")
                adapter._initialized = True

                adapter.reset()

                mock_compiled_strategy.reset.assert_called_once()
                assert adapter._initialized is False


class TestStrategyAdapterProperties:
    """Tests for property accessors."""

    def test_name_property(self, mock_ast, mock_compiled_strategy):
        """Test name property returns compiled name."""
        mock_compiled_strategy.name = "My Strategy"

        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                assert adapter.name == "My Strategy"

    def test_min_bars_property(self, mock_ast, mock_compiled_strategy):
        """Test min_bars property returns compiled min_bars."""
        mock_compiled_strategy.min_bars = 20

        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = StrategyAdapter("(strategy test)")

                assert adapter.min_bars == 20


class TestLoadStrategyAdapter:
    """Tests for load_strategy_adapter factory function."""

    def test_load_creates_adapter(self, mock_ast, mock_compiled_strategy):
        """Test that load_strategy_adapter creates an adapter."""
        with patch("src.compiler_adapter.parse_strategy", return_value=mock_ast):
            with patch(
                "src.compiler_adapter.compile_strategy", return_value=mock_compiled_strategy
            ):
                adapter = load_strategy_adapter("(strategy test)")

                assert isinstance(adapter, StrategyAdapter)


class TestFetchStrategyAndCreateAdapter:
    """Tests for fetch_strategy_and_create_adapter."""

    async def test_fetch_returns_none_placeholder(self):
        """Test that placeholder returns None."""
        result = await fetch_strategy_and_create_adapter("strategy-123", version=1)

        assert result is None
