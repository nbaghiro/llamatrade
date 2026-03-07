# llamatrade-alpaca

Shared Alpaca API client library for LlamaTrade services.

## Features

- **Base HTTP Client**: Configurable client with authentication and resilience
- **Resilience Patterns**: Rate limiting, circuit breaker, and retry with exponential backoff
- **Typed Exceptions**: Hierarchical error types for precise error handling
- **Shared Models**: Common data models (Bar, Quote, Trade, Snapshot)
- **URL Configuration**: Easy switching between paper and live environments

## Installation

```bash
pip install -e libs/alpaca
```

## Usage

### Creating a Custom Client

```python
from llamatrade_alpaca import (
    AlpacaClientBase,
    AlpacaUrls,
    Bar,
    create_market_data_resilience,
    parse_bar,
    retry_with_backoff,
    RetryConfig,
)

class AlpacaDataClient(AlpacaClientBase):
    BASE_URL_LIVE = AlpacaUrls.DATA_LIVE
    BASE_URL_PAPER = AlpacaUrls.DATA_PAPER

    def __init__(self, paper: bool = True):
        rate_limiter, circuit_breaker = create_market_data_resilience()
        super().__init__(
            paper=paper,
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
        )

    @retry_with_backoff(RetryConfig())
    async def get_bars(self, symbol: str) -> list[Bar]:
        response = await self._get(f"/stocks/{symbol}/bars")
        return [parse_bar(b) for b in response.json().get("bars", [])]
```

### Using Credentials

```python
from llamatrade_alpaca import AlpacaCredentials

# From environment variables (ALPACA_API_KEY, ALPACA_API_SECRET)
creds = AlpacaCredentials.from_env()

# Explicit credentials
creds = AlpacaCredentials(api_key="...", api_secret="...")

# Pass to client
client = AlpacaDataClient(credentials=creds)
```

### Error Handling

```python
from llamatrade_alpaca import (
    AlpacaError,
    AlpacaRateLimitError,
    SymbolNotFoundError,
    CircuitOpenError,
)

try:
    bars = await client.get_bars("INVALID")
except SymbolNotFoundError as e:
    print(f"Symbol {e.symbol} not found")
except AlpacaRateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
except CircuitOpenError:
    print("Service unavailable, circuit breaker open")
except AlpacaError as e:
    print(f"API error: {e.message} (status: {e.status_code})")
```

## Components

### Config (`config.py`)
- `AlpacaUrls`: URL constants for all Alpaca APIs
- `AlpacaCredentials`: Credential management with env var support
- `AlpacaEnvironment`: Paper/Live environment enum

### Errors (`errors.py`)
- `AlpacaError`: Base exception
- `AlpacaRateLimitError`: 429 rate limit exceeded
- `AlpacaServerError`: 5xx server errors
- `SymbolNotFoundError`: 404/422 symbol not found
- `InvalidRequestError`: 400 bad request
- `AuthenticationError`: 401/403 auth failures
- `CircuitOpenError`: Circuit breaker is open

### Resilience (`resilience.py`)
- `RateLimiter`: Token bucket rate limiting
- `CircuitBreaker`: Circuit breaker pattern
- `RetryConfig`: Retry configuration
- `retry_with_backoff`: Decorator for automatic retries
- `parse_alpaca_error`: Convert HTTP responses to typed exceptions

### Models (`models.py`)
- `Bar`, `Quote`, `Trade`, `Snapshot`: Pydantic models
- `Timeframe`: Enum for bar timeframes
- `parse_bar`, `parse_quote`, `parse_trade`, `parse_snapshot`: JSON parsers
