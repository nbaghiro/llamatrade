"""Tests for the indicator pipeline module."""

import numpy as np
import pytest

from src.compiler.extractor import IndicatorSpec
from src.compiler.pipeline import (
    PriceData,
    compute_all_indicators,
    compute_indicator,
)


@pytest.fixture
def sample_prices() -> PriceData:
    """Create sample OHLCV data for testing."""
    # Generate 100 bars of synthetic data
    np.random.seed(42)
    n = 100
    base = 100.0
    returns = np.random.randn(n) * 0.02

    close = base * np.cumprod(1 + returns)
    open_ = close * (1 + np.random.randn(n) * 0.005)
    high = np.maximum(open_, close) * (1 + np.abs(np.random.randn(n) * 0.01))
    low = np.minimum(open_, close) * (1 - np.abs(np.random.randn(n) * 0.01))
    volume = np.random.randint(100000, 1000000, n)

    return PriceData(
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class TestPriceData:
    """Tests for PriceData class."""

    def test_length_validation(self) -> None:
        """Test that mismatched array lengths raise error."""
        with pytest.raises(ValueError, match="same length"):
            PriceData(
                open=np.array([1.0, 2.0]),
                high=np.array([1.5, 2.5, 3.5]),  # Different length
                low=np.array([0.5, 1.5]),
                close=np.array([1.2, 2.2]),
                volume=np.array([1000, 2000]),
            )

    def test_len(self, sample_prices: PriceData) -> None:
        """Test __len__ method."""
        assert len(sample_prices) == 100

    def test_get_source(self, sample_prices: PriceData) -> None:
        """Test get_source method."""
        close = sample_prices.get_source("close")
        assert len(close) == 100
        assert isinstance(close, np.ndarray)

        volume = sample_prices.get_source("volume")
        assert len(volume) == 100
        assert volume.dtype == float

    def test_get_source_unknown(self, sample_prices: PriceData) -> None:
        """Test get_source with unknown source."""
        with pytest.raises(KeyError):
            sample_prices.get_source("unknown")


class TestSMA:
    """Tests for SMA computation."""

    def test_sma_basic(self, sample_prices: PriceData) -> None:
        """Test basic SMA computation."""
        spec = IndicatorSpec(
            indicator_type="sma",
            source="close",
            params=(20,),
            output_key="sma_close_20",
            output_field=None,
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)
        sma = result["sma_close_20"]

        # First 19 values should be NaN
        assert np.all(np.isnan(sma[:19]))

        # From index 19 onward should have values
        assert not np.isnan(sma[19])

        # Manual check for one value
        expected = np.mean(sample_prices.close[:20])
        np.testing.assert_almost_equal(sma[19], expected)

    def test_sma_short_period(self, sample_prices: PriceData) -> None:
        """Test SMA with short period."""
        spec = IndicatorSpec(
            indicator_type="sma",
            source="close",
            params=(5,),
            output_key="sma_close_5",
            output_field=None,
            required_bars=5,
        )

        result = compute_indicator(spec, sample_prices)
        sma = result["sma_close_5"]

        assert np.all(np.isnan(sma[:4]))
        assert not np.isnan(sma[4])


class TestEMA:
    """Tests for EMA computation."""

    def test_ema_basic(self, sample_prices: PriceData) -> None:
        """Test basic EMA computation."""
        spec = IndicatorSpec(
            indicator_type="ema",
            source="close",
            params=(20,),
            output_key="ema_close_20",
            output_field=None,
            required_bars=22,
        )

        result = compute_indicator(spec, sample_prices)
        ema = result["ema_close_20"]

        # First 19 values should be NaN
        assert np.all(np.isnan(ema[:19]))

        # From index 19 onward should have values
        assert not np.isnan(ema[19])

        # EMA should be different from SMA (tests weighting)
        sma_spec = IndicatorSpec(
            indicator_type="sma",
            source="close",
            params=(20,),
            output_key="sma_close_20",
            output_field=None,
            required_bars=20,
        )
        sma_result = compute_indicator(sma_spec, sample_prices)
        sma = sma_result["sma_close_20"]

        # They start the same but diverge
        np.testing.assert_almost_equal(ema[19], sma[19])
        # Later values should differ
        assert ema[50] != sma[50]


class TestRSI:
    """Tests for RSI computation."""

    def test_rsi_basic(self, sample_prices: PriceData) -> None:
        """Test basic RSI computation."""
        spec = IndicatorSpec(
            indicator_type="rsi",
            source="close",
            params=(14,),
            output_key="rsi_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)
        rsi = result["rsi_close_14"]

        # RSI values should be between 0 and 100
        valid_rsi = rsi[~np.isnan(rsi)]
        assert np.all(valid_rsi >= 0)
        assert np.all(valid_rsi <= 100)

    def test_rsi_overbought_oversold(self) -> None:
        """Test RSI in extreme conditions."""
        # Create strongly uptrending data
        close = np.linspace(100, 150, 50)  # Consistent uptrend
        prices = PriceData(
            open=close * 0.99,
            high=close * 1.01,
            low=close * 0.98,
            close=close,
            volume=np.full(50, 1000000),
        )

        spec = IndicatorSpec(
            indicator_type="rsi",
            source="close",
            params=(14,),
            output_key="rsi_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, prices)
        rsi = result["rsi_close_14"]

        # Strong uptrend should have high RSI
        valid_rsi = rsi[~np.isnan(rsi)]
        assert valid_rsi[-1] > 70  # Should be overbought


class TestMACD:
    """Tests for MACD computation."""

    def test_macd_outputs(self, sample_prices: PriceData) -> None:
        """Test MACD returns all three outputs."""
        spec = IndicatorSpec(
            indicator_type="macd",
            source="close",
            params=(12, 26, 9),
            output_key="macd_close_12_26_9_line",
            output_field="line",
            required_bars=26,
        )

        result = compute_indicator(spec, sample_prices)

        # Should have all three outputs
        assert "macd_close_12_26_9_line" in result
        assert "macd_close_12_26_9_signal" in result
        assert "macd_close_12_26_9_histogram" in result

        # Histogram should be line - signal
        line = result["macd_close_12_26_9_line"]
        signal = result["macd_close_12_26_9_signal"]
        histogram = result["macd_close_12_26_9_histogram"]

        valid_indices = ~np.isnan(histogram)
        np.testing.assert_array_almost_equal(
            histogram[valid_indices], (line - signal)[valid_indices]
        )


class TestBollingerBands:
    """Tests for Bollinger Bands computation."""

    def test_bbands_outputs(self, sample_prices: PriceData) -> None:
        """Test Bollinger Bands returns all three bands."""
        spec = IndicatorSpec(
            indicator_type="bbands",
            source="close",
            params=(20, 2.0),
            output_key="bbands_close_20_2.0_upper",
            output_field="upper",
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        assert "bbands_close_20_2.0_upper" in result
        assert "bbands_close_20_2.0_middle" in result
        assert "bbands_close_20_2.0_lower" in result

        upper = result["bbands_close_20_2.0_upper"]
        middle = result["bbands_close_20_2.0_middle"]
        lower = result["bbands_close_20_2.0_lower"]

        # Upper should be above middle, lower below
        valid = ~np.isnan(upper)
        assert np.all(upper[valid] > middle[valid])
        assert np.all(lower[valid] < middle[valid])

        # Bands should be symmetric around middle
        upper_diff = upper[valid] - middle[valid]
        lower_diff = middle[valid] - lower[valid]
        np.testing.assert_array_almost_equal(upper_diff, lower_diff)


class TestATR:
    """Tests for ATR computation."""

    def test_atr_basic(self, sample_prices: PriceData) -> None:
        """Test basic ATR computation."""
        spec = IndicatorSpec(
            indicator_type="atr",
            source="close",
            params=(14,),
            output_key="atr_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)
        atr = result["atr_close_14"]

        # ATR should be positive
        valid_atr = atr[~np.isnan(atr)]
        assert np.all(valid_atr > 0)


class TestOBV:
    """Tests for OBV computation."""

    def test_obv_basic(self, sample_prices: PriceData) -> None:
        """Test basic OBV computation."""
        spec = IndicatorSpec(
            indicator_type="obv",
            source="close",
            params=(),
            output_key="obv_close",
            output_field=None,
            required_bars=1,
        )

        result = compute_indicator(spec, sample_prices)
        obv = result["obv_close"]

        # OBV should have no NaN values
        assert not np.any(np.isnan(obv))

        # First value should equal first volume
        assert obv[0] == sample_prices.volume[0]


class TestADX:
    """Tests for ADX computation."""

    def test_adx_outputs(self, sample_prices: PriceData) -> None:
        """Test ADX returns ADX, +DI, and -DI."""
        spec = IndicatorSpec(
            indicator_type="adx",
            source="close",
            params=(14,),
            output_key="adx_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)

        assert "adx_close_14" in result
        assert "adx_close_14_plus_di" in result
        assert "adx_close_14_minus_di" in result

        adx = result["adx_close_14"]
        valid_adx = adx[~np.isnan(adx)]

        # ADX should be between 0 and 100
        assert np.all(valid_adx >= 0)
        assert np.all(valid_adx <= 100)


class TestStochastic:
    """Tests for Stochastic oscillator computation."""

    def test_stoch_outputs(self, sample_prices: PriceData) -> None:
        """Test Stochastic returns %K and %D."""
        spec = IndicatorSpec(
            indicator_type="stoch",
            source="close",
            params=(14, 3, 3),
            output_key="stoch_close_14_3_3_k",
            output_field="k",
            required_bars=14,
        )

        result = compute_indicator(spec, sample_prices)

        assert "stoch_close_14_3_3_k" in result
        assert "stoch_close_14_3_3_d" in result

        k = result["stoch_close_14_3_3_k"]
        d = result["stoch_close_14_3_3_d"]

        # Values should be between 0 and 100
        valid_k = k[~np.isnan(k)]
        valid_d = d[~np.isnan(d)]

        assert np.all(valid_k >= 0)
        assert np.all(valid_k <= 100)
        assert np.all(valid_d >= 0)
        assert np.all(valid_d <= 100)


class TestCCI:
    """Tests for CCI computation."""

    def test_cci_basic(self, sample_prices: PriceData) -> None:
        """Test basic CCI computation."""
        spec = IndicatorSpec(
            indicator_type="cci",
            source="close",
            params=(20,),
            output_key="cci_close_20",
            output_field=None,
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)
        cci = result["cci_close_20"]

        # CCI should have valid values (can be any number, typically -200 to +200)
        valid_cci = cci[~np.isnan(cci)]
        assert len(valid_cci) > 0


class TestWilliamsR:
    """Tests for Williams %R computation."""

    def test_williams_r_basic(self, sample_prices: PriceData) -> None:
        """Test basic Williams %R computation."""
        spec = IndicatorSpec(
            indicator_type="williams-r",
            source="close",
            params=(14,),
            output_key="williams-r_close_14",
            output_field=None,
            required_bars=14,
        )

        result = compute_indicator(spec, sample_prices)
        williams_r = result["williams-r_close_14"]

        # Williams %R should be between -100 and 0
        valid = williams_r[~np.isnan(williams_r)]
        assert np.all(valid >= -100)
        assert np.all(valid <= 0)


class TestMFI:
    """Tests for MFI computation."""

    def test_mfi_basic(self, sample_prices: PriceData) -> None:
        """Test basic MFI computation."""
        spec = IndicatorSpec(
            indicator_type="mfi",
            source="close",
            params=(14,),
            output_key="mfi_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)
        mfi = result["mfi_close_14"]

        # MFI should be between 0 and 100
        valid_mfi = mfi[~np.isnan(mfi)]
        assert np.all(valid_mfi >= 0)
        assert np.all(valid_mfi <= 100)


class TestVWAP:
    """Tests for VWAP computation."""

    def test_vwap_basic(self, sample_prices: PriceData) -> None:
        """Test basic VWAP computation."""
        spec = IndicatorSpec(
            indicator_type="vwap",
            source="close",
            params=(),
            output_key="vwap_close",
            output_field=None,
            required_bars=1,
        )

        result = compute_indicator(spec, sample_prices)
        vwap = result["vwap_close"]

        # VWAP should have no NaN values and be positive
        assert not np.any(np.isnan(vwap))
        assert np.all(vwap > 0)


class TestKeltner:
    """Tests for Keltner Channel computation."""

    def test_keltner_outputs(self, sample_prices: PriceData) -> None:
        """Test Keltner Channel returns upper, middle, lower."""
        spec = IndicatorSpec(
            indicator_type="keltner",
            source="close",
            params=(20, 2.0),
            output_key="keltner_close_20_2.0_upper",
            output_field="upper",
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        assert "keltner_close_20_2.0_upper" in result
        assert "keltner_close_20_2.0_middle" in result
        assert "keltner_close_20_2.0_lower" in result

        upper = result["keltner_close_20_2.0_upper"]
        middle = result["keltner_close_20_2.0_middle"]
        lower = result["keltner_close_20_2.0_lower"]

        # Upper should be above middle, lower below
        valid = ~np.isnan(upper)
        assert np.all(upper[valid] >= middle[valid])
        assert np.all(lower[valid] <= middle[valid])


class TestDonchian:
    """Tests for Donchian Channel computation."""

    def test_donchian_outputs(self, sample_prices: PriceData) -> None:
        """Test Donchian Channel returns upper and lower."""
        spec = IndicatorSpec(
            indicator_type="donchian",
            source="close",
            params=(20,),
            output_key="donchian_close_20_upper",
            output_field="upper",
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        assert "donchian_close_20_upper" in result
        assert "donchian_close_20_lower" in result

        upper = result["donchian_close_20_upper"]
        lower = result["donchian_close_20_lower"]

        # Upper should be >= lower
        valid = ~np.isnan(upper)
        assert np.all(upper[valid] >= lower[valid])


class TestStddev:
    """Tests for Standard Deviation computation."""

    def test_stddev_basic(self, sample_prices: PriceData) -> None:
        """Test basic standard deviation computation."""
        spec = IndicatorSpec(
            indicator_type="stddev",
            source="close",
            params=(20,),
            output_key="stddev_close_20",
            output_field=None,
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)
        stddev = result["stddev_close_20"]

        # Stddev should be non-negative
        valid = stddev[~np.isnan(stddev)]
        assert np.all(valid >= 0)


class TestMomentum:
    """Tests for Momentum indicator computation."""

    def test_momentum_basic(self, sample_prices: PriceData) -> None:
        """Test basic momentum computation."""
        spec = IndicatorSpec(
            indicator_type="momentum",
            source="close",
            params=(10,),
            output_key="momentum_close_10",
            output_field=None,
            required_bars=10,
        )

        result = compute_indicator(spec, sample_prices)
        momentum = result["momentum_close_10"]

        # First 10 values should be NaN
        assert np.all(np.isnan(momentum[:10]))

        # Rest should have values
        assert not np.any(np.isnan(momentum[10:]))

        # Manual check: momentum[10] = close[10] - close[0]
        expected = sample_prices.close[10] - sample_prices.close[0]
        np.testing.assert_almost_equal(momentum[10], expected)


class TestComputeAllIndicators:
    """Tests for compute_all_indicators function."""

    def test_multiple_indicators(self, sample_prices: PriceData) -> None:
        """Test computing multiple indicators at once."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                source="close",
                params=(20,),
                output_key="sma_close_20",
                output_field=None,
                required_bars=20,
            ),
            IndicatorSpec(
                indicator_type="rsi",
                source="close",
                params=(14,),
                output_key="rsi_close_14",
                output_field=None,
                required_bars=15,
            ),
        ]

        results = compute_all_indicators(indicators, sample_prices)

        assert "sma_close_20" in results
        assert "rsi_close_14" in results

    def test_empty_list(self, sample_prices: PriceData) -> None:
        """Test computing with empty indicator list."""
        results = compute_all_indicators([], sample_prices)
        assert results == {}
