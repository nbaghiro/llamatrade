# Observability stack

Collects the telemetry emitted by `llamatrade_telemetry` (see
[`.docs/telemetry.md`](../../.docs/telemetry.md)): Prometheus scrapes every
service's `/metrics`, Grafana visualizes it, the OTel Collector receives traces,
and Alertmanager routes SLO alerts.

## Run (dev)

```bash
# from repo root — brings up the full stack incl. observability
docker compose -f infrastructure/docker/docker-compose.yml \
               -f infrastructure/docker/docker-compose.dev.yml up

# or just the observability services
docker compose -f infrastructure/docker/docker-compose.yml \
               -f infrastructure/docker/docker-compose.dev.yml \
               up prometheus grafana otel-collector alertmanager
```

| Service | URL | Notes |
|---|---|---|
| Prometheus | http://localhost:9090 | targets at `/targets`, alerts at `/alerts` |
| Grafana | http://localhost:3001 | login `admin` / `admin`; dashboards auto-provisioned under the **LlamaTrade** folder |
| Alertmanager | http://localhost:9093 | |
| OTel Collector | OTLP http `:4318`, grpc `:4317`; health `:13133` | debug exporter logs spans |

## Metrics

Every backend service exposes OTel-backed Prometheus metrics at `GET /metrics`.
Metrics carry **no `service` label** — the Prometheus scrape **`job`** label (set
per target in `prometheus/prometheus.yml`) is how dashboards/alerts distinguish
services, alongside OTel `target_info`.

## Traces (opt-in)

Tracing exports only when a service has `OTEL_EXPORTER_OTLP_ENDPOINT` set. To turn
it on in dev, add to the relevant service in `docker-compose.dev.yml`:

```yaml
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4318
```

Spans flow service → collector (and to Tempo/Cloud Trace once that exporter is
uncommented in `otel-collector/config.yaml`). Sampling defaults to 10%
(`OTEL_TRACES_SAMPLER_ARG`).

## Files

```
prometheus/prometheus.yml   # scrape config (job=<service>) + Alertmanager wiring
prometheus/alerts.yml       # SLO / burn-rate alert rules (PromQL on llamatrade_* metrics)
alertmanager/alertmanager.yml
otel-collector/config.yaml  # OTLP receivers → batch → exporter
grafana/provisioning/       # datasource + dashboard providers (auto-loaded)
grafana/dashboards/         # dashboard JSON (Platform/RED, ...)
```

## Kubernetes

See `infrastructure/k8s/base/observability/` — a `PrometheusRule` mirroring the
alerts above, plus scraping guidance (a PodMonitor template for Prometheus
Operator clusters, or `prometheus.io/scrape` pod annotations otherwise). These
are opt-in and not in the default kustomization.
