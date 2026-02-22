"""Volume indicators - OBV, MFI, VWAP."""

import numpy as np


class OBV:
    """On-Balance Volume indicator."""

    def calculate(self, close: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """Calculate OBV values."""
        n = len(close)

        if n < 2:
            return np.array([0] if n == 1 else [])

        obv = np.zeros(n)
        obv[0] = volume[0]

        for i in range(1, n):
            if close[i] > close[i - 1]:
                obv[i] = obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv[i] = obv[i - 1] - volume[i]
            else:
                obv[i] = obv[i - 1]

        return obv


class MFI:
    """Money Flow Index indicator."""

    def __init__(self, period: int = 14):
        self.period = period

    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
    ) -> np.ndarray:
        """Calculate MFI values (0-100)."""
        n = len(close)

        if n < self.period + 1:
            return np.full(n, np.nan)

        # Calculate Typical Price
        tp = (high + low + close) / 3

        # Calculate Raw Money Flow
        raw_mf = tp * volume

        # Determine positive and negative money flow
        positive_mf = np.zeros(n)
        negative_mf = np.zeros(n)

        for i in range(1, n):
            if tp[i] > tp[i - 1]:
                positive_mf[i] = raw_mf[i]
            elif tp[i] < tp[i - 1]:
                negative_mf[i] = raw_mf[i]

        # Calculate MFI
        mfi = np.full(n, np.nan)

        for i in range(self.period, n):
            pos_sum = np.sum(positive_mf[i - self.period + 1 : i + 1])
            neg_sum = np.sum(negative_mf[i - self.period + 1 : i + 1])

            if neg_sum != 0:
                money_ratio = pos_sum / neg_sum
                mfi[i] = 100 - (100 / (1 + money_ratio))
            else:
                mfi[i] = 100

        return mfi


class VWAP:
    """Volume Weighted Average Price indicator."""

    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
    ) -> np.ndarray:
        """Calculate VWAP values.

        Note: VWAP typically resets daily. This implementation
        calculates cumulative VWAP from the start of the data.
        For intraday use, filter data to current day first.
        """
        n = len(close)

        if n < 1:
            return np.array([])

        # Calculate Typical Price
        tp = (high + low + close) / 3

        # Calculate cumulative values
        cum_tp_vol = np.cumsum(tp * volume)
        cum_vol = np.cumsum(volume)

        # Calculate VWAP
        vwap = np.where(cum_vol != 0, cum_tp_vol / cum_vol, np.nan)

        return vwap


class DonchianChannel:
    """Donchian Channel indicator."""

    def __init__(self, period: int = 20):
        self.period = period

    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Calculate upper, middle, and lower channels."""
        n = len(high)

        if n < self.period:
            return {
                "upper": np.full(n, np.nan),
                "middle": np.full(n, np.nan),
                "lower": np.full(n, np.nan),
            }

        upper = np.full(n, np.nan)
        lower = np.full(n, np.nan)

        for i in range(self.period - 1, n):
            upper[i] = np.max(high[i - self.period + 1 : i + 1])
            lower[i] = np.min(low[i - self.period + 1 : i + 1])

        middle = (upper + lower) / 2

        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
        }
