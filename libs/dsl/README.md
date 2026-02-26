# llamatrade-dsl

S-expression DSL parser and compiler for LlamaTrade trading strategies.

## Features

- **Parser**: Parse S-expression strategy definitions into AST
- **Validator**: Semantic validation (indicators, operators, types)
- **Serializer**: Convert AST back to S-expression strings
- **JSON**: Convert AST to/from JSON for database storage

## Example

```python
from llamatrade_dsl import parse_strategy, validate_strategy, to_json

source = """
(strategy
  :name "EMA Crossover"
  :symbols ["AAPL" "MSFT"]
  :timeframe "1D"
  :entry (cross-above (ema close 12) (ema close 26))
  :exit (cross-below (ema close 12) (ema close 26))
  :stop-loss-pct 2.0
  :take-profit-pct 6.0)
"""

strategy = parse_strategy(source)
result = validate_strategy(strategy)

if result.valid:
    json_data = to_json(strategy)
    # Store in database
```

## Installation

```bash
pip install -e .
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```
