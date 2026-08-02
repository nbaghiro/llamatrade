"""Test harness: the shipped in-memory ``FakeTransport`` so the lib runs without a broker."""

from __future__ import annotations

import re

import pytest

from llamatrade_events.bus import EventBus
from llamatrade_events.testing import FakeTransport, PublishRecord
from llamatrade_telemetry import get_metrics

__all__ = ["FakeTransport", "PublishRecord", "metric_value"]


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


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def bus(transport: FakeTransport) -> EventBus:
    return EventBus(transport=transport)
