"""Evaluation state for allocation strategy condition evaluation."""

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from llamatrade_dsl import Indicator, Metric
from llamatrade_runtime.evaluation.statistics import return_volatility, trailing_return
from llamatrade_runtime.types import Bar


@dataclass
class EvaluationState:
    """
    Runtime state for evaluating allocation strategy conditions.

    Contains all the data needed to evaluate If block conditions:
    - Price data for each symbol
    - Pre-computed indicator values
    - Current bar data for each symbol
    """

    # Current bar data per symbol: {symbol: Bar}
    current_bars: dict[str, Bar] = field(default_factory=lambda: {})

    # Previous bar data per symbol: {symbol: Bar}
    prev_bars: dict[str, Bar] = field(default_factory=lambda: {})

    # Pre-computed indicators: {key: array or float}
    indicators: dict[str, float | NDArray[np.floating]] = field(default_factory=lambda: {})

    # Historical bar data per symbol: {symbol: [Bar, ...]}
    bar_history: dict[str, list[Bar]] = field(default_factory=lambda: {})

    # Count of conditions this bar that could not be meaningfully evaluated
    # (NaN operand, missing data) and were treated as False. Surfaced upward so
    # a degraded run is observable rather than a silent stream of "no signal".
    degraded_evaluations: int = 0

    def get_price(self, symbol: str, price_field: str = "close") -> float:
        """Get current price for a symbol.

        Args:
            symbol: The asset symbol
            price_field: Price field (close, open, high, low, volume)

        Returns:
            The current price value
        """
        if symbol not in self.current_bars:
            raise KeyError(f"No price data for symbol: {symbol}")

        bar = self.current_bars[symbol]
        if price_field == "close":
            return bar.close
        if price_field == "open":
            return bar.open
        if price_field == "high":
            return bar.high
        if price_field == "low":
            return bar.low
        if price_field == "volume":
            return float(bar.volume)

        raise KeyError(f"Unknown price field: {price_field}")

    def get_prev_price(self, symbol: str, price_field: str = "close") -> float:
        """Get previous bar's price for a symbol.

        Args:
            symbol: The asset symbol
            price_field: Price field (close, open, high, low, volume)

        Returns:
            The previous price value
        """
        if symbol not in self.prev_bars:
            raise KeyError(f"No previous price data for symbol: {symbol}")

        bar = self.prev_bars[symbol]
        if price_field == "close":
            return bar.close
        if price_field == "open":
            return bar.open
        if price_field == "high":
            return bar.high
        if price_field == "low":
            return bar.low
        if price_field == "volume":
            return float(bar.volume)

        raise KeyError(f"Unknown price field: {price_field}")

    def get_indicator_value(self, indicator: Indicator) -> float:
        """Get current indicator value.

        Args:
            indicator: The Indicator AST node

        Returns:
            The current indicator value
        """
        key = self._build_indicator_key(indicator)

        if key not in self.indicators:
            # Try without output field
            if indicator.output:
                key_without_output = self._build_indicator_key_base(indicator)
                if key_without_output in self.indicators:
                    key = key_without_output

        if key not in self.indicators:
            raise KeyError(f"Indicator not computed: {key}")

        value = self.indicators[key]
        if isinstance(value, np.ndarray):
            return float(value[-1])
        return float(value)

    def get_prev_indicator_value(self, indicator: Indicator) -> float:
        """Get previous bar's indicator value.

        Args:
            indicator: The Indicator AST node

        Returns:
            The previous indicator value
        """
        key = self._build_indicator_key(indicator)

        if key not in self.indicators:
            if indicator.output:
                key_without_output = self._build_indicator_key_base(indicator)
                if key_without_output in self.indicators:
                    key = key_without_output

        if key not in self.indicators:
            raise KeyError(f"Indicator not computed: {key}")

        value = self.indicators[key]
        if isinstance(value, np.ndarray):
            if len(value) > 1:
                return float(value[-2])
            return float(value[-1])
        return float(value)

    def get_indicator_array(self, key: str) -> np.ndarray:
        """Get full indicator array by key.

        Args:
            key: The indicator cache key

        Returns:
            The indicator array
        """
        if key not in self.indicators:
            raise KeyError(f"Indicator not found: {key}")

        value = self.indicators[key]
        if isinstance(value, np.ndarray):
            return value
        return np.array([value])

    def get_metric_value(self, metric: Metric) -> float:
        """Get a metric value.

        Args:
            metric: The Metric AST node

        Returns:
            The metric value
        """
        if metric.name == "drawdown":
            return self._calculate_drawdown(metric.symbol, metric.period)
        if metric.name == "return":
            return self._calculate_return(metric.symbol, metric.period)
        if metric.name == "volatility":
            return self._calculate_volatility(metric.symbol, metric.period)

        raise KeyError(f"Unknown metric: {metric.name}")

    def _calculate_drawdown(self, symbol: str, period: int | None = None) -> float:
        """Calculate current drawdown from peak."""
        if symbol not in self.bar_history:
            return 0.0

        bars = self.bar_history[symbol]
        if not bars:
            return 0.0

        if period:
            bars = bars[-period:]

        closes = [b.close for b in bars]
        peak = max(closes)
        current = closes[-1]

        if peak == 0:
            return 0.0

        return (peak - current) / peak

    def _calculate_return(self, symbol: str, period: int | None = None) -> float:
        """Return over ``period`` bars, or the full window when unset or history is shorter."""
        bars = self.bar_history.get(symbol, [])
        if len(bars) < 2:
            return 0.0
        if period is not None and len(bars) > period:
            return trailing_return(bars, period)
        start = bars[0].close
        return (bars[-1].close - start) / start if start > 0 else 0.0

    def _calculate_volatility(self, symbol: str, period: int | None = None) -> float:
        """Annualized (×√252) volatility of returns over the (optional) period window."""
        bars = self.bar_history.get(symbol, [])
        if len(bars) < 2:
            return 0.0
        return return_volatility(bars, period) * float(np.sqrt(252))

    def _build_indicator_key(self, indicator: Indicator) -> str:
        """Build cache key for an indicator."""
        parts = [indicator.name, indicator.symbol, "close"]
        parts.extend(str(p) for p in indicator.params)
        if indicator.output:
            parts.append(indicator.output)
        return "_".join(parts)

    def _build_indicator_key_base(self, indicator: Indicator) -> str:
        """Build cache key without output field."""
        parts = [indicator.name, indicator.symbol, "close"]
        parts.extend(str(p) for p in indicator.params)
        return "_".join(parts)

    # Single-bar convenience properties (for single-symbol strategies)

    @property
    def current_bar(self) -> Bar | None:
        """Get first current bar (for single-symbol strategies)."""
        if self.current_bars:
            return next(iter(self.current_bars.values()))
        return None

    @property
    def prev_bar(self) -> Bar | None:
        """Get first previous bar (for single-symbol strategies)."""
        if self.prev_bars:
            return next(iter(self.prev_bars.values()))
        return None
