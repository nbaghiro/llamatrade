# Kubernetes observability

Opt-in monitoring manifests. **Not** wired into the default kustomization so a
cluster without the Prometheus Operator still applies cleanly.

## PrometheusRule (`prometheusrule.yaml`)

The SLO / burn-rate alerts (mirrors `infrastructure/observability/prometheus/alerts.yml`).
Requires the Prometheus Operator (`monitoring.coreos.com` CRDs):

```bash
kubectl apply -f infrastructure/k8s/base/observability/prometheusrule.yaml
```

## Scraping `/metrics`

Every service exposes OTel-backed Prometheus metrics at `:<service-port>/metrics`.
Pick the path that matches your cluster:

**A. Prometheus Operator — PodMonitor.** Services use per-app labels (`app: auth`,
`app: trading`, …). Either add a shared label `app.kubernetes.io/part-of: llamatrade`
to the deployments and use one PodMonitor, or create one per service. Template:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: llamatrade
spec:
  selector:
    matchLabels:
      app.kubernetes.io/part-of: llamatrade   # add this label to the deployments
  podMetricsEndpoints:
    - path: /metrics
      port: http            # name the container port in each Deployment
      interval: 15s
```

**B. Annotation-based scraping** (no operator). Add to each Deployment's pod
template:

```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/path: "/metrics"
    prometheus.io/port: "8810"   # the service's port
```

## Traces

Set `OTEL_EXPORTER_OTLP_ENDPOINT` (e.g. an OTel Collector Service URL) in the
service env to enable OTLP trace export; unset = no-op.
