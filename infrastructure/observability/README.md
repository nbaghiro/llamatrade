# Observability stack

Collects the telemetry emitted by `llamatrade_telemetry` (see
[`.docs/telemetry.md`](../../.docs/telemetry.md)): Prometheus scrapes every
service's `/metrics`, the OTel Collector receives traces and logs and forwards
them to Tempo and Loki, Grafana visualizes all three, and Alertmanager routes
SLO alerts.

## Run (dev)

```bash
# from repo root — brings up the full stack incl. observability
docker compose -f infrastructure/docker/docker-compose.yml \
               -f infrastructure/docker/docker-compose.dev.yml up

# or just the observability services
docker compose -f infrastructure/docker/docker-compose.yml \
               -f infrastructure/docker/docker-compose.dev.yml \
               up prometheus grafana otel-collector alertmanager tempo loki
```

| Service | URL | Notes |
|---|---|---|
| Prometheus | http://localhost:9090 | targets at `/targets`, alerts at `/alerts` |
| Grafana | http://localhost:3001 | login `admin` / `admin`; dashboards auto-provisioned under the **LlamaTrade** folder |
| Alertmanager | http://localhost:9093 | |
| OTel Collector | OTLP http `:4318`, grpc `:4317`; health `:13133` | debug exporter logs spans |
| Tempo | http://localhost:3200 | trace backend (TraceQL) |
| Loki | http://localhost:3100 | log backend (LogQL) |

## Metrics

Every backend service exposes OTel-backed Prometheus metrics at `GET /metrics`.
Metrics carry **no `service` label** — the Prometheus scrape **`job`** label (set
per target in `prometheus/prometheus.yml`) is how dashboards/alerts distinguish
services, alongside OTel `target_info`.

## Traces and logs

Both export only when a service has `OTEL_EXPORTER_OTLP_ENDPOINT` set, which
`docker-compose.dev.yml` does for every service. Trace sampling defaults to 10%
(`OTEL_TRACES_SAMPLER_ARG`); logs are not sampled.

Container stdout is independent of this pipeline and stays the source of truth.
The dev stack sets `LOG_FORMAT=console` so `docker compose logs` renders for a
person, while the same records go to Loki with their fields intact. Deployments
leave the `json` default, which the GKE node agent parses into Cloud Logging
natively, so no logs exporter is needed there.

To read a request end to end: open its trace in Tempo and use **Logs for this
span**, or find a log line in Loki and follow its **TraceID** link back. Both
directions are provisioned in `grafana/provisioning/datasources/datasource.yml`.

Useful LogQL, given the fields the library binds:

```logql
{service_name="trading"} | json | client_order_id="lt-8f21c4de"
{service_name=~"trading|portfolio"} | json | severity="ERROR"
{service_name="portfolio"} | json | tenant_id="<uuid>"
```

## Files

```
prometheus/prometheus.yml   # scrape config (job=<service>) + Alertmanager wiring
prometheus/alerts.yml       # SLO / burn-rate alert rules (PromQL on llamatrade_* metrics)
alertmanager/alertmanager.yml
otel-collector/config.yaml  # OTLP receivers → batch → Tempo (traces) + Loki (logs)
tempo/tempo.yaml            # trace backend
loki/loki.yaml              # log backend
grafana/provisioning/       # datasource + dashboard providers (auto-loaded)
grafana/dashboards/         # dashboard JSON (Platform/RED, ...)
```

## Kubernetes

See `infrastructure/k8s/base/observability/` — a `PrometheusRule` mirroring the
alerts above, plus scraping guidance (a PodMonitor template for Prometheus
Operator clusters, or `prometheus.io/scrape` pod annotations otherwise). These
are opt-in and not in the default kustomization.
