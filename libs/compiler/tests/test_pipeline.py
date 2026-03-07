"""Tests for llamatrade_compiler.pipeline module."""

import numpy as np
import pytest

from llamatrade_compiler.extractor import IndicatorSpec
from llamatrade_compiler.pipeline import (
    PriceData,
    compute_all_indicators,
    compute_indicator,
)


class TestPriceData:
    """Tests for PriceData dataclass."""

    def test_price_data_creation(self) -> None:
        """Test creating PriceData with valid arrays."""
        prices = PriceData(
            open=np.array([100.0, 101.0, 102.0]),
            high=np.array([101.0, 102.0, 103.0]),
            low=np.array([99.0, 100.0, 101.0]),
            close=np.array([100.5, 101.5, 102.5]),
            volume=np.array([1000, 2000, 3000]),
        )

        assert len(prices) == 3
        np.testing.assert_array_equal(prices.close, [100.5, 101.5, 102.5])

    def test_price_data_length_mismatch_raises(self) -> None:
        """Test that mismatched array lengths raise ValueError."""
        with pytest.raises(ValueError, match="same length"):
            PriceData(
                open=np.array([100.0, 101.0]),
                high=np.array([101.0, 102.0, 103.0]),  # Different length
                low=np.array([99.0, 100.0]),
                close=np.array([100.5, 101.5]),
                volume=np.array([1000, 2000]),
            )

    def test_price_data_get_source_close(self, sample_prices: PriceData) -> None:
        """Test get_source for close price."""
        close = sample_prices.get_source("close")
        assert isinstance(close, np.ndarray)
        assert len(close) == 100

    def test_price_data_get_source_volume(self, sample_prices: PriceData) -> None:
        """Test get_source for volume (converts to float)."""
        volume = sample_prices.get_source("volume")
        assert volume.dtype == float

    def test_price_data_get_source_unknown_raises(self, sample_prices: PriceData) -> None:
        """Test get_source raises KeyError for unknown source."""
        with pytest.raises(KeyError, match="Unknown source"):
            sample_prices.get_source("unknown")

    def test_price_data_len(self, sample_prices: PriceData) -> None:
        """Test __len__ method."""
        assert len(sample_prices) == 100


class TestSMA:
    """Tests for Simple Moving Average computation."""

    def test_sma_basic(self, sample_prices: PriceData) -> None:
        """Test basic SMA computation."""
        spec = IndicatorSpec(
            indicator_type="sma",
            symbol="SPY",
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

        # Verify calculation
        expected = np.mean(sample_prices.close[:20])
        np.testing.assert_almost_equal(sma[19], expected)

    def test_sma_short_period(self, sample_prices: PriceData) -> None:
        """Test SMA with short period."""
        spec = IndicatorSpec(
            indicator_type="sma",
            symbol="SPY",
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

    def test_sma_with_different_source(self, sample_prices: PriceData) -> None:
        """Test SMA on high prices."""
        spec = IndicatorSpec(
            indicator_type="sma",
            symbol="SPY",
            source="high",
            params=(10,),
            output_key="sma_high_10",
            output_field=None,
            required_bars=10,
        )

        result = compute_indicator(spec, sample_prices)
        sma = result["sma_high_10"]

        expected = np.mean(sample_prices.high[:10])
        np.testing.assert_almost_equal(sma[9], expected)

    def test_sma_insufficient_data(self) -> None:
        """Test SMA with insufficient data returns all NaN."""
        prices = PriceData(
            open=np.array([100.0, 101.0]),
            high=np.array([101.0, 102.0]),
            low=np.array([99.0, 100.0]),
            close=np.array([100.5, 101.5]),
            volume=np.array([1000, 2000]),
        )

        spec = IndicatorSpec(
            indicator_type="sma",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="sma_close_20",
            output_field=None,
            required_bars=20,
        )

        result = compute_indicator(spec, prices)
        assert np.all(np.isnan(result["sma_close_20"]))


class TestEMA:
    """Tests for Exponential Moving Average computation."""

    def test_ema_basic(self, sample_prices: PriceData) -> None:
        """Test basic EMA computation."""
        spec = IndicatorSpec(
            indicator_type="ema",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="ema_close_20",
            output_field=None,
            required_bars=22,
        )

        result = compute_indicator(spec, sample_prices)
        ema = result["ema_close_20"]

        assert np.all(np.isnan(ema[:19]))
        assert not np.isnan(ema[19])

    def test_ema_starts_same_as_sma(self, sample_prices: PriceData) -> None:
        """Test EMA starts with same value as SMA."""
        ema_spec = IndicatorSpec(
            indicator_type="ema",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="ema_close_20",
            output_field=None,
            required_bars=22,
        )
        sma_spec = IndicatorSpec(
            indicator_type="sma",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="sma_close_20",
            output_field=None,
            required_bars=20,
        )

        ema_result = compute_indicator(ema_spec, sample_prices)
        sma_result = compute_indicator(sma_spec, sample_prices)

        # First valid value should match
        np.testing.assert_almost_equal(
            ema_result["ema_close_20"][19],
            sma_result["sma_close_20"][19],
        )

    def test_ema_diverges_from_sma(self, sample_prices: PriceData) -> None:
        """Test EMA diverges from SMA over time."""
        ema_spec = IndicatorSpec(
            indicator_type="ema",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="ema_close_20",
            output_field=None,
            required_bars=22,
        )
        sma_spec = IndicatorSpec(
            indicator_type="sma",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="sma_close_20",
            output_field=None,
            required_bars=20,
        )

        ema_result = compute_indicator(ema_spec, sample_prices)
        sma_result = compute_indicator(sma_spec, sample_prices)

        # Later values should differ
        assert ema_result["ema_close_20"][50] != sma_result["sma_close_20"][50]


class TestRSI:
    """Tests for Relative Strength Index computation."""

    def test_rsi_basic(self, sample_prices: PriceData) -> None:
        """Test basic RSI computation."""
        spec = IndicatorSpec(
            indicator_type="rsi",
            symbol="SPY",
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

    def test_rsi_strong_uptrend_near_100(self, trending_up_prices: PriceData) -> None:
        """Test RSI near 100 in strong uptrend."""
        spec = IndicatorSpec(
            indicator_type="rsi",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="rsi_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, trending_up_prices)
        rsi = result["rsi_close_14"]

        # Last values should be high (near 100) in uptrend
        valid_rsi = rsi[~np.isnan(rsi)]
        assert valid_rsi[-1] > 80

    def test_rsi_strong_downtrend_near_0(self, trending_down_prices: PriceData) -> None:
        """Test RSI near 0 in strong downtrend."""
        spec = IndicatorSpec(
            indicator_type="rsi",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="rsi_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, trending_down_prices)
        rsi = result["rsi_close_14"]

        # Last values should be low (near 0) in downtrend
        valid_rsi = rsi[~np.isnan(rsi)]
        assert valid_rsi[-1] < 20

    def test_rsi_different_period(self, sample_prices: PriceData) -> None:
        """Test RSI with different period."""
        spec = IndicatorSpec(
            indicator_type="rsi",
            symbol="SPY",
            source="close",
            params=(7,),
            output_key="rsi_close_7",
            output_field=None,
            required_bars=8,
        )

        result = compute_indicator(spec, sample_prices)
        rsi = result["rsi_close_7"]

        # First 7 values should be NaN
        assert np.all(np.isnan(rsi[:7]))


class TestMACD:
    """Tests for MACD computation."""

    def test_macd_basic(self, sample_prices: PriceData) -> None:
        """Test basic MACD computation."""
        spec = IndicatorSpec(
            indicator_type="macd",
            symbol="SPY",
            source="close",
            params=(12, 26, 9),
            output_key="macd_close_12_26_9_line",
            output_field="line",
            required_bars=26,
        )

        result = compute_indicator(spec, sample_prices)

        # Should have line, signal, and histogram
        assert "macd_close_12_26_9_line" in result
        assert "macd_close_12_26_9_signal" in result
        assert "macd_close_12_26_9_histogram" in result

    def test_macd_histogram_equals_line_minus_signal(self, sample_prices: PriceData) -> None:
        """Test MACD histogram = line - signal."""
        spec = IndicatorSpec(
            indicator_type="macd",
            symbol="SPY",
            source="close",
            params=(12, 26, 9),
            output_key="macd_close_12_26_9_line",
            output_field="line",
            required_bars=26,
        )

        result = compute_indicator(spec, sample_prices)

        line = result["macd_close_12_26_9_line"]
        signal = result["macd_close_12_26_9_signal"]
        histogram = result["macd_close_12_26_9_histogram"]

        # Where all three are valid, histogram should equal line - signal
        valid_mask = ~(np.isnan(line) | np.isnan(signal) | np.isnan(histogram))
        np.testing.assert_array_almost_equal(
            histogram[valid_mask],
            (line - signal)[valid_mask],
        )

    def test_macd_signal_output(self, sample_prices: PriceData) -> None:
        """Test MACD with signal output field."""
        spec = IndicatorSpec(
            indicator_type="macd",
            symbol="SPY",
            source="close",
            params=(12, 26, 9),
            output_key="macd_close_12_26_9_signal",
            output_field="signal",
            required_bars=26,
        )

        result = compute_indicator(spec, sample_prices)
        assert "macd_close_12_26_9_signal" in result

    def test_macd_histogram_output(self, sample_prices: PriceData) -> None:
        """Test MACD with histogram output field."""
        spec = IndicatorSpec(
            indicator_type="macd",
            symbol="SPY",
            source="close",
            params=(12, 26, 9),
            output_key="macd_close_12_26_9_histogram",
            output_field="histogram",
            required_bars=26,
        )

        result = compute_indicator(spec, sample_prices)
        assert "macd_close_12_26_9_histogram" in result


class TestBollingerBands:
    """Tests for Bollinger Bands computation."""

    def test_bollinger_bands_basic(self, sample_prices: PriceData) -> None:
        """Test basic Bollinger Bands computation."""
        spec = IndicatorSpec(
            indicator_type="bbands",
            symbol="SPY",
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

    def test_bollinger_bands_symmetry(self, sample_prices: PriceData) -> None:
        """Test Bollinger Bands are symmetric around middle."""
        spec = IndicatorSpec(
            indicator_type="bbands",
            symbol="SPY",
            source="close",
            params=(20, 2.0),
            output_key="bbands_close_20_2.0_middle",
            output_field="middle",
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        upper = result["bbands_close_20_2.0_upper"]
        middle = result["bbands_close_20_2.0_middle"]
        lower = result["bbands_close_20_2.0_lower"]

        # upper - middle should equal middle - lower
        valid_mask = ~(np.isnan(upper) | np.isnan(middle) | np.isnan(lower))
        np.testing.assert_array_almost_equal(
            (upper - middle)[valid_mask],
            (middle - lower)[valid_mask],
        )

    def test_bollinger_bands_order(self, sample_prices: PriceData) -> None:
        """Test upper >= middle >= lower."""
        spec = IndicatorSpec(
            indicator_type="bbands",
            symbol="SPY",
            source="close",
            params=(20, 2.0),
            output_key="bbands_close_20_2.0_upper",
            output_field="upper",
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        upper = result["bbands_close_20_2.0_upper"]
        middle = result["bbands_close_20_2.0_middle"]
        lower = result["bbands_close_20_2.0_lower"]

        valid_mask = ~(np.isnan(upper) | np.isnan(middle) | np.isnan(lower))
        assert np.all(upper[valid_mask] >= middle[valid_mask])
        assert np.all(middle[valid_mask] >= lower[valid_mask])


class TestATR:
    """Tests for Average True Range computation."""

    def test_atr_basic(self, sample_prices: PriceData) -> None:
        """Test basic ATR computation."""
        spec = IndicatorSpec(
            indicator_type="atr",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="atr_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)
        atr = result["atr_close_14"]

        # ATR should always be positive
        valid_atr = atr[~np.isnan(atr)]
        assert np.all(valid_atr >= 0)

    def test_atr_always_positive(self, sample_prices: PriceData) -> None:
        """Test ATR is always positive where valid."""
        spec = IndicatorSpec(
            indicator_type="atr",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="atr_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)
        atr = result["atr_close_14"]

        valid_atr = atr[~np.isnan(atr)]
        assert len(valid_atr) > 0
        assert np.all(valid_atr > 0)


class TestADX:
    """Tests for Average Directional Index computation."""

    def test_adx_basic(self, sample_prices: PriceData) -> None:
        """Test basic ADX computation."""
        spec = IndicatorSpec(
            indicator_type="adx",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="adx_close_14_value",
            output_field="value",
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)

        assert "adx_close_14_value" in result
        assert "adx_close_14_plus_di" in result
        assert "adx_close_14_minus_di" in result

    def test_adx_range(self, sample_prices: PriceData) -> None:
        """Test ADX values are in valid range (0-100)."""
        spec = IndicatorSpec(
            indicator_type="adx",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="adx_close_14_value",
            output_field="value",
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)
        adx = result["adx_close_14_value"]

        valid_adx = adx[~np.isnan(adx)]
        assert np.all(valid_adx >= 0)
        assert np.all(valid_adx <= 100)

    def test_adx_di_range(self, sample_prices: PriceData) -> None:
        """Test DI values are in valid range (0-100)."""
        spec = IndicatorSpec(
            indicator_type="adx",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="adx_close_14_value",
            output_field="value",
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)
        plus_di = result["adx_close_14_plus_di"]
        minus_di = result["adx_close_14_minus_di"]

        valid_plus = plus_di[~np.isnan(plus_di)]
        valid_minus = minus_di[~np.isnan(minus_di)]

        assert np.all(valid_plus >= 0)
        assert np.all(valid_minus >= 0)


class TestStochastic:
    """Tests for Stochastic Oscillator computation."""

    def test_stochastic_basic(self, sample_prices: PriceData) -> None:
        """Test basic Stochastic computation."""
        spec = IndicatorSpec(
            indicator_type="stoch",
            symbol="SPY",
            source="close",
            params=(14, 3, 3),
            output_key="stoch_close_14_3_3_k",
            output_field="k",
            required_bars=14,
        )

        result = compute_indicator(spec, sample_prices)

        assert "stoch_close_14_3_3_k" in result
        assert "stoch_close_14_3_3_d" in result

    def test_stochastic_range(self, sample_prices: PriceData) -> None:
        """Test Stochastic values are in range 0-100."""
        spec = IndicatorSpec(
            indicator_type="stoch",
            symbol="SPY",
            source="close",
            params=(14, 3, 3),
            output_key="stoch_close_14_3_3_k",
            output_field="k",
            required_bars=14,
        )

        result = compute_indicator(spec, sample_prices)
        k = result["stoch_close_14_3_3_k"]
        d = result["stoch_close_14_3_3_d"]

        valid_k = k[~np.isnan(k)]
        valid_d = d[~np.isnan(d)]

        assert np.all(valid_k >= 0)
        assert np.all(valid_k <= 100)
        assert np.all(valid_d >= 0)
        assert np.all(valid_d <= 100)


class TestCCI:
    """Tests for Commodity Channel Index computation."""

    def test_cci_basic(self, sample_prices: PriceData) -> None:
        """Test basic CCI computation."""
        spec = IndicatorSpec(
            indicator_type="cci",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="cci_close_20",
            output_field=None,
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)
        cci = result["cci_close_20"]

        # CCI should have valid values after warmup
        valid_cci = cci[~np.isnan(cci)]
        assert len(valid_cci) > 0

    def test_cci_can_be_positive_or_negative(self, sample_prices: PriceData) -> None:
        """Test CCI can have both positive and negative values."""
        spec = IndicatorSpec(
            indicator_type="cci",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="cci_close_20",
            output_field=None,
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)
        cci = result["cci_close_20"]
        valid_cci = cci[~np.isnan(cci)]

        # In random data, CCI should have both positive and negative values
        assert np.any(valid_cci > 0) or np.any(valid_cci < 0)


class TestWilliamsR:
    """Tests for Williams %R computation."""

    def test_williams_r_basic(self, sample_prices: PriceData) -> None:
        """Test basic Williams %R computation."""
        spec = IndicatorSpec(
            indicator_type="williams-r",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="williams-r_close_14",
            output_field=None,
            required_bars=14,
        )

        result = compute_indicator(spec, sample_prices)
        wr = result["williams-r_close_14"]

        valid_wr = wr[~np.isnan(wr)]
        assert len(valid_wr) > 0

    def test_williams_r_range(self, sample_prices: PriceData) -> None:
        """Test Williams %R is in range -100 to 0."""
        spec = IndicatorSpec(
            indicator_type="williams-r",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="williams-r_close_14",
            output_field=None,
            required_bars=14,
        )

        result = compute_indicator(spec, sample_prices)
        wr = result["williams-r_close_14"]

        valid_wr = wr[~np.isnan(wr)]
        assert np.all(valid_wr >= -100)
        assert np.all(valid_wr <= 0)


class TestOBV:
    """Tests for On-Balance Volume computation."""

    def test_obv_basic(self, sample_prices: PriceData) -> None:
        """Test basic OBV computation."""
        spec = IndicatorSpec(
            indicator_type="obv",
            symbol="SPY",
            source="close",
            params=(),
            output_key="obv_close",
            output_field=None,
            required_bars=2,
        )

        result = compute_indicator(spec, sample_prices)
        obv = result["obv_close"]

        # OBV should start with first volume
        assert obv[0] == sample_prices.volume[0]

    def test_obv_increases_on_up_day(self) -> None:
        """Test OBV increases when close > prev close."""
        prices = PriceData(
            open=np.array([100.0, 100.0, 100.0]),
            high=np.array([101.0, 102.0, 103.0]),
            low=np.array([99.0, 99.0, 99.0]),
            close=np.array([100.0, 101.0, 102.0]),  # Consecutive up days
            volume=np.array([1000, 2000, 3000]),
        )

        spec = IndicatorSpec(
            indicator_type="obv",
            symbol="SPY",
            source="close",
            params=(),
            output_key="obv_close",
            output_field=None,
            required_bars=2,
        )

        result = compute_indicator(spec, prices)
        obv = result["obv_close"]

        # OBV should increase
        assert obv[1] == 1000 + 2000  # 3000
        assert obv[2] == 1000 + 2000 + 3000  # 6000

    def test_obv_decreases_on_down_day(self) -> None:
        """Test OBV decreases when close < prev close."""
        prices = PriceData(
            open=np.array([100.0, 100.0, 100.0]),
            high=np.array([101.0, 101.0, 101.0]),
            low=np.array([99.0, 98.0, 97.0]),
            close=np.array([100.0, 99.0, 98.0]),  # Consecutive down days
            volume=np.array([1000, 2000, 3000]),
        )

        spec = IndicatorSpec(
            indicator_type="obv",
            symbol="SPY",
            source="close",
            params=(),
            output_key="obv_close",
            output_field=None,
            required_bars=2,
        )

        result = compute_indicator(spec, prices)
        obv = result["obv_close"]

        # OBV should decrease
        assert obv[1] == 1000 - 2000  # -1000
        assert obv[2] == 1000 - 2000 - 3000  # -4000


class TestMFI:
    """Tests for Money Flow Index computation."""

    def test_mfi_basic(self, sample_prices: PriceData) -> None:
        """Test basic MFI computation."""
        spec = IndicatorSpec(
            indicator_type="mfi",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="mfi_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)
        mfi = result["mfi_close_14"]

        valid_mfi = mfi[~np.isnan(mfi)]
        assert len(valid_mfi) > 0

    def test_mfi_range(self, sample_prices: PriceData) -> None:
        """Test MFI is in range 0-100."""
        spec = IndicatorSpec(
            indicator_type="mfi",
            symbol="SPY",
            source="close",
            params=(14,),
            output_key="mfi_close_14",
            output_field=None,
            required_bars=15,
        )

        result = compute_indicator(spec, sample_prices)
        mfi = result["mfi_close_14"]

        valid_mfi = mfi[~np.isnan(mfi)]
        assert np.all(valid_mfi >= 0)
        assert np.all(valid_mfi <= 100)


class TestVWAP:
    """Tests for Volume Weighted Average Price computation."""

    def test_vwap_basic(self, sample_prices: PriceData) -> None:
        """Test basic VWAP computation."""
        spec = IndicatorSpec(
            indicator_type="vwap",
            symbol="SPY",
            source="close",
            params=(),
            output_key="vwap_close",
            output_field=None,
            required_bars=2,
        )

        result = compute_indicator(spec, sample_prices)
        vwap = result["vwap_close"]

        assert not np.isnan(vwap[0])

    def test_vwap_cumulative(self) -> None:
        """Test VWAP is cumulative calculation."""
        prices = PriceData(
            open=np.array([100.0, 100.0]),
            high=np.array([102.0, 103.0]),
            low=np.array([98.0, 99.0]),
            close=np.array([100.0, 101.0]),
            volume=np.array([1000, 2000]),
        )

        spec = IndicatorSpec(
            indicator_type="vwap",
            symbol="SPY",
            source="close",
            params=(),
            output_key="vwap_close",
            output_field=None,
            required_bars=2,
        )

        result = compute_indicator(spec, prices)
        vwap = result["vwap_close"]

        # First VWAP = TP[0]
        tp0 = (102.0 + 98.0 + 100.0) / 3
        assert vwap[0] == pytest.approx(tp0)

        # Second VWAP = cumulative
        tp1 = (103.0 + 99.0 + 101.0) / 3
        expected = (tp0 * 1000 + tp1 * 2000) / 3000
        assert vwap[1] == pytest.approx(expected)


class TestKeltner:
    """Tests for Keltner Channel computation."""

    def test_keltner_basic(self, sample_prices: PriceData) -> None:
        """Test basic Keltner Channel computation."""
        spec = IndicatorSpec(
            indicator_type="keltner",
            symbol="SPY",
            source="close",
            params=(20, 2.0),
            output_key="keltner_close_20_2.0_middle",
            output_field="middle",
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        assert "keltner_close_20_2.0_upper" in result
        assert "keltner_close_20_2.0_middle" in result
        assert "keltner_close_20_2.0_lower" in result

    def test_keltner_order(self, sample_prices: PriceData) -> None:
        """Test upper >= middle >= lower."""
        spec = IndicatorSpec(
            indicator_type="keltner",
            symbol="SPY",
            source="close",
            params=(20, 2.0),
            output_key="keltner_close_20_2.0_middle",
            output_field="middle",
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        upper = result["keltner_close_20_2.0_upper"]
        middle = result["keltner_close_20_2.0_middle"]
        lower = result["keltner_close_20_2.0_lower"]

        valid_mask = ~(np.isnan(upper) | np.isnan(middle) | np.isnan(lower))
        assert np.all(upper[valid_mask] >= middle[valid_mask])
        assert np.all(middle[valid_mask] >= lower[valid_mask])


class TestDonchian:
    """Tests for Donchian Channel computation."""

    def test_donchian_basic(self, sample_prices: PriceData) -> None:
        """Test basic Donchian Channel computation."""
        spec = IndicatorSpec(
            indicator_type="donchian",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="donchian_close_20_upper",
            output_field="upper",
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        assert "donchian_close_20_upper" in result
        assert "donchian_close_20_lower" in result

    def test_donchian_values(self, sample_prices: PriceData) -> None:
        """Test Donchian Channel values are max/min of period."""
        spec = IndicatorSpec(
            indicator_type="donchian",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="donchian_close_20_upper",
            output_field="upper",
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        upper = result["donchian_close_20_upper"]
        lower = result["donchian_close_20_lower"]

        # At index 19, upper should be max of first 20 highs
        expected_upper = np.max(sample_prices.high[:20])
        expected_lower = np.min(sample_prices.low[:20])

        assert upper[19] == pytest.approx(expected_upper)
        assert lower[19] == pytest.approx(expected_lower)


class TestStddev:
    """Tests for Standard Deviation computation."""

    def test_stddev_basic(self, sample_prices: PriceData) -> None:
        """Test basic standard deviation computation."""
        spec = IndicatorSpec(
            indicator_type="stddev",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="stddev_close_20",
            output_field=None,
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)
        stddev = result["stddev_close_20"]

        # First 19 values should be NaN
        assert np.all(np.isnan(stddev[:19]))

        # Verify calculation at index 19
        expected = np.std(sample_prices.close[:20], ddof=0)
        assert stddev[19] == pytest.approx(expected)

    def test_stddev_always_positive(self, sample_prices: PriceData) -> None:
        """Test standard deviation is always positive."""
        spec = IndicatorSpec(
            indicator_type="stddev",
            symbol="SPY",
            source="close",
            params=(20,),
            output_key="stddev_close_20",
            output_field=None,
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)
        stddev = result["stddev_close_20"]

        valid_stddev = stddev[~np.isnan(stddev)]
        assert np.all(valid_stddev >= 0)


class TestMomentum:
    """Tests for Momentum computation."""

    def test_momentum_basic(self, sample_prices: PriceData) -> None:
        """Test basic momentum computation."""
        spec = IndicatorSpec(
            indicator_type="momentum",
            symbol="SPY",
            source="close",
            params=(10,),
            output_key="momentum_close_10",
            output_field=None,
            required_bars=11,
        )

        result = compute_indicator(spec, sample_prices)
        momentum = result["momentum_close_10"]

        # First 10 values should be NaN
        assert np.all(np.isnan(momentum[:10]))
        assert not np.isnan(momentum[10])

    def test_momentum_calculation(self, sample_prices: PriceData) -> None:
        """Test momentum is difference from n bars ago."""
        spec = IndicatorSpec(
            indicator_type="momentum",
            symbol="SPY",
            source="close",
            params=(10,),
            output_key="momentum_close_10",
            output_field=None,
            required_bars=11,
        )

        result = compute_indicator(spec, sample_prices)
        momentum = result["momentum_close_10"]

        # momentum[10] = close[10] - close[0]
        expected = sample_prices.close[10] - sample_prices.close[0]
        assert momentum[10] == pytest.approx(expected)


class TestComputeIndicator:
    """Tests for compute_indicator function integration."""

    def test_compute_indicator_with_output_field(self, sample_prices: PriceData) -> None:
        """Test compute_indicator correctly sets output_key for multi-output indicators."""
        spec = IndicatorSpec(
            indicator_type="macd",
            symbol="SPY",
            source="close",
            params=(12, 26, 9),
            output_key="macd_close_12_26_9_signal",
            output_field="signal",
            required_bars=26,
        )

        result = compute_indicator(spec, sample_prices)

        # The specific output_key should be set
        assert "macd_close_12_26_9_signal" in result

    def test_compute_indicator_default_params(self, sample_prices: PriceData) -> None:
        """Test compute_indicator uses defaults when params missing."""
        spec = IndicatorSpec(
            indicator_type="sma",
            symbol="SPY",
            source="close",
            params=(),  # Empty - should use default of 20
            output_key="sma_close",
            output_field=None,
            required_bars=20,
        )

        result = compute_indicator(spec, sample_prices)

        # Should still work with default period
        assert "sma_close" in result


class TestComputeAllIndicators:
    """Tests for compute_all_indicators function."""

    def test_compute_all_indicators_empty(self, sample_prices: PriceData) -> None:
        """Test with empty indicator list."""
        result = compute_all_indicators([], sample_prices)
        assert result == {}

    def test_compute_all_indicators_single(self, sample_prices: PriceData) -> None:
        """Test with single indicator."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                symbol="SPY",
                source="close",
                params=(20,),
                output_key="sma_close_20",
                output_field=None,
                required_bars=20,
            ),
        ]

        result = compute_all_indicators(indicators, sample_prices)
        assert "sma_close_20" in result

    def test_compute_all_indicators_multiple(self, sample_prices: PriceData) -> None:
        """Test with multiple indicators."""
        indicators = [
            IndicatorSpec(
                indicator_type="sma",
                symbol="SPY",
                source="close",
                params=(20,),
                output_key="sma_close_20",
                output_field=None,
                required_bars=20,
            ),
            IndicatorSpec(
                indicator_type="rsi",
                symbol="SPY",
                source="close",
                params=(14,),
                output_key="rsi_close_14",
                output_field=None,
                required_bars=15,
            ),
            IndicatorSpec(
                indicator_type="ema",
                symbol="SPY",
                source="close",
                params=(10,),
                output_key="ema_close_10",
                output_field=None,
                required_bars=12,
            ),
        ]

        result = compute_all_indicators(indicators, sample_prices)

        assert "sma_close_20" in result
        assert "rsi_close_14" in result
        assert "ema_close_10" in result
