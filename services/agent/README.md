# LlamaTrade Agent Service

AI-powered agent for creating and optimizing trading strategies through natural language conversation.

## Features

- Generate valid DSL strategies from natural language descriptions
- Edit and improve existing strategies based on feedback
- Query portfolio, strategies, and backtest results
- Research assets and market conditions
- Validate DSL code before presenting to users

## Tools

The agent has access to the following tools:

- `list_strategies` - List user's existing strategies
- `get_strategy` - Get full details of a specific strategy
- `list_templates` - Get pre-built strategy templates
- `get_portfolio_summary` - Get user's current portfolio
- `get_positions` - Get detailed position information
- `get_portfolio_performance` - Get portfolio performance metrics
- `validate_dsl` - Parse and validate DSL code
- `get_asset_info` - Get fundamental information about assets
- `get_backtest_results` - Get backtest results for a strategy
- `list_backtests` - List backtests for a strategy
- `run_backtest` - Run a backtest on a strategy

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Run service
uv run python -m uvicorn src.main:app --reload
```
