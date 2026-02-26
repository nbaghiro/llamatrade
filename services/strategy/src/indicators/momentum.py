"""Momentum indicators - RSI, Stochastic, CCI, Williams %R."""

import numpy as np


class RSI:
    """Relative Strength Index indicator."""

    def __init__(self, period: int = 14):
        self.period = period

    def calculate(self, prices: np.ndarray) -> np.ndarray:
        """Calculate RSI values (0-100)."""
        if len(prices) < self.period + 1:
            return np.full(len(prices), np.nan)

        # Calculate price changes
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate average gain and loss using Wilder's smoothing
        avg_gain = np.zeros(len(deltas))
        avg_loss = np.zeros(len(deltas))

        # First average
        avg_gain[self.period - 1] = np.mean(gains[: self.period])
        avg_loss[self.period - 1] = np.mean(losses[: self.period])

        # Subsequent averages using smoothing
        for i in range(self.period, len(deltas)):
            avg_gain[i] = (avg_gain[i - 1] * (self.period - 1) + gains[i]) / self.period
            avg_loss[i] = (avg_loss[i - 1] * (self.period - 1) + losses[i]) / self.period

        # Calculate RS and RSI
        rs = np.where(avg_loss != 0, avg_gain / avg_loss, 100)
        rsi = 100 - (100 / (1 + rs))

        # Set initial values to NaN
        rsi[: self.period - 1] = np.nan

        # Prepend NaN to match original price length
        return np.concatenate([[np.nan], rsi])


class Stochastic:
    """Stochastic Oscillator indicator."""

    def __init__(self, k_period: int = 14, d_period: int = 3, smooth_k: int = 3):
        self.k_period = k_period
        self.d_period = d_period
        self.smooth_k = smooth_k

    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Calculate %K and %D values."""
        n = len(close)

        if n < self.k_period:
            return {
                "k": np.full(n, np.nan),
                "d": np.full(n, np.nan),
            }

        # Calculate raw %K
        raw_k = np.full(n, np.nan)
        for i in range(self.k_period - 1, n):
            highest_high = np.max(high[i - self.k_period + 1 : i + 1])
            lowest_low = np.min(low[i - self.k_period + 1 : i + 1])
            if highest_high != lowest_low:
                raw_k[i] = 100 * (close[i] - lowest_low) / (highest_high - lowest_low)
            else:
                raw_k[i] = 50

        # Smooth %K
        k = self._sma(raw_k, self.smooth_k)

        # Calculate %D (SMA of %K)
        d = self._sma(k, self.d_period)

        return {"k": k, "d": d}

    def _sma(self, values: np.ndarray, period: int) -> np.ndarray:
        """Calculate SMA handling NaN values."""
        result = np.full(len(values), np.nan)
        for i in range(len(values)):
            if i >= period - 1:
                window = values[i - period + 1 : i + 1]
                if not np.any(np.isnan(window)):
                    result[i] = np.mean(window)
        return result


class CCI:
    """Commodity Channel Index indicator."""

    def __init__(self, period: int = 20):
        self.period = period
        self.constant = 0.015

    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> np.ndarray:
        """Calculate CCI values."""
        n = len(close)

        if n < self.period:
            return np.full(n, np.nan)

        # Calculate Typical Price
        tp = (high + low + close) / 3

        # Calculate SMA of TP
        sma_tp = np.full(n, np.nan)
        for i in range(self.period - 1, n):
            sma_tp[i] = np.mean(tp[i - self.period + 1 : i + 1])

        # Calculate Mean Deviation
        mean_dev = np.full(n, np.nan)
        for i in range(self.period - 1, n):
            mean_dev[i] = np.mean(np.abs(tp[i - self.period + 1 : i + 1] - sma_tp[i]))

        # Calculate CCI
        cci: np.ndarray = (tp - sma_tp) / (self.constant * mean_dev)

        return cci


class WilliamsR:
    """Williams %R indicator."""

    def __init__(self, period: int = 14):
        self.period = period

    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> np.ndarray:
        """Calculate Williams %R values (-100 to 0)."""
        n = len(close)

        if n < self.period:
            return np.full(n, np.nan)

        williams_r = np.full(n, np.nan)

        for i in range(self.period - 1, n):
            highest_high = np.max(high[i - self.period + 1 : i + 1])
            lowest_low = np.min(low[i - self.period + 1 : i + 1])

            if highest_high != lowest_low:
                williams_r[i] = -100 * (highest_high - close[i]) / (highest_high - lowest_low)
            else:
                williams_r[i] = -50

        return williams_r
