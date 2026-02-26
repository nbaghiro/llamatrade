"""Indicator service - indicator metadata and information."""

from src.models import IndicatorInfoResponse, IndicatorParamInfo, IndicatorType


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
INDICATORS: dict[IndicatorType, IndicatorInfoResponse] = {
    IndicatorType.SMA: IndicatorInfoResponse(
        type=IndicatorType.SMA,
        name="Simple Moving Average",
        description="Average price over a specified period",
        category="trend",
        params=[_param("period", "int", 20, 1, 500, "Lookback period")],
        outputs=["value"],
    ),
    IndicatorType.EMA: IndicatorInfoResponse(
        type=IndicatorType.EMA,
        name="Exponential Moving Average",
        description="Weighted average giving more weight to recent prices",
        category="trend",
        params=[_param("period", "int", 20, 1, 500, "Lookback period")],
        outputs=["value"],
    ),
    IndicatorType.MACD: IndicatorInfoResponse(
        type=IndicatorType.MACD,
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
    IndicatorType.ADX: IndicatorInfoResponse(
        type=IndicatorType.ADX,
        name="Average Directional Index",
        description="Measures trend strength regardless of direction",
        category="trend",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value", "plus_di", "minus_di"],
    ),
    IndicatorType.RSI: IndicatorInfoResponse(
        type=IndicatorType.RSI,
        name="Relative Strength Index",
        description="Momentum oscillator measuring speed and magnitude of price changes (0-100)",
        category="momentum",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    IndicatorType.STOCHASTIC: IndicatorInfoResponse(
        type=IndicatorType.STOCHASTIC,
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
    IndicatorType.CCI: IndicatorInfoResponse(
        type=IndicatorType.CCI,
        name="Commodity Channel Index",
        description="Measures deviation from statistical mean",
        category="momentum",
        params=[_param("period", "int", 20, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    IndicatorType.WILLIAMS_R: IndicatorInfoResponse(
        type=IndicatorType.WILLIAMS_R,
        name="Williams %R",
        description="Momentum indicator showing overbought/oversold levels",
        category="momentum",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    IndicatorType.BOLLINGER_BANDS: IndicatorInfoResponse(
        type=IndicatorType.BOLLINGER_BANDS,
        name="Bollinger Bands",
        description="Volatility bands placed above and below a moving average",
        category="volatility",
        params=[
            _param("period", "int", 20, 1, 200, "Moving average period"),
            _param("std_dev", "float", 2.0, 0.5, 5.0, "Standard deviation multiplier"),
        ],
        outputs=["upper", "middle", "lower"],
    ),
    IndicatorType.ATR: IndicatorInfoResponse(
        type=IndicatorType.ATR,
        name="Average True Range",
        description="Measures market volatility",
        category="volatility",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    IndicatorType.KELTNER_CHANNEL: IndicatorInfoResponse(
        type=IndicatorType.KELTNER_CHANNEL,
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
    IndicatorType.OBV: IndicatorInfoResponse(
        type=IndicatorType.OBV,
        name="On-Balance Volume",
        description="Cumulative volume indicator relating volume to price changes",
        category="volume",
        params=[],
        outputs=["value"],
    ),
    IndicatorType.MFI: IndicatorInfoResponse(
        type=IndicatorType.MFI,
        name="Money Flow Index",
        description="Volume-weighted RSI (0-100)",
        category="volume",
        params=[_param("period", "int", 14, 1, 100, "Lookback period")],
        outputs=["value"],
    ),
    IndicatorType.VWAP: IndicatorInfoResponse(
        type=IndicatorType.VWAP,
        name="Volume Weighted Average Price",
        description="Average price weighted by volume (intraday)",
        category="volume",
        params=[],
        outputs=["value"],
    ),
    IndicatorType.DONCHIAN_CHANNEL: IndicatorInfoResponse(
        type=IndicatorType.DONCHIAN_CHANNEL,
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
        indicator_type: IndicatorType,
    ) -> IndicatorInfoResponse | None:
        """Get indicator information."""
        return INDICATORS.get(indicator_type)

    async def list_categories(self) -> list[str]:
        """List indicator categories."""
        return CATEGORIES


def get_indicator_service() -> IndicatorService:
    """Dependency to get indicator service."""
    return IndicatorService()
