"""Indicator service - indicator metadata and information."""

from typing import Any

from src.models import IndicatorType

# Indicator metadata
INDICATORS: dict[IndicatorType, dict[str, Any]] = {
    IndicatorType.SMA: {
        "type": IndicatorType.SMA,
        "name": "Simple Moving Average",
        "description": "Average price over a specified period",
        "category": "trend",
        "params": [
            {"name": "period", "type": "int", "default": 20, "min": 1, "max": 500},
        ],
        "outputs": ["value"],
    },
    IndicatorType.EMA: {
        "type": IndicatorType.EMA,
        "name": "Exponential Moving Average",
        "description": "Weighted average giving more weight to recent prices",
        "category": "trend",
        "params": [
            {"name": "period", "type": "int", "default": 20, "min": 1, "max": 500},
        ],
        "outputs": ["value"],
    },
    IndicatorType.MACD: {
        "type": IndicatorType.MACD,
        "name": "Moving Average Convergence Divergence",
        "description": "Trend-following momentum indicator showing relationship between two EMAs",
        "category": "trend",
        "params": [
            {"name": "fast_period", "type": "int", "default": 12, "min": 1, "max": 100},
            {"name": "slow_period", "type": "int", "default": 26, "min": 1, "max": 200},
            {"name": "signal_period", "type": "int", "default": 9, "min": 1, "max": 50},
        ],
        "outputs": ["line", "signal", "histogram"],
    },
    IndicatorType.ADX: {
        "type": IndicatorType.ADX,
        "name": "Average Directional Index",
        "description": "Measures trend strength regardless of direction",
        "category": "trend",
        "params": [
            {"name": "period", "type": "int", "default": 14, "min": 1, "max": 100},
        ],
        "outputs": ["value", "plus_di", "minus_di"],
    },
    IndicatorType.RSI: {
        "type": IndicatorType.RSI,
        "name": "Relative Strength Index",
        "description": "Momentum oscillator measuring speed and magnitude of price changes (0-100)",
        "category": "momentum",
        "params": [
            {"name": "period", "type": "int", "default": 14, "min": 1, "max": 100},
        ],
        "outputs": ["value"],
    },
    IndicatorType.STOCHASTIC: {
        "type": IndicatorType.STOCHASTIC,
        "name": "Stochastic Oscillator",
        "description": "Compares closing price to price range over a period",
        "category": "momentum",
        "params": [
            {"name": "k_period", "type": "int", "default": 14, "min": 1, "max": 100},
            {"name": "d_period", "type": "int", "default": 3, "min": 1, "max": 50},
            {"name": "smooth_k", "type": "int", "default": 3, "min": 1, "max": 50},
        ],
        "outputs": ["k", "d"],
    },
    IndicatorType.CCI: {
        "type": IndicatorType.CCI,
        "name": "Commodity Channel Index",
        "description": "Measures deviation from statistical mean",
        "category": "momentum",
        "params": [
            {"name": "period", "type": "int", "default": 20, "min": 1, "max": 100},
        ],
        "outputs": ["value"],
    },
    IndicatorType.WILLIAMS_R: {
        "type": IndicatorType.WILLIAMS_R,
        "name": "Williams %R",
        "description": "Momentum indicator showing overbought/oversold levels",
        "category": "momentum",
        "params": [
            {"name": "period", "type": "int", "default": 14, "min": 1, "max": 100},
        ],
        "outputs": ["value"],
    },
    IndicatorType.BOLLINGER_BANDS: {
        "type": IndicatorType.BOLLINGER_BANDS,
        "name": "Bollinger Bands",
        "description": "Volatility bands placed above and below a moving average",
        "category": "volatility",
        "params": [
            {"name": "period", "type": "int", "default": 20, "min": 1, "max": 200},
            {"name": "std_dev", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0},
        ],
        "outputs": ["upper", "middle", "lower"],
    },
    IndicatorType.ATR: {
        "type": IndicatorType.ATR,
        "name": "Average True Range",
        "description": "Measures market volatility",
        "category": "volatility",
        "params": [
            {"name": "period", "type": "int", "default": 14, "min": 1, "max": 100},
        ],
        "outputs": ["value"],
    },
    IndicatorType.KELTNER_CHANNEL: {
        "type": IndicatorType.KELTNER_CHANNEL,
        "name": "Keltner Channel",
        "description": "Volatility-based envelope around an EMA",
        "category": "volatility",
        "params": [
            {"name": "ema_period", "type": "int", "default": 20, "min": 1, "max": 200},
            {"name": "atr_period", "type": "int", "default": 10, "min": 1, "max": 100},
            {"name": "multiplier", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0},
        ],
        "outputs": ["upper", "middle", "lower"],
    },
    IndicatorType.OBV: {
        "type": IndicatorType.OBV,
        "name": "On-Balance Volume",
        "description": "Cumulative volume indicator relating volume to price changes",
        "category": "volume",
        "params": [],
        "outputs": ["value"],
    },
    IndicatorType.MFI: {
        "type": IndicatorType.MFI,
        "name": "Money Flow Index",
        "description": "Volume-weighted RSI (0-100)",
        "category": "volume",
        "params": [
            {"name": "period", "type": "int", "default": 14, "min": 1, "max": 100},
        ],
        "outputs": ["value"],
    },
    IndicatorType.VWAP: {
        "type": IndicatorType.VWAP,
        "name": "Volume Weighted Average Price",
        "description": "Average price weighted by volume (intraday)",
        "category": "volume",
        "params": [],
        "outputs": ["value"],
    },
    IndicatorType.DONCHIAN_CHANNEL: {
        "type": IndicatorType.DONCHIAN_CHANNEL,
        "name": "Donchian Channel",
        "description": "Highest high and lowest low over a period",
        "category": "channel",
        "params": [
            {"name": "period", "type": "int", "default": 20, "min": 1, "max": 200},
        ],
        "outputs": ["upper", "middle", "lower"],
    },
}

CATEGORIES = ["trend", "momentum", "volatility", "volume", "channel"]


class IndicatorService:
    """Service for indicator metadata operations."""

    async def list_indicators(
        self,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """List available indicators."""
        indicators = list(INDICATORS.values())

        if category:
            indicators = [i for i in indicators if i["category"] == category]

        return indicators

    async def get_indicator(
        self,
        indicator_type: IndicatorType,
    ) -> dict[str, Any] | None:
        """Get indicator information."""
        return INDICATORS.get(indicator_type)

    async def list_categories(self) -> list[str]:
        """List indicator categories."""
        return CATEGORIES


def get_indicator_service() -> IndicatorService:
    """Dependency to get indicator service."""
    return IndicatorService()
