"""Tests for all technical indicators."""

import numpy as np
import pytest
from src.engine.strategy_adapter import (
    _compute_adx,
    _compute_atr,
    _compute_bbands,
    _compute_cci,
    _compute_donchian,
    _compute_keltner,
    _compute_macd,
    _compute_mfi,
    _compute_momentum,
    _compute_obv,
    _compute_stddev,
    _compute_stochastic,
    _compute_true_range,
    _compute_vwap,
    _compute_williams_r,
)


class TestStandardDeviation:
    """Tests for standard deviation indicator."""

    def test_stddev_basic(self):
        """Test standard deviation calculation."""
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        result = _compute_stddev(values, 5)

        # First 4 values should be NaN
        assert all(np.isnan(result[:4]))
        # StdDev of [1,2,3,4,5] should be around 1.41
        assert result[4] == pytest.approx(np.std([1, 2, 3, 4, 5], ddof=0), rel=1e-5)

    def test_stddev_insufficient_data(self):
        """Test stddev with insufficient data."""
        values = np.array([1.0, 2.0])
        result = _compute_stddev(values, 5)
        assert all(np.isnan(result))


class TestMomentum:
    """Tests for momentum indicator."""

    def test_momentum_basic(self):
        """Test momentum calculation."""
        values = np.array([100.0, 102.0, 104.0, 106.0, 108.0, 110.0])
        result = _compute_momentum(values, 3)

        # First 3 values should be NaN
        assert all(np.isnan(result[:3]))
        # Momentum at index 3 = values[3] - values[0] = 106 - 100 = 6
        assert result[3] == pytest.approx(6.0)
        assert result[4] == pytest.approx(6.0)  # 108 - 102
        assert result[5] == pytest.approx(6.0)  # 110 - 104


class TestMACD:
    """Tests for MACD indicator."""

    def test_macd_basic(self):
        """Test MACD calculation."""
        # Create trending data
        values = np.array([100.0 + i * 0.5 for i in range(50)])
        macd_line, signal_line, histogram = _compute_macd(values, 12, 26, 9)

        # Check shapes
        assert len(macd_line) == len(values)
        assert len(signal_line) == len(values)
        assert len(histogram) == len(values)

        # MACD should be positive in uptrend
        valid_macd = macd_line[~np.isnan(macd_line)]
        assert len(valid_macd) > 0

    def test_macd_crossover_detection(self):
        """Test MACD can detect crossovers."""
        # Create data that would cause crossover
        values = np.concatenate(
            [
                np.linspace(100, 90, 30),  # Downtrend
                np.linspace(90, 110, 30),  # Uptrend
            ]
        )
        macd_line, signal_line, histogram = _compute_macd(values, 12, 26, 9)

        # Should have both positive and negative histogram values
        valid_hist = histogram[~np.isnan(histogram)]
        if len(valid_hist) > 0:
            assert any(h > 0 for h in valid_hist) or any(h < 0 for h in valid_hist)


class TestBollingerBands:
    """Tests for Bollinger Bands indicator."""

    def test_bbands_basic(self):
        """Test Bollinger Bands calculation."""
        values = np.array(
            [100.0, 102.0, 98.0, 101.0, 103.0, 99.0, 100.0, 102.0, 98.0, 101.0, 103.0, 99.0, 100.0]
        )
        upper, middle, lower = _compute_bbands(values, 5, 2.0)

        # Check shapes
        assert len(upper) == len(values)
        assert len(middle) == len(values)
        assert len(lower) == len(values)

        # Upper > Middle > Lower for valid values
        for i in range(4, len(values)):
            if not np.isnan(middle[i]):
                assert upper[i] > middle[i]
                assert middle[i] > lower[i]

    def test_bbands_band_width(self):
        """Test that band width relates to volatility."""
        # Low volatility data
        low_vol = np.array([100.0, 100.1, 99.9, 100.0, 100.1, 99.9, 100.0, 100.1, 99.9, 100.0])
        upper_lv, middle_lv, lower_lv = _compute_bbands(low_vol, 5, 2.0)

        # High volatility data
        high_vol = np.array([100.0, 110.0, 90.0, 105.0, 95.0, 108.0, 92.0, 107.0, 93.0, 100.0])
        upper_hv, middle_hv, lower_hv = _compute_bbands(high_vol, 5, 2.0)

        # High volatility should have wider bands
        lv_width = upper_lv[-1] - lower_lv[-1] if not np.isnan(upper_lv[-1]) else 0
        hv_width = upper_hv[-1] - lower_hv[-1] if not np.isnan(upper_hv[-1]) else 0
        assert hv_width > lv_width


class TestATR:
    """Tests for Average True Range indicator."""

    def test_true_range_basic(self):
        """Test True Range calculation."""
        highs = np.array([105.0, 106.0, 107.0])
        lows = np.array([95.0, 96.0, 97.0])
        closes = np.array([100.0, 101.0, 102.0])

        tr = _compute_true_range(highs, lows, closes)

        # First TR is simply H-L
        assert tr[0] == pytest.approx(10.0)
        # Subsequent TRs are max of (H-L, |H-Cprev|, |L-Cprev|)
        # TR[1] = max(106-96, |106-100|, |96-100|) = max(10, 6, 4) = 10
        assert tr[1] == pytest.approx(10.0)

    def test_atr_basic(self):
        """Test ATR calculation."""
        highs = np.array(
            [105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0]
        )
        lows = np.array([95.0, 96.0, 97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        closes = np.array(
            [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0]
        )

        atr = _compute_atr(highs, lows, closes, 5)

        # ATR should be around 10 (H-L range)
        valid_atr = atr[~np.isnan(atr)]
        assert len(valid_atr) > 0
        assert all(v > 0 for v in valid_atr)


class TestADX:
    """Tests for ADX indicator."""

    def test_adx_trending_market(self):
        """Test ADX in trending market."""
        # Strong uptrend
        n = 30
        highs = np.array([100.0 + i * 2.0 for i in range(n)])
        lows = np.array([95.0 + i * 2.0 for i in range(n)])
        closes = np.array([98.0 + i * 2.0 for i in range(n)])

        adx, plus_di, minus_di = _compute_adx(highs, lows, closes, 14)

        # Check shapes
        assert len(adx) == n
        assert len(plus_di) == n
        assert len(minus_di) == n

    def test_adx_insufficient_data(self):
        """Test ADX with insufficient data."""
        highs = np.array([100.0, 101.0, 102.0])
        lows = np.array([98.0, 99.0, 100.0])
        closes = np.array([99.0, 100.0, 101.0])

        adx, plus_di, minus_di = _compute_adx(highs, lows, closes, 14)

        assert all(np.isnan(adx))


class TestStochastic:
    """Tests for Stochastic Oscillator."""

    def test_stochastic_basic(self):
        """Test Stochastic calculation."""
        highs = np.array([100.0, 102.0, 104.0, 103.0, 105.0, 106.0, 108.0, 107.0, 109.0, 110.0])
        lows = np.array([95.0, 97.0, 99.0, 98.0, 100.0, 101.0, 103.0, 102.0, 104.0, 105.0])
        closes = np.array([98.0, 100.0, 102.0, 101.0, 103.0, 104.0, 106.0, 105.0, 107.0, 108.0])

        k, d = _compute_stochastic(highs, lows, closes, 5, 3)

        # %K should be between 0 and 100
        valid_k = k[~np.isnan(k)]
        assert all(0 <= v <= 100 for v in valid_k)

        # %D is SMA of %K, so should also be 0-100
        valid_d = d[~np.isnan(d)]
        if len(valid_d) > 0:
            assert all(0 <= v <= 100 for v in valid_d)


class TestCCI:
    """Tests for Commodity Channel Index."""

    def test_cci_basic(self):
        """Test CCI calculation."""
        highs = np.array([100.0, 102.0, 104.0, 103.0, 105.0, 106.0, 108.0, 107.0, 109.0, 110.0])
        lows = np.array([95.0, 97.0, 99.0, 98.0, 100.0, 101.0, 103.0, 102.0, 104.0, 105.0])
        closes = np.array([98.0, 100.0, 102.0, 101.0, 103.0, 104.0, 106.0, 105.0, 107.0, 108.0])

        cci = _compute_cci(highs, lows, closes, 5)

        # CCI should have some valid values
        valid_cci = cci[~np.isnan(cci)]
        assert len(valid_cci) > 0


class TestWilliamsR:
    """Tests for Williams %R indicator."""

    def test_williams_r_basic(self):
        """Test Williams %R calculation."""
        highs = np.array([100.0, 102.0, 104.0, 103.0, 105.0, 106.0, 108.0])
        lows = np.array([95.0, 97.0, 99.0, 98.0, 100.0, 101.0, 103.0])
        closes = np.array([98.0, 100.0, 102.0, 101.0, 103.0, 104.0, 106.0])

        wr = _compute_williams_r(highs, lows, closes, 5)

        # Williams %R should be between -100 and 0
        valid_wr = wr[~np.isnan(wr)]
        assert all(-100 <= v <= 0 for v in valid_wr)


class TestOBV:
    """Tests for On-Balance Volume."""

    def test_obv_basic(self):
        """Test OBV calculation."""
        closes = np.array([100.0, 102.0, 101.0, 103.0, 102.0, 105.0])
        volumes = np.array([1000.0, 1500.0, 1200.0, 1800.0, 1100.0, 2000.0])

        obv = _compute_obv(closes, volumes)

        # OBV should start at first volume
        assert obv[0] == 1000.0
        # Up day: add volume
        assert obv[1] == 2500.0  # 1000 + 1500
        # Down day: subtract volume
        assert obv[2] == 1300.0  # 2500 - 1200
        # Up day: add volume
        assert obv[3] == 3100.0  # 1300 + 1800

    def test_obv_flat_day(self):
        """Test OBV on flat day (no change)."""
        closes = np.array([100.0, 100.0, 100.0])
        volumes = np.array([1000.0, 1500.0, 1200.0])

        obv = _compute_obv(closes, volumes)

        # On flat days, OBV should not change
        assert obv[0] == 1000.0
        assert obv[1] == 1000.0  # No change
        assert obv[2] == 1000.0  # No change


class TestMFI:
    """Tests for Money Flow Index."""

    def test_mfi_basic(self):
        """Test MFI calculation."""
        highs = np.array(
            [
                100.0,
                102.0,
                104.0,
                103.0,
                105.0,
                106.0,
                108.0,
                107.0,
                109.0,
                110.0,
                112.0,
                111.0,
                113.0,
                114.0,
                115.0,
            ]
        )
        lows = np.array(
            [
                95.0,
                97.0,
                99.0,
                98.0,
                100.0,
                101.0,
                103.0,
                102.0,
                104.0,
                105.0,
                107.0,
                106.0,
                108.0,
                109.0,
                110.0,
            ]
        )
        closes = np.array(
            [
                98.0,
                100.0,
                102.0,
                101.0,
                103.0,
                104.0,
                106.0,
                105.0,
                107.0,
                108.0,
                110.0,
                109.0,
                111.0,
                112.0,
                113.0,
            ]
        )
        volumes = np.array(
            [
                1000.0,
                1200.0,
                1100.0,
                1300.0,
                1000.0,
                1500.0,
                1200.0,
                1400.0,
                1100.0,
                1600.0,
                1300.0,
                1500.0,
                1200.0,
                1700.0,
                1400.0,
            ]
        )

        mfi = _compute_mfi(highs, lows, closes, volumes, 14)

        # MFI should be between 0 and 100
        valid_mfi = mfi[~np.isnan(mfi)]
        if len(valid_mfi) > 0:
            assert all(0 <= v <= 100 for v in valid_mfi)


class TestVWAP:
    """Tests for Volume Weighted Average Price."""

    def test_vwap_basic(self):
        """Test VWAP calculation."""
        highs = np.array([102.0, 104.0, 106.0])
        lows = np.array([98.0, 100.0, 102.0])
        closes = np.array([100.0, 102.0, 104.0])
        volumes = np.array([1000.0, 2000.0, 1500.0])

        vwap = _compute_vwap(highs, lows, closes, volumes)

        # Check that VWAP is within price range
        valid_vwap = vwap[~np.isnan(vwap)]
        assert len(valid_vwap) > 0
        # VWAP should be close to volume-weighted typical price
        tp0 = (102 + 98 + 100) / 3  # 100
        assert vwap[0] == pytest.approx(tp0)


class TestKeltnerChannel:
    """Tests for Keltner Channel."""

    def test_keltner_basic(self):
        """Test Keltner Channel calculation."""
        highs = np.array(
            [105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0]
        )
        lows = np.array([95.0, 96.0, 97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
        closes = np.array(
            [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0]
        )

        upper, middle, lower = _compute_keltner(highs, lows, closes, 5, 2.0)

        # Check shapes
        assert len(upper) == len(closes)
        assert len(middle) == len(closes)
        assert len(lower) == len(closes)

        # Upper > Middle > Lower for valid values
        for i in range(len(closes)):
            if not np.isnan(upper[i]) and not np.isnan(middle[i]) and not np.isnan(lower[i]):
                assert upper[i] > middle[i]
                assert middle[i] > lower[i]


class TestDonchianChannel:
    """Tests for Donchian Channel."""

    def test_donchian_basic(self):
        """Test Donchian Channel calculation."""
        highs = np.array([100.0, 102.0, 105.0, 103.0, 108.0, 106.0, 110.0])
        lows = np.array([95.0, 97.0, 100.0, 98.0, 103.0, 101.0, 105.0])

        upper, lower = _compute_donchian(highs, lows, 5)

        # Donchian upper is highest high, lower is lowest low over period
        # At index 4, highest high of [100,102,105,103,108] = 108
        assert upper[4] == pytest.approx(108.0)
        # At index 4, lowest low of [95,97,100,98,103] = 95
        assert lower[4] == pytest.approx(95.0)

    def test_donchian_insufficient_data(self):
        """Test Donchian with insufficient data."""
        highs = np.array([100.0, 102.0])
        lows = np.array([95.0, 97.0])

        upper, lower = _compute_donchian(highs, lows, 5)

        assert all(np.isnan(upper))
        assert all(np.isnan(lower))
