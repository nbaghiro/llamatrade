"""Shared containment-based metric assertion helper for trading tests.

Reads the real Prometheus exposition (``llamatrade_telemetry.get_metrics``)
so tests assert on before/after deltas of actual samples rather than poking
at instrument internals.
"""

import re

from llamatrade_telemetry import get_metrics


def sample_metric(metric: str, **labels: str) -> float:
    """Value of a single exposition sample matching ``labels``, or 0.0 if absent.

    Matches a line like ``metric{a="b",c="d"} 3.0`` regardless of label order.
    """
    for line in get_metrics().decode().splitlines():
        if line.startswith("#") or not line.startswith(metric):
            continue
        match = re.match(
            rf"{re.escape(metric)}(?:\{{(?P<labels>[^}}]*)\}})?\s+(?P<value>\S+)$", line
        )
        if not match:
            continue
        present = dict(re.findall(r'(\w+)="([^"]*)"', match.group("labels") or ""))
        if all(present.get(k) == v for k, v in labels.items()):
            return float(match.group("value"))
    return 0.0
