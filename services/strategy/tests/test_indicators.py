"""Tests for technical indicators."""

import numpy as np
import pytest

from src.indicators.momentum import CCI, RSI, Stochastic, WilliamsR
from src.indicators.trend import ADX, EMA, MACD, SMA
from src.indicators.volatility import ATR, BollingerBands, KeltnerChannel
from src.indicators.volume import MFI, OBV, VWAP, DonchianChannel

# ===================
# Test Data Fixtures
# ===================


@pytest.fixture
def prices():
    """Sample price data for testing."""
    return np.array(
        [
            100.0,
            102.0,
            101.0,
            103.0,
            105.0,
            104.0,
            106.0,
            108.0,
            107.0,
            109.0,
            110.0,
            108.0,
            107.0,
            109.0,
            111.0,
            113.0,
            112.0,
            114.0,
            116.0,
            115.0,
        ]
    )


@pytest.fixture
def ohlcv_data():
    """Sample OHLCV data for testing."""
    n = 30
    np.random.seed(42)
    base = 100 + np.cumsum(np.random.randn(n) * 2)
    return {
        "high": base + np.abs(np.random.randn(n)),
        "low": base - np.abs(np.random.randn(n)),
        "close": base + np.random.randn(n) * 0.5,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    }


@pytest.fixture
def short_prices():
    """Short price series for edge case testing."""
    return np.array([100.0, 101.0, 102.0])


# ===================
# Trend Indicators Tests
# ===================


class TestSMA:
    """Tests for Simple Moving Average."""

    def test_sma_calculation(self, prices):
        """Test SMA calculation with valid data."""
        sma = SMA(period=5)
        result = sma.calculate(prices)

        assert len(result) == len(prices)
        # First 4 values should be NaN
        assert np.all(np.isnan(result[:4]))
        # Value at index 4 should be average of first 5 prices
        expected = np.mean(prices[:5])
        assert np.isclose(result[4], expected)

    def test_sma_short_data(self, short_prices):
        """Test SMA with data shorter than period."""
        sma = SMA(period=5)
        result = sma.calculate(short_prices)

        assert len(result) == len(short_prices)
        assert np.all(np.isnan(result))

    def test_sma_default_period(self):
        """Test SMA with default period."""
        sma = SMA()
        assert sma.period == 20


class TestEMA:
    """Tests for Exponential Moving Average."""

    def test_ema_calculation(self, prices):
        """Test EMA calculation with valid data."""
        ema = EMA(period=5)
        result = ema.calculate(prices)

        assert len(result) == len(prices)
        # First 4 values should be NaN
        assert np.all(np.isnan(result[:4]))
        # First EMA value should equal SMA
        expected_first = np.mean(prices[:5])
        assert np.isclose(result[4], expected_first)
        # Subsequent values should not be NaN
        assert not np.any(np.isnan(result[4:]))

    def test_ema_short_data(self, short_prices):
        """Test EMA with data shorter than period."""
        ema = EMA(period=5)
        result = ema.calculate(short_prices)

        assert len(result) == len(short_prices)
        assert np.all(np.isnan(result))

    def test_ema_multiplier(self):
        """Test EMA multiplier calculation."""
        ema = EMA(period=10)
        expected = 2 / (10 + 1)
        assert np.isclose(ema.multiplier, expected)


class TestMACD:
    """Tests for MACD indicator."""

    def test_macd_calculation(self, prices):
        """Test MACD calculation returns all components."""
        # Need longer data for MACD
        long_prices = np.concatenate([prices, prices, prices])
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        result = macd.calculate(long_prices)

        assert "line" in result
        assert "signal" in result
        assert "histogram" in result
        assert len(result["line"]) == len(long_prices)
        assert len(result["signal"]) == len(long_prices)
        assert len(result["histogram"]) == len(long_prices)

    def test_macd_default_periods(self):
        """Test MACD default periods."""
        macd = MACD()
        assert macd.fast_period == 12
        assert macd.slow_period == 26
        assert macd.signal_period == 9


class TestADX:
    """Tests for Average Directional Index."""

    def test_adx_calculation(self, ohlcv_data):
        """Test ADX calculation returns all components."""
        adx = ADX(period=14)
        result = adx.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
            close=ohlcv_data["close"],
        )

        assert "value" in result
        assert "plus_di" in result
        assert "minus_di" in result
        assert len(result["value"]) == len(ohlcv_data["close"])

    def test_adx_short_data(self):
        """Test ADX with data shorter than period."""
        adx = ADX(period=14)
        result = adx.calculate(
            high=np.array([100.0, 101.0]),
            low=np.array([99.0, 100.0]),
            close=np.array([100.0, 100.5]),
        )

        assert np.all(np.isnan(result["value"]))
        assert np.all(np.isnan(result["plus_di"]))
        assert np.all(np.isnan(result["minus_di"]))


# ===================
# Momentum Indicators Tests
# ===================


class TestRSI:
    """Tests for Relative Strength Index."""

    def test_rsi_calculation(self, prices):
        """Test RSI calculation with valid data."""
        rsi = RSI(period=14)
        result = rsi.calculate(prices)

        assert len(result) == len(prices)
        # RSI should be between 0 and 100 for valid values
        valid_values = result[~np.isnan(result)]
        assert np.all(valid_values >= 0)
        assert np.all(valid_values <= 100)

    def test_rsi_short_data(self, short_prices):
        """Test RSI with data shorter than period."""
        rsi = RSI(period=14)
        result = rsi.calculate(short_prices)

        assert len(result) == len(short_prices)
        assert np.all(np.isnan(result))

    def test_rsi_default_period(self):
        """Test RSI default period."""
        rsi = RSI()
        assert rsi.period == 14

    def test_rsi_trending_up(self):
        """Test RSI with strongly uptrending prices."""
        trending_up = np.array([100.0 + i * 2 for i in range(20)])
        rsi = RSI(period=14)
        result = rsi.calculate(trending_up)

        # RSI should be high (close to 100) in uptrend
        valid = result[~np.isnan(result)]
        assert len(valid) > 0
        assert np.mean(valid) > 70

    def test_rsi_trending_down(self):
        """Test RSI with strongly downtrending prices."""
        trending_down = np.array([200.0 - i * 2 for i in range(20)])
        rsi = RSI(period=14)
        result = rsi.calculate(trending_down)

        # RSI should be low (close to 0) in downtrend
        valid = result[~np.isnan(result)]
        assert len(valid) > 0
        assert np.mean(valid) < 30


class TestStochastic:
    """Tests for Stochastic Oscillator."""

    def test_stochastic_calculation(self, ohlcv_data):
        """Test Stochastic calculation returns K and D."""
        stoch = Stochastic(k_period=14, d_period=3, smooth_k=3)
        result = stoch.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
            close=ohlcv_data["close"],
        )

        assert "k" in result
        assert "d" in result
        assert len(result["k"]) == len(ohlcv_data["close"])
        assert len(result["d"]) == len(ohlcv_data["close"])

    def test_stochastic_short_data(self):
        """Test Stochastic with short data."""
        stoch = Stochastic(k_period=14)
        result = stoch.calculate(
            high=np.array([100.0, 101.0]),
            low=np.array([99.0, 100.0]),
            close=np.array([100.0, 100.5]),
        )

        assert np.all(np.isnan(result["k"]))
        assert np.all(np.isnan(result["d"]))

    def test_stochastic_range(self, ohlcv_data):
        """Test Stochastic values are in valid range."""
        stoch = Stochastic(k_period=14)
        result = stoch.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
            close=ohlcv_data["close"],
        )

        valid_k = result["k"][~np.isnan(result["k"])]
        if len(valid_k) > 0:
            assert np.all(valid_k >= 0)
            assert np.all(valid_k <= 100)


class TestCCI:
    """Tests for Commodity Channel Index."""

    def test_cci_calculation(self, ohlcv_data):
        """Test CCI calculation."""
        cci = CCI(period=20)
        result = cci.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
            close=ohlcv_data["close"],
        )

        assert len(result) == len(ohlcv_data["close"])

    def test_cci_short_data(self):
        """Test CCI with short data."""
        cci = CCI(period=20)
        result = cci.calculate(
            high=np.array([100.0, 101.0]),
            low=np.array([99.0, 100.0]),
            close=np.array([100.0, 100.5]),
        )

        assert np.all(np.isnan(result))


class TestWilliamsR:
    """Tests for Williams %R."""

    def test_williams_r_calculation(self, ohlcv_data):
        """Test Williams %R calculation."""
        wr = WilliamsR(period=14)
        result = wr.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
            close=ohlcv_data["close"],
        )

        assert len(result) == len(ohlcv_data["close"])
        # Williams %R should be between -100 and 0
        valid = result[~np.isnan(result)]
        if len(valid) > 0:
            assert np.all(valid >= -100)
            assert np.all(valid <= 0)

    def test_williams_r_short_data(self):
        """Test Williams %R with short data."""
        wr = WilliamsR(period=14)
        result = wr.calculate(
            high=np.array([100.0, 101.0]),
            low=np.array([99.0, 100.0]),
            close=np.array([100.0, 100.5]),
        )

        assert np.all(np.isnan(result))


# ===================
# Volatility Indicators Tests
# ===================


class TestBollingerBands:
    """Tests for Bollinger Bands."""

    def test_bollinger_calculation(self, prices):
        """Test Bollinger Bands calculation."""
        bb = BollingerBands(period=5, std_dev=2.0)
        result = bb.calculate(prices)

        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert len(result["upper"]) == len(prices)

        # Upper should be above middle, middle above lower
        valid_idx = ~np.isnan(result["middle"])
        assert np.all(result["upper"][valid_idx] >= result["middle"][valid_idx])
        assert np.all(result["middle"][valid_idx] >= result["lower"][valid_idx])

    def test_bollinger_short_data(self, short_prices):
        """Test Bollinger Bands with short data."""
        bb = BollingerBands(period=5)
        result = bb.calculate(short_prices)

        assert np.all(np.isnan(result["upper"]))
        assert np.all(np.isnan(result["middle"]))
        assert np.all(np.isnan(result["lower"]))


class TestATR:
    """Tests for Average True Range."""

    def test_atr_calculation(self, ohlcv_data):
        """Test ATR calculation."""
        atr = ATR(period=14)
        result = atr.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
            close=ohlcv_data["close"],
        )

        assert len(result) == len(ohlcv_data["close"])
        # ATR should be positive for valid values
        valid = result[~np.isnan(result)]
        if len(valid) > 0:
            assert np.all(valid >= 0)

    def test_atr_very_short_data(self):
        """Test ATR with very short data."""
        atr = ATR(period=14)
        result = atr.calculate(
            high=np.array([100.0]),
            low=np.array([99.0]),
            close=np.array([99.5]),
        )

        assert len(result) == 1


class TestKeltnerChannel:
    """Tests for Keltner Channel."""

    def test_keltner_calculation(self, ohlcv_data):
        """Test Keltner Channel calculation."""
        kc = KeltnerChannel(ema_period=20, atr_period=10, multiplier=2.0)
        result = kc.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
            close=ohlcv_data["close"],
        )

        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert len(result["upper"]) == len(ohlcv_data["close"])


# ===================
# Volume Indicators Tests
# ===================


class TestOBV:
    """Tests for On-Balance Volume."""

    def test_obv_calculation(self, ohlcv_data):
        """Test OBV calculation."""
        obv = OBV()
        result = obv.calculate(
            close=ohlcv_data["close"],
            volume=ohlcv_data["volume"],
        )

        assert len(result) == len(ohlcv_data["close"])
        # First OBV should equal first volume
        assert result[0] == ohlcv_data["volume"][0]

    def test_obv_empty_data(self):
        """Test OBV with empty data."""
        obv = OBV()
        result = obv.calculate(
            close=np.array([]),
            volume=np.array([]),
        )

        assert len(result) == 0

    def test_obv_single_data_point(self):
        """Test OBV with single data point."""
        obv = OBV()
        result = obv.calculate(
            close=np.array([100.0]),
            volume=np.array([1000.0]),
        )

        assert len(result) == 1
        assert result[0] == 0

    def test_obv_price_up(self):
        """Test OBV with price going up."""
        obv = OBV()
        result = obv.calculate(
            close=np.array([100.0, 101.0, 102.0]),
            volume=np.array([1000.0, 1000.0, 1000.0]),
        )

        # OBV should increase when price goes up
        assert result[2] > result[1] > result[0]

    def test_obv_price_down(self):
        """Test OBV with price going down."""
        obv = OBV()
        result = obv.calculate(
            close=np.array([100.0, 99.0, 98.0]),
            volume=np.array([1000.0, 1000.0, 1000.0]),
        )

        # OBV should decrease when price goes down
        assert result[2] < result[1] < result[0]

    def test_obv_price_unchanged(self):
        """Test OBV with unchanged price."""
        obv = OBV()
        result = obv.calculate(
            close=np.array([100.0, 100.0, 100.0]),
            volume=np.array([1000.0, 1000.0, 1000.0]),
        )

        # OBV should stay the same when price unchanged
        assert result[0] == result[1] == result[2]


class TestMFI:
    """Tests for Money Flow Index."""

    def test_mfi_calculation(self, ohlcv_data):
        """Test MFI calculation."""
        mfi = MFI(period=14)
        result = mfi.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
            close=ohlcv_data["close"],
            volume=ohlcv_data["volume"],
        )

        assert len(result) == len(ohlcv_data["close"])
        # MFI should be between 0 and 100
        valid = result[~np.isnan(result)]
        if len(valid) > 0:
            assert np.all(valid >= 0)
            assert np.all(valid <= 100)

    def test_mfi_short_data(self):
        """Test MFI with short data."""
        mfi = MFI(period=14)
        result = mfi.calculate(
            high=np.array([100.0, 101.0]),
            low=np.array([99.0, 100.0]),
            close=np.array([100.0, 100.5]),
            volume=np.array([1000.0, 1000.0]),
        )

        assert np.all(np.isnan(result))


class TestVWAP:
    """Tests for Volume Weighted Average Price."""

    def test_vwap_calculation(self, ohlcv_data):
        """Test VWAP calculation."""
        vwap = VWAP()
        result = vwap.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
            close=ohlcv_data["close"],
            volume=ohlcv_data["volume"],
        )

        assert len(result) == len(ohlcv_data["close"])
        # VWAP should not have NaN values (unless volume is 0)
        non_zero_vol = ohlcv_data["volume"] != 0
        assert not np.any(np.isnan(result[non_zero_vol]))

    def test_vwap_empty_data(self):
        """Test VWAP with empty data."""
        vwap = VWAP()
        result = vwap.calculate(
            high=np.array([]),
            low=np.array([]),
            close=np.array([]),
            volume=np.array([]),
        )

        assert len(result) == 0


class TestDonchianChannel:
    """Tests for Donchian Channel."""

    def test_donchian_calculation(self, ohlcv_data):
        """Test Donchian Channel calculation."""
        dc = DonchianChannel(period=20)
        result = dc.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
        )

        assert "upper" in result
        assert "middle" in result
        assert "lower" in result
        assert len(result["upper"]) == len(ohlcv_data["high"])

        # Upper should be max high, lower should be min low
        valid_idx = ~np.isnan(result["upper"])
        if np.any(valid_idx):
            assert np.all(result["upper"][valid_idx] >= result["lower"][valid_idx])

    def test_donchian_short_data(self):
        """Test Donchian Channel with short data."""
        dc = DonchianChannel(period=20)
        result = dc.calculate(
            high=np.array([100.0, 101.0]),
            low=np.array([99.0, 100.0]),
        )

        assert np.all(np.isnan(result["upper"]))
        assert np.all(np.isnan(result["middle"]))
        assert np.all(np.isnan(result["lower"]))

    def test_donchian_middle_is_average(self, ohlcv_data):
        """Test that Donchian middle is average of upper and lower."""
        dc = DonchianChannel(period=20)
        result = dc.calculate(
            high=ohlcv_data["high"],
            low=ohlcv_data["low"],
        )

        valid_idx = ~np.isnan(result["middle"])
        expected_middle = (result["upper"][valid_idx] + result["lower"][valid_idx]) / 2
        assert np.allclose(result["middle"][valid_idx], expected_middle)
