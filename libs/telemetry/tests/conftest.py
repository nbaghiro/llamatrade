"""Shared fixtures: configure telemetry once for the whole session.

Counters are monotonic across the session, so tests that assert exact values use
unique label values to avoid cross-test interference.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from llamatrade_telemetry import init_telemetry, registry, tracing


@pytest.fixture(scope="session", autouse=True)
def _telemetry() -> Iterator[None]:
    # Deterministic trace ids for trace-correlation assertions.
    os.environ.setdefault("OTEL_TRACES_SAMPLER", "always_on")
    registry.reset_for_testing()
    tracing.reset_for_testing()
    init_telemetry(service="test", version="0.0.0")
    yield


def scrape() -> str:
    """Current Prometheus exposition as text."""
    return registry.get_metrics().decode()
