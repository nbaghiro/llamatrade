"""Golden-value tests for the indicator library, validated against TA-Lib.

The existing ``test_pipeline.py`` checks *properties* (range bounds, NaN warm-up,
internal consistency). Those are necessary but cannot catch a wrong formula — a
"0 <= RSI <= 100" assertion passes whether or not the smoothing is correct, and it
even passes vacuously on an all-NaN output. These tests instead pin numerical
correctness against TA-Lib, the de-facto reference implementation, over a fixed
deterministic dataset.

Reference: https://ta-lib.org/  (installed as the ``ta-lib`` dev dependency).

Two classes of indicator:

* **Exact** — our output equals TA-Lib to floating-point tolerance everywhere both
  are defined (SMA, EMA, RSI, Bollinger, ATR, Stochastic, CCI, Williams %R, OBV,
  MFI, StdDev, Momentum).
* **Converges after an unstable period** — Wilder's recursive ADX / +DI / -DI seed
  slightly differently from TA-Lib, so early values differ but converge to within
  ~1e-4 once warmed up. We compare only the converged tail, matching how TA-Lib
  itself frames its "unstable period". MACD's line follows the conventional
  (TradingView/Pine) definition ``EMA(fast) - EMA(slow)``; it differs from TA-Lib's
  MACD only during that warm-up.

A few indicators have no plain TA-Lib equivalent (VWAP cumulative, Donchian,
Keltner) and are checked against hand-computed / self-consistent references.
"""

import numpy as np
import pytest

from llamatrade_compiler.indicators.library import (
    atr,
    bollinger_bands,
    cci,
    donchian,
    ema,
    keltner,
    macd,
    mfi,
    momentum,
    obv,
    rsi,
    sma,
    stddev,
    stochastic,
    vwap,
    williams_r,
)

talib = pytest.importorskip("talib", reason="ta-lib reference oracle not installed")

# --- Fixed, deterministic OHLCV series (committed via the seed) -------------------

_N = 250
_RNG = np.random.default_rng(20240613)
_CLOSE = 100.0 + np.cumsum(_RNG.standard_normal(_N))
_HIGH = _CLOSE + np.abs(_RNG.standard_normal(_N))
_LOW = _CLOSE - np.abs(_RNG.standard_normal(_N))
_VOLUME = _RNG.integers(100_000, 1_000_000, _N).astype(float)

# Wilder/EMA recursive indicators carry an unstable warm-up; skip it before comparing.
# ADX is doubly smoothed (Wilder of DX, which is itself built from Wilder-smoothed DM/TR),
# so its seed sensitivity decays more slowly than the singly-smoothed +DI/-DI and MACD line.
_UNSTABLE_SKIP = 80
_ADX_UNSTABLE_SKIP = 120


def _assert_close(ours: np.ndarray, ref: np.ndarray, *, atol: float, skip: int = 0) -> None:
    """Assert two series match on their overlapping valid region (after ``skip``)."""
    mask = ~np.isnan(ours) & ~np.isnan(ref)
    idx = np.where(mask)[0]
    assert idx.size > skip, f"no overlapping valid values (got {idx.size}, skip {skip})"
    idx = idx[skip:]
    diff = np.abs(ours[idx] - ref[idx])
    worst = float(diff.max())
    assert worst <= atol, f"maxdiff {worst:.3e} exceeds atol {atol:.0e} (n={idx.size})"


class TestExactMatchTALib:
    """Indicators that must equal TA-Lib to floating-point tolerance."""

    def test_sma(self) -> None:
        _assert_close(sma(_CLOSE, 20), talib.SMA(_CLOSE, 20), atol=1e-9)

    def test_ema(self) -> None:
        _assert_close(ema(_CLOSE, 20), talib.EMA(_CLOSE, 20), atol=1e-9)

    def test_rsi(self) -> None:
        _assert_close(rsi(_CLOSE, 14), talib.RSI(_CLOSE, 14), atol=1e-9)

    def test_bollinger_bands(self) -> None:
        upper, middle, lower = bollinger_bands(_CLOSE, 20, 2.0)
        t_up, t_mid, t_low = talib.BBANDS(_CLOSE, 20, 2.0, 2.0)
        _assert_close(upper, t_up, atol=1e-9)
        _assert_close(middle, t_mid, atol=1e-9)
        _assert_close(lower, t_low, atol=1e-9)

    def test_atr_uses_wilder_smoothing(self) -> None:
        # Regression: ATR previously used SMA smoothing and diverged from TA-Lib.
        _assert_close(atr(_HIGH, _LOW, _CLOSE, 14), talib.ATR(_HIGH, _LOW, _CLOSE, 14), atol=1e-9)

    def test_stochastic(self) -> None:
        k, d = stochastic(_HIGH, _LOW, _CLOSE, 14, 3, 3)
        t_k, t_d = talib.STOCH(_HIGH, _LOW, _CLOSE, 14, 3, 0, 3, 0)
        _assert_close(k, t_k, atol=1e-9)
        _assert_close(d, t_d, atol=1e-9)

    def test_cci(self) -> None:
        _assert_close(cci(_HIGH, _LOW, _CLOSE, 20), talib.CCI(_HIGH, _LOW, _CLOSE, 20), atol=1e-9)

    def test_williams_r(self) -> None:
        _assert_close(
            williams_r(_HIGH, _LOW, _CLOSE, 14), talib.WILLR(_HIGH, _LOW, _CLOSE, 14), atol=1e-9
        )

    def test_obv(self) -> None:
        _assert_close(obv(_CLOSE, _VOLUME), talib.OBV(_CLOSE, _VOLUME), atol=1e-6)

    def test_mfi(self) -> None:
        _assert_close(
            mfi(_HIGH, _LOW, _CLOSE, _VOLUME, 14),
            talib.MFI(_HIGH, _LOW, _CLOSE, _VOLUME, 14),
            atol=1e-9,
        )

    def test_stddev(self) -> None:
        _assert_close(stddev(_CLOSE, 20), talib.STDDEV(_CLOSE, 20, 1.0), atol=1e-9)

    def test_momentum(self) -> None:
        _assert_close(momentum(_CLOSE, 10), talib.MOM(_CLOSE, 10), atol=1e-9)


class TestWilderConvergesToTALib:
    """ADX/+DI/-DI converge to TA-Lib after the unstable warm-up period."""

    def test_plus_di(self) -> None:
        _, plus_di, _ = atr_adx_plus_minus()
        _assert_close(
            plus_di, talib.PLUS_DI(_HIGH, _LOW, _CLOSE, 14), atol=1e-2, skip=_UNSTABLE_SKIP
        )

    def test_minus_di(self) -> None:
        _, _, minus_di = atr_adx_plus_minus()
        _assert_close(
            minus_di, talib.MINUS_DI(_HIGH, _LOW, _CLOSE, 14), atol=1e-2, skip=_UNSTABLE_SKIP
        )

    def test_adx(self) -> None:
        adx_vals, _, _ = atr_adx_plus_minus()
        _assert_close(
            adx_vals, talib.ADX(_HIGH, _LOW, _CLOSE, 14), atol=1e-2, skip=_ADX_UNSTABLE_SKIP
        )


class TestMACD:
    """MACD uses the conventional EMA(fast) - EMA(slow) definition (TradingView/Pine)."""

    def test_line_is_ema_difference(self) -> None:
        line, _, _ = macd(_CLOSE, 12, 26, 9)
        expected = ema(_CLOSE, 12) - ema(_CLOSE, 26)
        _assert_close(line, expected, atol=1e-9)

    def test_signal_is_ema_of_line(self) -> None:
        line, signal, _ = macd(_CLOSE, 12, 26, 9)
        _assert_close(signal, ema(line, 9), atol=1e-9)

    def test_histogram_is_line_minus_signal(self) -> None:
        line, signal, hist = macd(_CLOSE, 12, 26, 9)
        _assert_close(hist, line - signal, atol=1e-9)

    def test_line_converges_to_talib(self) -> None:
        # TA-Lib's MACD seeds its internal EMAs differently; our line still converges to it.
        line, _, _ = macd(_CLOSE, 12, 26, 9)
        _assert_close(line, talib.MACD(_CLOSE, 12, 26, 9)[0], atol=1e-2, skip=_UNSTABLE_SKIP)


class TestNaNPoisoningRegression:
    """Regression for the leading-NaN bug that made these indicators return all-NaN.

    _sma/_ema previously poisoned the whole output when fed an already-warming
    (leading-NaN) series, so ADX, Stochastic, and the MACD signal/histogram were
    entirely NaN — and in production every condition referencing them silently
    evaluated False.
    """

    def test_adx_not_all_nan(self) -> None:
        adx_vals, plus_di, minus_di = atr_adx_plus_minus()
        assert np.isfinite(adx_vals).sum() > 0
        assert np.isfinite(plus_di).sum() > 0
        assert np.isfinite(minus_di).sum() > 0

    def test_stochastic_not_all_nan(self) -> None:
        k, d = stochastic(_HIGH, _LOW, _CLOSE, 14, 3, 3)
        assert np.isfinite(k).sum() > 0
        assert np.isfinite(d).sum() > 0

    def test_macd_signal_and_histogram_not_all_nan(self) -> None:
        _, signal, hist = macd(_CLOSE, 12, 26, 9)
        assert np.isfinite(signal).sum() > 0
        assert np.isfinite(hist).sum() > 0

    def test_sma_tolerates_leading_nan(self) -> None:
        series = np.concatenate([[np.nan, np.nan, np.nan], np.arange(1.0, 11.0)])
        result = sma(series, 3)
        # First clean 3-window ends at index 5; value = mean(1,2,3) = 2.
        assert np.isnan(result[4])
        assert result[5] == pytest.approx(2.0)
        assert result[-1] == pytest.approx(9.0)  # mean(8,9,10)

    def test_ema_tolerates_leading_nan(self) -> None:
        series = np.concatenate([[np.nan, np.nan], np.arange(1.0, 21.0)])
        result = ema(series, 5)
        assert np.isfinite(result).sum() > 0
        # Seeds with the SMA of the first clean window, then runs the recurrence.
        assert result[-1] == pytest.approx(ema(np.arange(1.0, 21.0), 5)[-1])


class TestNoTALibEquivalent:
    """Indicators without a plain TA-Lib counterpart: hand-computed / self-consistent."""

    def test_vwap_cumulative(self) -> None:
        result = vwap(_HIGH, _LOW, _CLOSE, _VOLUME)
        tp = (_HIGH + _LOW + _CLOSE) / 3.0
        expected = np.cumsum(tp * _VOLUME) / np.cumsum(_VOLUME)
        _assert_close(result, expected, atol=1e-6)

    def test_donchian_channels(self) -> None:
        upper, lower = donchian(_HIGH, _LOW, 20)
        for i in range(19, _N):
            assert upper[i] == pytest.approx(_HIGH[i - 19 : i + 1].max())
            assert lower[i] == pytest.approx(_LOW[i - 19 : i + 1].min())

    def test_keltner_self_consistent(self) -> None:
        upper, middle, lower = keltner(_HIGH, _LOW, _CLOSE, 20, 2.0)
        mid_expected = ema(_CLOSE, 20)
        atr_expected = atr(_HIGH, _LOW, _CLOSE, 20)
        _assert_close(middle, mid_expected, atol=1e-9)
        _assert_close(upper, mid_expected + 2.0 * atr_expected, atol=1e-9)
        _assert_close(lower, mid_expected - 2.0 * atr_expected, atol=1e-9)


def atr_adx_plus_minus() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Helper: our ADX bundle (adx, +DI, -DI) for the fixed dataset."""
    from llamatrade_compiler.indicators.library import _adx

    return _adx(_HIGH, _LOW, _CLOSE, 14)
