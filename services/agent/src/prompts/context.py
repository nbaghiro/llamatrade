"""Context-aware prompt generation.

This module provides utilities for generating contextual prompts and
suggestions based on the current UI state and user data.
"""

from typing import Any


def get_suggested_actions(page: str, context: dict[str, Any]) -> list[str]:
    """Get suggested actions based on current page and context.

    Args:
        page: Current UI page identifier
        context: Additional context data (strategy_id, backtest_id, etc.)

    Returns:
        List of suggested prompt strings
    """
    suggestions: dict[str, list[str]] = {
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
            "Identify which conditions triggered most trades",
        ],
        "portfolio": [
            "Create a strategy to replicate current holdings",
            "Suggest rebalancing based on current allocation",
            "Recommend strategies for underweight sectors",
            "Analyze portfolio risk exposure",
        ],
        "strategy_list": [
            "Compare performance across strategies",
            "Suggest a new strategy based on best performers",
            "Identify strategies that need attention",
            "Create a new strategy",
        ],
        "dashboard": [
            "Summarize portfolio and strategy performance",
            "Identify opportunities for improvement",
            "Create a new strategy based on goals",
            "Show me my best performing strategy",
        ],
    }

    # Default suggestions if page not found
    default_suggestions = [
        "Create a 60/40 portfolio",
        "Build a momentum strategy",
        "Show me my portfolio",
        "Explain how indicators work",
    ]

    return suggestions.get(page, default_suggestions)


def build_contextual_section(context: dict[str, Any]) -> str:
    """Build the contextual injection section for the system prompt.

    Args:
        context: Context data including strategy, backtest, portfolio info

    Returns:
        Formatted context string for system prompt injection
    """
    sections = ["## Current Context"]

    # Strategy context (when viewing a strategy)
    if context.get("strategy"):
        strategy = context["strategy"]
        sections.append(f"""
### Active Strategy: {strategy.get("name", "Unknown")}
Status: {strategy.get("status", "Unknown")}
Rebalance: {strategy.get("rebalance", "Not set")}
Symbols: {", ".join(strategy.get("symbols", []))}

Current DSL:
```lisp
{strategy.get("config_sexpr", "")}
```
""")

        if strategy.get("last_backtest"):
            bt = strategy["last_backtest"]
            sections.append(f"""
Latest Backtest ({bt.get("start_date", "N/A")} to {bt.get("end_date", "N/A")}):
- Total Return: {bt.get("total_return", 0):+.2%}
- Sharpe Ratio: {bt.get("sharpe_ratio", 0):.2f}
- Max Drawdown: {bt.get("max_drawdown", 0):.2%}
- Win Rate: {bt.get("win_rate", 0):.1%}
""")

    # Portfolio context (when viewing portfolio or dashboard)
    if context.get("portfolio"):
        port = context["portfolio"]
        sections.append(f"""
### User's Portfolio
Total Equity: ${port.get("equity", 0):,.2f}
Cash: ${port.get("cash", 0):,.2f}
Day P&L: {port.get("day_pnl_percent", 0):+.2%}
""")

        positions = port.get("positions", [])
        if positions:
            top_5 = sorted(positions, key=lambda p: p.get("market_value", 0), reverse=True)[:5]
            sections.append("Top Holdings:")
            for p in top_5:
                sections.append(
                    f"- {p.get('symbol', '?')}: ${p.get('market_value', 0):,.0f} "
                    f"({p.get('weight', 0):.1%}) | P&L: {p.get('unrealized_pnl_percent', 0):+.2%}"
                )

    # Backtest context (when viewing backtest results)
    if context.get("backtest") and not context.get("strategy"):
        bt = context["backtest"]
        sections.append(f"""
### Backtest Results: {bt.get("strategy_name", "Unknown")}
Period: {bt.get("start_date", "N/A")} to {bt.get("end_date", "N/A")}
Initial Capital: ${bt.get("initial_capital", 0):,.0f}
Final Equity: ${bt.get("final_equity", 0):,.0f}

Performance:
- Total Return: {bt.get("total_return", 0):+.2%}
- Annual Return: {bt.get("annual_return", 0):+.2%}
- Sharpe Ratio: {bt.get("sharpe_ratio", 0):.2f}
- Sortino Ratio: {bt.get("sortino_ratio", 0):.2f}
- Max Drawdown: {bt.get("max_drawdown", 0):.2%}

Trading:
- Total Trades: {bt.get("total_trades", 0)}
- Win Rate: {bt.get("win_rate", 0):.1%}
- Profit Factor: {bt.get("profit_factor", 0):.2f}
""")

    # Page-specific suggested actions
    if context.get("page"):
        page = context["page"]
        suggestions = get_suggested_actions(page, context)
        if suggestions:
            sections.append(f"""
### Suggested Actions for This Context
The user is on the {page} page. Relevant suggestions:
{chr(10).join(f"- {s}" for s in suggestions)}
""")

    return "\n".join(sections)
