"""Template service - pre-built strategy templates using S-expression DSL."""

from typing import TypedDict

from src.models import StrategyType, TemplateResponse


class TemplateData(TypedDict):
    """Template data structure for internal storage."""

    id: str
    name: str
    description: str
    strategy_type: StrategyType
    tags: list[str]
    difficulty: str
    config_sexpr: str


# Pre-built strategy templates using S-expression DSL
TEMPLATES: dict[str, TemplateData] = {
    "ma_crossover": {
        "id": "ma_crossover",
        "name": "Moving Average Crossover",
        "description": "Classic trend-following strategy using fast and slow EMA crossovers",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "tags": ["trend", "ema", "beginner"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy
  :name "Moving Average Crossover"
  :type trend_following
  :symbols ["AAPL"]
  :timeframe "1D"
  :entry (cross-above (ema close 12) (ema close 26))
  :exit (cross-below (ema close 12) (ema close 26))
  :position-size-pct 10.0
  :stop-loss-pct 5.0
  :take-profit-pct 15.0)""",
    },
    "rsi_mean_reversion": {
        "id": "rsi_mean_reversion",
        "name": "RSI Mean Reversion",
        "description": "Buy oversold conditions (RSI < 30), sell overbought (RSI > 70)",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["mean-reversion", "rsi", "intermediate"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy
  :name "RSI Mean Reversion"
  :type mean_reversion
  :symbols ["SPY"]
  :timeframe "1D"
  :entry (< (rsi close 14) 30)
  :exit (> (rsi close 14) 70)
  :position-size-pct 10.0
  :stop-loss-pct 3.0
  :take-profit-pct 10.0)""",
    },
    "macd_strategy": {
        "id": "macd_strategy",
        "name": "MACD Strategy",
        "description": "Trade MACD line crossovers with the signal line",
        "strategy_type": StrategyType.MOMENTUM,
        "tags": ["momentum", "macd", "beginner"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy
  :name "MACD Strategy"
  :type momentum
  :symbols ["QQQ"]
  :timeframe "1D"
  :entry (cross-above (macd-line close 12 26 9) (macd-signal close 12 26 9))
  :exit (cross-below (macd-line close 12 26 9) (macd-signal close 12 26 9))
  :position-size-pct 10.0
  :stop-loss-pct 4.0
  :take-profit-pct 12.0)""",
    },
    "bollinger_bounce": {
        "id": "bollinger_bounce",
        "name": "Bollinger Bands Bounce",
        "description": "Mean reversion strategy trading bounces off Bollinger Band boundaries",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["mean-reversion", "bollinger", "intermediate"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy
  :name "Bollinger Bands Bounce"
  :type mean_reversion
  :symbols ["SPY"]
  :timeframe "1H"
  :entry (and
    (< close (bb-lower close 20 2.0))
    (< (rsi close 14) 35))
  :exit (> close (bb-middle close 20 2.0))
  :position-size-pct 5.0
  :stop-loss-pct 2.0
  :take-profit-pct 6.0)""",
    },
    "donchian_breakout": {
        "id": "donchian_breakout",
        "name": "Donchian Channel Breakout",
        "description": "Classic breakout strategy using Donchian channels (Turtle Trading style)",
        "strategy_type": StrategyType.BREAKOUT,
        "tags": ["breakout", "donchian", "trend", "advanced"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy
  :name "Donchian Channel Breakout"
  :type breakout
  :symbols ["GLD"]
  :timeframe "1D"
  :entry (> close (donchian-upper high 20))
  :exit (< close (donchian-lower low 20))
  :position-size-pct 5.0
  :stop-loss-pct 5.0
  :trailing-stop-pct 3.0)""",
    },
    "dual_momentum": {
        "id": "dual_momentum",
        "name": "Dual Momentum",
        "description": ("Combines relative momentum (vs benchmark) with absolute momentum"),
        "strategy_type": StrategyType.MOMENTUM,
        "tags": ["momentum", "relative", "absolute", "advanced"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy
  :name "Dual Momentum"
  :type momentum
  :symbols ["SPY" "EFA"]
  :timeframe "1D"
  :entry (and
    (> close (sma close 200))
    (> (roc close 252) 0))
  :exit (< close (sma close 200))
  :position-size-pct 50.0)""",
    },
    "zscore_mean_reversion": {
        "id": "zscore_mean_reversion",
        "name": "Z-Score Mean Reversion",
        "description": "Statistical mean reversion using z-score of price deviations",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["mean-reversion", "statistical", "zscore", "advanced"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy
  :name "Z-Score Mean Reversion"
  :type mean_reversion
  :symbols ["XLF"]
  :timeframe "1H"
  :entry (< close (bb-lower close 20 1.0))
  :exit (> close (sma close 20))
  :position-size-pct 10.0
  :stop-loss-pct 2.0)""",
    },
    "vwap_strategy": {
        "id": "vwap_strategy",
        "name": "VWAP Strategy",
        "description": "Intraday strategy using VWAP as dynamic support/resistance",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["intraday", "vwap", "volume", "intermediate"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy
  :name "VWAP Strategy"
  :type mean_reversion
  :symbols ["TSLA"]
  :timeframe "5m"
  :entry (and
    (cross-above close (vwap close volume))
    (> (rsi close 14) 50))
  :exit (cross-below close (vwap close volume))
  :position-size-pct 5.0
  :stop-loss-pct 1.0
  :take-profit-pct 2.0)""",
    },
    "pairs_trading": {
        "id": "pairs_trading",
        "name": "Pairs Trading",
        "description": "Statistical arbitrage between correlated assets (e.g., KO/PEP)",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["arbitrage", "pairs", "correlation", "advanced"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy
  :name "Pairs Trading"
  :type mean_reversion
  :symbols ["KO" "PEP"]
  :timeframe "1H"
  :description "Trade the spread between KO and PEP when it deviates from the mean"
  :entry (< (spread KO PEP) (bb-lower (spread KO PEP) 20 2.0))
  :exit (> (spread KO PEP) (sma (spread KO PEP) 20))
  :position-size-pct 5.0
  :stop-loss-pct 3.0)""",
    },
    "adx_trend_filter": {
        "id": "adx_trend_filter",
        "name": "ADX Trend Filter",
        "description": "Only trade in strong trends using ADX filter with EMA crossover signals",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "tags": ["trend", "adx", "filter", "intermediate"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy
  :name "ADX Trend Filter"
  :type trend_following
  :symbols ["SPY"]
  :timeframe "1D"
  :entry (and
    (> (adx high low close 14) 25)
    (cross-above (ema close 9) (ema close 21)))
  :exit (or
    (< (adx high low close 14) 20)
    (cross-below (ema close 9) (ema close 21)))
  :position-size-pct 10.0
  :stop-loss-pct 3.0
  :take-profit-pct 9.0)""",
    },
}


class TemplateService:
    """Service for strategy template operations."""

    async def list_templates(
        self,
        strategy_type: StrategyType | None = None,
        difficulty: str | None = None,
    ) -> list[TemplateResponse]:
        """List available strategy templates.

        Args:
            strategy_type: Filter by strategy type
            difficulty: Filter by difficulty level (beginner, intermediate, advanced)

        Returns:
            List of TemplateResponse objects
        """
        templates = list(TEMPLATES.values())

        if strategy_type:
            templates = [t for t in templates if t["strategy_type"] == strategy_type]

        if difficulty:
            templates = [t for t in templates if t["difficulty"] == difficulty]

        return [
            TemplateResponse(
                id=t["id"],
                name=t["name"],
                description=t["description"],
                strategy_type=t["strategy_type"],
                config_sexpr=t["config_sexpr"],
                config_json={},  # Parsed on demand
                tags=t["tags"],
                difficulty=t["difficulty"],
            )
            for t in templates
        ]

    async def get_template(self, template_id: str) -> TemplateResponse | None:
        """Get a specific template by ID.

        Args:
            template_id: The template identifier

        Returns:
            TemplateResponse or None if not found
        """
        t = TEMPLATES.get(template_id)
        if not t:
            return None
        return TemplateResponse(
            id=t["id"],
            name=t["name"],
            description=t["description"],
            strategy_type=t["strategy_type"],
            config_sexpr=t["config_sexpr"],
            config_json={},  # Parsed on demand
            tags=t["tags"],
            difficulty=t["difficulty"],
        )

    async def get_template_config(self, template_id: str) -> str | None:
        """Get just the S-expression config for a template.

        Args:
            template_id: The template identifier

        Returns:
            S-expression config string or None if not found
        """
        template = TEMPLATES.get(template_id)
        return template["config_sexpr"] if template else None


def get_template_service() -> TemplateService:
    """Dependency to get template service."""
    return TemplateService()
