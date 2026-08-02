"""Containment-based Prometheus exposition reader shared by metric tests."""

import re

from llamatrade_telemetry import get_metrics


def metric_value(name: str, **labels: str) -> float:
    """Read a single metric value from the Prometheus exposition (0.0 if absent).

    Matches on label containment, not equality: the OTel Prometheus exporter
    appends ``otel_scope_*`` labels whose presence varies by exporter version.
    """
    for line in get_metrics().decode().splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        match = re.match(rf"{re.escape(name)}(?:\{{(?P<labels>[^}}]*)\}})?\s+(?P<value>\S+)$", line)
        if match is None:
            continue
        present = dict(re.findall(r'(\w+)="([^"]*)"', match.group("labels") or ""))
        if all(present.get(k) == v for k, v in labels.items()):
            return float(match.group("value"))
    return 0.0
