"""Volatility indicators - Bollinger Bands, ATR, Keltner Channel."""

import numpy as np

from src.indicators.trend import EMA, SMA


class BollingerBands:
    """Bollinger Bands indicator."""

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.period = period
        self.std_dev = std_dev

    def calculate(self, prices: np.ndarray) -> dict[str, np.ndarray]:
        """Calculate upper, middle, and lower bands."""
        n = len(prices)

        if n < self.period:
            return {
                "upper": np.full(n, np.nan),
                "middle": np.full(n, np.nan),
                "lower": np.full(n, np.nan),
            }

        # Calculate middle band (SMA)
        middle = SMA(self.period).calculate(prices)

        # Calculate standard deviation
        std = np.full(n, np.nan)
        for i in range(self.period - 1, n):
            std[i] = np.std(prices[i - self.period + 1 : i + 1], ddof=0)

        # Calculate bands
        upper = middle + (self.std_dev * std)
        lower = middle - (self.std_dev * std)

        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
        }


class ATR:
    """Average True Range indicator."""

    def __init__(self, period: int = 14):
        self.period = period

    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> np.ndarray:
        """Calculate ATR values."""
        n = len(close)

        if n < 2:
            return np.full(n, np.nan)

        # Calculate True Range
        tr = np.zeros(n)
        tr[0] = high[0] - low[0]

        for i in range(1, n):
            tr1 = high[i] - low[i]
            tr2 = abs(high[i] - close[i - 1])
            tr3 = abs(low[i] - close[i - 1])
            tr[i] = max(tr1, tr2, tr3)

        # Calculate ATR using Wilder's smoothing
        atr = np.full(n, np.nan)

        if n >= self.period:
            atr[self.period - 1] = np.mean(tr[: self.period])
            for i in range(self.period, n):
                atr[i] = (atr[i - 1] * (self.period - 1) + tr[i]) / self.period

        return atr


class KeltnerChannel:
    """Keltner Channel indicator."""

    def __init__(
        self,
        ema_period: int = 20,
        atr_period: int = 10,
        multiplier: float = 2.0,
    ):
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.multiplier = multiplier

    def calculate(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """Calculate upper, middle, and lower channels."""
        len(close)

        # Calculate middle band (EMA of close)
        middle = EMA(self.ema_period).calculate(close)

        # Calculate ATR
        atr = ATR(self.atr_period).calculate(high, low, close)

        # Calculate channels
        upper = middle + (self.multiplier * atr)
        lower = middle - (self.multiplier * atr)

        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
        }
