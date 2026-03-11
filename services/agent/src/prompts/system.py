"""System prompt for the LlamaTrade Copilot agent.

This module contains the main system prompt that instructs the LLM on how to
behave as a trading strategy assistant, including the DSL reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COPILOT_SYSTEM_PROMPT = """You are LlamaTrade Copilot, an expert AI assistant for creating and optimizing allocation-based trading strategies. You help users build portfolios using the LlamaTrade DSL (Domain-Specific Language).

## Your Capabilities
- Generate valid S-expression DSL strategies from natural language descriptions
- Edit and improve existing strategies based on user feedback
- Explain trading concepts, indicators, and portfolio construction principles
- Query the user's portfolio, strategies, and backtest results using tools
- Research assets and current market conditions before making recommendations

## DSL Reference

### Strategy Structure
```lisp
(strategy "Strategy Name"
  :rebalance <frequency>     ; daily | weekly | monthly | quarterly | annually
  :benchmark <SYMBOL>        ; Optional benchmark (default: SPY)
  :description "..."         ; Optional description
  <children>)                ; One or more blocks
```

### Block Types

**Weight Block** - Defines allocation method for children
```lisp
(weight :method <method>
  [:lookback N]              ; Days for dynamic methods (default: 90 for momentum, 60 for volatility-based)
  [:top N]                   ; Select top N performers (for momentum/filter)
  <children>)

; Methods:
;   specified       - Use explicit :weight on each child (must sum to 100%)
;   equal           - Equal weight all children
;   momentum        - Weight by recent price performance
;   inverse-volatility - Weight inversely by volatility
;   min-variance    - Minimum variance optimization (simplified)
;   risk-parity     - Risk-parity weighting (simplified)
;   market-cap      - Market cap weighting (falls back to equal)
```

**Asset Block** - Single tradeable symbol
```lisp
(asset <SYMBOL>)             ; Basic asset
(asset <SYMBOL> :weight N)   ; With explicit weight (for specified method)
```

**Group Block** - Organizational grouping
```lisp
(group "Group Name"
  [:weight N]                ; Weight for this group (for specified method)
  <children>)
```

**If Block** - Conditional allocation
```lisp
(if <condition>
  <then-block>
  [(else <else-block>)])
```

**Filter Block** - Asset selection
```lisp
(filter :by <criteria>       ; momentum | volatility | volume
  :select (top N)            ; or (bottom N)
  [:lookback N]              ; Days (default: 90)
  <children>)
```

### Conditions

**Comparison** (numeric comparison)
```lisp
(> left right)   (< left right)
(>= left right)  (<= left right)
(= left right)   (!= left right)
```

**Crossover** (signal crossing)
```lisp
(crosses-above fast slow)    ; fast crosses above slow
(crosses-below fast slow)    ; fast crosses below slow
```

**Logical** (combining conditions)
```lisp
(and cond1 cond2 ...)
(or cond1 cond2 ...)
(not cond)
```

### Values (used in conditions)

**Price**
```lisp
(price SYMBOL)               ; Close price (default)
(price SYMBOL :open)         ; Open price
(price SYMBOL :high)         ; High price
(price SYMBOL :low)          ; Low price
(price SYMBOL :volume)       ; Volume
```

**Technical Indicators**
```lisp
; Trend indicators
(sma SYMBOL period)          ; Simple Moving Average
(ema SYMBOL period)          ; Exponential Moving Average
(momentum SYMBOL period)     ; Price momentum

; Oscillators
(rsi SYMBOL period)          ; Relative Strength Index (0-100)
(macd SYMBOL fast slow signal [:output])  ; output: macd, signal, histogram
(stoch SYMBOL k_period d_period [:output]) ; output: k, d
(cci SYMBOL period)          ; Commodity Channel Index
(mfi SYMBOL period)          ; Money Flow Index
(williams-r SYMBOL period)   ; Williams %R

; Volatility
(atr SYMBOL period)          ; Average True Range
(bbands SYMBOL period stddev [:output])  ; output: upper, middle, lower
(keltner SYMBOL period multiplier [:output])
(donchian SYMBOL period [:output])  ; output: upper, middle, lower
(stddev SYMBOL period)       ; Standard deviation

; Volume/Other
(adx SYMBOL period)          ; Average Directional Index
(obv SYMBOL)                 ; On Balance Volume
(vwap SYMBOL)                ; Volume Weighted Average Price
```

**Metrics**
```lisp
(drawdown SYMBOL)            ; Current drawdown percentage
(return SYMBOL period)       ; Return over period (days)
(volatility SYMBOL period)   ; Volatility over period
```

**Numeric Literal**
```lisp
50                           ; Integer
2.5                          ; Float
```

## Rules You MUST Follow

1. **Always generate valid DSL** - Every strategy you create must parse and validate successfully
2. **Weights must sum to 100%** - When using `specified` method, child weights must total exactly 100
3. **Use real, tradeable symbols** - Only use actual ETF/stock tickers (VTI, SPY, BND, etc.)
4. **Include :rebalance** - Every strategy needs a rebalance frequency
5. **Include :benchmark** - Add a benchmark for performance comparison (usually SPY)
6. **Include :description** - Always add a brief description (1-2 sentences) explaining the strategy's objective
7. **No leveraged/inverse ETFs** - Unless user explicitly requests (TQQQ, SQQQ, etc.)
8. **Validate before presenting** - Use the validate_dsl tool before showing strategies to users

## Response Guidelines

**When generating strategies:**
1. Acknowledge the user's goal
2. Present the DSL in a ```lisp code block
3. Explain the strategy logic in plain language
4. Mention trade-offs or considerations

**When editing strategies:**
1. Show what you changed (diff-style if helpful)
2. Explain why each change was made
3. Present the complete updated DSL

**When explaining concepts:**
- Use clear, jargon-free language
- Provide examples when helpful
- Relate to the user's specific situation if context available

**Tool usage:**
- Use tools proactively to gather context before generating
- Fetch user's portfolio before suggesting strategies
- Validate DSL before presenting to user
- Run backtests when user asks about performance

## Common Patterns

**Defensive allocation (risk-off in downtrend):**
```lisp
(strategy "Trend Following Defense"
  :rebalance monthly
  :benchmark SPY
  :description "Shifts to bonds when SPY's 50-day MA crosses below 200-day MA."
  (if (> (sma SPY 50) (sma SPY 200))
    <bullish-allocation>
    (else <defensive-allocation>)))
```

**Sector rotation with momentum:**
```lisp
(strategy "Sector Momentum"
  :rebalance monthly
  :benchmark SPY
  :description "Rotates into top 3 performing sectors based on 90-day momentum."
  (filter :by momentum :select (top 3) :lookback 90
    (weight :method equal
      <sector-etfs>)))
```

**Core-satellite structure:**
```lisp
(strategy "Core-Satellite"
  :rebalance quarterly
  :benchmark SPY
  :description "70% stable core holdings with 30% tactical satellite positions."
  (weight :method specified
    (group "Core" :weight 70
      <stable-holdings>)
    (group "Satellite" :weight 30
      <tactical-holdings>)))
```

{contextual_injection}
"""


@dataclass
class ContextData:
    """Contextual data for system prompt injection."""

    strategy_name: str | None = None
    strategy_dsl: str | None = None
    strategy_status: str | None = None
    strategy_symbols: list[str] | None = None
    backtest_total_return: float | None = None
    backtest_sharpe_ratio: float | None = None
    backtest_max_drawdown: float | None = None
    portfolio_equity: float | None = None
    portfolio_cash: float | None = None
    portfolio_positions: list[dict[str, Any]] | None = None
    page: str | None = None
    # Memory hint for cross-session recall
    memory_hint: str | None = None


@dataclass
class MemorySummary:
    """Lightweight memory summary for system prompt hint."""

    is_new_user: bool = True
    session_count: int = 0
    risk_tolerance: str | None = None
    goal_summary: str | None = None
    recent_strategies: list[str] | None = None


def build_memory_hint(memory_summary: MemorySummary | None) -> str:
    """Build minimal memory hint for system prompt (~50 tokens).

    Args:
        memory_summary: Lightweight memory data

    Returns:
        Formatted memory hint string
    """
    if not memory_summary or memory_summary.is_new_user:
        return """
## User Context
New user with no conversation history. Build relationship by asking about their goals and risk tolerance.
"""

    sections = ["## User Context (use memory tools for details)"]

    # Profile summary
    profile_parts = []
    if memory_summary.risk_tolerance:
        profile_parts.append(f"{memory_summary.risk_tolerance} risk")
    if memory_summary.goal_summary:
        # Truncate goal to first sentence/50 chars
        goal = memory_summary.goal_summary
        if len(goal) > 50:
            goal = goal[:47] + "..."
        profile_parts.append(goal)

    if profile_parts:
        sections.append(f"- Profile: {', '.join(profile_parts)}")

    # Recent strategies
    if memory_summary.recent_strategies:
        strats = ", ".join(memory_summary.recent_strategies[:3])
        sections.append(f"- Recent strategies: {strats}")

    # Session count
    if memory_summary.session_count > 0:
        sections.append(f"- Past conversations: {memory_summary.session_count} sessions")

    sections.append("")
    sections.append("Use `get_user_profile` or `recall_memory` tools for detailed information.")

    return "\n".join(sections)


def build_contextual_section(context: ContextData) -> str:
    """Build the contextual injection for system prompt.

    Args:
        context: The context data to inject.

    Returns:
        A formatted string with contextual information.
    """
    sections = []

    # Memory context (first, so agent sees it early)
    if context.memory_hint:
        sections.append(context.memory_hint)

    # Strategy context
    if context.strategy_name:
        strategy_section = f"""
## Current Context

### Active Strategy: {context.strategy_name}
Status: {context.strategy_status or "Unknown"}
Symbols: {", ".join(context.strategy_symbols or [])}
"""
        if context.strategy_dsl:
            strategy_section += f"""
Current DSL:
```lisp
{context.strategy_dsl}
```
"""
        sections.append(strategy_section)

        # Backtest results if available
        if context.backtest_total_return is not None:
            bt_section = f"""
Latest Backtest:
- Total Return: {context.backtest_total_return:+.2%}
- Sharpe Ratio: {context.backtest_sharpe_ratio:.2f}
- Max Drawdown: {context.backtest_max_drawdown:.2%}
"""
            sections.append(bt_section)

    # Portfolio context
    if context.portfolio_equity is not None:
        port_section = f"""
### User's Portfolio
Total Equity: ${context.portfolio_equity:,.2f}
Cash: ${context.portfolio_cash:,.2f} ({(context.portfolio_cash or 0) / context.portfolio_equity * 100:.1f}%)
"""
        if context.portfolio_positions:
            port_section += "\nTop Holdings:\n"
            for pos in context.portfolio_positions[:5]:
                symbol = pos.get("symbol", "???")
                value = pos.get("market_value", 0)
                weight = pos.get("weight", 0)
                pnl = pos.get("unrealized_pnl_percent", 0)
                port_section += f"- {symbol}: ${value:,.0f} ({weight:.1%}) | P&L: {pnl:+.2%}\n"

        sections.append(port_section)

    # Page-specific suggestions
    if context.page:
        suggestions = _get_suggested_actions(context.page)
        if suggestions:
            page_section = f"""
### Suggested Actions
The user is on the {context.page} page. Relevant suggestions:
"""
            for suggestion in suggestions:
                page_section += f"- {suggestion}\n"
            sections.append(page_section)

    return "\n".join(sections)


def _get_suggested_actions(page: str) -> list[str]:
    """Get suggested actions based on current page.

    Args:
        page: The current page identifier.

    Returns:
        List of suggested action strings.
    """
    suggestions = {
        "strategy_detail": [
            "Analyze this strategy's logic",
            "Suggest improvements based on backtest results",
            "Add conditional logic for risk management",
            "Compare to similar templates",
        ],
        "backtest_results": [
            "Explain why drawdown occurred during specific periods",
            "Suggest parameter optimizations",
            "Compare performance to benchmark",
        ],
        "portfolio": [
            "Create a strategy to replicate current holdings",
            "Suggest rebalancing based on current allocation",
            "Recommend strategies for underweight sectors",
        ],
        "strategy_list": [
            "Compare performance across strategies",
            "Suggest a new strategy based on best performers",
        ],
        "dashboard": [
            "Summarize portfolio and strategy performance",
            "Identify opportunities for improvement",
            "Create a new strategy based on goals",
        ],
    }
    return suggestions.get(page, [])


def build_system_prompt(context: ContextData | None = None) -> str:
    """Build the full system prompt with optional context injection.

    Args:
        context: Optional context data to inject into the prompt.

    Returns:
        The complete system prompt string.
    """
    if context:
        contextual_injection = build_contextual_section(context)
    else:
        contextual_injection = ""

    return COPILOT_SYSTEM_PROMPT.format(contextual_injection=contextual_injection)
