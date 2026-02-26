"""Indicator computation pipeline.

Computes indicator values from OHLCV price data using numpy.
Each indicator function takes arrays and returns computed values.
"""

from dataclasses import dataclass

import numpy as np

from llamatrade_compiler.extractor import IndicatorSpec


@dataclass
class PriceData:
    """Container for OHLCV price data arrays.

    All arrays must be the same length and time-aligned.
    """

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    def __post_init__(self) -> None:
        """Validate array lengths match."""
        lengths = {
            len(self.open),
            len(self.high),
            len(self.low),
            len(self.close),
            len(self.volume),
        }
        if len(lengths) > 1:
            raise ValueError("All price arrays must have the same length")

    def __len__(self) -> int:
        return len(self.close)

    def get_source(self, name: str) -> np.ndarray:
        """Get a price source array by name."""
        if name == "open":
            return self.open
        if name == "high":
            return self.high
        if name == "low":
            return self.low
        if name == "close":
            return self.close
        if name == "volume":
            return self.volume.astype(float)
        raise KeyError(f"Unknown source: {name}")


def _sma(values: np.ndarray, period: int) -> np.ndarray:
    """Simple Moving Average."""
    if len(values) < period:
        return np.full(len(values), np.nan)

    result = np.full(len(values), np.nan)
    cumsum = np.cumsum(values)
    result[period - 1 :] = (cumsum[period - 1 :] - np.concatenate([[0], cumsum[:-period]])) / period
    return result


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    if len(values) < period:
        return np.full(len(values), np.nan)

    result = np.full(len(values), np.nan)
    multiplier = 2.0 / (period + 1)

    # Initialize with SMA
    result[period - 1] = np.mean(values[:period])

    # Calculate EMA
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i - 1]) * multiplier + result[i - 1]

    return result


def _rsi(values: np.ndarray, period: int) -> np.ndarray:
    """Relative Strength Index."""
    if len(values) < period + 1:
        return np.full(len(values), np.nan)

    # Calculate price changes
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    result = np.full(len(values), np.nan)

    # Initial average
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    # Smoothed average
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return result


def _macd(
    values: np.ndarray, fast: int, slow: int, signal: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD: line, signal, histogram."""
    fast_ema = _ema(values, fast)
    slow_ema = _ema(values, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger_bands(
    values: np.ndarray, period: int, std_mult: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands: upper, middle, lower."""
    middle = _sma(values, period)

    # Calculate rolling standard deviation
    std = np.full(len(values), np.nan)
    for i in range(period - 1, len(values)):
        std[i] = np.std(values[i - period + 1 : i + 1], ddof=0)

    upper = middle + std_mult * std
    lower = middle - std_mult * std

    return upper, middle, lower


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Average True Range."""
    if len(close) < 2:
        return np.full(len(close), np.nan)

    # True Range
    tr = np.zeros(len(close))
    tr[0] = high[0] - low[0]

    for i in range(1, len(close)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    # Smoothed average
    return _sma(tr, period)


def _adx(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ADX: value, plus_di, minus_di."""
    if len(close) < period + 1:
        return (
            np.full(len(close), np.nan),
            np.full(len(close), np.nan),
            np.full(len(close), np.nan),
        )

    # Directional Movement
    plus_dm = np.zeros(len(close))
    minus_dm = np.zeros(len(close))

    for i in range(1, len(close)):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]

        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    # True Range
    tr = np.zeros(len(close))
    tr[0] = high[0] - low[0]
    for i in range(1, len(close)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    # Smooth with EMA-like method
    atr_smooth = _sma(tr, period)
    plus_dm_smooth = _sma(plus_dm, period)
    minus_dm_smooth = _sma(minus_dm, period)

    # DI calculation
    plus_di = np.full(len(close), np.nan)
    minus_di = np.full(len(close), np.nan)

    for i in range(period - 1, len(close)):
        if atr_smooth[i] != 0:
            plus_di[i] = 100 * plus_dm_smooth[i] / atr_smooth[i]
            minus_di[i] = 100 * minus_dm_smooth[i] / atr_smooth[i]

    # DX and ADX
    dx = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        if plus_di[i] is not np.nan and minus_di[i] is not np.nan:
            di_sum = plus_di[i] + minus_di[i]
            if di_sum != 0:
                dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum

    adx = _sma(dx, period)

    return adx, plus_di, minus_di


def _stochastic(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, k_period: int, d_period: int, smooth: int
) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic: %K, %D."""
    if len(close) < k_period:
        return np.full(len(close), np.nan), np.full(len(close), np.nan)

    # Raw %K
    raw_k = np.full(len(close), np.nan)
    for i in range(k_period - 1, len(close)):
        highest = np.max(high[i - k_period + 1 : i + 1])
        lowest = np.min(low[i - k_period + 1 : i + 1])
        if highest != lowest:
            raw_k[i] = 100 * (close[i] - lowest) / (highest - lowest)
        else:
            raw_k[i] = 50.0  # Midpoint if no range

    # Smoothed %K
    k = _sma(raw_k, smooth)

    # %D is SMA of %K
    d = _sma(k, d_period)

    return k, d


def _cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Commodity Channel Index."""
    # Typical Price
    tp = (high + low + close) / 3.0

    # SMA of typical price
    tp_sma = _sma(tp, period)

    # Mean Deviation
    mad = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        mad[i] = np.mean(np.abs(tp[i - period + 1 : i + 1] - tp_sma[i]))

    # CCI
    cci_val = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        if mad[i] != 0:
            cci_val[i] = (tp[i] - tp_sma[i]) / (0.015 * mad[i])

    return cci_val


def _williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Williams %R."""
    if len(close) < period:
        return np.full(len(close), np.nan)

    result = np.full(len(close), np.nan)
    for i in range(period - 1, len(close)):
        highest = np.max(high[i - period + 1 : i + 1])
        lowest = np.min(low[i - period + 1 : i + 1])
        if highest != lowest:
            result[i] = -100 * (highest - close[i]) / (highest - lowest)
        else:
            result[i] = -50.0

    return result


def _obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """On-Balance Volume."""
    obv_val = np.zeros(len(close))
    obv_val[0] = volume[0]

    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv_val[i] = obv_val[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv_val[i] = obv_val[i - 1] - volume[i]
        else:
            obv_val[i] = obv_val[i - 1]

    return obv_val


def _mfi(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, period: int
) -> np.ndarray:
    """Money Flow Index."""
    # Typical Price
    tp = (high + low + close) / 3.0

    # Money Flow
    mf = tp * volume

    # Positive and Negative Money Flow
    pos_mf = np.zeros(len(close))
    neg_mf = np.zeros(len(close))

    for i in range(1, len(close)):
        if tp[i] > tp[i - 1]:
            pos_mf[i] = mf[i]
        elif tp[i] < tp[i - 1]:
            neg_mf[i] = mf[i]

    # Sum over period
    result = np.full(len(close), np.nan)
    for i in range(period, len(close)):
        pos_sum = np.sum(pos_mf[i - period + 1 : i + 1])
        neg_sum = np.sum(neg_mf[i - period + 1 : i + 1])

        if neg_sum == 0:
            result[i] = 100.0
        else:
            mf_ratio = pos_sum / neg_sum
            result[i] = 100.0 - (100.0 / (1.0 + mf_ratio))

    return result


def _vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """Volume Weighted Average Price (cumulative)."""
    tp = (high + low + close) / 3.0
    cumulative_tp_volume = np.cumsum(tp * volume)
    cumulative_volume = np.cumsum(volume)

    # Avoid division by zero
    with np.errstate(divide="ignore", invalid="ignore"):
        vwap_val = np.where(
            cumulative_volume != 0, cumulative_tp_volume / cumulative_volume, np.nan
        )

    return vwap_val


def _keltner(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    ema_period: int,
    atr_mult: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Keltner Channel: upper, middle, lower."""
    middle = _ema(close, ema_period)
    atr = _atr(high, low, close, ema_period)

    upper = middle + atr_mult * atr
    lower = middle - atr_mult * atr

    return upper, middle, lower


def _donchian(high: np.ndarray, low: np.ndarray, period: int) -> tuple[np.ndarray, np.ndarray]:
    """Donchian Channel: upper, lower."""
    if len(high) < period:
        return np.full(len(high), np.nan), np.full(len(high), np.nan)

    upper = np.full(len(high), np.nan)
    lower = np.full(len(high), np.nan)

    for i in range(period - 1, len(high)):
        upper[i] = np.max(high[i - period + 1 : i + 1])
        lower[i] = np.min(low[i - period + 1 : i + 1])

    return upper, lower


def _stddev(values: np.ndarray, period: int) -> np.ndarray:
    """Rolling Standard Deviation."""
    if len(values) < period:
        return np.full(len(values), np.nan)

    result = np.full(len(values), np.nan)
    for i in range(period - 1, len(values)):
        result[i] = np.std(values[i - period + 1 : i + 1], ddof=0)

    return result


def _momentum(values: np.ndarray, period: int) -> np.ndarray:
    """Price Momentum (difference from n periods ago)."""
    if len(values) < period + 1:
        return np.full(len(values), np.nan)

    result = np.full(len(values), np.nan)
    result[period:] = values[period:] - values[:-period]

    return result


def compute_indicator(spec: IndicatorSpec, prices: PriceData) -> dict[str, np.ndarray]:
    """Compute a single indicator.

    Args:
        spec: The indicator specification
        prices: OHLCV price data

    Returns:
        Dictionary mapping output keys to computed arrays
    """
    results: dict[str, np.ndarray] = {}

    indicator_type = spec.indicator_type
    params = spec.params

    if indicator_type == "sma":
        source = prices.get_source(spec.source)
        period = int(params[0]) if params else 20
        value = _sma(source, period)
        results[spec.output_key] = value

    elif indicator_type == "ema":
        source = prices.get_source(spec.source)
        period = int(params[0]) if params else 20
        value = _ema(source, period)
        results[spec.output_key] = value

    elif indicator_type == "rsi":
        source = prices.get_source(spec.source)
        period = int(params[0]) if params else 14
        value = _rsi(source, period)
        results[spec.output_key] = value

    elif indicator_type == "macd":
        source = prices.get_source(spec.source)
        fast = int(params[0]) if len(params) > 0 else 12
        slow = int(params[1]) if len(params) > 1 else 26
        signal = int(params[2]) if len(params) > 2 else 9
        line, sig, hist = _macd(source, fast, slow, signal)

        # Store all outputs with base key
        base_key = f"macd_{spec.source}_{fast}_{slow}_{signal}"
        results[f"{base_key}_line"] = line
        results[f"{base_key}_signal"] = sig
        results[f"{base_key}_histogram"] = hist

        # Also store the specific output requested
        if spec.output_field == "line":
            results[spec.output_key] = line
        elif spec.output_field == "signal":
            results[spec.output_key] = sig
        elif spec.output_field == "histogram":
            results[spec.output_key] = hist

    elif indicator_type == "bbands":
        source = prices.get_source(spec.source)
        period = int(params[0]) if len(params) > 0 else 20
        std_mult = float(params[1]) if len(params) > 1 else 2.0
        upper, middle, lower = _bollinger_bands(source, period, std_mult)

        base_key = f"bbands_{spec.source}_{period}_{std_mult}"
        results[f"{base_key}_upper"] = upper
        results[f"{base_key}_middle"] = middle
        results[f"{base_key}_lower"] = lower

        if spec.output_field == "upper":
            results[spec.output_key] = upper
        elif spec.output_field == "middle":
            results[spec.output_key] = middle
        elif spec.output_field == "lower":
            results[spec.output_key] = lower

    elif indicator_type == "atr":
        period = int(params[0]) if params else 14
        value = _atr(prices.high, prices.low, prices.close, period)
        results[spec.output_key] = value

    elif indicator_type == "adx":
        period = int(params[0]) if params else 14
        adx, plus_di, minus_di = _adx(prices.high, prices.low, prices.close, period)

        base_key = f"adx_{spec.source}_{period}"
        results[f"{base_key}_value"] = adx
        results[f"{base_key}_plus_di"] = plus_di
        results[f"{base_key}_minus_di"] = minus_di

        if spec.output_field == "value" or spec.output_field is None:
            results[spec.output_key] = adx
        elif spec.output_field == "plus_di":
            results[spec.output_key] = plus_di
        elif spec.output_field == "minus_di":
            results[spec.output_key] = minus_di

    elif indicator_type == "stoch":
        k_period = int(params[0]) if len(params) > 0 else 14
        d_period = int(params[1]) if len(params) > 1 else 3
        smooth = int(params[2]) if len(params) > 2 else 3
        k, d = _stochastic(prices.high, prices.low, prices.close, k_period, d_period, smooth)

        base_key = f"stoch_{spec.source}_{k_period}_{d_period}_{smooth}"
        results[f"{base_key}_k"] = k
        results[f"{base_key}_d"] = d

        if spec.output_field == "k":
            results[spec.output_key] = k
        elif spec.output_field == "d":
            results[spec.output_key] = d

    elif indicator_type == "cci":
        period = int(params[0]) if params else 20
        value = _cci(prices.high, prices.low, prices.close, period)
        results[spec.output_key] = value

    elif indicator_type == "williams-r":
        period = int(params[0]) if params else 14
        value = _williams_r(prices.high, prices.low, prices.close, period)
        results[spec.output_key] = value

    elif indicator_type == "obv":
        value = _obv(prices.close, prices.volume.astype(float))
        results[spec.output_key] = value

    elif indicator_type == "mfi":
        period = int(params[0]) if params else 14
        value = _mfi(prices.high, prices.low, prices.close, prices.volume.astype(float), period)
        results[spec.output_key] = value

    elif indicator_type == "vwap":
        value = _vwap(prices.high, prices.low, prices.close, prices.volume.astype(float))
        results[spec.output_key] = value

    elif indicator_type == "keltner":
        ema_period = int(params[0]) if len(params) > 0 else 20
        atr_mult = float(params[1]) if len(params) > 1 else 2.0
        upper, middle, lower = _keltner(prices.high, prices.low, prices.close, ema_period, atr_mult)

        base_key = f"keltner_{spec.source}_{ema_period}_{atr_mult}"
        results[f"{base_key}_upper"] = upper
        results[f"{base_key}_middle"] = middle
        results[f"{base_key}_lower"] = lower

        if spec.output_field == "upper":
            results[spec.output_key] = upper
        elif spec.output_field == "middle":
            results[spec.output_key] = middle
        elif spec.output_field == "lower":
            results[spec.output_key] = lower

    elif indicator_type == "donchian":
        period = int(params[0]) if params else 20
        upper, lower = _donchian(prices.high, prices.low, period)

        base_key = f"donchian_{spec.source}_{period}"
        results[f"{base_key}_upper"] = upper
        results[f"{base_key}_lower"] = lower

        if spec.output_field == "upper":
            results[spec.output_key] = upper
        elif spec.output_field == "lower":
            results[spec.output_key] = lower

    elif indicator_type == "stddev":
        source = prices.get_source(spec.source)
        period = int(params[0]) if params else 20
        value = _stddev(source, period)
        results[spec.output_key] = value

    elif indicator_type == "momentum":
        source = prices.get_source(spec.source)
        period = int(params[0]) if params else 10
        value = _momentum(source, period)
        results[spec.output_key] = value

    return results


def compute_all_indicators(
    indicators: list[IndicatorSpec], prices: PriceData
) -> dict[str, np.ndarray]:
    """Compute all indicators for a strategy.

    Args:
        indicators: List of indicator specifications
        prices: OHLCV price data

    Returns:
        Dictionary mapping output keys to computed arrays
    """
    all_results: dict[str, np.ndarray] = {}

    for spec in indicators:
        results = compute_indicator(spec, prices)
        all_results.update(results)

    return all_results
