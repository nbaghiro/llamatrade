"""Template service - pre-built strategy templates."""

from typing import Any

from src.models import (
    ActionConfig,
    ActionType,
    ConditionConfig,
    ConditionOperator,
    IndicatorConfig,
    IndicatorType,
    RiskConfig,
    StrategyConfig,
    StrategyType,
)

# Pre-built strategy templates
TEMPLATES = {
    "ma_crossover": {
        "id": "ma_crossover",
        "name": "Moving Average Crossover",
        "description": "Classic trend-following strategy using fast and slow EMA crossovers",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "tags": ["trend", "ema", "beginner"],
        "config": StrategyConfig(
            symbols=["AAPL"],
            timeframe="1D",
            indicators=[
                IndicatorConfig(
                    type=IndicatorType.EMA, params={"period": 12}, output_name="fast_ema"
                ),
                IndicatorConfig(
                    type=IndicatorType.EMA, params={"period": 26}, output_name="slow_ema"
                ),
            ],
            entry_conditions=[
                ConditionConfig(
                    left="fast_ema", operator=ConditionOperator.CROSS_ABOVE, right="slow_ema"
                ),
            ],
            exit_conditions=[
                ConditionConfig(
                    left="fast_ema", operator=ConditionOperator.CROSS_BELOW, right="slow_ema"
                ),
            ],
            entry_action=ActionConfig(
                type=ActionType.BUY, quantity_type="percent", quantity_value=10
            ),
            exit_action=ActionConfig(type=ActionType.CLOSE_ALL),
            risk=RiskConfig(stop_loss_percent=5, take_profit_percent=15),
        ),
    },
    "rsi_mean_reversion": {
        "id": "rsi_mean_reversion",
        "name": "RSI Mean Reversion",
        "description": "Buy oversold conditions (RSI < 30), sell overbought (RSI > 70)",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["mean-reversion", "rsi", "intermediate"],
        "config": StrategyConfig(
            symbols=["SPY"],
            timeframe="1D",
            indicators=[
                IndicatorConfig(type=IndicatorType.RSI, params={"period": 14}, output_name="rsi"),
            ],
            entry_conditions=[
                ConditionConfig(left="rsi", operator=ConditionOperator.LESS_THAN, right=30),
            ],
            exit_conditions=[
                ConditionConfig(left="rsi", operator=ConditionOperator.GREATER_THAN, right=70),
            ],
            entry_action=ActionConfig(
                type=ActionType.BUY, quantity_type="percent", quantity_value=10
            ),
            exit_action=ActionConfig(type=ActionType.CLOSE_ALL),
            risk=RiskConfig(stop_loss_percent=3, take_profit_percent=10),
        ),
    },
    "macd_strategy": {
        "id": "macd_strategy",
        "name": "MACD Strategy",
        "description": "Trade MACD line crossovers with the signal line",
        "strategy_type": StrategyType.MOMENTUM,
        "tags": ["momentum", "macd", "beginner"],
        "config": StrategyConfig(
            symbols=["QQQ"],
            timeframe="1D",
            indicators=[
                IndicatorConfig(
                    type=IndicatorType.MACD,
                    params={"fast_period": 12, "slow_period": 26, "signal_period": 9},
                    output_name="macd",
                ),
            ],
            entry_conditions=[
                ConditionConfig(
                    left="macd.line", operator=ConditionOperator.CROSS_ABOVE, right="macd.signal"
                ),
            ],
            exit_conditions=[
                ConditionConfig(
                    left="macd.line", operator=ConditionOperator.CROSS_BELOW, right="macd.signal"
                ),
            ],
            entry_action=ActionConfig(
                type=ActionType.BUY, quantity_type="percent", quantity_value=10
            ),
            exit_action=ActionConfig(type=ActionType.CLOSE_ALL),
            risk=RiskConfig(stop_loss_percent=4, take_profit_percent=12),
        ),
    },
    "bollinger_bounce": {
        "id": "bollinger_bounce",
        "name": "Bollinger Bands Bounce",
        "description": "Mean reversion strategy trading bounces off Bollinger Band boundaries",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["mean-reversion", "bollinger", "intermediate"],
        "config": StrategyConfig(
            symbols=["SPY"],
            timeframe="1H",
            indicators=[
                IndicatorConfig(
                    type=IndicatorType.BOLLINGER_BANDS,
                    params={"period": 20, "std_dev": 2},
                    output_name="bb",
                ),
                IndicatorConfig(type=IndicatorType.RSI, params={"period": 14}, output_name="rsi"),
            ],
            entry_conditions=[
                ConditionConfig(
                    left="price", operator=ConditionOperator.LESS_THAN, right="bb.lower"
                ),
                ConditionConfig(left="rsi", operator=ConditionOperator.LESS_THAN, right=35),
            ],
            exit_conditions=[
                ConditionConfig(
                    left="price", operator=ConditionOperator.GREATER_THAN, right="bb.middle"
                ),
            ],
            entry_action=ActionConfig(
                type=ActionType.BUY, quantity_type="percent", quantity_value=5
            ),
            exit_action=ActionConfig(type=ActionType.CLOSE_ALL),
            risk=RiskConfig(stop_loss_percent=2, take_profit_percent=6),
        ),
    },
    "donchian_breakout": {
        "id": "donchian_breakout",
        "name": "Donchian Channel Breakout",
        "description": "Classic breakout strategy using Donchian channels (Turtle Trading style)",
        "strategy_type": StrategyType.BREAKOUT,
        "tags": ["breakout", "donchian", "trend", "advanced"],
        "config": StrategyConfig(
            symbols=["GLD"],
            timeframe="1D",
            indicators=[
                IndicatorConfig(
                    type=IndicatorType.DONCHIAN_CHANNEL,
                    params={"period": 20},
                    output_name="donchian",
                ),
                IndicatorConfig(type=IndicatorType.ATR, params={"period": 14}, output_name="atr"),
            ],
            entry_conditions=[
                ConditionConfig(
                    left="price", operator=ConditionOperator.GREATER_THAN, right="donchian.upper"
                ),
            ],
            exit_conditions=[
                ConditionConfig(
                    left="price", operator=ConditionOperator.LESS_THAN, right="donchian.lower"
                ),
            ],
            entry_action=ActionConfig(
                type=ActionType.BUY, quantity_type="percent", quantity_value=5
            ),
            exit_action=ActionConfig(type=ActionType.CLOSE_ALL),
            risk=RiskConfig(stop_loss_percent=5, trailing_stop_percent=3),
        ),
    },
    "dual_momentum": {
        "id": "dual_momentum",
        "name": "Dual Momentum",
        "description": "Combines relative momentum (vs benchmark) with absolute momentum (positive returns)",
        "strategy_type": StrategyType.MOMENTUM,
        "tags": ["momentum", "relative", "absolute", "advanced"],
        "config": StrategyConfig(
            symbols=["SPY", "EFA"],
            timeframe="1D",
            indicators=[
                IndicatorConfig(
                    type=IndicatorType.SMA, params={"period": 200}, output_name="sma_200"
                ),
                IndicatorConfig(
                    type=IndicatorType.SMA, params={"period": 12}, output_name="momentum_12m"
                ),
            ],
            entry_conditions=[
                ConditionConfig(
                    left="price", operator=ConditionOperator.GREATER_THAN, right="sma_200"
                ),
                ConditionConfig(
                    left="momentum_12m", operator=ConditionOperator.GREATER_THAN, right=0
                ),
            ],
            exit_conditions=[
                ConditionConfig(
                    left="price", operator=ConditionOperator.LESS_THAN, right="sma_200"
                ),
            ],
            entry_action=ActionConfig(
                type=ActionType.BUY, quantity_type="percent", quantity_value=50
            ),
            exit_action=ActionConfig(type=ActionType.CLOSE_ALL),
            risk=RiskConfig(max_position_size_percent=50),
        ),
    },
    "zscore_mean_reversion": {
        "id": "zscore_mean_reversion",
        "name": "Z-Score Mean Reversion",
        "description": "Statistical mean reversion using z-score of price deviations",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["mean-reversion", "statistical", "zscore", "advanced"],
        "config": StrategyConfig(
            symbols=["XLF"],
            timeframe="1H",
            indicators=[
                IndicatorConfig(type=IndicatorType.SMA, params={"period": 20}, output_name="sma"),
                IndicatorConfig(
                    type=IndicatorType.BOLLINGER_BANDS,
                    params={"period": 20, "std_dev": 1},
                    output_name="bb_1std",
                ),
            ],
            entry_conditions=[
                ConditionConfig(
                    left="price", operator=ConditionOperator.LESS_THAN, right="bb_1std.lower"
                ),
            ],
            exit_conditions=[
                ConditionConfig(left="price", operator=ConditionOperator.GREATER_THAN, right="sma"),
            ],
            entry_action=ActionConfig(
                type=ActionType.BUY, quantity_type="percent", quantity_value=10
            ),
            exit_action=ActionConfig(type=ActionType.CLOSE_ALL),
            risk=RiskConfig(stop_loss_percent=2, max_daily_loss_percent=5),
        ),
    },
    "vwap_strategy": {
        "id": "vwap_strategy",
        "name": "VWAP Strategy",
        "description": "Intraday strategy using Volume Weighted Average Price as dynamic support/resistance",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["intraday", "vwap", "volume", "intermediate"],
        "config": StrategyConfig(
            symbols=["TSLA"],
            timeframe="5m",
            indicators=[
                IndicatorConfig(type=IndicatorType.VWAP, params={}, output_name="vwap"),
                IndicatorConfig(type=IndicatorType.RSI, params={"period": 14}, output_name="rsi"),
            ],
            entry_conditions=[
                ConditionConfig(left="price", operator=ConditionOperator.CROSS_ABOVE, right="vwap"),
                ConditionConfig(left="rsi", operator=ConditionOperator.GREATER_THAN, right=50),
            ],
            exit_conditions=[
                ConditionConfig(left="price", operator=ConditionOperator.CROSS_BELOW, right="vwap"),
            ],
            entry_action=ActionConfig(
                type=ActionType.BUY, quantity_type="percent", quantity_value=5
            ),
            exit_action=ActionConfig(type=ActionType.CLOSE_ALL),
            risk=RiskConfig(stop_loss_percent=1, take_profit_percent=2),
        ),
    },
    "pairs_trading": {
        "id": "pairs_trading",
        "name": "Pairs Trading",
        "description": "Statistical arbitrage between correlated assets (e.g., KO/PEP)",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["arbitrage", "pairs", "correlation", "advanced"],
        "config": StrategyConfig(
            symbols=["KO", "PEP"],
            timeframe="1H",
            indicators=[
                IndicatorConfig(
                    type=IndicatorType.SMA, params={"period": 20}, output_name="spread_sma"
                ),
                IndicatorConfig(
                    type=IndicatorType.BOLLINGER_BANDS,
                    params={"period": 20, "std_dev": 2},
                    output_name="spread_bb",
                ),
            ],
            entry_conditions=[
                ConditionConfig(
                    left="spread", operator=ConditionOperator.LESS_THAN, right="spread_bb.lower"
                ),
            ],
            exit_conditions=[
                ConditionConfig(
                    left="spread", operator=ConditionOperator.GREATER_THAN, right="spread_sma"
                ),
            ],
            entry_action=ActionConfig(
                type=ActionType.BUY, quantity_type="percent", quantity_value=5
            ),
            exit_action=ActionConfig(type=ActionType.CLOSE_ALL),
            risk=RiskConfig(stop_loss_percent=3, max_open_positions=2),
        ),
    },
    "stop_loss_take_profit": {
        "id": "stop_loss_take_profit",
        "name": "Stop Loss / Take Profit Management",
        "description": "Risk management overlay template - add to any strategy for automated exits",
        "strategy_type": StrategyType.CUSTOM,
        "tags": ["risk-management", "stops", "beginner"],
        "config": StrategyConfig(
            symbols=["SPY"],
            timeframe="1D",
            indicators=[
                IndicatorConfig(type=IndicatorType.ATR, params={"period": 14}, output_name="atr"),
            ],
            entry_conditions=[],  # No entry - overlay only
            exit_conditions=[],  # Exits handled by risk config
            risk=RiskConfig(
                stop_loss_percent=2,
                take_profit_percent=6,
                trailing_stop_percent=1.5,
                max_position_size_percent=10,
                max_daily_loss_percent=5,
            ),
        ),
    },
}


class TemplateService:
    """Service for strategy template operations."""

    async def list_templates(
        self,
        strategy_type: StrategyType | None = None,
    ) -> list[dict[str, Any]]:
        """List available strategy templates."""
        templates = list(TEMPLATES.values())

        if strategy_type:
            templates = [t for t in templates if t["strategy_type"] == strategy_type]

        return templates

    async def get_template(self, template_id: str) -> dict[str, Any] | None:
        """Get a specific template by ID."""
        return TEMPLATES.get(template_id)


def get_template_service() -> TemplateService:
    """Dependency to get template service."""
    return TemplateService()
