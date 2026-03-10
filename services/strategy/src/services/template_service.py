"""Template service - pre-built strategy templates using allocation-based S-expression DSL.

This is the SINGLE SOURCE OF TRUTH for all strategy templates.
Frontend fetches these via API and parses S-expressions into visual blocks.
"""

from typing import TypedDict

from llamatrade_proto.generated.strategy_pb2 import (
    ASSET_CLASS_COMMODITY,
    ASSET_CLASS_CRYPTO,
    ASSET_CLASS_EQUITY,
    ASSET_CLASS_FIXED_INCOME,
    ASSET_CLASS_MULTI_ASSET,
    ASSET_CLASS_OPTIONS,
    TEMPLATE_CATEGORY_ALTERNATIVES,
    TEMPLATE_CATEGORY_BUY_AND_HOLD,
    TEMPLATE_CATEGORY_FACTOR,
    TEMPLATE_CATEGORY_INCOME,
    TEMPLATE_CATEGORY_MEAN_REVERSION,
    TEMPLATE_CATEGORY_TACTICAL,
    TEMPLATE_CATEGORY_TREND,
    TEMPLATE_DIFFICULTY_ADVANCED,
    TEMPLATE_DIFFICULTY_BEGINNER,
    TEMPLATE_DIFFICULTY_INTERMEDIATE,
    AssetClass,
    TemplateCategory,
    TemplateDifficulty,
)

from src.models import TemplateResponse


class TemplateData(TypedDict):
    """Template data structure for internal storage."""

    id: str
    name: str
    description: str
    category: TemplateCategory.ValueType
    asset_class: AssetClass.ValueType
    tags: list[str]
    difficulty: TemplateDifficulty.ValueType
    config_sexpr: str


# =============================================================================
# CURATED STRATEGY TEMPLATES (56 total)
# Quality over quantity - each template properly matches its difficulty level
# =============================================================================

TEMPLATES: dict[str, TemplateData] = {
    # =========================================================================
    # BUY-AND-HOLD STRATEGIES (8)
    # Static allocations with periodic rebalancing
    # =========================================================================
    "classic-60-40": {
        "id": "classic-60-40",
        "name": "Classic 60/40",
        "description": "The foundational portfolio—60% stocks, 40% bonds. Simple, time-tested, effective.",
        "category": TEMPLATE_CATEGORY_BUY_AND_HOLD,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["classic", "balanced"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Classic 60/40"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Equities" :weight 60
      (weight :method equal
        (asset VTI)
        (asset VEA)
        (asset VWO)))
    (group "Bonds" :weight 40
      (weight :method equal
        (asset BND)
        (asset BNDX)))))""",
    },
    "three-fund": {
        "id": "three-fund",
        "name": "Three-Fund Portfolio",
        "description": "Bogleheads classic—total US market, international, and bonds for maximum diversification.",
        "category": TEMPLATE_CATEGORY_BUY_AND_HOLD,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["bogleheads", "diversified"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Three-Fund Portfolio"
  :rebalance quarterly
  :benchmark VTI
  (weight :method specified
    (group "US Equities" :weight 50
      (weight :method specified
        (asset VTI :weight 80)
        (asset VXF :weight 20)))
    (group "International" :weight 30
      (weight :method equal
        (asset VXUS)
        (asset VEA)
        (asset VWO)))
    (group "Fixed Income" :weight 20
      (weight :method equal
        (asset BND)
        (asset BNDX)))))""",
    },
    "permanent-portfolio": {
        "id": "permanent-portfolio",
        "name": "Permanent Portfolio",
        "description": "Harry Browne's 4x25% allocation designed for all economic conditions—stocks, bonds, gold, cash.",
        "category": TEMPLATE_CATEGORY_BUY_AND_HOLD,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["all-weather", "harry-browne", "famous-portfolio"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Permanent Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Growth" :weight 25
      (weight :method equal
        (asset VTI)
        (asset VEA)))
    (group "Deflation Hedge" :weight 25
      (weight :method specified
        (asset TLT :weight 70)
        (asset EDV :weight 30)))
    (group "Inflation Hedge" :weight 25
      (weight :method equal
        (asset GLD)
        (asset IAU)))
    (group "Cash" :weight 25
      (weight :method equal
        (asset SHY)
        (asset BIL)))))""",
    },
    "all-weather": {
        "id": "all-weather",
        "name": "All-Weather Portfolio",
        "description": "Ray Dalio inspired diversified allocation for all economic conditions.",
        "category": TEMPLATE_CATEGORY_BUY_AND_HOLD,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["all-weather", "ray-dalio", "famous-portfolio"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "All-Weather Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Equities" :weight 30
      (weight :method equal
        (asset VTI)
        (asset VEA)
        (asset VWO)))
    (group "Long Bonds" :weight 40
      (weight :method specified
        (asset TLT :weight 60)
        (asset EDV :weight 40)))
    (group "Intermediate Bonds" :weight 15
      (weight :method equal
        (asset IEF)
        (asset VGIT)))
    (group "Commodities" :weight 15
      (weight :method equal
        (asset GLD)
        (asset DBC)
        (asset PDBC)))))""",
    },
    "golden-butterfly": {
        "id": "golden-butterfly",
        "name": "Golden Butterfly",
        "description": "Balanced allocation with small-cap value tilt—total market, SCV, long bonds, short bonds, gold.",
        "category": TEMPLATE_CATEGORY_BUY_AND_HOLD,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["all-weather", "small-cap-value", "famous-portfolio"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Golden Butterfly"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Large Cap" :weight 20
      (weight :method equal
        (asset VTI)
        (asset VOO)))
    (group "Small Cap Value" :weight 20
      (weight :method equal
        (asset IJS)
        (asset AVUV)
        (asset VBR)))
    (group "Long Bonds" :weight 20
      (weight :method specified
        (asset TLT :weight 60)
        (asset EDV :weight 40)))
    (group "Short Bonds" :weight 20
      (weight :method equal
        (asset SHY)
        (asset VGSH)
        (asset BIL)))
    (group "Gold" :weight 20
      (weight :method equal
        (asset GLD)
        (asset IAU)))))""",
    },
    "core-satellite": {
        "id": "core-satellite",
        "name": "Core-Satellite",
        "description": "Stable core of index funds combined with satellite positions in higher-conviction plays.",
        "category": TEMPLATE_CATEGORY_BUY_AND_HOLD,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["core-satellite", "hybrid"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Core-Satellite"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Core" :weight 70
      (weight :method specified
        (group "US Large" :weight 50
          (weight :method equal
            (asset VTI)
            (asset VOO)
            (asset IVV)))
        (group "International" :weight 20
          (weight :method equal
            (asset VXUS)
            (asset VEA)
            (asset VWO)))
        (group "Bonds" :weight 30
          (weight :method equal
            (asset BND)
            (asset AGG)
            (asset BNDX)))))
    (group "Satellite" :weight 30
      (weight :method momentum :lookback 60
        (asset QQQ)
        (asset ARKK)
        (asset VNQ)
        (asset SMH)
        (asset XBI)))))""",
    },
    "risk-parity": {
        "id": "risk-parity",
        "name": "Risk Parity",
        "description": "Allocate by risk contribution using inverse volatility—equal risk across asset classes.",
        "category": TEMPLATE_CATEGORY_BUY_AND_HOLD,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["risk-parity", "all-weather"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Risk Parity"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Equities" :weight 25
      (weight :method inverse-volatility :lookback 60
        (asset SPY)
        (asset VEA)
        (asset VWO)
        (asset IWM)))
    (group "Fixed Income" :weight 25
      (weight :method inverse-volatility :lookback 60
        (asset TLT)
        (asset IEF)
        (asset LQD)
        (asset TIP)))
    (group "Commodities" :weight 25
      (weight :method inverse-volatility :lookback 60
        (asset GLD)
        (asset DBC)
        (asset USO)
        (asset UNG)))
    (group "Alternatives" :weight 25
      (weight :method inverse-volatility :lookback 60
        (asset VNQ)
        (asset VNQI)
        (asset DBMF)))))""",
    },
    "adaptive-asset-allocation": {
        "id": "adaptive-asset-allocation",
        "name": "Adaptive Asset Allocation",
        "description": "Dynamic allocation based on momentum and volatility signals across asset classes.",
        "category": TEMPLATE_CATEGORY_BUY_AND_HOLD,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["adaptive", "momentum", "volatility", "dynamic"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Adaptive Asset Allocation"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Risk Assets" :weight 60
      (filter :by momentum :select (top 3) :lookback 90
        (weight :method inverse-volatility :lookback 60
          (asset SPY)
          (asset VEA)
          (asset VWO)
          (asset VNQ)
          (asset DBC))))
    (group "Safe Assets" :weight 40
      (filter :by momentum :select (top 2) :lookback 60
        (weight :method inverse-volatility :lookback 60
          (asset TLT)
          (asset IEF)
          (asset GLD)
          (asset SHY))))))""",
    },
    # =========================================================================
    # FACTOR STRATEGIES (8)
    # Factor-tilted strategies (momentum, value, quality, size)
    # =========================================================================
    "larry-portfolio": {
        "id": "larry-portfolio",
        "name": "Larry Portfolio",
        "description": "Larry Swedroe's factor-tilted allocation emphasizing small-cap value globally.",
        "category": TEMPLATE_CATEGORY_FACTOR,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["small-cap-value", "larry-swedroe", "famous-portfolio"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Larry Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "US Small Value" :weight 30
      (weight :method equal
        (asset AVUV)
        (asset IJS)
        (asset VBR)))
    (group "Intl Small Value" :weight 30
      (weight :method equal
        (asset AVDV)
        (asset DLS)
        (asset VSS)))
    (group "Emerging Value" :weight 10
      (weight :method equal
        (asset AVES)
        (asset DEM)))
    (group "Fixed Income" :weight 30
      (weight :method equal
        (asset BND)
        (asset BNDX)
        (asset TIP)))))""",
    },
    "multi-factor-smart-beta": {
        "id": "multi-factor-smart-beta",
        "name": "Multi-Factor Smart Beta",
        "description": "Combined Value + Momentum + Quality + Size factor exposure via ETFs.",
        "category": TEMPLATE_CATEGORY_FACTOR,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["smart-beta", "multi-factor"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Multi-Factor Smart Beta"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Value Factor" :weight 25
      (weight :method equal
        (asset VLUE)
        (asset VTV)
        (asset RPV)))
    (group "Momentum Factor" :weight 25
      (weight :method equal
        (asset MTUM)
        (asset PDP)))
    (group "Quality Factor" :weight 25
      (weight :method equal
        (asset QUAL)
        (asset SPHQ)))
    (group "Size Factor" :weight 25
      (weight :method equal
        (asset SIZE)
        (asset IJR)
        (asset VBR)))))""",
    },
    "momentum-sectors": {
        "id": "momentum-sectors",
        "name": "Momentum Sectors",
        "description": "Weight sectors by recent momentum—more allocation to stronger performers.",
        "category": TEMPLATE_CATEGORY_FACTOR,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["momentum", "sectors", "rotation"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Momentum Sectors"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Cyclical Sectors" :weight 50
      (filter :by momentum :select (top 3) :lookback 90
        (weight :method equal
          (asset XLK)
          (asset XLF)
          (asset XLI)
          (asset XLY)
          (asset XLC))))
    (group "Defensive Sectors" :weight 30
      (filter :by momentum :select (top 2) :lookback 90
        (weight :method equal
          (asset XLV)
          (asset XLP)
          (asset XLU)
          (asset XLRE))))
    (group "Commodity Sectors" :weight 20
      (weight :method momentum :lookback 60
        (asset XLE)
        (asset XLB)))))""",
    },
    "small-cap-value-tilt": {
        "id": "small-cap-value-tilt",
        "name": "Small-Cap Value Tilt",
        "description": "Size + value factor combination for enhanced returns.",
        "category": TEMPLATE_CATEGORY_FACTOR,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["factor", "small-cap-value"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Small-Cap Value Tilt"
  :rebalance monthly
  :benchmark IWM
  (weight :method specified
    (group "US Small Value Core" :weight 50
      (weight :method inverse-volatility :lookback 60
        (asset AVUV)
        (asset IJS)
        (asset VBR)
        (asset SLYV)))
    (group "Intl Small Value" :weight 30
      (weight :method inverse-volatility :lookback 60
        (asset AVDV)
        (asset DLS)
        (asset SCZ)))
    (group "Micro Cap" :weight 20
      (weight :method inverse-volatility :lookback 60
        (asset IWC)
        (asset FDM)))))""",
    },
    "deep-value": {
        "id": "deep-value",
        "name": "Deep Value",
        "description": "Concentrated value factor exposure with rotation to top performers.",
        "category": TEMPLATE_CATEGORY_FACTOR,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["factor", "value", "concentrated"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Deep Value"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Large Value" :weight 40
      (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
          (asset VTV)
          (asset RPV)
          (asset SPYV)
          (asset SCHV))))
    (group "Small Value" :weight 40
      (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
          (asset IJS)
          (asset VBR)
          (asset SLYV)
          (asset AVUV))))
    (group "Intl Value" :weight 20
      (filter :by momentum :select (top 1) :lookback 60
        (weight :method equal
          (asset EFV)
          (asset FNDF)
          (asset IVAL))))))""",
    },
    "sector-rsi-rotation": {
        "id": "sector-rsi-rotation",
        "name": "Sector RSI Rotation",
        "description": "Rotate into oversold sectors using RSI signals with momentum-weighted allocation.",
        "category": TEMPLATE_CATEGORY_FACTOR,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["rotation", "rsi", "sectors", "mean-reversion"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Sector RSI Rotation"
  :rebalance weekly
  :benchmark SPY
  (if (< (rsi XLK 14) 35)
    (group "Oversold Tech"
      (weight :method inverse-volatility :lookback 20
        (asset XLK)
        (asset SMH)
        (asset SOXX)
        (asset IGV)))
    (else
      (if (< (rsi XLF 14) 35)
        (group "Oversold Financials"
          (weight :method inverse-volatility :lookback 20
            (asset XLF)
            (asset KRE)
            (asset KBE)
            (asset IAI)))
        (else
          (if (< (rsi XLV 14) 35)
            (group "Oversold Healthcare"
              (weight :method inverse-volatility :lookback 20
                (asset XLV)
                (asset XBI)
                (asset IBB)
                (asset IHI)))
            (else
              (if (< (rsi XLE 14) 35)
                (group "Oversold Energy"
                  (weight :method inverse-volatility :lookback 20
                    (asset XLE)
                    (asset XOP)
                    (asset OIH)
                    (asset AMLP)))
                (else
                  (group "Default Momentum"
                    (filter :by momentum :select (top 4) :lookback 60
        (weight :method equal
                        (asset XLK)
                        (asset XLF)
                        (asset XLV)
                        (asset XLI)
                        (asset XLE)
                        (asset XLY))))))))))))""",
    },
    "international-value-momentum": {
        "id": "international-value-momentum",
        "name": "International Value Momentum",
        "description": "Combine value and momentum factors internationally with trend filter.",
        "category": TEMPLATE_CATEGORY_FACTOR,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["international", "value", "momentum", "multi-factor"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "International Value Momentum"
  :rebalance monthly
  :benchmark VEU
  (weight :method specified
    (group "Value Core" :weight 40
      (if (> (price VEU) (sma VEU 200))
        (weight :method inverse-volatility :lookback 60
          (asset EFV)
          (asset FNDF)
          (asset IVAL)
          (asset DEM))
        (else
          (weight :method equal
            (asset SHY)
            (asset BIL)))))
    (group "Momentum Satellite" :weight 35
      (if (> (price VEU) (sma VEU 200))
        (if (> (momentum VWO 60) (momentum VEA 60))
          (weight :method momentum :lookback 90
            (asset VWO)
            (asset IEMG)
            (asset EEM)
            (asset SCHE))
          (else
            (weight :method momentum :lookback 90
              (asset VEA)
              (asset EFA)
              (asset IEFA)
              (asset SCHF))))
        (else
          (weight :method equal
            (asset SHY)
            (asset BIL)))))
    (group "Regional Rotation" :weight 25
      (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
          (asset EWJ)
          (asset EWG)
          (asset EWU)
          (asset EWC)
          (asset EWA)
          (asset EWZ))))))""",
    },
    "factor-timing": {
        "id": "factor-timing",
        "name": "Factor Timing Strategy",
        "description": "Dynamic factor rotation: momentum vs value based on trend, low-vol vs size based on VIX, plus quality core.",
        "category": TEMPLATE_CATEGORY_FACTOR,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["factors", "timing", "rotation", "multi-factor"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Factor Timing Strategy"
  :rebalance weekly
  :benchmark SPY
  (weight :method specified
    (group "Trend Factor" :weight 25
      (if (> (price SPY) (sma SPY 200))
        (if (> (momentum MTUM 30) (momentum VLUE 30))
          (weight :method equal
            (asset MTUM)
            (asset PDP)
            (asset DWAS))
          (else
            (weight :method equal
              (asset VLUE)
              (asset VTV)
              (asset SCHV))))
        (else
          (weight :method equal
            (asset USMV)
            (asset SPLV)
            (asset ACWV)))))
    (group "Vol Factor" :weight 25
      (if (< (price VIX) 15)
        (weight :method inverse-volatility :lookback 30
          (asset SIZE)
          (asset IJR)
          (asset IWM)
          (asset SCHA))
        (else
          (if (< (price VIX) 25)
            (weight :method equal
              (asset USMV)
              (asset SPLV))
            (else
              (weight :method equal
                (asset SHY)
                (asset BIL)
                (asset MINT)))))))
    (group "Quality Core" :weight 30
      (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
          (asset QUAL)
          (asset SPHQ)
          (asset JQUA)
          (asset DGRW))))
    (group "Dividend Anchor" :weight 20
      (weight :method inverse-volatility :lookback 60
        (asset SCHD)
        (asset VIG)
        (asset NOBL)
        (asset SDY)))))""",
    },
    # =========================================================================
    # INCOME STRATEGIES (8)
    # Dividend and yield-focused strategies
    # =========================================================================
    "dividend-aristocrats": {
        "id": "dividend-aristocrats",
        "name": "Dividend Aristocrats",
        "description": "Blue-chip companies with 25+ years of consecutive dividend increases.",
        "category": TEMPLATE_CATEGORY_INCOME,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["dividends", "aristocrats", "blue-chip"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Dividend Aristocrats"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Dividend ETFs" :weight 40
      (weight :method equal
        (asset NOBL)
        (asset SDY)
        (asset VIG)
        (asset DGRO)))
    (group "Consumer Staples Aristocrats" :weight 30
      (weight :method equal
        (asset KO)
        (asset PEP)
        (asset PG)
        (asset CL)))
    (group "Healthcare Aristocrats" :weight 30
      (weight :method equal
        (asset JNJ)
        (asset ABT)
        (asset ADP)
        (asset MDT)))))""",
    },
    "quality-dividend": {
        "id": "quality-dividend",
        "name": "Quality Dividend",
        "description": "High-quality dividend growers with proven track records of increasing payouts.",
        "category": TEMPLATE_CATEGORY_INCOME,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["dividends", "quality", "dividend-growth"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Quality Dividend"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Dividend Growth" :weight 50
      (weight :method equal
        (asset DGRW)
        (asset SCHD)
        (asset VIG)
        (asset NOBL)))
    (group "Quality Income" :weight 30
      (weight :method equal
        (asset SPHD)
        (asset HDV)
        (asset DVY)))
    (group "International Dividend" :weight 20
      (weight :method equal
        (asset VIGI)
        (asset IDV)
        (asset SCHY)))))""",
    },
    "covered-call-income": {
        "id": "covered-call-income",
        "name": "Covered Call Income",
        "description": "Buy-write strategy using covered call ETFs for enhanced income generation.",
        "category": TEMPLATE_CATEGORY_INCOME,
        "asset_class": ASSET_CLASS_OPTIONS,
        "tags": ["covered-call", "options", "premium-income"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Covered Call Income"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Index Covered Calls" :weight 50
      (weight :method equal
        (asset XYLD)
        (asset QYLD)
        (asset DIVO)))
    (group "Active Premium" :weight 30
      (weight :method equal
        (asset JEPI)
        (asset JEPQ)))
    (group "Buffer Income" :weight 20
      (weight :method equal
        (asset NUSI)
        (asset PBP)))))""",
    },
    "reit-income": {
        "id": "reit-income",
        "name": "REIT Income",
        "description": "Diversified REIT income portfolio across property sectors.",
        "category": TEMPLATE_CATEGORY_INCOME,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["reits", "real-estate", "income", "diversified"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "REIT Income"
  :rebalance quarterly
  :benchmark VNQ
  (weight :method specified
    (group "Diversified REITs" :weight 40
      (weight :method equal
        (asset VNQ)
        (asset VNQI)
        (asset RWR)
        (asset USRT)))
    (group "Specialty REITs" :weight 35
      (weight :method equal
        (asset XLRE)
        (asset ICF)
        (asset IYR)))
    (group "Mortgage REITs" :weight 25
      (weight :method equal
        (asset REM)
        (asset MORT)))))""",
    },
    "income-focus": {
        "id": "income-focus",
        "name": "Income Focus",
        "description": "Maximize income through dividends, REITs, and high-yield bonds.",
        "category": TEMPLATE_CATEGORY_INCOME,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["dividends", "reits", "high-yield"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Income Focus"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Dividend Equities" :weight 35
      (weight :method inverse-volatility :lookback 60
        (asset SCHD)
        (asset VYM)
        (asset DVY)
        (asset HDV)
        (asset SPHD)))
    (group "REITs" :weight 25
      (weight :method inverse-volatility :lookback 60
        (asset VNQ)
        (asset VNQI)
        (asset RWR)
        (asset USRT)))
    (group "Fixed Income" :weight 25
      (weight :method inverse-volatility :lookback 60
        (asset HYG)
        (asset LQD)
        (asset VCIT)
        (asset VCLT)))
    (group "Preferred & MLPs" :weight 15
      (weight :method equal
        (asset PFF)
        (asset PFFD)
        (asset AMLP)))))""",
    },
    "dividend-growth-barbell": {
        "id": "dividend-growth-barbell",
        "name": "Dividend Growth Barbell",
        "description": "Barbell strategy combining stable dividend income with conditional growth exposure.",
        "category": TEMPLATE_CATEGORY_INCOME,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["dividends", "growth", "barbell", "conditional"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Dividend Growth Barbell"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Dividend Core" :weight 60
      (weight :method inverse-volatility :lookback 60
        (asset SCHD)
        (asset VIG)
        (asset NOBL)
        (asset DGRO)
        (asset DGRW)))
    (group "Growth Satellite" :weight 25
      (if (> (price SPY) (sma SPY 50))
        (if (> (momentum QQQ 30) (momentum VUG 30))
          (weight :method equal
            (asset QQQ)
            (asset QQQM)
            (asset VGT))
          (else
            (weight :method equal
              (asset VUG)
              (asset SCHG)
              (asset IWF))))
        (else
          (weight :method equal
            (asset SHY)
            (asset MINT)
            (asset BIL)))))
    (group "Defensive Anchor" :weight 15
      (weight :method equal
        (asset XLP)
        (asset XLU)
        (asset VPU)))))""",
    },
    "high-yield-rotation": {
        "id": "high-yield-rotation",
        "name": "High Yield Rotation",
        "description": "Rotate between high-yield sectors by spread and momentum signals.",
        "category": TEMPLATE_CATEGORY_INCOME,
        "asset_class": ASSET_CLASS_FIXED_INCOME,
        "tags": ["high-yield", "rotation", "spreads", "income"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "High Yield Rotation"
  :rebalance monthly
  :benchmark HYG
  (weight :method specified
    (group "Corporate High Yield" :weight 50
      (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
          (asset HYG)
          (asset JNK)
          (asset USHY)
          (asset SHYG)
          (asset HYLB))))
    (group "Emerging Markets Debt" :weight 30
      (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
          (asset EMB)
          (asset VWOB)
          (asset PCY)
          (asset EMLC))))
    (group "Floating Rate" :weight 20
      (weight :method equal
        (asset BKLN)
        (asset SRLN)
        (asset FLOT)))))""",
    },
    "income-regime-switch": {
        "id": "income-regime-switch",
        "name": "Income Regime Switch",
        "description": "Dynamic income allocation switching between rate-sensitive and equity income based on bond trends and equity momentum.",
        "category": TEMPLATE_CATEGORY_INCOME,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["regime", "rates", "switch", "income"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Income Regime Switch"
  :rebalance weekly
  :benchmark SPY
  (if (> (price TLT) (sma TLT 50))
    (if (> (momentum SCHD 60) 0)
      (group "Falling Rates + Strong Dividends"
        (weight :method specified
          (group "Duration" :weight 35
            (weight :method equal
              (asset TLT)
              (asset EDV)
              (asset ZROZ)))
          (group "Corporate Bonds" :weight 25
            (weight :method equal
              (asset VCLT)
              (asset LQD)
              (asset IGIB)))
          (group "Dividend Equity" :weight 40
            (weight :method inverse-volatility :lookback 30
              (asset SCHD)
              (asset VIG)
              (asset NOBL)
              (asset DGRO)))))
      (else
        (group "Falling Rates + Weak Dividends"
          (weight :method specified
            (group "Long Duration" :weight 50
              (weight :method equal
                (asset TLT)
                (asset EDV)
                (asset ZROZ)))
            (group "Investment Grade" :weight 30
              (weight :method equal
                (asset VCLT)
                (asset LQD)))
            (group "Cash" :weight 20
              (weight :method equal
                (asset SHY)
                (asset BIL)
                (asset MINT)))))))
    (else
      (if (> (momentum VNQ 60) (momentum SCHD 60))
        (group "Rising Rates + Strong REITs"
          (weight :method specified
            (group "REITs" :weight 45
              (weight :method inverse-volatility :lookback 30
                (asset VNQ)
                (asset VNQI)
                (asset RWR)
                (asset USRT)))
            (group "Dividends" :weight 35
              (weight :method equal
                (asset SCHD)
                (asset VIG)
                (asset NOBL)))
            (group "Short Duration" :weight 20
              (weight :method equal
                (asset SHY)
                (asset VGSH)
                (asset BIL)))))
        (else
          (group "Rising Rates + Weak REITs"
            (weight :method specified
              (group "Dividend Focus" :weight 55
                (weight :method inverse-volatility :lookback 30
                  (asset SCHD)
                  (asset VIG)
                  (asset NOBL)
                  (asset DGRO)
                  (asset HDV)))
              (group "Floating Rate" :weight 25
                (weight :method equal
                  (asset BKLN)
                  (asset SRLN)
                  (asset FLOT)))
              (group "Cash" :weight 20
                (weight :method equal
                  (asset SHY)
                  (asset BIL)))))))))""",
    },
    # =========================================================================
    # TACTICAL STRATEGIES (8)
    # Market timing and regime-based switching
    # =========================================================================
    "tail-risk-hedged": {
        "id": "tail-risk-hedged",
        "name": "Tail Risk Hedged",
        "description": "Core equity exposure with tail hedge allocation for crash protection.",
        "category": TEMPLATE_CATEGORY_TACTICAL,
        "asset_class": ASSET_CLASS_OPTIONS,
        "tags": ["hedged", "tail-risk", "crash-protection"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Tail Risk Hedged"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Equity Core" :weight 75
      (weight :method equal
        (asset SPY)
        (asset VTI)
        (asset VOO)))
    (group "Tail Hedge" :weight 15
      (weight :method equal
        (asset TAIL)
        (asset VIXY)))
    (group "Bond Ballast" :weight 10
      (weight :method equal
        (asset TLT)
        (asset IEF)))))""",
    },
    "simple-defensive": {
        "id": "simple-defensive",
        "name": "Simple Defensive",
        "description": "Simple SPY/TLT 50/50 allocation with VIX-triggered defensive shift.",
        "category": TEMPLATE_CATEGORY_TACTICAL,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["defensive", "simple", "vix", "beginner"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Simple Defensive"
  :rebalance daily
  :benchmark SPY
  (if (> (price VIX) 30)
    (group "High Vol Defensive"
      (weight :method specified
        (group "Minimal Equity" :weight 20
          (weight :method equal
            (asset SPY)
            (asset USMV)))
        (group "Safety" :weight 80
          (weight :method inverse-volatility :lookback 20
            (asset TLT)
            (asset IEF)
            (asset GLD)
            (asset SHY)))))
    (else
      (if (> (price VIX) 20)
        (group "Moderate Vol"
          (weight :method specified
            (group "Equity" :weight 40
              (weight :method equal
                (asset SPY)
                (asset VTI)))
            (group "Bonds" :weight 60
              (weight :method equal
                (asset TLT)
                (asset IEF)
                (asset AGG)))))
        (else
          (group "Low Vol Risk On"
            (weight :method specified
              (group "Equity" :weight 60
                (weight :method equal
                  (asset SPY)
                  (asset VTI)
                  (asset QQQ)))
              (group "Bonds" :weight 40
                (weight :method equal
                  (asset TLT)
                  (asset IEF)))))))))""",
    },
    "volatility-regime": {
        "id": "volatility-regime",
        "name": "Volatility Regime",
        "description": "Adjust allocation based on VIX levels—aggressive in low vol, defensive in high vol.",
        "category": TEMPLATE_CATEGORY_TACTICAL,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["vix", "regime", "volatility"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Volatility Regime"
  :rebalance daily
  :benchmark SPY
  (if (> (price VIX) 35)
    (group "Crisis Mode"
      (weight :method specified
        (group "Safety First" :weight 50
          (weight :method equal
            (asset SHY)
            (asset BIL)
            (asset MINT)))
        (group "Flight to Quality" :weight 30
          (weight :method equal
            (asset TLT)
            (asset IEF)
            (asset VGIT)))
        (group "Hard Assets" :weight 20
          (weight :method equal
            (asset GLD)
            (asset IAU)))))
    (else
      (if (> (price VIX) 25)
        (group "High Alert"
          (weight :method specified
            (group "Defensive Equity" :weight 35
              (weight :method inverse-volatility :lookback 20
                (asset USMV)
                (asset SPLV)
                (asset XLP)
                (asset XLU)))
            (group "Duration" :weight 40
              (weight :method equal
                (asset TLT)
                (asset IEF)
                (asset AGG)))
            (group "Hedges" :weight 25
              (weight :method equal
                (asset GLD)
                (asset SHY)))))
        (else
          (if (> (price VIX) 18)
            (group "Cautious"
              (weight :method specified
                (group "Broad Equity" :weight 50
                  (weight :method equal
                    (asset SPY)
                    (asset VTI)
                    (asset VOO)))
                (group "Bonds" :weight 35
                  (weight :method equal
                    (asset TLT)
                    (asset IEF)
                    (asset AGG)))
                (group "Alternatives" :weight 15
                  (weight :method equal
                    (asset GLD)
                    (asset VNQ)))))
            (else
              (group "Risk On"
                (weight :method specified
                  (group "Growth Equity" :weight 60
                    (weight :method momentum :lookback 60
                      (asset SPY)
                      (asset QQQ)
                      (asset IWM)
                      (asset VWO)))
                  (group "Factor Tilt" :weight 25
                    (weight :method momentum :lookback 60
                      (asset MTUM)
                      (asset SIZE)
                      (asset QUAL)))
                  (group "Minimal Bonds" :weight 15
                    (weight :method equal
                      (asset TLT)
                      (asset IEF)))))))))))""",
    },
    "sector-rotation-tactical": {
        "id": "sector-rotation-tactical",
        "name": "Sector Rotation Tactical",
        "description": "Rotate into top 3 sectors by momentum with trend filter.",
        "category": TEMPLATE_CATEGORY_TACTICAL,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["sectors", "rotation", "momentum", "tactical"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Sector Rotation Tactical"
  :rebalance weekly
  :benchmark SPY
  (if (> (price SPY) (sma SPY 200))
    (if (> (price SPY) (sma SPY 50))
      (group "Strong Uptrend"
        (weight :method specified
          (group "Top Cyclicals" :weight 60
            (filter :by momentum :select (top 3) :lookback 90
        (weight :method equal
                (asset XLK)
                (asset XLF)
                (asset XLI)
                (asset XLY)
                (asset XLC))))
          (group "Top Defensives" :weight 25
            (filter :by momentum :select (top 2) :lookback 90
        (weight :method equal
                (asset XLV)
                (asset XLP)
                (asset XLU))))
          (group "Commodities" :weight 15
            (weight :method momentum :lookback 60
              (asset XLE)
              (asset XLB)))))
      (else
        (group "Weakening Uptrend"
          (weight :method specified
            (group "Quality Sectors" :weight 50
              (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
                  (asset XLK)
                  (asset XLV)
                  (asset XLP))))
            (group "Bond Buffer" :weight 30
              (weight :method equal
                (asset IEF)
                (asset TLT)
                (asset AGG)))
            (group "Gold Hedge" :weight 20
              (weight :method equal
                (asset GLD)
                (asset IAU)))))))
    (else
      (if (< (price SPY) (sma SPY 50))
        (group "Strong Downtrend"
          (weight :method specified
            (group "Full Defense" :weight 70
              (weight :method inverse-volatility :lookback 20
                (asset SHY)
                (asset IEF)
                (asset TLT)
                (asset BIL)))
            (group "Safe Havens" :weight 30
              (weight :method equal
                (asset GLD)
                (asset IAU)
                (asset TAIL)))))
        (else
          (group "Bottoming"
            (weight :method specified
              (group "Defensive Equity" :weight 40
                (weight :method inverse-volatility :lookback 30
                  (asset XLP)
                  (asset XLU)
                  (asset XLV)
                  (asset USMV)))
              (group "Duration" :weight 40
                (weight :method equal
                  (asset TLT)
                  (asset IEF)
                  (asset AGG)))
              (group "Gold" :weight 20
                (weight :method equal
                  (asset GLD)
                  (asset IAU)))))))))""",
    },
    "macd-regime-tactical": {
        "id": "macd-regime-tactical",
        "name": "MACD Regime Tactical",
        "description": "Use MACD histogram for market regime detection—positive histogram is risk-on, negative is defensive.",
        "category": TEMPLATE_CATEGORY_TACTICAL,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["macd", "histogram", "regime", "tactical"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "MACD Regime Tactical"
  :rebalance daily
  :benchmark SPY
  (if (> (macd SPY 12 26 9 :output histogram) 0)
    (if (> (price SPY) (sma SPY 200))
      (group "Strong Bull"
        (weight :method specified
          (group "Growth Core" :weight 50
            (weight :method momentum :lookback 60
              (asset SPY)
              (asset QQQ)
              (asset VGT)
              (asset SMH)))
          (group "International" :weight 25
            (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
                (asset VEA)
                (asset VWO)
                (asset EFA))))
          (group "Small Bonds" :weight 25
            (weight :method equal
              (asset TLT)
              (asset IEF)))))
      (else
        (group "Recovery Phase"
          (weight :method specified
            (group "Broad Equity" :weight 40
              (weight :method equal
                (asset SPY)
                (asset VTI)
                (asset VOO)))
            (group "Bonds" :weight 40
              (weight :method equal
                (asset TLT)
                (asset IEF)
                (asset AGG)))
            (group "Alternatives" :weight 20
              (weight :method equal
                (asset GLD)
                (asset VNQ)))))))
    (else
      (if (> (price SPY) (sma SPY 200))
        (group "Weakening Bull"
          (weight :method specified
            (group "Defensive Equity" :weight 35
              (weight :method inverse-volatility :lookback 30
                (asset USMV)
                (asset SPLV)
                (asset XLP)
                (asset XLU)))
            (group "Duration" :weight 40
              (weight :method equal
                (asset TLT)
                (asset IEF)
                (asset VGIT)))
            (group "Hedges" :weight 25
              (weight :method equal
                (asset GLD)
                (asset SHY)))))
        (else
          (group "Bear Market"
            (weight :method specified
              (group "Flight to Safety" :weight 50
                (weight :method inverse-volatility :lookback 20
                  (asset TLT)
                  (asset IEF)
                  (asset SHY)
                  (asset BIL)))
              (group "Hard Assets" :weight 35
                (weight :method equal
                  (asset GLD)
                  (asset IAU)
                  (asset TIP)))
              (group "Cash" :weight 15
                (weight :method equal
                  (asset MINT)
                  (asset BIL)))))))))""",
    },
    "multi-regime-adaptive": {
        "id": "multi-regime-adaptive",
        "name": "Multi-Regime Adaptive Allocation",
        "description": "Three-tier VIX regime system: crisis mode (defensive), cautious mode (balanced), risk-on mode (aggressive).",
        "category": TEMPLATE_CATEGORY_TACTICAL,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["regime", "vix", "adaptive", "multi-tier"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Multi-Regime Adaptive"
  :rebalance daily
  :benchmark SPY
  (if (> (price VIX) 35)
    (group "Crisis Mode"
      (weight :method specified
        (group "Cash & Short Duration" :weight 45
          (weight :method equal
            (asset SHY)
            (asset BIL)
            (asset MINT)
            (asset VGSH)))
        (group "Long Duration" :weight 30
          (weight :method equal
            (asset TLT)
            (asset EDV)
            (asset ZROZ)))
        (group "Gold & Hedges" :weight 25
          (weight :method equal
            (asset GLD)
            (asset IAU)
            (asset TAIL)))))
    (else
      (if (> (price VIX) 25)
        (group "High Caution Mode"
          (weight :method specified
            (group "Defensive Equity" :weight 30
              (weight :method inverse-volatility :lookback 20
                (asset USMV)
                (asset SPLV)
                (asset XLP)
                (asset XLU)
                (asset XLV)))
            (group "Quality Bonds" :weight 45
              (weight :method equal
                (asset TLT)
                (asset IEF)
                (asset AGG)
                (asset VGIT)))
            (group "Alternatives" :weight 25
              (weight :method equal
                (asset GLD)
                (asset VNQ)
                (asset TIP)))))
        (else
          (if (> (price VIX) 18)
            (group "Cautious Mode"
              (weight :method specified
                (group "Broad Equity" :weight 45
                  (weight :method equal
                    (asset SPY)
                    (asset VTI)
                    (asset VOO)
                    (asset VEA)))
                (group "Bonds" :weight 35
                  (weight :method equal
                    (asset TLT)
                    (asset IEF)
                    (asset AGG)))
                (group "Alternatives" :weight 20
                  (weight :method equal
                    (asset GLD)
                    (asset VNQ)
                    (asset DBC)))))
            (else
              (group "Risk-On Mode"
                (weight :method specified
                  (group "Growth Equity" :weight 55
                    (weight :method momentum :lookback 60
                      (asset SPY)
                      (asset QQQ)
                      (asset IWM)
                      (asset VWO)
                      (asset VEA)))
                  (group "Factor Exposure" :weight 25
                    (filter :by momentum :select (top 3) :lookback 60
        (weight :method equal
                        (asset MTUM)
                        (asset SIZE)
                        (asset QUAL)
                        (asset VLUE))))
                  (group "Minimal Bonds" :weight 20
                    (weight :method equal
                      (asset TLT)
                      (asset IEF)
                      (asset VNQ)))))))))))""",
    },
    "global-macro-multi-asset": {
        "id": "global-macro-multi-asset",
        "name": "Global Macro Multi-Asset",
        "description": "Institutional-style global macro: US/International equity rotation, inflation-protected bonds, trend-filtered commodities.",
        "category": TEMPLATE_CATEGORY_TACTICAL,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["global", "macro", "rotation", "institutional"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Global Macro Multi-Asset"
  :rebalance weekly
  :benchmark SPY
  (weight :method specified
    (group "Equity Rotation" :weight 35
      (if (> (momentum SPY 90) (momentum VEU 90))
        (if (> (price SPY) (sma SPY 200))
          (weight :method momentum :lookback 60
            (asset SPY)
            (asset QQQ)
            (asset VTI)
            (asset IWM))
          (else
            (weight :method inverse-volatility :lookback 30
              (asset SPY)
              (asset VTI)
              (asset USMV))))
        (else
          (if (> (price VEU) (sma VEU 200))
            (weight :method momentum :lookback 60
              (asset VEU)
              (asset VEA)
              (asset VWO)
              (asset EFA))
            (else
              (weight :method equal
                (asset SHY)
                (asset IEF)))))))
    (group "Inflation Protected" :weight 25
      (if (> (momentum TIP 60) 0)
        (weight :method equal
          (asset TIP)
          (asset VTIP)
          (asset SCHP)
          (asset STIP))
        (else
          (weight :method equal
            (asset IEF)
            (asset VGIT)))))
    (group "Commodities" :weight 25
      (if (> (price DBC) (sma DBC 100))
        (if (> (momentum GLD 60) (momentum DBC 60))
          (weight :method equal
            (asset GLD)
            (asset IAU)
            (asset SGOL))
          (else
            (weight :method momentum :lookback 60
              (asset DBC)
              (asset PDBC)
              (asset DBA)
              (asset DBE))))
        (else
          (weight :method equal
            (asset SHY)
            (asset BIL)))))
    (group "Trend Following" :weight 15
      (weight :method inverse-volatility :lookback 60
        (asset DBMF)
        (asset KMLM)
        (asset CTA)))))""",
    },
    "risk-on-off": {
        "id": "risk-on-off",
        "name": "Risk-On/Risk-Off Tactical",
        "description": "Switch between aggressive growth and defensive positions based on market regime.",
        "category": TEMPLATE_CATEGORY_TACTICAL,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["regime", "risk-management"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Risk-On/Risk-Off Tactical"
  :rebalance daily
  :benchmark SPY
  (weight :method specified
    (if (> (price SPY) (sma SPY 200))
      (if (> (price SPY) (sma SPY 50))
        (group "Full Risk On" :weight 85
          (weight :method specified
            (group "Growth Core" :weight 40
              (weight :method momentum :lookback 60
                (asset QQQ)
                (asset VGT)
                (asset SMH)
                (asset ARKK)
                (asset XBI)))
            (group "High Beta" :weight 35
              (filter :by momentum :select (top 4) :lookback 60
        (weight :method equal
                  (asset TSLA)
                  (asset NVDA)
                  (asset AMD)
                  (asset AMZN)
                  (asset GOOGL)
                  (asset META))))
            (group "International Growth" :weight 25
              (weight :method momentum :lookback 60
                (asset VWO)
                (asset EEM)
                (asset VEA)
                (asset EFA)))))
        (else
          (group "Cautious Risk On" :weight 85
            (weight :method specified
              (group "Quality Growth" :weight 50
                (weight :method inverse-volatility :lookback 30
                  (asset SPY)
                  (asset QQQ)
                  (asset VTI)
                  (asset QUAL)))
              (group "Defensive Growth" :weight 50
                (weight :method equal
                  (asset USMV)
                  (asset SPLV)
                  (asset XLV)
                  (asset XLP)))))))
      (else
        (if (> (price SPY) (sma SPY 50))
          (group "Early Recovery" :weight 85
            (weight :method specified
              (group "Broad Equity" :weight 50
                (weight :method equal
                  (asset SPY)
                  (asset VTI)
                  (asset VOO)))
              (group "Bonds" :weight 30
                (weight :method equal
                  (asset TLT)
                  (asset IEF)
                  (asset AGG)))
              (group "Gold" :weight 20
                (weight :method equal
                  (asset GLD)
                  (asset IAU)))))
          (else
            (group "Risk Off" :weight 85
              (weight :method specified
                (group "Treasuries" :weight 45
                  (weight :method inverse-volatility :lookback 20
                    (asset TLT)
                    (asset IEF)
                    (asset SHY)
                    (asset VGIT)))
                (group "Defensive Equity" :weight 25
                  (weight :method equal
                    (asset XLU)
                    (asset XLP)
                    (asset USMV)
                    (asset SPLV)))
                (group "Safe Havens" :weight 30
                  (weight :method equal
                    (asset GLD)
                    (asset IAU)
                    (asset TAIL)
                    (asset TIP))))))))
    (group "Core Anchor" :weight 15
      (weight :method inverse-volatility :lookback 60
        (asset VTI)
        (asset BND)
        (asset BNDX)
        (asset VNQ)))))""",
    },
    # =========================================================================
    # TREND-FOLLOWING STRATEGIES (8)
    # Trend-following and breakout strategies
    # =========================================================================
    "ma-crossover": {
        "id": "ma-crossover",
        "name": "Moving Average Crossover",
        "description": "Trend-following allocation using EMA crossovers.",
        "category": TEMPLATE_CATEGORY_TREND,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["trend", "ema", "crossover"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Moving Average Crossover"
  :rebalance daily
  :benchmark SPY
  (if (> (ema SPY 12) (ema SPY 26))
    (group "Risk On"
      (weight :method equal
        (asset SPY)
        (asset VTI)
        (asset VOO)))
    (else
      (group "Risk Off"
        (weight :method equal
          (asset TLT)
          (asset IEF)
          (asset SHY))))))""",
    },
    "dual-ma": {
        "id": "dual-ma",
        "name": "Dual Moving Average",
        "description": "Golden cross strategy—bullish when 50-day crosses above 200-day moving average.",
        "category": TEMPLATE_CATEGORY_TREND,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["golden-cross", "moving-average", "crossover"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Dual Moving Average"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (group "Bull Market"
      (weight :method specified
        (group "US Equity" :weight 60
          (weight :method momentum :lookback 60
            (asset SPY)
            (asset VTI)
            (asset VOO)
            (asset IVV)))
        (group "Growth Tilt" :weight 40
          (weight :method momentum :lookback 60
            (asset QQQ)
            (asset VGT)
            (asset IWF)))))
    (else
      (group "Bear Market"
        (weight :method specified
          (group "Duration" :weight 50
            (weight :method inverse-volatility :lookback 30
              (asset TLT)
              (asset IEF)
              (asset VGIT)
              (asset EDV)))
          (group "Cash & Gold" :weight 50
            (weight :method equal
              (asset SHY)
              (asset GLD)
              (asset IAU)
              (asset BIL))))))))""",
    },
    "dual-momentum": {
        "id": "dual-momentum",
        "name": "Dual Momentum",
        "description": "Classic dual momentum: compare US vs International, allocate to winner or bonds.",
        "category": TEMPLATE_CATEGORY_TREND,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["momentum", "trend", "dual-momentum"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Dual Momentum"
  :rebalance monthly
  :benchmark SPY
  (if (> (momentum SPY 252) 0)
    (if (> (momentum SPY 252) (momentum EFA 252))
      (group "US Equity"
        (weight :method specified
          (group "Large Cap" :weight 60
            (weight :method momentum :lookback 60
              (asset SPY)
              (asset VTI)
              (asset VOO)))
          (group "Mid/Small" :weight 40
            (weight :method momentum :lookback 60
              (asset IJH)
              (asset IWM)
              (asset VB)))))
      (else
        (group "International Equity"
          (weight :method specified
            (group "Developed" :weight 60
              (weight :method momentum :lookback 60
                (asset EFA)
                (asset VEA)
                (asset IEFA)
                (asset SCHF)))
            (group "Emerging" :weight 40
              (weight :method momentum :lookback 60
                (asset VWO)
                (asset EEM)
                (asset IEMG)))))))
    (else
      (group "Bonds"
        (weight :method specified
          (group "Treasury" :weight 60
            (weight :method inverse-volatility :lookback 30
              (asset AGG)
              (asset BND)
              (asset TLT)
              (asset IEF)))
          (group "Short Duration" :weight 40
            (weight :method equal
              (asset SHY)
              (asset VGSH)
              (asset BIL)))))))""",
    },
    "donchian-breakout": {
        "id": "donchian-breakout",
        "name": "Donchian Channel Breakout",
        "description": "Turtle trading inspired breakout strategy.",
        "category": TEMPLATE_CATEGORY_TREND,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["breakout", "donchian", "turtle"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Donchian Breakout"
  :rebalance daily
  :benchmark SPY
  (if (> (price SPY) (donchian SPY 20 :output upper))
    (group "Breakout Long"
      (weight :method specified
        (group "Core Equity" :weight 60
          (weight :method momentum :lookback 20
            (asset SPY)
            (asset QQQ)
            (asset IWM)
            (asset VTI)))
        (group "Leveraged Satellite" :weight 40
          (weight :method inverse-volatility :lookback 10
            (asset SSO)
            (asset QLD)
            (asset UWM)))))
    (else
      (if (< (price SPY) (donchian SPY 20 :output lower))
        (group "Breakdown Defensive"
          (weight :method specified
            (group "Treasuries" :weight 50
              (weight :method inverse-volatility :lookback 20
                (asset TLT)
                (asset IEF)
                (asset SHY)
                (asset VGIT)))
            (group "Safe Havens" :weight 50
              (weight :method equal
                (asset GLD)
                (asset IAU)
                (asset TAIL)
                (asset BIL)))))
        (else
          (group "Range Bound"
            (weight :method specified
              (group "Balanced Equity" :weight 50
                (weight :method inverse-volatility :lookback 30
                  (asset SPY)
                  (asset VTI)
                  (asset USMV)
                  (asset SPLV)))
              (group "Bonds" :weight 50
                (weight :method equal
                  (asset TLT)
                  (asset IEF)
                  (asset AGG)
                  (asset BND)))))))))""",
    },
    "multi-asset-trend": {
        "id": "multi-asset-trend",
        "name": "Multi-Asset Trend",
        "description": "Trend following across 4 major asset classes with individual trend filters.",
        "category": TEMPLATE_CATEGORY_TREND,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["multi-asset", "trend", "diversified"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Multi-Asset Trend"
  :rebalance weekly
  :benchmark SPY
  (weight :method specified
    (group "Equities" :weight 30
      (if (> (price SPY) (sma SPY 200))
        (if (> (momentum SPY 60) (momentum VEU 60))
          (weight :method momentum :lookback 60
            (asset SPY)
            (asset VTI)
            (asset QQQ)
            (asset IWM))
          (else
            (weight :method momentum :lookback 60
              (asset VEU)
              (asset VEA)
              (asset VWO)
              (asset EFA))))
        (else
          (weight :method equal
            (asset SHY)
            (asset BIL)
            (asset MINT)))))
    (group "Bonds" :weight 25
      (if (> (price TLT) (sma TLT 200))
        (weight :method inverse-volatility :lookback 30
          (asset TLT)
          (asset IEF)
          (asset EDV)
          (asset ZROZ))
        (else
          (weight :method equal
            (asset SHY)
            (asset VGSH)
            (asset BIL)))))
    (group "Gold" :weight 20
      (if (> (price GLD) (sma GLD 200))
        (weight :method equal
          (asset GLD)
          (asset IAU)
          (asset SGOL))
        (else
          (weight :method equal
            (asset SHY)
            (asset BIL)))))
    (group "Commodities" :weight 25
      (if (> (price DBC) (sma DBC 200))
        (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
            (asset DBC)
            (asset PDBC)
            (asset DBA)
            (asset DBE)
            (asset DBB)))
        (else
          (weight :method equal
            (asset SHY)
            (asset BIL)))))))""",
    },
    "turtle-trend-system": {
        "id": "turtle-trend-system",
        "name": "Turtle Trend System",
        "description": "Full turtle rules implementation with channel breakouts and position sizing.",
        "category": TEMPLATE_CATEGORY_TREND,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["turtle", "breakout", "position-sizing", "trend"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Turtle Trend System"
  :rebalance daily
  :benchmark SPY
  (if (> (price SPY) (donchian SPY 20 :output upper))
    (group "Long Entry"
      (weight :method specified
        (group "Core Positions" :weight 60
          (weight :method inverse-volatility :lookback 20
            (asset SPY)
            (asset QQQ)
            (asset IWM)
            (asset VEA)))
        (group "Commodity Trend" :weight 25
          (if (> (price GLD) (donchian GLD 20 :output upper))
            (weight :method equal
              (asset GLD)
              (asset DBC))
            (else
              (weight :method equal
                (asset SHY)
                (asset BIL)))))
        (group "Bond Trend" :weight 15
          (if (> (price TLT) (donchian TLT 20 :output upper))
            (weight :method equal
              (asset TLT)
              (asset IEF))
            (else
              (weight :method equal
                (asset SHY)
                (asset BIL)))))))
    (else
      (if (< (price SPY) (donchian SPY 10 :output lower))
        (group "Exit to Safety"
          (weight :method specified
            (group "Cash" :weight 50
              (weight :method equal
                (asset SHY)
                (asset BIL)
                (asset MINT)
                (asset VGSH)))
            (group "Safe Havens" :weight 50
              (weight :method inverse-volatility :lookback 20
                (asset TLT)
                (asset GLD)
                (asset IAU)
                (asset TAIL)))))
        (else
          (group "Hold Pattern"
            (weight :method specified
              (group "Reduced Equity" :weight 40
                (weight :method inverse-volatility :lookback 30
                  (asset SPY)
                  (asset VTI)
                  (asset USMV)))
              (group "Bonds" :weight 40
                (weight :method equal
                  (asset TLT)
                  (asset IEF)
                  (asset AGG)))
              (group "Gold" :weight 20
                (weight :method equal
                  (asset GLD)
                  (asset IAU)))))))))""",
    },
    "adaptive-trend-filter": {
        "id": "adaptive-trend-filter",
        "name": "Adaptive Trend Filter",
        "description": "ATR-based adaptive lookback for trend following with volatility adjustment.",
        "category": TEMPLATE_CATEGORY_TREND,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["adaptive", "atr", "trend", "volatility"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Adaptive Trend Filter"
  :rebalance daily
  :benchmark SPY
  (if (> (price VIX) 30)
    (group "High Vol Regime"
      (if (> (price SPY) (sma SPY 50))
        (weight :method specified
          (group "Short Lookback Long" :weight 50
            (weight :method inverse-volatility :lookback 10
              (asset SPY)
              (asset VTI)
              (asset USMV)))
          (group "Hedges" :weight 50
            (weight :method equal
              (asset TLT)
              (asset GLD)
              (asset SHY)
              (asset TAIL))))
        (else
          (weight :method specified
            (group "Defensive" :weight 70
              (weight :method inverse-volatility :lookback 10
                (asset TLT)
                (asset IEF)
                (asset SHY)
                (asset BIL)))
            (group "Safe Havens" :weight 30
              (weight :method equal
                (asset GLD)
                (asset IAU)
                (asset TAIL)))))))
    (else
      (if (> (price VIX) 20)
        (group "Medium Vol Regime"
          (if (> (price SPY) (sma SPY 100))
            (weight :method specified
              (group "Moderate Equity" :weight 60
                (weight :method inverse-volatility :lookback 30
                  (asset SPY)
                  (asset VTI)
                  (asset QQQ)
                  (asset USMV)))
              (group "Bonds" :weight 40
                (weight :method equal
                  (asset TLT)
                  (asset IEF)
                  (asset AGG))))
            (else
              (weight :method specified
                (group "Defensive Equity" :weight 40
                  (weight :method inverse-volatility :lookback 30
                    (asset USMV)
                    (asset SPLV)
                    (asset XLP)
                    (asset XLU)))
                (group "Bonds" :weight 60
                  (weight :method equal
                    (asset TLT)
                    (asset IEF)
                    (asset AGG)
                    (asset SHY)))))))
        (else
          (group "Low Vol Regime"
            (if (> (price SPY) (sma SPY 200))
              (weight :method specified
                (group "Full Risk" :weight 70
                  (weight :method momentum :lookback 60
                    (asset SPY)
                    (asset QQQ)
                    (asset IWM)
                    (asset VEA)
                    (asset VWO)))
                (group "Satellite" :weight 30
                  (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
                      (asset MTUM)
                      (asset SIZE)
                      (asset QUAL)
                      (asset VLUE)))))
              (else
                (weight :method specified
                  (group "Cautious" :weight 50
                    (weight :method equal
                      (asset SPY)
                      (asset VTI)
                      (asset USMV)))
                  (group "Bonds" :weight 50
                    (weight :method equal
                      (asset TLT)
                      (asset IEF)
                      (asset AGG)))))))))))""",
    },
    "trend-mean-reversion-hybrid": {
        "id": "trend-mean-reversion-hybrid",
        "name": "Trend Mean Reversion Hybrid",
        "description": "Trend core with mean reversion satellite for diversified alpha.",
        "category": TEMPLATE_CATEGORY_TREND,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["hybrid", "trend", "mean-reversion", "diversified"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Trend Mean Reversion Hybrid"
  :rebalance daily
  :benchmark SPY
  (weight :method specified
    (group "Trend Core" :weight 50
      (if (> (price SPY) (sma SPY 200))
        (if (> (momentum SPY 60) (momentum TLT 60))
          (weight :method momentum :lookback 60
            (asset SPY)
            (asset QQQ)
            (asset VTI)
            (asset IWM))
          (else
            (weight :method inverse-volatility :lookback 30
              (asset SPY)
              (asset VTI)
              (asset TLT)
              (asset IEF))))
        (else
          (weight :method inverse-volatility :lookback 30
            (asset TLT)
            (asset IEF)
            (asset GLD)
            (asset SHY)))))
    (group "Mean Reversion Satellite" :weight 35
      (if (< (rsi SPY 14) 25)
        (group "Deep Oversold"
          (weight :method specified
            (group "Aggressive Long" :weight 70
              (weight :method equal
                (asset SPY)
                (asset QQQ)
                (asset IWM)))
            (group "Leveraged" :weight 30
              (weight :method equal
                (asset SSO)
                (asset QLD)))))
        (else
          (if (< (rsi SPY 14) 35)
            (group "Oversold"
              (weight :method inverse-volatility :lookback 20
                (asset SPY)
                (asset VTI)
                (asset QQQ)
                (asset USMV)))
            (else
              (if (> (rsi SPY 14) 75)
                (group "Deep Overbought"
                  (weight :method inverse-volatility :lookback 20
                    (asset TLT)
                    (asset IEF)
                    (asset GLD)
                    (asset SHY)))
                (else
                  (if (> (rsi SPY 14) 65)
                    (group "Overbought"
                      (weight :method equal
                        (asset USMV)
                        (asset SPLV)
                        (asset TLT)
                        (asset IEF)))
                    (else
                      (group "Neutral"
                        (weight :method equal
                          (asset SPY)
                          (asset TLT)
                          (asset SHY))))))))))))
    (group "Anchor" :weight 15
      (weight :method inverse-volatility :lookback 60
        (asset VTI)
        (asset BND)
        (asset GLD)
        (asset VNQ)))))""",
    },
    # =========================================================================
    # MEAN REVERSION STRATEGIES (8)
    # Counter-trend strategies
    # =========================================================================
    "pullback-buyer": {
        "id": "pullback-buyer",
        "name": "Pullback Buyer",
        "description": "Buy 5% pullbacks in uptrending markets for mean reversion entries.",
        "category": TEMPLATE_CATEGORY_MEAN_REVERSION,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["pullback", "dip-buying", "beginner", "mean-reversion"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Pullback Buyer"
  :rebalance daily
  :benchmark SPY
  (if (> (price SPY) (sma SPY 200))
    (if (< (rsi SPY 5) 20)
      (group "Deep Oversold"
        (weight :method equal
          (asset SPY)
          (asset QQQ)
          (asset VTI)))
      (else
        (if (< (rsi SPY 5) 30)
          (group "Oversold"
            (weight :method equal
              (asset SPY)
              (asset VTI)))
          (else
            (group "Neutral"
              (weight :method equal
                (asset SHY)
                (asset BIL)
                (asset MINT)))))))
    (else
      (group "Downtrend Safety"
        (weight :method equal
          (asset SHY)
          (asset IEF)
          (asset TLT))))))""",
    },
    "macd-strategy": {
        "id": "macd-strategy",
        "name": "MACD Momentum",
        "description": "Trade based on MACD histogram crossovers.",
        "category": TEMPLATE_CATEGORY_MEAN_REVERSION,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["momentum", "macd"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "MACD Momentum"
  :rebalance daily
  :benchmark SPY
  (if (> (macd SPY 12 26 9 :output histogram) 0)
    (if (> (price SPY) (sma SPY 200))
      (group "Strong Long"
        (weight :method momentum :lookback 30
          (asset SPY)
          (asset QQQ)
          (asset VTI)
          (asset IWM)))
      (else
        (group "Cautious Long"
          (weight :method inverse-volatility :lookback 20
            (asset SPY)
            (asset VTI)
            (asset USMV)
            (asset SPLV)))))
    (else
      (if (> (price SPY) (sma SPY 200))
        (group "Weakening"
          (weight :method specified
            (group "Reduced Equity" :weight 40
              (weight :method equal
                (asset SPY)
                (asset USMV)))
            (group "Bonds" :weight 60
              (weight :method equal
                (asset TLT)
                (asset IEF)
                (asset SHY)))))
        (else
          (group "Defensive"
            (weight :method inverse-volatility :lookback 20
              (asset SHY)
              (asset IEF)
              (asset TLT)
              (asset GLD)))))))""",
    },
    "rsi-mean-reversion": {
        "id": "rsi-mean-reversion",
        "name": "RSI Mean Reversion",
        "description": "Allocate to equities when oversold, bonds when overbought.",
        "category": TEMPLATE_CATEGORY_MEAN_REVERSION,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["mean-reversion", "rsi", "oscillator"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "RSI Mean Reversion"
  :rebalance daily
  :benchmark SPY
  (if (< (rsi SPY 14) 25)
    (group "Deep Oversold Long"
      (weight :method specified
        (group "Core Long" :weight 70
          (weight :method equal
            (asset SPY)
            (asset QQQ)
            (asset VTI)))
        (group "Leverage Tilt" :weight 30
          (weight :method equal
            (asset SSO)
            (asset QLD)))))
    (else
      (if (< (rsi SPY 14) 35)
        (group "Oversold Long"
          (weight :method inverse-volatility :lookback 20
            (asset SPY)
            (asset VTI)
            (asset QQQ)
            (asset IWM)))
        (else
          (if (> (rsi SPY 14) 75)
            (group "Deep Overbought Defensive"
              (weight :method inverse-volatility :lookback 20
                (asset TLT)
                (asset IEF)
                (asset GLD)
                (asset SHY)))
            (else
              (if (> (rsi SPY 14) 65)
                (group "Overbought Cautious"
                  (weight :method specified
                    (group "Defensive Equity" :weight 40
                      (weight :method equal
                        (asset USMV)
                        (asset SPLV)
                        (asset XLP)))
                    (group "Bonds" :weight 60
                      (weight :method equal
                        (asset TLT)
                        (asset IEF)
                        (asset AGG)))))
                (else
                  (group "Neutral"
                    (weight :method specified
                      (group "Equity" :weight 50
                        (weight :method equal
                          (asset SPY)
                          (asset VTI)))
                      (group "Bonds" :weight 50
                        (weight :method equal
                          (asset TLT)
                          (asset IEF))))))))))))""",
    },
    "bollinger-bounce": {
        "id": "bollinger-bounce",
        "name": "Bollinger Bounce",
        "description": "Mean reversion strategy using Bollinger Bands.",
        "category": TEMPLATE_CATEGORY_MEAN_REVERSION,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["mean-reversion", "bollinger", "bands"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Bollinger Bounce"
  :rebalance daily
  :benchmark SPY
  (if (< (price SPY) (bbands SPY 20 2 :output lower))
    (if (> (price SPY) (sma SPY 200))
      (group "Oversold in Uptrend"
        (weight :method specified
          (group "Core Long" :weight 60
            (weight :method equal
              (asset SPY)
              (asset QQQ)
              (asset VTI)))
          (group "Momentum Tilt" :weight 40
            (weight :method momentum :lookback 20
              (asset IWM)
              (asset VWO)
              (asset VEA)))))
      (else
        (group "Oversold in Downtrend"
          (weight :method inverse-volatility :lookback 20
            (asset SPY)
            (asset VTI)
            (asset USMV)
            (asset SHY)))))
    (else
      (if (> (price SPY) (bbands SPY 20 2 :output upper))
        (if (> (price SPY) (sma SPY 200))
          (group "Overbought in Uptrend"
            (weight :method specified
              (group "Reduced Equity" :weight 50
                (weight :method equal
                  (asset SPY)
                  (asset USMV)
                  (asset SPLV)))
              (group "Bond Buffer" :weight 50
                (weight :method equal
                  (asset TLT)
                  (asset IEF)
                  (asset AGG)))))
          (else
            (group "Overbought in Downtrend"
              (weight :method inverse-volatility :lookback 20
                (asset TLT)
                (asset IEF)
                (asset GLD)
                (asset SHY)))))
        (else
          (group "Middle Band"
            (weight :method specified
              (group "Equity" :weight 50
                (weight :method equal
                  (asset SPY)
                  (asset VTI)
                  (asset VOO)))
              (group "Bonds" :weight 50
                (weight :method equal
                  (asset TLT)
                  (asset IEF)
                  (asset AGG)))))))))""",
    },
    "pairs-trading": {
        "id": "pairs-trading",
        "name": "Pairs Trading",
        "description": "Mean reversion on correlated asset pairs (KO/PEP).",
        "category": TEMPLATE_CATEGORY_MEAN_REVERSION,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["pairs", "mean-reversion", "statistical-arbitrage"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Pairs Trading"
  :rebalance daily
  :benchmark SPY
  (weight :method specified
    (group "Consumer Staples Pair" :weight 35
      (if (< (rsi KO 14) 30)
        (weight :method specified
          (asset KO :weight 70)
          (asset PEP :weight 30))
        (else
          (if (< (rsi PEP 14) 30)
            (weight :method specified
              (asset PEP :weight 70)
              (asset KO :weight 30))
            (else
              (weight :method equal
                (asset KO)
                (asset PEP)))))))
    (group "Tech Pair" :weight 35
      (if (< (rsi MSFT 14) 30)
        (weight :method specified
          (asset MSFT :weight 70)
          (asset AAPL :weight 30))
        (else
          (if (< (rsi AAPL 14) 30)
            (weight :method specified
              (asset AAPL :weight 70)
              (asset MSFT :weight 30))
            (else
              (weight :method equal
                (asset MSFT)
                (asset AAPL)))))))
    (group "Financial Pair" :weight 30
      (if (< (rsi JPM 14) 30)
        (weight :method specified
          (asset JPM :weight 70)
          (asset BAC :weight 30))
        (else
          (if (< (rsi BAC 14) 30)
            (weight :method specified
              (asset BAC :weight 70)
              (asset JPM :weight 30))
            (else
              (weight :method equal
                (asset JPM)
                (asset BAC)))))))))""",
    },
    "oversold-sectors": {
        "id": "oversold-sectors",
        "name": "Oversold Sectors",
        "description": "Buy oversold sector ETFs for sector-level mean reversion.",
        "category": TEMPLATE_CATEGORY_MEAN_REVERSION,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["sectors", "oversold", "mean-reversion"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Oversold Sectors"
  :rebalance weekly
  :benchmark SPY
  (if (> (price SPY) (sma SPY 200))
    (if (< (rsi XLK 14) 30)
      (group "Oversold Tech"
        (weight :method inverse-volatility :lookback 20
          (asset XLK)
          (asset SMH)
          (asset SOXX)
          (asset IGV)))
      (else
        (if (< (rsi XLF 14) 30)
          (group "Oversold Financials"
            (weight :method inverse-volatility :lookback 20
              (asset XLF)
              (asset KRE)
              (asset KBE)
              (asset IAI)))
          (else
            (if (< (rsi XLV 14) 30)
              (group "Oversold Healthcare"
                (weight :method inverse-volatility :lookback 20
                  (asset XLV)
                  (asset XBI)
                  (asset IBB)
                  (asset IHI)))
              (else
                (if (< (rsi XLE 14) 30)
                  (group "Oversold Energy"
                    (weight :method inverse-volatility :lookback 20
                      (asset XLE)
                      (asset XOP)
                      (asset OIH)
                      (asset AMLP)))
                  (else
                    (if (< (rsi XLI 14) 30)
                      (group "Oversold Industrials"
                        (weight :method inverse-volatility :lookback 20
                          (asset XLI)
                          (asset ITA)
                          (asset XAR)))
                      (else
                        (group "No Oversold - Cash"
                          (weight :method equal
                            (asset SHY)
                            (asset BIL)
                            (asset MINT)))))))))))))
    (else
      (group "Downtrend Safety"
        (weight :method inverse-volatility :lookback 20
          (asset SHY)
          (asset IEF)
          (asset TLT)
          (asset GLD))))))""",
    },
    "vix-term-structure": {
        "id": "vix-term-structure",
        "name": "VIX Term Structure",
        "description": "VIX contango/backwardation plays for volatility mean reversion.",
        "category": TEMPLATE_CATEGORY_MEAN_REVERSION,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["vix", "term-structure", "contango", "mean-reversion"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "VIX Term Structure"
  :rebalance daily
  :benchmark SPY
  (if (> (price VIX) 35)
    (group "Extreme Fear - Fade"
      (weight :method specified
        (group "Core Equity" :weight 50
          (weight :method inverse-volatility :lookback 10
            (asset SPY)
            (asset VTI)
            (asset QQQ)
            (asset IWM)))
        (group "Safe Haven Hedge" :weight 50
          (weight :method equal
            (asset TLT)
            (asset GLD)
            (asset SHY)
            (asset TAIL)))))
    (else
      (if (> (price VIX) 25)
        (group "High Fear"
          (weight :method specified
            (group "Equity" :weight 60
              (weight :method inverse-volatility :lookback 20
                (asset SPY)
                (asset VTI)
                (asset USMV)
                (asset SPLV)))
            (group "Bonds" :weight 40
              (weight :method equal
                (asset TLT)
                (asset IEF)
                (asset AGG)))))
        (else
          (if (> (price VIX) 18)
            (group "Moderate Fear"
              (weight :method specified
                (group "Equity" :weight 70
                  (weight :method momentum :lookback 60
                    (asset SPY)
                    (asset QQQ)
                    (asset VTI)
                    (asset IWM)))
                (group "Bonds" :weight 30
                  (weight :method equal
                    (asset TLT)
                    (asset IEF)))))
            (else
              (if (< (price VIX) 12)
                (group "Extreme Complacency"
                  (weight :method specified
                    (group "Reduced Equity" :weight 50
                      (weight :method equal
                        (asset SPY)
                        (asset USMV)
                        (asset SPLV)))
                    (group "Hedges" :weight 50
                      (weight :method equal
                        (asset TAIL)
                        (asset VIXY)
                        (asset TLT)
                        (asset GLD)))))
                (else
                  (group "Normal - Full Risk"
                    (weight :method specified
                      (group "Equity" :weight 80
                        (weight :method momentum :lookback 60
                          (asset SPY)
                          (asset QQQ)
                          (asset VTI)
                          (asset IWM)
                          (asset VEA)))
                      (group "Bonds" :weight 20
                        (weight :method equal
                          (asset TLT)
                          (asset IEF)))))))))))))""",
    },
    "double-oversold-reversion": {
        "id": "double-oversold-reversion",
        "name": "Double Oversold Reversion",
        "description": "Requires both RSI and Bollinger Band oversold confirmation—higher conviction mean reversion entries.",
        "category": TEMPLATE_CATEGORY_MEAN_REVERSION,
        "asset_class": ASSET_CLASS_EQUITY,
        "tags": ["double-confirmation", "rsi", "bollinger", "mean-reversion"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Double Oversold Reversion"
  :rebalance daily
  :benchmark SPY
  (if (> (price SPY) (sma SPY 200))
    (if (< (rsi SPY 14) 25)
      (if (< (price SPY) (bbands SPY 20 2.5 :output lower))
        (group "Double Confirm Deep Oversold"
          (weight :method specified
            (group "Core Long" :weight 50
              (weight :method equal
                (asset SPY)
                (asset QQQ)
                (asset VTI)))
            (group "Leverage Satellite" :weight 30
              (weight :method equal
                (asset SSO)
                (asset QLD)
                (asset UWM)))
            (group "High Beta" :weight 20
              (weight :method momentum :lookback 10
                (asset IWM)
                (asset VWO)
                (asset ARKK)))))
        (else
          (group "RSI Only Oversold"
            (weight :method inverse-volatility :lookback 15
              (asset SPY)
              (asset QQQ)
              (asset VTI)
              (asset IWM)))))
      (else
        (if (< (rsi SPY 14) 35)
          (if (< (price SPY) (bbands SPY 20 2 :output lower))
            (group "Moderate Double Confirm"
              (weight :method inverse-volatility :lookback 20
                (asset SPY)
                (asset VTI)
                (asset QQQ)
                (asset VOO)))
            (else
              (group "Light Oversold"
                (weight :method equal
                  (asset SPY)
                  (asset VTI)
                  (asset SHY)))))
          (else
            (if (> (rsi SPY 14) 75)
              (if (> (price SPY) (bbands SPY 20 2.5 :output upper))
                (group "Double Confirm Overbought"
                  (weight :method inverse-volatility :lookback 20
                    (asset TLT)
                    (asset IEF)
                    (asset GLD)
                    (asset SHY)))
                (else
                  (group "RSI Only Overbought"
                    (weight :method specified
                      (group "Defensive Equity" :weight 40
                        (weight :method equal
                          (asset USMV)
                          (asset SPLV)
                          (asset XLP)))
                      (group "Bonds" :weight 60
                        (weight :method equal
                          (asset TLT)
                          (asset IEF)
                          (asset SHY)))))))
              (else
                (group "Neutral Zone"
                  (weight :method specified
                    (group "Equity" :weight 60
                      (weight :method equal
                        (asset SPY)
                        (asset VTI)
                        (asset VOO)))
                    (group "Bonds" :weight 40
                      (weight :method equal
                        (asset IEF)
                        (asset AGG)))))))))))
    (else
      (group "Downtrend Protection"
        (weight :method inverse-volatility :lookback 20
          (asset SHY)
          (asset IEF)
          (asset TLT)
          (asset GLD)
          (asset TAIL))))))""",
    },
    # =========================================================================
    # ALTERNATIVES STRATEGIES (8)
    # Non-traditional assets (Crypto, Managed Futures, Commodities)
    # =========================================================================
    "crypto-market-cap": {
        "id": "crypto-market-cap",
        "name": "Crypto Market Cap",
        "description": "Market-cap weighted allocation to top cryptocurrencies—BTC, ETH, SOL.",
        "category": TEMPLATE_CATEGORY_ALTERNATIVES,
        "asset_class": ASSET_CLASS_CRYPTO,
        "tags": ["bitcoin", "ethereum", "market-cap"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Crypto Market Cap"
  :rebalance weekly
  :benchmark BTCUSD
  (weight :method specified
    (group "Large Cap" :weight 70
      (weight :method specified
        (asset BTC :weight 70)
        (asset ETH :weight 30)))
    (group "Mid Cap" :weight 30
      (weight :method equal
        (asset SOL)
        (asset AVAX)
        (asset MATIC)
        (asset DOT)))))""",
    },
    "real-assets-balanced": {
        "id": "real-assets-balanced",
        "name": "Real Assets Balanced",
        "description": "REITs, commodities, and TIPS for real asset exposure.",
        "category": TEMPLATE_CATEGORY_ALTERNATIVES,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["real-assets", "reits", "tips", "alternatives"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Real Assets Balanced"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Real Estate" :weight 30
      (weight :method equal
        (asset VNQ)
        (asset VNQI)
        (asset RWR)
        (asset USRT)))
    (group "Commodities" :weight 30
      (weight :method equal
        (asset DBC)
        (asset PDBC)
        (asset GLD)
        (asset DBA)))
    (group "Inflation Protected" :weight 25
      (weight :method equal
        (asset TIP)
        (asset VTIP)
        (asset SCHP)))
    (group "Precious Metals" :weight 15
      (weight :method equal
        (asset GLD)
        (asset IAU)
        (asset SLV)))))""",
    },
    "dragon-portfolio": {
        "id": "dragon-portfolio",
        "name": "Dragon Portfolio",
        "description": "Chris Cole's 100-year portfolio—stocks, bonds, gold, commodity trend, and long volatility for all regimes.",
        "category": TEMPLATE_CATEGORY_ALTERNATIVES,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["chris-cole", "artemis", "100-year", "famous-portfolio"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": """(strategy "Dragon Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Equity Growth" :weight 24
      (weight :method equal
        (asset VTI)
        (asset VEA)
        (asset VWO)))
    (group "Fixed Income" :weight 18
      (weight :method equal
        (asset TLT)
        (asset IEF)
        (asset AGG)))
    (group "Gold Store of Value" :weight 19
      (weight :method equal
        (asset GLD)
        (asset IAU)
        (asset SGOL)))
    (group "Commodity Trend" :weight 18
      (weight :method equal
        (asset DBMF)
        (asset KMLM)
        (asset CTA)))
    (group "Long Volatility" :weight 21
      (weight :method equal
        (asset TAIL)
        (asset VIXY)))))""",
    },
    "managed-futures-trend": {
        "id": "managed-futures-trend",
        "name": "Managed Futures Trend",
        "description": "CTA-style trend following via managed futures ETFs.",
        "category": TEMPLATE_CATEGORY_ALTERNATIVES,
        "asset_class": ASSET_CLASS_COMMODITY,
        "tags": ["managed-futures", "trend", "cta"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Managed Futures Trend"
  :rebalance monthly
  :benchmark SPY
  (weight :method specified
    (group "Core CTA" :weight 60
      (weight :method inverse-volatility :lookback 60
        (asset DBMF)
        (asset KMLM)
        (asset CTA)
        (asset WTMF)))
    (group "Commodity Trend" :weight 25
      (filter :by momentum :select (top 2) :lookback 60
        (weight :method equal
          (asset DBC)
          (asset PDBC)
          (asset GLD)
          (asset DBA))))
    (group "Cash Buffer" :weight 15
      (weight :method equal
        (asset SHY)
        (asset BIL)))))""",
    },
    "gold-miners-rotation": {
        "id": "gold-miners-rotation",
        "name": "Gold Miners Rotation",
        "description": "Gold vs miners rotation based on relative strength.",
        "category": TEMPLATE_CATEGORY_ALTERNATIVES,
        "asset_class": ASSET_CLASS_COMMODITY,
        "tags": ["gold", "miners", "rotation", "alternatives"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Gold Miners Rotation"
  :rebalance monthly
  :benchmark GLD
  (if (> (momentum GLD 60) (momentum GDX 60))
    (group "Physical Gold"
      (weight :method equal
        (asset GLD)
        (asset IAU)
        (asset SGOL)
        (asset AAAU)))
    (else
      (if (> (momentum GDX 60) (momentum GDXJ 60))
        (group "Senior Miners"
          (weight :method inverse-volatility :lookback 30
            (asset GDX)
            (asset RING)
            (asset SGDM)))
        (else
          (group "Junior Miners"
            (weight :method inverse-volatility :lookback 30
              (asset GDXJ)
              (asset GOEX)
              (asset SILJ))))))))""",
    },
    "commodity-momentum": {
        "id": "commodity-momentum",
        "name": "Commodity Momentum",
        "description": "Trend following across commodity sectors with momentum weighting.",
        "category": TEMPLATE_CATEGORY_ALTERNATIVES,
        "asset_class": ASSET_CLASS_COMMODITY,
        "tags": ["commodity", "momentum", "trend"],
        "difficulty": TEMPLATE_DIFFICULTY_INTERMEDIATE,
        "config_sexpr": """(strategy "Commodity Momentum"
  :rebalance monthly
  :benchmark DBC
  (weight :method specified
    (group "Energy" :weight 30
      (weight :method momentum :lookback 60
        (asset DBE)
        (asset USO)
        (asset UNG)
        (asset XLE)))
    (group "Agriculture" :weight 25
      (weight :method momentum :lookback 60
        (asset DBA)
        (asset CORN)
        (asset WEAT)
        (asset SOYB)))
    (group "Metals" :weight 25
      (weight :method momentum :lookback 60
        (asset GLD)
        (asset SLV)
        (asset DBB)
        (asset CPER)))
    (group "Broad" :weight 20
      (weight :method momentum :lookback 60
        (asset DBC)
        (asset PDBC)
        (asset GSG)))))""",
    },
    "global-macro-regime": {
        "id": "global-macro-regime",
        "name": "Global Macro Regime",
        "description": "Regime-based allocation using VIX for growth vs defensive positioning.",
        "category": TEMPLATE_CATEGORY_ALTERNATIVES,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["macro", "regime", "vix"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Global Macro Regime"
  :rebalance daily
  :benchmark SPY
  (if (< (price VIX) 15)
    (group "Risk On"
      (weight :method specified
        (group "Global Equity" :weight 50
          (weight :method momentum :lookback 60
            (asset SPY)
            (asset QQQ)
            (asset VEA)
            (asset VWO)
            (asset EEM)))
        (group "Commodities" :weight 35
          (weight :method momentum :lookback 60
            (asset DBC)
            (asset GLD)
            (asset DBA)
            (asset DBE)
            (asset DBB)))
        (group "Alternatives" :weight 15
          (weight :method equal
            (asset VNQ)
            (asset VNQI)))))
    (else
      (if (< (price VIX) 22)
        (group "Balanced"
          (weight :method specified
            (group "Equity" :weight 40
              (weight :method inverse-volatility :lookback 30
                (asset SPY)
                (asset VTI)
                (asset VEA)
                (asset USMV)))
            (group "Commodities" :weight 25
              (weight :method equal
                (asset GLD)
                (asset DBC)
                (asset TIP)))
            (group "Bonds" :weight 35
              (weight :method equal
                (asset TLT)
                (asset IEF)
                (asset AGG)))))
        (else
          (if (< (price VIX) 30)
            (group "Cautious"
              (weight :method specified
                (group "Defensive Equity" :weight 25
                  (weight :method inverse-volatility :lookback 20
                    (asset USMV)
                    (asset SPLV)
                    (asset XLP)
                    (asset XLU)))
                (group "Safe Haven" :weight 40
                  (weight :method equal
                    (asset TLT)
                    (asset IEF)
                    (asset GLD)
                    (asset IAU)))
                (group "Cash" :weight 35
                  (weight :method equal
                    (asset SHY)
                    (asset BIL)
                    (asset MINT)))))
            (else
              (group "Crisis"
                (weight :method specified
                  (group "Treasuries" :weight 45
                    (weight :method inverse-volatility :lookback 10
                      (asset TLT)
                      (asset IEF)
                      (asset SHY)
                      (asset EDV)))
                  (group "Gold" :weight 35
                    (weight :method equal
                      (asset GLD)
                      (asset IAU)
                      (asset SGOL)))
                  (group "Cash" :weight 20
                    (weight :method equal
                      (asset BIL)
                      (asset MINT)))))))))))""",
    },
    "crypto-trend-vol-filter": {
        "id": "crypto-trend-vol-filter",
        "name": "Crypto Trend Vol Filter",
        "description": "Crypto allocation with dual trend filters: BTC trend for core, ETH trend for altcoin satellite. Safety to stablecoins when down.",
        "category": TEMPLATE_CATEGORY_ALTERNATIVES,
        "asset_class": ASSET_CLASS_CRYPTO,
        "tags": ["crypto", "trend", "volatility", "stablecoin"],
        "difficulty": TEMPLATE_DIFFICULTY_ADVANCED,
        "config_sexpr": """(strategy "Crypto Trend Vol Filter"
  :rebalance daily
  :benchmark BTCUSD
  (weight :method specified
    (group "BTC Core" :weight 40
      (if (> (price BTC) (sma BTC 50))
        (if (> (price BTC) (sma BTC 200))
          (group "Strong BTC Trend"
            (weight :method specified
              (asset BTC :weight 80)
              (asset WBTC :weight 20)))
          (else
            (group "Weak BTC Trend"
              (weight :method equal
                (asset BTC)
                (asset USDC)))))
        (else
          (group "BTC Downtrend"
            (weight :method equal
              (asset USDC)
              (asset USDT))))))
    (group "ETH Ecosystem" :weight 35
      (if (> (price ETH) (sma ETH 50))
        (if (> (momentum ETH 30) (momentum BTC 30))
          (group "ETH Outperforming"
            (weight :method specified
              (group "Core ETH" :weight 60
                (asset ETH :weight 100))
              (group "L2s" :weight 40
                (weight :method equal
                  (asset MATIC)
                  (asset ARB)
                  (asset OP)))))
          (else
            (group "ETH Underperforming"
              (weight :method equal
                (asset ETH)
                (asset USDC)))))
        (else
          (group "ETH Downtrend"
            (weight :method equal
              (asset USDC)
              (asset USDT))))))
    (group "Alt Satellite" :weight 25
      (if (> (price ETH) (sma ETH 50))
        (if (> (price BTC) (sma BTC 50))
          (group "Risk On Alts"
            (filter :by momentum :select (top 3) :lookback 30
        (weight :method equal
                (asset SOL)
                (asset AVAX)
                (asset DOT)
                (asset LINK)
                (asset ATOM))))
          (else
            (group "Cautious Alts"
              (weight :method equal
                (asset SOL)
                (asset AVAX)
                (asset USDC)))))
        (else
          (group "Alt Downtrend"
            (weight :method equal
              (asset USDC)
              (asset USDT))))))))""",
    },
}


class TemplateService:
    """Service for strategy template operations."""

    async def list_templates(
        self,
        category: TemplateCategory.ValueType | None = None,
        asset_class: AssetClass.ValueType | None = None,
        difficulty: TemplateDifficulty.ValueType | None = None,
    ) -> list[TemplateResponse]:
        """List available strategy templates.

        Args:
            category: Filter by template category (proto enum value)
            asset_class: Filter by asset class (proto enum value)
            difficulty: Filter by difficulty level (proto enum value)

        Returns:
            List of TemplateResponse objects
        """
        templates = list(TEMPLATES.values())

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
