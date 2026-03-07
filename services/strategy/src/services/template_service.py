"""Template service - pre-built strategy templates using allocation-based S-expression DSL."""

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


# Pre-built allocation strategy templates using S-expression DSL
TEMPLATES: dict[str, TemplateData] = {
    "ma_crossover": {
        "id": "ma_crossover",
        "name": "Moving Average Crossover",
        "description": "Trend-following allocation using EMA crossovers",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "tags": ["trend", "ema", "beginner"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Moving Average Crossover"
  :rebalance daily
  :benchmark SPY
  (if (crosses-above (ema SPY 12) (ema SPY 26))
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))""",
    },
    "rsi_mean_reversion": {
        "id": "rsi_mean_reversion",
        "name": "RSI Mean Reversion",
        "description": "Allocate to equities when oversold, bonds when overbought",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["mean-reversion", "rsi", "intermediate"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "RSI Mean Reversion"
  :rebalance daily
  :benchmark SPY
  (if (< (rsi SPY 14) 30)
    (asset SPY :weight 100)
    (else (if (> (rsi SPY 14) 70)
      (asset TLT :weight 100)
      (else (weight :method equal
        (asset SPY)
        (asset TLT)))))))""",
    },
    "sixty_forty": {
        "id": "sixty_forty",
        "name": "60/40 Portfolio",
        "description": "Classic 60% equities / 40% bonds allocation",
        "strategy_type": StrategyType.CUSTOM,
        "tags": ["classic", "balanced", "beginner"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "60/40 Portfolio"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 60)
    (asset BND :weight 40)))""",
    },
    "momentum_rotation": {
        "id": "momentum_rotation",
        "name": "Momentum Sector Rotation",
        "description": "Rotate to top momentum sectors",
        "strategy_type": StrategyType.MOMENTUM,
        "tags": ["momentum", "sectors", "intermediate"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Momentum Sector Rotation"
  :rebalance monthly
  :benchmark SPY
  (filter :by momentum :select (top 3) :lookback 90
    (weight :method momentum :lookback 90
      (asset XLK)
      (asset XLF)
      (asset XLE)
      (asset XLV)
      (asset XLI)
      (asset XLP)
      (asset XLY)
      (asset XLU)
      (asset XLRE)
      (asset XLC)
      (asset XLB))))""",
    },
    "risk_parity": {
        "id": "risk_parity",
        "name": "Risk Parity",
        "description": "Equal risk contribution across asset classes",
        "strategy_type": StrategyType.CUSTOM,
        "tags": ["risk-parity", "diversification", "advanced"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Risk Parity"
  :rebalance monthly
  :benchmark SPY
  (weight :method inverse-volatility :lookback 60
    (asset SPY)
    (asset TLT)
    (asset GLD)
    (asset DBC)))""",
    },
    "dual_momentum": {
        "id": "dual_momentum",
        "name": "Dual Momentum",
        "description": "Classic dual momentum: compare US vs International, allocate to winner or bonds",
        "strategy_type": StrategyType.MOMENTUM,
        "tags": ["momentum", "trend", "advanced"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Dual Momentum"
  :rebalance monthly
  :benchmark SPY
  (if (and
        (> (momentum SPY 252) (momentum EFA 252))
        (> (momentum SPY 252) 0))
    (asset SPY :weight 100)
    (else (if (and
          (> (momentum EFA 252) (momentum SPY 252))
          (> (momentum EFA 252) 0))
      (asset EFA :weight 100)
      (else (asset AGG :weight 100))))))""",
    },
    "golden_cross": {
        "id": "golden_cross",
        "name": "Golden Cross",
        "description": "Allocate to equities when 50-day SMA crosses above 200-day SMA",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "tags": ["trend", "sma", "beginner"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Golden Cross"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (asset SPY :weight 100)
    (else (asset AGG :weight 100))))""",
    },
    "volatility_targeting": {
        "id": "volatility_targeting",
        "name": "Volatility Targeting",
        "description": "Reduce equity allocation when VIX is high",
        "strategy_type": StrategyType.CUSTOM,
        "tags": ["volatility", "risk-management", "advanced"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Volatility Targeting"
  :rebalance daily
  :benchmark SPY
  (if (> (price VIX) 30)
    (weight :method specified
      (asset SPY :weight 25)
      (asset TLT :weight 75))
    (else (if (> (price VIX) 20)
      (weight :method specified
        (asset SPY :weight 50)
        (asset TLT :weight 50))
      (else (weight :method specified
        (asset SPY :weight 75)
        (asset TLT :weight 25)))))))""",
    },
    "all_weather": {
        "id": "all_weather",
        "name": "All Weather Portfolio",
        "description": "Ray Dalio inspired diversified allocation",
        "strategy_type": StrategyType.CUSTOM,
        "tags": ["diversified", "all-weather", "beginner"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "All Weather Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 30)
    (asset TLT :weight 40)
    (asset IEF :weight 15)
    (asset GLD :weight 7.5)
    (asset DBC :weight 7.5)))""",
    },
    "equal_weight_tech": {
        "id": "equal_weight_tech",
        "name": "Equal Weight Tech",
        "description": "Equal allocation across major tech stocks",
        "strategy_type": StrategyType.CUSTOM,
        "tags": ["tech", "equal-weight", "beginner"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Equal Weight Tech"
  :rebalance monthly
  :benchmark QQQ
  (weight :method equal
    (asset AAPL)
    (asset MSFT)
    (asset GOOGL)
    (asset AMZN)
    (asset META)
    (asset NVDA)
    (asset TSLA)))""",
    },
    "macd_strategy": {
        "id": "macd_strategy",
        "name": "MACD Momentum",
        "description": "Trade based on MACD histogram crossovers",
        "strategy_type": StrategyType.MOMENTUM,
        "tags": ["momentum", "macd", "intermediate"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "MACD Momentum"
  :rebalance daily
  :benchmark SPY
  (if (> (macd SPY 12 26 9 :output histogram) 0)
    (asset SPY :weight 100)
    (else (asset SHY :weight 100))))""",
    },
    "bollinger_bounce": {
        "id": "bollinger_bounce",
        "name": "Bollinger Bounce",
        "description": "Mean reversion strategy using Bollinger Bands",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["mean-reversion", "bollinger", "intermediate"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Bollinger Bounce"
  :rebalance daily
  :benchmark SPY
  (if (< (price SPY) (bbands SPY 20 2 :output lower))
    (asset SPY :weight 100)
    (else (if (> (price SPY) (bbands SPY 20 2 :output upper))
      (asset TLT :weight 100)
      (else (weight :method equal
        (asset SPY)
        (asset TLT)))))))""",
    },
    "donchian_breakout": {
        "id": "donchian_breakout",
        "name": "Donchian Channel Breakout",
        "description": "Turtle trading inspired breakout strategy",
        "strategy_type": StrategyType.BREAKOUT,
        "tags": ["breakout", "donchian", "trend", "advanced"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Donchian Breakout"
  :rebalance daily
  :benchmark SPY
  (if (> (price SPY) (donchian SPY 20 :output upper))
    (asset SPY :weight 100)
    (else (if (< (price SPY) (donchian SPY 20 :output lower))
      (asset TLT :weight 100)
      (else (weight :method specified
        (asset SPY :weight 50)
        (asset TLT :weight 50)))))))""",
    },
    "pairs_trading": {
        "id": "pairs_trading",
        "name": "Pairs Trading",
        "description": "Mean reversion on correlated asset pairs (KO/PEP)",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "tags": ["pairs", "mean-reversion", "advanced"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Pairs Trading"
  :rebalance daily
  :benchmark SPY
  (if (< (zscore (ratio KO PEP) 20) -2)
    (weight :method specified
      (asset KO :weight 50)
      (asset PEP :weight -50))
    (else (if (> (zscore (ratio KO PEP) 20) 2)
      (weight :method specified
        (asset KO :weight -50)
        (asset PEP :weight 50))
      (else (asset SHY :weight 100))))))""",
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
