"""Indicator service - indicator metadata and information."""

from llamatrade_proto.generated.strategy_pb2 import (
    INDICATOR_TYPE_ADX,
    INDICATOR_TYPE_ATR,
    INDICATOR_TYPE_BOLLINGER_BANDS,
    INDICATOR_TYPE_CCI,
    INDICATOR_TYPE_DONCHIAN_CHANNEL,
    INDICATOR_TYPE_EMA,
    INDICATOR_TYPE_KELTNER_CHANNEL,
    INDICATOR_TYPE_MACD,
    INDICATOR_TYPE_MFI,
    INDICATOR_TYPE_OBV,
    INDICATOR_TYPE_RSI,
    INDICATOR_TYPE_SMA,
    INDICATOR_TYPE_STOCHASTIC,
    INDICATOR_TYPE_VWAP,
    INDICATOR_TYPE_WILLIAMS_R,
    IndicatorType,
)

from src.models import IndicatorInfoResponse, IndicatorParamInfo


def _param(
    name: str,
    param_type: str,
    default: int | float | str | None,
    min_val: int | float | None = None,
    max_val: int | float | None = None,
    description: str = "",
) -> IndicatorParamInfo:
    """Helper to create typed indicator parameter info."""
    return IndicatorParamInfo(
        name=name,
        type=param_type,
        default=default,
        min=min_val,
        max=max_val,
        description=description,
    )


# Indicator metadata as properly typed IndicatorInfoResponse objects
INDICATORS: dict[IndicatorType.ValueType, IndicatorInfoResponse] = {
    INDICATOR_TYPE_SMA: IndicatorInfoResponse(
        type=INDICATOR_TYPE_SMA,
        name="Simple Moving Average",
        description="Average price over a specified period",
        category="trend",
        params=[_param("period", "int", 20, 1, 500, "Lookback period")],
        outputs=["value"],
    ),
    INDICATOR_TYPE_EMA: IndicatorInfoResponse(
        type=INDICATOR_TYPE_EMA,
        name="Exponential Moving Average",
        description="Weighted average giving more weight to recent prices",
        category="trend",
        params=[_param("period", "int", 20, 1, 500, "Lookback period")],
        outputs=["value"],
    ),
    INDICATOR_TYPE_MACD: IndicatorInfoResponse(
        type=INDICATOR_TYPE_MACD,
        name="Moving Average Convergence Divergence",
        description="Trend-following momentum indicator showing relationship between two EMAs",
        category="trend",
        params=[
            _param("fast_period", "int", 12, 1, 100, "Fast EMA period"),
            _param("slow_period", "int", 26, 1, 200, "Slow EMA period"),
            _param("signal_period", "int", 9, 1, 50, "Signal line period"),
        ],
        outputs=["line", "signal", "histogram"],
    ),
    INDICATOR_TYPE_ADX: IndicatorInfoResponse(
        type=INDICATOR_TYPE_ADX,
        name="Average Directional Index",
        description="Measures trend strength regardless of direction",
        category="trend",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value", "plus_di", "minus_di"],
    ),
    INDICATOR_TYPE_RSI: IndicatorInfoResponse(
        type=INDICATOR_TYPE_RSI,
        name="Relative Strength Index",
        description="Momentum oscillator measuring speed and magnitude of price changes (0-100)",
        category="momentum",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    INDICATOR_TYPE_STOCHASTIC: IndicatorInfoResponse(
        type=INDICATOR_TYPE_STOCHASTIC,
        name="Stochastic Oscillator",
        description="Compares closing price to price range over a period",
        category="momentum",
        params=[
            _param("k_period", "int", 14, 1, 100, "%K lookback period"),
            _param("d_period", "int", 3, 1, 50, "%D smoothing period"),
            _param("smooth_k", "int", 3, 1, 50, "%K smoothing factor"),
        ],
        outputs=["k", "d"],
    ),
    INDICATOR_TYPE_CCI: IndicatorInfoResponse(
        type=INDICATOR_TYPE_CCI,
        name="Commodity Channel Index",
        description="Measures deviation from statistical mean",
        category="momentum",
        params=[_param("period", "int", 20, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    INDICATOR_TYPE_WILLIAMS_R: IndicatorInfoResponse(
        type=INDICATOR_TYPE_WILLIAMS_R,
        name="Williams %R",
        description="Momentum indicator showing overbought/oversold levels",
        category="momentum",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    INDICATOR_TYPE_BOLLINGER_BANDS: IndicatorInfoResponse(
        type=INDICATOR_TYPE_BOLLINGER_BANDS,
        name="Bollinger Bands",
        description="Volatility bands placed above and below a moving average",
        category="volatility",
        params=[
            _param("period", "int", 20, 1, 200, "Moving average period"),
            _param("std_dev", "float", 2.0, 0.5, 5.0, "Standard deviation multiplier"),
        ],
        outputs=["upper", "middle", "lower"],
    ),
    INDICATOR_TYPE_ATR: IndicatorInfoResponse(
        type=INDICATOR_TYPE_ATR,
        name="Average True Range",
        description="Measures market volatility",
        category="volatility",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    INDICATOR_TYPE_KELTNER_CHANNEL: IndicatorInfoResponse(
        type=INDICATOR_TYPE_KELTNER_CHANNEL,
        name="Keltner Channel",
        description="Volatility-based envelope around an EMA",
        category="volatility",
        params=[
            _param("ema_period", "int", 20, 1, 200, "EMA period"),
            _param("atr_period", "int", 10, 1, 100, "ATR period"),
            _param("multiplier", "float", 2.0, 0.5, 5.0, "ATR multiplier"),
        ],
        outputs=["upper", "middle", "lower"],
    ),
    INDICATOR_TYPE_OBV: IndicatorInfoResponse(
        type=INDICATOR_TYPE_OBV,
        name="On-Balance Volume",
        description="Cumulative volume indicator relating volume to price changes",
        category="volume",
        params=[],
        outputs=["value"],
    ),
    INDICATOR_TYPE_MFI: IndicatorInfoResponse(
        type=INDICATOR_TYPE_MFI,
        name="Money Flow Index",
        description="Volume-weighted RSI (0-100)",
        category="volume",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    INDICATOR_TYPE_VWAP: IndicatorInfoResponse(
        type=INDICATOR_TYPE_VWAP,
        name="Volume Weighted Average Price",
        description="Average price weighted by volume (intraday)",
        category="volume",
        params=[],
        outputs=["value"],
    ),
    INDICATOR_TYPE_DONCHIAN_CHANNEL: IndicatorInfoResponse(
        type=INDICATOR_TYPE_DONCHIAN_CHANNEL,
        name="Donchian Channel",
        description="Highest high and lowest low over a period",
        category="channel",
        params=[_param("period", "int", 20, 1, 200, "Lookback period")],
        outputs=["upper", "middle", "lower"],
    ),
}

CATEGORIES = ["trend", "momentum", "volatility", "volume", "channel"]


class IndicatorService:
    """Service for indicator metadata operations."""

    async def list_indicators(
        self,
        category: str | None = None,
    ) -> list[IndicatorInfoResponse]:
        """List available indicators."""
        indicators = list(INDICATORS.values())

        if category:
            indicators = [i for i in indicators if i.category == category]

        return indicators

    async def get_indicator(
        self,
        indicator_type: IndicatorType.ValueType,
    ) -> IndicatorInfoResponse | None:
        """Get indicator information."""
        return INDICATORS.get(indicator_type)

    async def list_categories(self) -> list[str]:
        """List indicator categories."""
        return CATEGORIES


def get_indicator_service() -> IndicatorService:
    """Dependency to get indicator service."""
    return IndicatorService()
