"""Few-shot examples for the LlamaTrade Copilot agent.

This module contains example conversations that demonstrate how the agent
should behave when generating and editing strategies.
"""

from __future__ import annotations

from typing import Any

# Few-shot examples as conversation pairs
FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    # Example 1: Simple strategy generation
    {
        "role": "user",
        "content": "Create a simple 60/40 portfolio",
    },
    {
        "role": "assistant",
        "content": """I'll create a classic 60/40 portfolio - 60% stocks, 40% bonds.

```lisp
(strategy "Classic 60/40"
  :rebalance quarterly
  :benchmark SPY
  :description "Balanced portfolio with 60% global equities and 40% bonds for moderate growth."
  (weight :method specified
    (group "Equities" :weight 60
      (weight :method equal
        (asset VTI)
        (asset VEA)))
    (group "Bonds" :weight 40
      (weight :method equal
        (asset BND)
        (asset BNDX)))))
```

This strategy:
- **60% Equities**: Split equally between US total market (VTI) and developed international (VEA)
- **40% Bonds**: Split equally between US bonds (BND) and international bonds (BNDX)
- **Quarterly rebalancing** to maintain target weights
- **SPY benchmark** for performance comparison

This is a time-tested allocation suitable for long-term investors seeking moderate growth with reduced volatility.""",
    },
    # Example 2: Strategy with risk-off signal
    {
        "role": "user",
        "content": "Add a risk-off signal when the market is in a downtrend",
    },
    {
        "role": "assistant",
        "content": """I'll add conditional logic to shift to a defensive allocation when SPY's 50-day SMA crosses below the 200-day SMA (a common trend-following signal).

```lisp
(strategy "Tactical 60/40"
  :rebalance daily
  :benchmark SPY
  :description "Defensive 60/40 that shifts to 20/80 bonds when SPY trends down."
  (if (> (sma SPY 50) (sma SPY 200))
    ;; Bullish: Standard 60/40
    (weight :method specified
      (group "Equities" :weight 60
        (weight :method equal
          (asset VTI)
          (asset VEA)))
      (group "Bonds" :weight 40
        (weight :method equal
          (asset BND)
          (asset BNDX))))
    (else
      ;; Bearish: Risk-off 20/80
      (weight :method specified
        (group "Equities" :weight 20
          (asset VTI))
        (group "Bonds" :weight 80
          (weight :method specified
            (asset BND :weight 50)
            (asset SHY :weight 30)))))))
```

**Changes made:**
1. Added `(if (> (sma SPY 50) (sma SPY 200)) ...)` to detect market trend
2. Changed rebalance to **daily** to respond quickly to signal changes
3. In risk-off mode: reduced equities to 20%, increased bonds to 80% with short-duration bias (SHY)

**Trade-off:** Daily rebalancing increases monitoring frequency but captures trend changes faster.""",
    },
    # Example 3: Momentum strategy
    {
        "role": "user",
        "content": "Create a momentum-based sector rotation strategy",
    },
    {
        "role": "assistant",
        "content": """I'll create a sector rotation strategy that invests in the top-performing sectors based on recent momentum.

```lisp
(strategy "Sector Momentum"
  :rebalance monthly
  :benchmark SPY
  :description "Rotates into top 3 performing S&P sectors based on 90-day momentum."
  (filter :by momentum :select (top 3) :lookback 90
    (weight :method equal
      (asset XLK)
      (asset XLV)
      (asset XLF)
      (asset XLE)
      (asset XLI)
      (asset XLY)
      (asset XLP)
      (asset XLU)
      (asset XLRE)
      (asset XLB)
      (asset XLC))))
```

This strategy:
- **Selects top 3 sectors** based on 90-day momentum
- **Equal weights** the selected sectors (~33% each)
- **Monthly rebalancing** to capture medium-term trends
- Includes all 11 S&P 500 sector ETFs

**How it works:**
Each month, the strategy ranks all sectors by their 90-day price momentum and invests equally in the top 3 performers. This captures sector leadership while maintaining diversification.

**Considerations:**
- Higher turnover than buy-and-hold strategies
- May underperform during market transitions
- Works best when sectors have clear leadership""",
    },
    # Example 4: Three-fund portfolio
    {
        "role": "user",
        "content": "I want a simple three-fund portfolio for long-term investing",
    },
    {
        "role": "assistant",
        "content": """Here's a classic three-fund portfolio, popularized by Bogleheads for its simplicity and low costs.

```lisp
(strategy "Three Fund Portfolio"
  :rebalance quarterly
  :benchmark SPY
  :description "Simple Boglehead-style portfolio with US stocks, international stocks, and bonds."
  (weight :method specified
    (asset VTI :weight 50)
    (asset VXUS :weight 30)
    (asset BND :weight 20)))
```

This strategy:
- **VTI (50%)**: Total US stock market - captures all US equities
- **VXUS (30%)**: Total international stocks - global diversification
- **BND (20%)**: Total US bond market - stability and income

**Why this works:**
- Extremely low cost (all Vanguard ETFs with sub-0.1% expense ratios)
- Captures the entire global stock and bond markets
- Simple to understand and maintain
- Quarterly rebalancing keeps allocations on target

**Customization options:**
- More aggressive: Increase VTI/VXUS, decrease BND
- More conservative: Increase BND to 30-40%
- Add small-cap tilt: Replace some VTI with VB (Vanguard Small Cap)""",
    },
    # Example 5: Risk parity
    {
        "role": "user",
        "content": "Create a risk parity portfolio",
    },
    {
        "role": "assistant",
        "content": """I'll create a risk parity portfolio that balances risk contribution across asset classes rather than capital allocation.

```lisp
(strategy "Risk Parity"
  :rebalance monthly
  :benchmark SPY
  :description "Equalizes risk contribution across equities, bonds, and alternatives."
  (weight :method risk-parity :lookback 60
    (group "Equities"
      (weight :method equal
        (asset VTI)
        (asset VEA)
        (asset VWO)))
    (group "Fixed Income"
      (weight :method equal
        (asset TLT)
        (asset BND)
        (asset TIP)))
    (group "Alternatives"
      (weight :method equal
        (asset GLD)
        (asset VNQ)))))
```

This strategy:
- Uses **risk-parity weighting** to equalize risk contribution
- **60-day lookback** for volatility estimation
- Three asset classes: Equities, Fixed Income, Alternatives

**How risk parity works:**
Instead of equal dollar allocation, risk parity allocates more to lower-volatility assets (bonds) and less to higher-volatility assets (stocks). This typically results in:
- ~25-35% equities
- ~50-60% bonds
- ~10-20% alternatives

**Benefits:**
- More stable returns across market environments
- Lower drawdowns than traditional portfolios
- True diversification of risk

**Trade-offs:**
- May underperform in strong bull markets
- Higher bond allocation requires more capital for same expected return""",
    },
]


def get_few_shot_messages() -> list[dict[str, str]]:
    """Get few-shot examples as a list of messages.

    Returns:
        List of message dicts with 'role' and 'content' keys.
    """
    return [{"role": ex["role"], "content": ex["content"]} for ex in FEW_SHOT_EXAMPLES]


def get_few_shot_for_task(task_type: str) -> list[dict[str, str]]:
    """Get few-shot examples relevant to a specific task type.

    Args:
        task_type: The type of task (e.g., 'generate', 'edit', 'explain').

    Returns:
        List of relevant few-shot examples.
    """
    # Map task types to relevant example indices
    task_examples = {
        "generate": [0, 2, 3, 4],  # Simple 60/40, Momentum, Three-fund, Risk parity
        "edit": [0, 1],  # 60/40 then add risk-off
        "explain": [3, 4],  # Three-fund and Risk parity have good explanations
    }

    indices = task_examples.get(task_type, list(range(0, len(FEW_SHOT_EXAMPLES), 2)))

    result = []
    for i in indices:
        if i < len(FEW_SHOT_EXAMPLES):
            # Include the user message and assistant response
            result.append(FEW_SHOT_EXAMPLES[i])
            if i + 1 < len(FEW_SHOT_EXAMPLES):
                result.append(FEW_SHOT_EXAMPLES[i + 1])

    return [{"role": ex["role"], "content": ex["content"]} for ex in result]
