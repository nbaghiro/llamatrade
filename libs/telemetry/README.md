# llamatrade-telemetry

Unified observability for LlamaTrade: **metrics + structured logs + distributed
traces** from a single `init_telemetry()` call.

- **OTel-native** instrumentation (`opentelemetry-api`/`-sdk`).
- **Prometheus exposition** at `/metrics` via `PrometheusMetricReader`.
- **OTLP trace export** (graceful no-op when no collector is configured).
- Naming + cardinality **conventions enforced in code** (see `conventions.py`).

See [`.docs/telemetry.md`](../../.docs/telemetry.md) for the full catalog and design.

```python
from llamatrade_telemetry import init_telemetry, get_logger, metrics

init_telemetry(app, service="trading", version="0.1.0", pool_stats_provider=get_pool_stats)
log = get_logger(__name__)

metrics.trading.order_submitted(side="buy", type="market", status="accepted")
with metrics.trading.fill_latency.time():
    ...
```
