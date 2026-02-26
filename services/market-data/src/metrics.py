"""Domain-specific metrics for market data service.

Custom Prometheus metrics for tracking:
- Alpaca API requests and latency
- Cache hit/miss rates
- WebSocket stream connections and messages
"""

from prometheus_client import Counter, Gauge, Histogram

# === Alpaca API Metrics ===

ALPACA_REQUESTS_TOTAL = Counter(
    "market_data_alpaca_requests_total",
    "Total Alpaca API requests",
    ["method", "status"],
)

ALPACA_REQUEST_LATENCY = Histogram(
    "market_data_alpaca_latency_seconds",
    "Alpaca API request latency in seconds",
    ["method"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

ALPACA_RATE_LIMIT_TOKENS = Gauge(
    "market_data_alpaca_rate_limit_tokens",
    "Available rate limit tokens",
)

ALPACA_CIRCUIT_BREAKER_STATE = Gauge(
    "market_data_alpaca_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
)


# === Cache Metrics ===

CACHE_OPERATIONS_TOTAL = Counter(
    "market_data_cache_operations_total",
    "Total cache operations",
    ["operation", "result"],  # operation: get/set/delete, result: hit/miss/error
)

CACHE_LATENCY = Histogram(
    "market_data_cache_latency_seconds",
    "Cache operation latency in seconds",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
)


# === WebSocket Streaming Metrics ===

STREAM_CONNECTIONS = Gauge(
    "market_data_stream_connections",
    "Current WebSocket connections",
)

STREAM_MESSAGES_TOTAL = Counter(
    "market_data_stream_messages_total",
    "Total stream messages sent",
    ["type"],  # trade, quote, bar
)

STREAM_SUBSCRIPTIONS = Gauge(
    "market_data_stream_subscriptions",
    "Current stream subscriptions",
    ["type"],  # trades, quotes, bars
)

STREAM_ALPACA_MESSAGES_TOTAL = Counter(
    "market_data_stream_alpaca_messages_total",
    "Total messages received from Alpaca stream",
    ["type"],  # trade, quote, bar, error
)


# === Helper Functions ===


def record_alpaca_request(method: str, status: str, latency: float) -> None:
    """Record an Alpaca API request.

    Args:
        method: API method (get_bars, get_quote, etc.)
        status: Response status (success, error, rate_limited, circuit_open)
        latency: Request duration in seconds
    """
    ALPACA_REQUESTS_TOTAL.labels(method=method, status=status).inc()
    ALPACA_REQUEST_LATENCY.labels(method=method).observe(latency)


def record_cache_operation(operation: str, result: str, latency: float) -> None:
    """Record a cache operation.

    Args:
        operation: Type of operation (get, set, delete)
        result: Result (hit, miss, error)
        latency: Operation duration in seconds
    """
    CACHE_OPERATIONS_TOTAL.labels(operation=operation, result=result).inc()
    CACHE_LATENCY.labels(operation=operation).observe(latency)


def update_stream_metrics(
    connections: int,
    trade_subs: int,
    quote_subs: int,
    bar_subs: int,
) -> None:
    """Update streaming metrics.

    Args:
        connections: Number of active WebSocket connections
        trade_subs: Number of trade subscriptions
        quote_subs: Number of quote subscriptions
        bar_subs: Number of bar subscriptions
    """
    STREAM_CONNECTIONS.set(connections)
    STREAM_SUBSCRIPTIONS.labels(type="trades").set(trade_subs)
    STREAM_SUBSCRIPTIONS.labels(type="quotes").set(quote_subs)
    STREAM_SUBSCRIPTIONS.labels(type="bars").set(bar_subs)


def record_stream_message(msg_type: str) -> None:
    """Record a stream message sent to clients.

    Args:
        msg_type: Type of message (trade, quote, bar)
    """
    STREAM_MESSAGES_TOTAL.labels(type=msg_type).inc()


def record_alpaca_stream_message(msg_type: str) -> None:
    """Record a message received from Alpaca stream.

    Args:
        msg_type: Type of message (trade, quote, bar, error)
    """
    STREAM_ALPACA_MESSAGES_TOTAL.labels(type=msg_type).inc()


def update_rate_limiter_metrics(available_tokens: float) -> None:
    """Update rate limiter metrics.

    Args:
        available_tokens: Number of available tokens
    """
    ALPACA_RATE_LIMIT_TOKENS.set(available_tokens)


def update_circuit_breaker_metrics(state: str) -> None:
    """Update circuit breaker state metric.

    Args:
        state: Circuit state (closed, half_open, open)
    """
    state_values = {"closed": 0, "half_open": 1, "open": 2}
    ALPACA_CIRCUIT_BREAKER_STATE.set(state_values.get(state, -1))
