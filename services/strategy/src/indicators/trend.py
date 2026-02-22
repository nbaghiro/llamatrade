"""Trend indicators - SMA, EMA, MACD, ADX."""

import numpy as np


class SMA:
    """Simple Moving Average indicator."""

    def __init__(self, period: int = 20):
        self.period = period

    def calculate(self, prices: np.ndarray) -> np.ndarray:
        """Calculate SMA values."""
        if len(prices) < self.period:
            return np.full(len(prices), np.nan)

        sma = np.convolve(prices, np.ones(self.period) / self.period, mode="valid")
        # Pad with NaN for the initial period
        return np.concatenate([np.full(self.period - 1, np.nan), sma])


class EMA:
    """Exponential Moving Average indicator."""

    def __init__(self, period: int = 20):
        self.period = period
        self.multiplier = 2 / (period + 1)

    def calculate(self, prices: np.ndarray) -> np.ndarray:
        """Calculate EMA values."""
        if len(prices) < self.period:
            return np.full(len(prices), np.nan)

        ema = np.zeros(len(prices))
        ema[:] = np.nan

        # First EMA is SMA
        ema[self.period - 1] = np.mean(prices[: self.period])

        # Calculate rest using EMA formula
        for i in range(self.period, len(prices)):
            ema[i] = (prices[i] * self.multiplier) + (ema[i - 1] * (1 - self.multiplier))

        return ema


class MACD:
    """Moving Average Convergence Divergence indicator."""

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def calculate(self, prices: np.ndarray) -> dict[str, np.ndarray]:
        """Calculate MACD line, signal line, and histogram."""
        fast_ema = EMA(self.fast_period).calculate(prices)
        slow_ema = EMA(self.slow_period).calculate(prices)

        macd_line = fast_ema - slow_ema

        # Calculate signal line (EMA of MACD line)
        # Need to handle NaN values
        valid_start = self.slow_period - 1
        signal_line = np.full(len(prices), np.nan)

        if len(prices) > valid_start + self.signal_period:
            valid_macd = macd_line[valid_start:]
            signal_ema = EMA(self.signal_period).calculate(valid_macd)
            signal_line[valid_start:] = signal_ema

        histogram = macd_line - signal_line

        return {
            "line": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }


class ADX:
    """Average Directional Index indicator."""

    def __init__(self, period: int = 14):
        self.period = period

    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Calculate ADX, +DI, and -DI."""
        n = len(close)

        if n < self.period + 1:
            return {
                "value": np.full(n, np.nan),
                "plus_di": np.full(n, np.nan),
                "minus_di": np.full(n, np.nan),
            }

        # Calculate True Range
        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))

        # Calculate +DM and -DM
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        # Smooth using Wilder's smoothing (similar to EMA)
        atr = self._wilder_smooth(tr, self.period)
        smooth_plus_dm = self._wilder_smooth(plus_dm, self.period)
        smooth_minus_dm = self._wilder_smooth(minus_dm, self.period)

        # Calculate +DI and -DI
        plus_di = 100 * smooth_plus_dm / atr
        minus_di = 100 * smooth_minus_dm / atr

        # Calculate DX and ADX
        di_diff = np.abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        dx = 100 * di_diff / np.where(di_sum != 0, di_sum, 1)
        adx = self._wilder_smooth(dx, self.period)

        # Pad results to match input length
        pad = np.full(1, np.nan)
        return {
            "value": np.concatenate([pad, adx]),
            "plus_di": np.concatenate([pad, plus_di]),
            "minus_di": np.concatenate([pad, minus_di]),
        }

    def _wilder_smooth(self, values: np.ndarray, period: int) -> np.ndarray:
        """Apply Wilder's smoothing method."""
        result = np.zeros(len(values))
        result[:period] = np.nan

        if len(values) >= period:
            result[period - 1] = np.mean(values[:period])
            for i in range(period, len(values)):
                result[i] = (result[i - 1] * (period - 1) + values[i]) / period

        return result
