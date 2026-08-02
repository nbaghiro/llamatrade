"""Test harness: the shipped in-memory ``FakeTransport`` so the lib runs without a broker."""

from __future__ import annotations

import re

import pytest

from llamatrade_events.bus import EventBus
from llamatrade_events.testing import FakeTransport, PublishRecord
from llamatrade_telemetry import get_metrics

__all__ = ["FakeTransport", "PublishRecord", "metric_value"]


def metric_value(name: str, **labels: str) -> float:
    """Read a single metric value from the Prometheus exposition (0.0 if absent)."""
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    pattern = re.compile(rf"^{re.escape(name)}\{{{re.escape(label_str)}\}} (.+)$", re.M)
    match = pattern.search(get_metrics().decode())
    return float(match.group(1)) if match else 0.0


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def bus(transport: FakeTransport) -> EventBus:
    return EventBus(transport=transport)
