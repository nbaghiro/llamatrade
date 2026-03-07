"""Tests for llamatrade_compiler.vectorized module."""

from datetime import UTC, datetime

import numpy as np

from llamatrade_compiler.vectorized import (
    VectorizedBarData,
    VectorizedCompiledStrategy,
    prepare_vectorized_bars,
    should_use_vectorized_engine,
)


class TestVectorizedBarData:
    """Tests for VectorizedBarData TypedDict."""

    def test_vectorized_bar_data_creation(self) -> None:
        """Test creating VectorizedBarData."""
        timestamps = np.array(["2024-01-01", "2024-01-02", "2024-01-03"], dtype="datetime64[D]")
        num_symbols = 2
        num_bars = 3

        data: VectorizedBarData = {
            "timestamps": timestamps,
            "opens": np.random.rand(num_symbols, num_bars) * 100,
            "highs": np.random.rand(num_symbols, num_bars) * 100 + 5,
            "lows": np.random.rand(num_symbols, num_bars) * 100 - 5,
            "closes": np.random.rand(num_symbols, num_bars) * 100,
            "volumes": np.random.randint(100000, 1000000, (num_symbols, num_bars)).astype(float),
        }

        assert data["timestamps"].shape == (3,)
        assert data["opens"].shape == (2, 3)
        assert data["closes"].shape == (2, 3)

    def test_vectorized_bar_data_shapes(self) -> None:
        """Test VectorizedBarData array shapes are consistent."""
        num_symbols = 5
        num_bars = 100

        data: VectorizedBarData = {
            "timestamps": np.arange(num_bars).astype("datetime64[D]"),
            "opens": np.ones((num_symbols, num_bars)),
            "highs": np.ones((num_symbols, num_bars)),
            "lows": np.ones((num_symbols, num_bars)),
            "closes": np.ones((num_symbols, num_bars)),
            "volumes": np.ones((num_symbols, num_bars)),
        }

        assert data["timestamps"].shape[0] == num_bars
        for key in ["opens", "highs", "lows", "closes", "volumes"]:
            assert data[key].shape == (num_symbols, num_bars)


class TestPrepareVectorizedBars:
    """Tests for prepare_vectorized_bars function."""

    def test_prepare_single_symbol(self) -> None:
        """Test preparing data for single symbol."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 98.0,
                    "close": 103.0,
                    "volume": 1000000,
                },
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    "open": 103.0,
                    "high": 108.0,
                    "low": 101.0,
                    "close": 106.0,
                    "volume": 1200000,
                },
            ]
        }
        symbols = ["AAPL"]

        data, timestamps = prepare_vectorized_bars(bars, symbols)

        assert data["closes"].shape == (1, 2)
        assert data["closes"][0, 0] == 103.0
        assert data["closes"][0, 1] == 106.0
        assert len(timestamps) == 2

    def test_prepare_multiple_symbols(self) -> None:
        """Test preparing data for multiple symbols."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 98.0,
                    "close": 103.0,
                    "volume": 1000000,
                },
            ],
            "GOOGL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 140.0,
                    "high": 145.0,
                    "low": 138.0,
                    "close": 142.0,
                    "volume": 500000,
                },
            ],
        }
        symbols = ["AAPL", "GOOGL"]

        data, timestamps = prepare_vectorized_bars(bars, symbols)

        assert data["closes"].shape == (2, 1)
        assert data["closes"][0, 0] == 103.0  # AAPL
        assert data["closes"][1, 0] == 142.0  # GOOGL

    def test_prepare_fills_missing_bars(self) -> None:
        """Test that missing bars are filled with NaN."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 98.0,
                    "close": 103.0,
                    "volume": 1000000,
                },
                {
                    "timestamp": datetime(2024, 1, 3, tzinfo=UTC),  # Skip day 2
                    "open": 105.0,
                    "high": 110.0,
                    "low": 103.0,
                    "close": 108.0,
                    "volume": 1100000,
                },
            ],
            "GOOGL": [
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),  # Only day 2
                    "open": 140.0,
                    "high": 145.0,
                    "low": 138.0,
                    "close": 142.0,
                    "volume": 500000,
                },
            ],
        }
        symbols = ["AAPL", "GOOGL"]

        data, timestamps = prepare_vectorized_bars(bars, symbols)

        # Should have 3 timestamps
        assert len(timestamps) == 3

        # AAPL has data for day 1 and 3, missing day 2 (forward-filled)
        assert data["closes"][0, 0] == 103.0
        assert data["closes"][0, 2] == 108.0

        # GOOGL only has day 2
        assert data["closes"][1, 1] == 142.0

    def test_prepare_preserves_symbol_order(self) -> None:
        """Test that symbol order is preserved."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 98.0,
                    "close": 100.0,
                    "volume": 1000000,
                },
            ],
            "GOOGL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 140.0,
                    "high": 145.0,
                    "low": 138.0,
                    "close": 200.0,
                    "volume": 500000,
                },
            ],
            "MSFT": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 350.0,
                    "high": 360.0,
                    "low": 345.0,
                    "close": 300.0,
                    "volume": 800000,
                },
            ],
        }
        symbols = ["GOOGL", "MSFT", "AAPL"]  # Custom order

        data, _ = prepare_vectorized_bars(bars, symbols)

        # Check order matches symbols list
        assert data["closes"][0, 0] == 200.0  # GOOGL
        assert data["closes"][1, 0] == 300.0  # MSFT
        assert data["closes"][2, 0] == 100.0  # AAPL

    def test_prepare_aligned_timestamps(self) -> None:
        """Test timestamps are aligned across symbols."""
        ts1 = datetime(2024, 1, 1, tzinfo=UTC)
        ts2 = datetime(2024, 1, 2, tzinfo=UTC)
        ts3 = datetime(2024, 1, 3, tzinfo=UTC)

        bars = {
            "AAPL": [
                {
                    "timestamp": ts1,
                    "open": 100.0,
                    "high": 105.0,
                    "low": 98.0,
                    "close": 100.0,
                    "volume": 1000000,
                },
                {
                    "timestamp": ts2,
                    "open": 100.0,
                    "high": 105.0,
                    "low": 98.0,
                    "close": 101.0,
                    "volume": 1000000,
                },
                {
                    "timestamp": ts3,
                    "open": 100.0,
                    "high": 105.0,
                    "low": 98.0,
                    "close": 102.0,
                    "volume": 1000000,
                },
            ],
            "GOOGL": [
                {
                    "timestamp": ts1,
                    "open": 140.0,
                    "high": 145.0,
                    "low": 138.0,
                    "close": 200.0,
                    "volume": 500000,
                },
                {
                    "timestamp": ts2,
                    "open": 140.0,
                    "high": 145.0,
                    "low": 138.0,
                    "close": 201.0,
                    "volume": 500000,
                },
                {
                    "timestamp": ts3,
                    "open": 140.0,
                    "high": 145.0,
                    "low": 138.0,
                    "close": 202.0,
                    "volume": 500000,
                },
            ],
        }
        symbols = ["AAPL", "GOOGL"]

        data, timestamps = prepare_vectorized_bars(bars, symbols)

        assert len(timestamps) == 3
        assert data["closes"].shape == (2, 3)

    def test_prepare_empty_symbol(self) -> None:
        """Test handling of symbol with no data."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 98.0,
                    "close": 103.0,
                    "volume": 1000000,
                },
            ],
        }
        symbols = ["AAPL", "GOOGL"]  # GOOGL has no data

        data, _ = prepare_vectorized_bars(bars, symbols)

        assert data["closes"].shape == (2, 1)
        assert data["closes"][0, 0] == 103.0  # AAPL
        assert np.isnan(data["opens"][1, 0])  # GOOGL has NaN


class TestShouldUseVectorizedEngine:
    """Tests for should_use_vectorized_engine function."""

    def test_below_threshold_returns_false(self) -> None:
        """Test returns False for small datasets."""
        assert should_use_vectorized_engine(1, 100, threshold=10000) is False
        assert should_use_vectorized_engine(10, 500, threshold=10000) is False
        assert should_use_vectorized_engine(5, 1000, threshold=10000) is False

    def test_above_threshold_returns_true(self) -> None:
        """Test returns True for large datasets."""
        assert should_use_vectorized_engine(10, 2000, threshold=10000) is True
        assert should_use_vectorized_engine(100, 200, threshold=10000) is True
        assert should_use_vectorized_engine(1, 20000, threshold=10000) is True

    def test_at_threshold_returns_false(self) -> None:
        """Test returns False at exactly threshold."""
        assert should_use_vectorized_engine(10, 1000, threshold=10000) is False
        assert should_use_vectorized_engine(100, 100, threshold=10000) is False

    def test_just_above_threshold_returns_true(self) -> None:
        """Test returns True just above threshold."""
        assert should_use_vectorized_engine(10, 1001, threshold=10000) is True

    def test_custom_threshold(self) -> None:
        """Test with custom threshold."""
        assert should_use_vectorized_engine(5, 100, threshold=100) is True
        assert should_use_vectorized_engine(5, 100, threshold=1000) is False

    def test_default_threshold(self) -> None:
        """Test default threshold is 10000."""
        # Default threshold should be 10000
        assert should_use_vectorized_engine(10, 1000) is False  # 10000 total
        assert should_use_vectorized_engine(10, 1001) is True  # 10010 total


class TestVectorizedCompiledStrategy:
    """Tests for VectorizedCompiledStrategy dataclass."""

    def test_vectorized_compiled_strategy_creation(self) -> None:
        """Test creating VectorizedCompiledStrategy."""

        def allocation_fn(bars: VectorizedBarData, indicators: dict) -> dict[str, np.ndarray]:
            num_bars = bars["closes"].shape[1]
            return {"AAPL": np.full(num_bars, 50.0), "GOOGL": np.full(num_bars, 50.0)}

        strategy = VectorizedCompiledStrategy(
            allocation_fn=allocation_fn,
            strategy_name="Test Strategy",
            rebalance_frequency="monthly",
            benchmark="SPY",
        )

        assert strategy.strategy_name == "Test Strategy"
        assert strategy.rebalance_frequency == "monthly"
        assert strategy.benchmark == "SPY"

    def test_vectorized_compiled_strategy_defaults(self) -> None:
        """Test VectorizedCompiledStrategy default values."""

        def dummy_fn(bars: VectorizedBarData, indicators: dict) -> dict[str, np.ndarray]:
            return {}

        strategy = VectorizedCompiledStrategy(
            allocation_fn=dummy_fn,
        )

        assert strategy.strategy_name == ""
        assert strategy.rebalance_frequency is None
        assert strategy.benchmark is None
        assert strategy.indicators == {}

    def test_vectorized_compiled_strategy_indicators(self) -> None:
        """Test VectorizedCompiledStrategy with pre-computed indicators."""

        def dummy_fn(bars: VectorizedBarData, indicators: dict) -> dict[str, np.ndarray]:
            return {}

        indicators = {
            "sma_AAPL_close_20": np.random.rand(10),
            "rsi_AAPL_close_14": np.random.rand(10),
        }

        strategy = VectorizedCompiledStrategy(
            allocation_fn=dummy_fn,
            indicators=indicators,
        )

        assert "sma_AAPL_close_20" in strategy.indicators
        assert "rsi_AAPL_close_14" in strategy.indicators

    def test_compute_weights_calls_allocation_fn(self) -> None:
        """Test compute_weights calls the allocation function."""

        def allocation_fn(bars: VectorizedBarData, indicators: dict) -> dict[str, np.ndarray]:
            num_bars = bars["closes"].shape[1]
            return {
                "AAPL": np.full(num_bars, 60.0),
                "GOOGL": np.full(num_bars, 40.0),
            }

        strategy = VectorizedCompiledStrategy(
            allocation_fn=allocation_fn,
            strategy_name="Test",
        )

        # Create test data
        data: VectorizedBarData = {
            "timestamps": np.array(["2024-01-01", "2024-01-02"], dtype="datetime64[D]"),
            "opens": np.array([[99.0, 101.0], [139.0, 141.0]]),
            "highs": np.array([[100.0, 102.0], [140.0, 142.0]]),
            "lows": np.array([[98.0, 100.0], [138.0, 140.0]]),
            "closes": np.array([[99.5, 101.5], [139.5, 141.5]]),
            "volumes": np.array([[1000000, 1100000], [500000, 550000]], dtype=float),
        }

        result = strategy.compute_weights(data)

        assert "AAPL" in result
        assert "GOOGL" in result
        assert result["AAPL"].shape == (2,)
        assert result["GOOGL"].shape == (2,)
        np.testing.assert_array_equal(result["AAPL"], [60.0, 60.0])
        np.testing.assert_array_equal(result["GOOGL"], [40.0, 40.0])

    def test_allocation_fn_receives_indicators(self) -> None:
        """Test that allocation_fn receives the indicators dict."""
        received_indicators = {}

        def allocation_fn(bars: VectorizedBarData, indicators: dict) -> dict[str, np.ndarray]:
            nonlocal received_indicators
            received_indicators = indicators.copy()
            num_bars = bars["closes"].shape[1]
            return {"AAPL": np.full(num_bars, 100.0)}

        pre_computed = {"sma_AAPL_close_20": np.array([100.0, 101.0])}

        strategy = VectorizedCompiledStrategy(
            allocation_fn=allocation_fn,
            indicators=pre_computed,
        )

        data: VectorizedBarData = {
            "timestamps": np.array(["2024-01-01", "2024-01-02"], dtype="datetime64[D]"),
            "opens": np.array([[99.0, 101.0]]),
            "highs": np.array([[100.0, 102.0]]),
            "lows": np.array([[98.0, 100.0]]),
            "closes": np.array([[99.5, 101.5]]),
            "volumes": np.array([[1000000, 1100000]], dtype=float),
        }

        strategy.compute_weights(data)

        assert "sma_AAPL_close_20" in received_indicators
