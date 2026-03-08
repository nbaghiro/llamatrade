"""Template service - pre-built strategy templates using allocation-based S-expression DSL.

This is the SINGLE SOURCE OF TRUTH for all strategy templates.
Frontend fetches these via API and parses S-expressions into visual blocks.
"""

from typing import TypedDict

from src.models import AssetClass, StrategyType, TemplateCategory, TemplateResponse


class TemplateData(TypedDict):
    """Template data structure for internal storage."""

    id: str
    name: str
    description: str
    strategy_type: StrategyType
    category: TemplateCategory
    asset_class: AssetClass
    tags: list[str]
    difficulty: str
    config_sexpr: str


# =============================================================================
# CONSOLIDATED STRATEGY TEMPLATES
# All templates defined here - frontend fetches via API
# =============================================================================

TEMPLATES: dict[str, TemplateData] = {
    # =========================================================================
    # BUY-AND-HOLD STRATEGIES
    # Static allocations with periodic rebalancing
    # =========================================================================
    "classic-60-40": {
        "id": "classic-60-40",
        "name": "Classic 60/40",
        "description": "The foundational portfolio—60% stocks, 40% bonds. Simple, time-tested, effective.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["classic", "balanced"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Classic 60/40"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 60)
    (asset BND :weight 40)))""",
    },
    "three-fund": {
        "id": "three-fund",
        "name": "Three-Fund Portfolio",
        "description": "Bogleheads classic—total US market, international, and bonds for maximum diversification.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["bogleheads", "diversified"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Three-Fund Portfolio"
  :rebalance quarterly
  :benchmark VTI
  (weight :method specified
    (asset VTI :weight 50)
    (asset VXUS :weight 30)
    (asset BND :weight 20)))""",
    },
    "equal-weight-sectors": {
        "id": "equal-weight-sectors",
        "name": "Equal Weight Sectors",
        "description": "Equal allocation across major market sectors. Removes market-cap bias.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.EQUITY,
        "tags": ["sectors", "equal-weight"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Equal Weight Sectors"
  :rebalance monthly
  :benchmark SPY
  (weight :method equal
    (asset XLK)
    (asset XLF)
    (asset XLV)
    (asset XLI)
    (asset XLP)
    (asset XLY)
    (asset XLE)
    (asset XLU)
    (asset XLRE)
    (asset XLC)
    (asset XLB)))""",
    },
    "tech-growth": {
        "id": "tech-growth",
        "name": "Tech Growth",
        "description": "Concentrated exposure to leading technology companies with conviction weights.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.EQUITY,
        "tags": ["tech", "growth", "concentrated"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Tech Growth"
  :rebalance monthly
  :benchmark QQQ
  (weight :method specified
    (asset AAPL :weight 20)
    (asset MSFT :weight 20)
    (asset NVDA :weight 15)
    (asset GOOGL :weight 15)
    (asset AMZN :weight 15)
    (asset META :weight 10)
    (asset TSLA :weight 5)))""",
    },
    "core-satellite": {
        "id": "core-satellite",
        "name": "Core-Satellite",
        "description": "Stable core of index funds combined with satellite positions in higher-conviction plays.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["core-satellite", "hybrid"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Core-Satellite"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Core"
      (weight :method specified
        (asset VTI :weight 50)
        (asset BND :weight 20)))
    (group "Satellite"
      (weight :method equal
        (asset QQQ)
        (asset ARKK)
        (asset VNQ)))))""",
    },
    "global-allocation": {
        "id": "global-allocation",
        "name": "Global Asset Allocation",
        "description": "Globally diversified portfolio across geographies and asset classes.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["global", "diversified"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Global Asset Allocation"
  :rebalance quarterly
  :benchmark VT
  (weight :method specified
    (group "US Equities"
      (asset VTI :weight 35))
    (group "International"
      (weight :method specified
        (asset VEA :weight 15)
        (asset VWO :weight 10)))
    (group "Fixed Income"
      (asset BND :weight 25))
    (group "Real Assets"
      (weight :method specified
        (asset VNQ :weight 10)
        (asset GLD :weight 5)))))""",
    },
    "risk-parity": {
        "id": "risk-parity",
        "name": "Risk Parity",
        "description": "Allocate by risk contribution using inverse volatility—equal risk across asset classes.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["risk-parity", "all-weather"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Risk Parity"
  :rebalance monthly
  :benchmark SPY
  (weight :method inverse-volatility :lookback 60
    (asset SPY)
    (asset TLT)
    (asset GLD)
    (asset DBC)))""",
    },
    "all-weather": {
        "id": "all-weather",
        "name": "All-Weather Portfolio",
        "description": "Ray Dalio inspired diversified allocation for all economic conditions.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["all-weather", "ray-dalio", "famous-portfolio"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "All-Weather Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 30)
    (asset TLT :weight 40)
    (asset IEF :weight 15)
    (asset GLD :weight 7.5)
    (asset DBC :weight 7.5)))""",
    },
    "permanent-portfolio": {
        "id": "permanent-portfolio",
        "name": "Permanent Portfolio",
        "description": "Harry Browne's 4x25% allocation designed for all economic conditions—stocks, bonds, gold, cash.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["all-weather", "harry-browne", "famous-portfolio"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Permanent Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 25)
    (asset TLT :weight 25)
    (asset GLD :weight 25)
    (asset SHY :weight 25)))""",
    },
    "ivy-portfolio": {
        "id": "ivy-portfolio",
        "name": "Ivy Portfolio",
        "description": "Meb Faber's endowment-style 5-asset allocation modeled on institutional investors.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["endowment", "meb-faber", "famous-portfolio"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Ivy Portfolio"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 20)
    (asset VEU :weight 20)
    (asset BND :weight 20)
    (asset VNQ :weight 20)
    (asset DBC :weight 20)))""",
    },
    "golden-butterfly": {
        "id": "golden-butterfly",
        "name": "Golden Butterfly",
        "description": "Balanced allocation with small-cap value tilt—total market, SCV, long bonds, short bonds, gold.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["all-weather", "small-cap-value", "famous-portfolio"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Golden Butterfly"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 20)
    (asset IJS :weight 20)
    (asset TLT :weight 20)
    (asset SHY :weight 20)
    (asset GLD :weight 20)))""",
    },
    "swensen-portfolio": {
        "id": "swensen-portfolio",
        "name": "Swensen Portfolio",
        "description": "David Swensen's Yale Endowment-inspired diversified model for individual investors.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["endowment", "yale", "david-swensen", "famous-portfolio"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Swensen Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 30)
    (asset VEA :weight 15)
    (asset VWO :weight 5)
    (asset VNQ :weight 20)
    (asset TIP :weight 15)
    (asset BND :weight 15)))""",
    },
    "low-volatility": {
        "id": "low-volatility",
        "name": "Low Volatility",
        "description": "Minimum volatility defensive strategy for reduced drawdowns and smoother returns.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.BUY_AND_HOLD,
        "asset_class": AssetClass.EQUITY,
        "tags": ["defensive", "low-vol"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Low Volatility"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (asset USMV :weight 40)
    (asset SPLV :weight 30)
    (asset EFAV :weight 30)))""",
    },
    # =========================================================================
    # FACTOR STRATEGIES
    # Factor-tilted strategies (momentum, value, quality, size)
    # =========================================================================
    "momentum-sectors": {
        "id": "momentum-sectors",
        "name": "Momentum Sectors",
        "description": "Weight sectors by recent momentum—more allocation to stronger performers.",
        "strategy_type": StrategyType.MOMENTUM,
        "category": TemplateCategory.FACTOR,
        "asset_class": AssetClass.EQUITY,
        "tags": ["momentum", "sectors", "rotation"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Momentum Sectors"
  :rebalance monthly
  :benchmark SPY
  (weight :method momentum :lookback 90
    (asset XLK)
    (asset XLF)
    (asset XLV)
    (asset XLI)
    (asset XLP)
    (asset XLY)
    (asset XLE)
    (asset XLU)
    (asset XLRE)
    (asset XLC)
    (asset XLB)))""",
    },
    "larry-portfolio": {
        "id": "larry-portfolio",
        "name": "Larry Portfolio",
        "description": "Larry Swedroe's factor-tilted allocation emphasizing small-cap value globally.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.FACTOR,
        "asset_class": AssetClass.EQUITY,
        "tags": ["small-cap-value", "larry-swedroe", "famous-portfolio"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Larry Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset AVUV :weight 30)
    (asset AVDV :weight 30)
    (asset AVES :weight 10)
    (asset BND :weight 30)))""",
    },
    "multi-factor-smart-beta": {
        "id": "multi-factor-smart-beta",
        "name": "Multi-Factor Smart Beta",
        "description": "Combined Value + Momentum + Quality + Size factor exposure via ETFs.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.FACTOR,
        "asset_class": AssetClass.EQUITY,
        "tags": ["smart-beta", "multi-factor"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Multi-Factor Smart Beta"
  :rebalance quarterly
  :benchmark SPY
  (weight :method equal
    (asset VLUE)
    (asset MTUM)
    (asset QUAL)
    (asset SIZE)))""",
    },
    "multi-factor-rotation": {
        "id": "multi-factor-rotation",
        "name": "Multi-Factor Sector Rotation",
        "description": "Rotate into top-performing sectors using filters with factor-based weighting.",
        "strategy_type": StrategyType.MOMENTUM,
        "category": TemplateCategory.FACTOR,
        "asset_class": AssetClass.EQUITY,
        "tags": ["rotation", "sectors", "filters"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Multi-Factor Sector Rotation"
  :rebalance monthly
  :benchmark SPY
  (filter :by momentum :select (top 3) :lookback 90
    (weight :method momentum :lookback 60
      (asset XLK)
      (asset XLF)
      (asset XLV)
      (asset XLI)
      (asset XLE)
      (asset XLP)
      (asset XLY))))""",
    },
    "deep-value": {
        "id": "deep-value",
        "name": "Deep Value",
        "description": "Concentrated value factor exposure with rotation to top performers.",
        "strategy_type": StrategyType.MOMENTUM,
        "category": TemplateCategory.FACTOR,
        "asset_class": AssetClass.EQUITY,
        "tags": ["factor", "value", "concentrated"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Deep Value"
  :rebalance monthly
  :benchmark SPY
  (filter :by momentum :select (top 2) :lookback 60
    (weight :method momentum :lookback 60
      (asset VTV)
      (asset RPV)
      (asset SPYV))))""",
    },
    "small-cap-value-tilt": {
        "id": "small-cap-value-tilt",
        "name": "Small-Cap Value Tilt",
        "description": "Size + value factor combination for enhanced returns.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.FACTOR,
        "asset_class": AssetClass.EQUITY,
        "tags": ["factor", "small-cap-value"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Small-Cap Value Tilt"
  :rebalance monthly
  :benchmark IWM
  (weight :method inverse-volatility :lookback 60
    (asset AVUV)
    (asset IJS)
    (asset VBR)
    (asset SLYV)))""",
    },
    "sector-rsi-rotation": {
        "id": "sector-rsi-rotation",
        "name": "Sector RSI Rotation",
        "description": "Rotate into oversold sectors using RSI signals with momentum-weighted allocation.",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "category": TemplateCategory.FACTOR,
        "asset_class": AssetClass.EQUITY,
        "tags": ["rotation", "rsi", "sectors", "mean-reversion"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Sector RSI Rotation"
  :rebalance weekly
  :benchmark SPY
  (if (< (rsi XLK 14) 40)
    (group "Oversold Tech"
      (weight :method specified
        (asset XLK :weight 30)
        (asset SMH :weight 20)))
    (else
      (if (< (rsi XLF 14) 40)
        (group "Oversold Financials"
          (weight :method specified
            (asset XLF :weight 30)
            (asset KRE :weight 20)))
        (else
          (weight :method momentum :lookback 60
            (asset XLK)
            (asset XLF)
            (asset XLV)
            (asset XLI)))))))""",
    },
    "international-value-momentum": {
        "id": "international-value-momentum",
        "name": "International Value Momentum",
        "description": "Combine value and momentum factors internationally with trend filter.",
        "strategy_type": StrategyType.MOMENTUM,
        "category": TemplateCategory.FACTOR,
        "asset_class": AssetClass.EQUITY,
        "tags": ["international", "value", "momentum", "multi-factor"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "International Value Momentum"
  :rebalance monthly
  :benchmark VEU
  (weight :method specified
    (group "Value Core"
      (weight :method equal
        (asset EFV)
        (asset VWO)))
    (group "Momentum Satellite"
      (if (> (price VEU) (sma VEU 200))
        (weight :method momentum :lookback 90
          (asset VEA)
          (asset VWO)
          (asset IEMG))
        (else (asset SHY :weight 100))))))""",
    },
    "factor-timing": {
        "id": "factor-timing",
        "name": "Factor Timing Strategy",
        "description": "Dynamic factor rotation: momentum vs value based on trend, low-vol vs size based on VIX, plus quality core.",
        "strategy_type": StrategyType.REGIME,
        "category": TemplateCategory.FACTOR,
        "asset_class": AssetClass.EQUITY,
        "tags": ["factors", "timing", "rotation", "multi-factor"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Factor Timing Strategy"
  :rebalance weekly
  :benchmark SPY
  (weight :method specified
    (group "Trend Factor"
      (if (> (price SPY) (sma SPY 200))
        (asset MTUM :weight 25)
        (else (asset VLUE :weight 25))))
    (group "Vol Factor"
      (if (< (price VIX) 20)
        (asset SIZE :weight 25)
        (else (asset USMV :weight 25))))
    (group "Quality Core"
      (asset QUAL :weight 50))))""",
    },
    # =========================================================================
    # INCOME STRATEGIES
    # Dividend and yield-focused strategies
    # =========================================================================
    "dividend-aristocrats": {
        "id": "dividend-aristocrats",
        "name": "Dividend Aristocrats",
        "description": "Blue-chip companies with 25+ years of consecutive dividend increases.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.INCOME,
        "asset_class": AssetClass.EQUITY,
        "tags": ["dividends", "aristocrats", "blue-chip"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Dividend Aristocrats"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Dividend ETFs"
      (weight :method equal
        (asset NOBL)
        (asset SDY)
        (asset VIG)))
    (group "Individual Aristocrats"
      (weight :method equal
        (asset JNJ)
        (asset PG)
        (asset KO)
        (asset PEP)
        (asset MMM)))))""",
    },
    "income-focus": {
        "id": "income-focus",
        "name": "Income Focus",
        "description": "Maximize income through dividends, REITs, and high-yield bonds.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.INCOME,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["dividends", "reits", "high-yield"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Income Focus"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Dividend Equities"
      (weight :method equal
        (asset SCHD)
        (asset VYM)
        (asset DVY)))
    (group "REITs"
      (weight :method equal
        (asset VNQ)
        (asset VNQI)))
    (group "Fixed Income"
      (weight :method equal
        (asset HYG)
        (asset LQD)))))""",
    },
    "quality-dividend": {
        "id": "quality-dividend",
        "name": "Quality Dividend",
        "description": "High-quality dividend growers with proven track records of increasing payouts.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.INCOME,
        "asset_class": AssetClass.EQUITY,
        "tags": ["dividends", "quality", "dividend-growth"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Quality Dividend"
  :rebalance quarterly
  :benchmark SPY
  (weight :method equal
    (asset DGRW)
    (asset SCHD)
    (asset VIG)
    (asset NOBL)))""",
    },
    "covered-call-income": {
        "id": "covered-call-income",
        "name": "Covered Call Income",
        "description": "Buy-write strategy using covered call ETFs for enhanced income generation.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.INCOME,
        "asset_class": AssetClass.OPTIONS,
        "tags": ["covered-call", "options", "premium-income"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Covered Call Income"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (asset QYLD :weight 40)
    (asset XYLD :weight 30)
    (asset JEPI :weight 30)))""",
    },
    "dividend-growth-barbell": {
        "id": "dividend-growth-barbell",
        "name": "Dividend Growth Barbell",
        "description": "Barbell strategy combining stable dividend income with conditional growth exposure.",
        "strategy_type": StrategyType.REGIME,
        "category": TemplateCategory.INCOME,
        "asset_class": AssetClass.EQUITY,
        "tags": ["dividends", "growth", "barbell", "conditional"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Dividend Growth Barbell"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Dividend Core"
      (weight :method equal
        (asset SCHD)
        (asset VIG)
        (asset NOBL)))
    (group "Growth Satellite"
      (if (> (price SPY) (sma SPY 50))
        (weight :method equal
          (asset QQQ)
          (asset VUG))
        (else (asset SHY :weight 100))))))""",
    },
    # =========================================================================
    # TACTICAL STRATEGIES
    # Market timing and regime-based switching
    # =========================================================================
    "volatility-regime": {
        "id": "volatility-regime",
        "name": "Volatility Regime",
        "description": "Adjust allocation based on VIX levels—aggressive in low vol, defensive in high vol.",
        "strategy_type": StrategyType.REGIME,
        "category": TemplateCategory.TACTICAL,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["vix", "regime", "volatility"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Volatility Regime"
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
    "risk-on-off": {
        "id": "risk-on-off",
        "name": "Risk-On/Risk-Off Tactical",
        "description": "Switch between aggressive growth and defensive positions based on market regime.",
        "strategy_type": StrategyType.REGIME,
        "category": TemplateCategory.TACTICAL,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["regime", "risk-management"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Risk-On/Risk-Off Tactical"
  :rebalance daily
  :benchmark SPY
  (weight :method specified
    (if (> (price SPY) (sma SPY 200))
      (group "Risk On"
        (weight :method specified
          (group "Growth"
            (weight :method equal
              (asset QQQ)
              (asset ARKK)
              (asset SMH)))
          (group "High Beta"
            (weight :method equal
              (asset TSLA)
              (asset NVDA)
              (asset AMD)))))
      (else
        (group "Risk Off"
          (weight :method specified
            (group "Treasuries"
              (weight :method equal
                (asset TLT)
                (asset IEF)
                (asset SHY)))
            (group "Defensive"
              (weight :method equal
                (asset XLU)
                (asset XLP)
                (asset GLD)))))))
    (group "Core"
      (weight :method equal
        (asset VTI)
        (asset BND)))))""",
    },
    "tail-risk-hedged": {
        "id": "tail-risk-hedged",
        "name": "Tail Risk Hedged",
        "description": "Core equity exposure with tail hedge allocation for crash protection.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.TACTICAL,
        "asset_class": AssetClass.OPTIONS,
        "tags": ["hedged", "tail-risk", "crash-protection"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Tail Risk Hedged"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (asset SPY :weight 85)
    (asset TAIL :weight 15)))""",
    },
    "buffer-protection": {
        "id": "buffer-protection",
        "name": "Buffer Protection",
        "description": "Hedged equity with downside buffer ETFs for smoother returns.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.TACTICAL,
        "asset_class": AssetClass.OPTIONS,
        "tags": ["buffer", "hedged", "options"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Buffer Protection"
  :rebalance quarterly
  :benchmark SPY
  (weight :method equal
    (asset BUFR)
    (asset BJUL)))""",
    },
    "bond-duration-regime": {
        "id": "bond-duration-regime",
        "name": "Bond Duration Regime",
        "description": "Switch between short and long duration bonds based on rate environment signals.",
        "strategy_type": StrategyType.REGIME,
        "category": TemplateCategory.TACTICAL,
        "asset_class": AssetClass.FIXED_INCOME,
        "tags": ["bonds", "duration", "rates", "regime"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Bond Duration Regime"
  :rebalance weekly
  :benchmark BND
  (if (> (price TLT) (sma TLT 50))
    (weight :method specified
      (asset TLT :weight 50)
      (asset IEF :weight 30)
      (asset SHY :weight 20))
    (else
      (weight :method specified
        (asset SHY :weight 50)
        (asset IEF :weight 30)
        (asset TLT :weight 20)))))""",
    },
    "multi-regime-adaptive": {
        "id": "multi-regime-adaptive",
        "name": "Multi-Regime Adaptive Allocation",
        "description": "Three-tier VIX regime system: crisis mode (defensive), cautious mode (balanced), risk-on mode (aggressive).",
        "strategy_type": StrategyType.REGIME,
        "category": TemplateCategory.TACTICAL,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["regime", "vix", "adaptive", "multi-tier"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Multi-Regime Adaptive"
  :rebalance daily
  :benchmark SPY
  (if (> (price VIX) 35)
    (group "Crisis Mode"
      (weight :method specified
        (asset SHY :weight 40)
        (asset TLT :weight 30)
        (asset GLD :weight 30)))
    (else
      (if (> (price VIX) 20)
        (group "Cautious Mode"
          (weight :method specified
            (asset SPY :weight 40)
            (asset TLT :weight 35)
            (asset GLD :weight 15)
            (asset SHY :weight 10)))
        (else
          (group "Risk-On Mode"
            (weight :method specified
              (asset SPY :weight 50)
              (asset QQQ :weight 25)
              (asset VWO :weight 15)
              (asset TLT :weight 10))))))))""",
    },
    "global-macro-multi-asset": {
        "id": "global-macro-multi-asset",
        "name": "Global Macro Multi-Asset",
        "description": "Institutional-style global macro: US/International equity rotation, inflation-protected bonds, trend-filtered commodities.",
        "strategy_type": StrategyType.REGIME,
        "category": TemplateCategory.TACTICAL,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["global", "macro", "rotation", "institutional"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Global Macro Multi-Asset"
  :rebalance weekly
  :benchmark SPY
  (weight :method specified
    (group "Equity Rotation"
      (if (> (momentum SPY 90) (momentum VEU 90))
        (asset SPY :weight 35)
        (else (asset VEU :weight 35))))
    (group "Inflation Protected"
      (weight :method equal
        (asset TIP)
        (asset VTIP)))
    (group "Commodities"
      (if (> (price DBC) (sma DBC 100))
        (weight :method equal
          (asset DBC)
          (asset GLD))
        (else (asset SHY :weight 100))))))""",
    },
    # =========================================================================
    # TREND-FOLLOWING STRATEGIES
    # Trend-following and breakout strategies
    # =========================================================================
    "simple-trend": {
        "id": "simple-trend",
        "name": "Simple Trend Following",
        "description": "Stay invested above 200-day SMA, move to bonds when below. Classic trend strategy.",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "category": TemplateCategory.TREND,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["sma", "200-day", "trend"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Simple Trend Following"
  :rebalance daily
  :benchmark SPY
  (if (> (price SPY) (sma SPY 200))
    (asset SPY :weight 100)
    (else (asset AGG :weight 100))))""",
    },
    "dual-ma": {
        "id": "dual-ma",
        "name": "Dual Moving Average",
        "description": "Golden cross strategy—bullish when 50-day crosses above 200-day moving average.",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "category": TemplateCategory.TREND,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["golden-cross", "moving-average", "crossover"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Dual Moving Average"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (group "Bull Market"
      (weight :method specified
        (asset SPY :weight 70)
        (asset QQQ :weight 30)))
    (else
      (group "Bear Market"
        (weight :method specified
          (asset TLT :weight 50)
          (asset SHY :weight 30)
          (asset GLD :weight 20))))))""",
    },
    "ma-crossover": {
        "id": "ma-crossover",
        "name": "Moving Average Crossover",
        "description": "Trend-following allocation using EMA crossovers.",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "category": TemplateCategory.TREND,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["trend", "ema", "crossover"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Moving Average Crossover"
  :rebalance daily
  :benchmark SPY
  (if (> (ema SPY 12) (ema SPY 26))
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))""",
    },
    "golden-cross": {
        "id": "golden-cross",
        "name": "Golden Cross",
        "description": "Allocate to equities when 50-day SMA crosses above 200-day SMA.",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "category": TemplateCategory.TREND,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["trend", "sma", "golden-cross"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Golden Cross"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (asset SPY :weight 100)
    (else (asset AGG :weight 100))))""",
    },
    "dual-momentum": {
        "id": "dual-momentum",
        "name": "Dual Momentum",
        "description": "Classic dual momentum: compare US vs International, allocate to winner or bonds.",
        "strategy_type": StrategyType.MOMENTUM,
        "category": TemplateCategory.TREND,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["momentum", "trend", "dual-momentum"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Dual Momentum"
  :rebalance monthly
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (asset SPY :weight 100)
    (else (if (> (sma EFA 50) (sma EFA 200))
      (asset EFA :weight 100)
      (else (asset AGG :weight 100))))))""",
    },
    "donchian-breakout": {
        "id": "donchian-breakout",
        "name": "Donchian Channel Breakout",
        "description": "Turtle trading inspired breakout strategy.",
        "strategy_type": StrategyType.BREAKOUT,
        "category": TemplateCategory.TREND,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["breakout", "donchian", "turtle"],
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
    # =========================================================================
    # MEAN REVERSION STRATEGIES
    # Counter-trend strategies
    # =========================================================================
    "rsi-mean-reversion": {
        "id": "rsi-mean-reversion",
        "name": "RSI Mean Reversion",
        "description": "Allocate to equities when oversold, bonds when overbought.",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "category": TemplateCategory.MEAN_REVERSION,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["mean-reversion", "rsi", "oscillator"],
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
    "bollinger-bounce": {
        "id": "bollinger-bounce",
        "name": "Bollinger Bounce",
        "description": "Mean reversion strategy using Bollinger Bands.",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "category": TemplateCategory.MEAN_REVERSION,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["mean-reversion", "bollinger", "bands"],
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
    "macd-strategy": {
        "id": "macd-strategy",
        "name": "MACD Momentum",
        "description": "Trade based on MACD histogram crossovers.",
        "strategy_type": StrategyType.MOMENTUM,
        "category": TemplateCategory.MEAN_REVERSION,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["momentum", "macd"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "MACD Momentum"
  :rebalance daily
  :benchmark SPY
  (if (> (macd SPY 12 26 9 :output histogram) 0)
    (asset SPY :weight 100)
    (else (asset SHY :weight 100))))""",
    },
    "pairs-trading": {
        "id": "pairs-trading",
        "name": "Pairs Trading",
        "description": "Mean reversion on correlated asset pairs (KO/PEP).",
        "strategy_type": StrategyType.MEAN_REVERSION,
        "category": TemplateCategory.MEAN_REVERSION,
        "asset_class": AssetClass.EQUITY,
        "tags": ["pairs", "mean-reversion", "statistical-arbitrage"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Pairs Trading"
  :rebalance daily
  :benchmark SPY
  (if (< (rsi KO 14) 30)
    (weight :method specified
      (asset KO :weight 50)
      (asset PEP :weight 50))
    (else (if (< (rsi PEP 14) 30)
      (weight :method specified
        (asset KO :weight 50)
        (asset PEP :weight 50))
      (else (asset SHY :weight 100))))))""",
    },
    # =========================================================================
    # ALTERNATIVES STRATEGIES
    # Non-traditional assets (Crypto, Managed Futures, Commodities)
    # =========================================================================
    "crypto-market-cap": {
        "id": "crypto-market-cap",
        "name": "Crypto Market Cap",
        "description": "Market-cap weighted allocation to top cryptocurrencies—BTC, ETH, SOL.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.ALTERNATIVES,
        "asset_class": AssetClass.CRYPTO,
        "tags": ["bitcoin", "ethereum", "market-cap"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "Crypto Market Cap"
  :rebalance weekly
  :benchmark BTCUSD
  (weight :method specified
    (asset BTC :weight 60)
    (asset ETH :weight 30)
    (asset SOL :weight 10)))""",
    },
    "defi-blue-chips": {
        "id": "defi-blue-chips",
        "name": "DeFi Blue Chips",
        "description": "Equal-weight allocation to leading DeFi protocol tokens with governance focus.",
        "strategy_type": StrategyType.ALLOCATION,
        "category": TemplateCategory.ALTERNATIVES,
        "asset_class": AssetClass.CRYPTO,
        "tags": ["defi", "governance", "protocols"],
        "difficulty": "beginner",
        "config_sexpr": """(strategy "DeFi Blue Chips"
  :rebalance weekly
  :benchmark ETHUSD
  (weight :method equal
    (asset UNI)
    (asset AAVE)
    (asset MKR)
    (asset LINK)))""",
    },
    "crypto-momentum-rotation": {
        "id": "crypto-momentum-rotation",
        "name": "Crypto Momentum Rotation",
        "description": "Rotate to top 3 cryptos by 90-day momentum.",
        "strategy_type": StrategyType.MOMENTUM,
        "category": TemplateCategory.ALTERNATIVES,
        "asset_class": AssetClass.CRYPTO,
        "tags": ["crypto", "momentum", "rotation"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Crypto Momentum Rotation"
  :rebalance weekly
  :benchmark BTCUSD
  (filter :by momentum :select (top 3) :lookback 90
    (weight :method momentum :lookback 90
      (asset BTC)
      (asset ETH)
      (asset SOL)
      (asset AVAX)
      (asset LINK))))""",
    },
    "crypto-trend-vol-filter": {
        "id": "crypto-trend-vol-filter",
        "name": "Crypto Trend Vol Filter",
        "description": "Crypto allocation with dual trend filters: BTC trend for core, ETH trend for altcoin satellite. Safety to stablecoins when down.",
        "strategy_type": StrategyType.REGIME,
        "category": TemplateCategory.ALTERNATIVES,
        "asset_class": AssetClass.CRYPTO,
        "tags": ["crypto", "trend", "volatility", "stablecoin"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Crypto Trend Vol Filter"
  :rebalance daily
  :benchmark BTCUSD
  (weight :method specified
    (group "BTC Core"
      (if (> (price BTC) (sma BTC 50))
        (asset BTC :weight 50)
        (else (asset USDC :weight 50))))
    (group "ETH Satellite"
      (if (> (price ETH) (sma ETH 50))
        (weight :method equal
          (asset ETH)
          (asset SOL)
          (asset AVAX))
        (else (asset USDC :weight 100))))))""",
    },
    "managed-futures-trend": {
        "id": "managed-futures-trend",
        "name": "Managed Futures Trend",
        "description": "CTA-style trend following via managed futures ETFs.",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "category": TemplateCategory.ALTERNATIVES,
        "asset_class": AssetClass.COMMODITY,
        "tags": ["managed-futures", "trend", "cta"],
        "difficulty": "intermediate",
        "config_sexpr": """(strategy "Managed Futures Trend"
  :rebalance monthly
  :benchmark SPY
  (weight :method inverse-volatility :lookback 60
    (asset DBMF)
    (asset KMLM)))""",
    },
    "commodity-momentum": {
        "id": "commodity-momentum",
        "name": "Commodity Momentum",
        "description": "Trend following across commodity sectors.",
        "strategy_type": StrategyType.MOMENTUM,
        "category": TemplateCategory.ALTERNATIVES,
        "asset_class": AssetClass.COMMODITY,
        "tags": ["commodity", "momentum", "trend"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Commodity Momentum"
  :rebalance monthly
  :benchmark DBC
  (filter :by momentum :select (top 2) :lookback 90
    (weight :method momentum :lookback 60
      (asset PDBC)
      (asset DBA)
      (asset DBE)
      (asset DBB))))""",
    },
    "global-macro-regime": {
        "id": "global-macro-regime",
        "name": "Global Macro Regime",
        "description": "Regime-based allocation using VIX for growth vs defensive positioning.",
        "strategy_type": StrategyType.REGIME,
        "category": TemplateCategory.ALTERNATIVES,
        "asset_class": AssetClass.MULTI_ASSET,
        "tags": ["macro", "regime", "vix"],
        "difficulty": "advanced",
        "config_sexpr": """(strategy "Global Macro Regime"
  :rebalance daily
  :benchmark SPY
  (if (< (price VIX) 20)
    (weight :method specified
      (asset SPY :weight 50)
      (asset DBC :weight 30)
      (asset GLD :weight 20))
    (else (if (< (price VIX) 30)
      (weight :method specified
        (asset SPY :weight 30)
        (asset TLT :weight 40)
        (asset GLD :weight 30))
      (else (weight :method specified
        (asset TLT :weight 50)
        (asset GLD :weight 40)
        (asset SHY :weight 10)))))))""",
    },
}


class TemplateService:
    """Service for strategy template operations."""

    async def list_templates(
        self,
        strategy_type: StrategyType | None = None,
        category: TemplateCategory | None = None,
        asset_class: AssetClass | None = None,
        difficulty: str | None = None,
    ) -> list[TemplateResponse]:
        """List available strategy templates.

        Args:
            strategy_type: Filter by strategy type
            category: Filter by template category
            asset_class: Filter by asset class
            difficulty: Filter by difficulty level (beginner, intermediate, advanced)

        Returns:
            List of TemplateResponse objects
        """
        templates = list(TEMPLATES.values())

        if strategy_type:
            templates = [t for t in templates if t["strategy_type"] == strategy_type]

        if category:
            templates = [t for t in templates if t["category"] == category]

        if asset_class:
            templates = [t for t in templates if t["asset_class"] == asset_class]

        if difficulty:
            templates = [t for t in templates if t["difficulty"] == difficulty]

        return [
            TemplateResponse(
                id=t["id"],
                name=t["name"],
                description=t["description"],
                strategy_type=t["strategy_type"],
                category=t["category"],
                asset_class=t["asset_class"],
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
            category=t["category"],
            asset_class=t["asset_class"],
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
