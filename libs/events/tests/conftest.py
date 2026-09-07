"""Test harness: the shipped in-memory ``FakeTransport`` so the lib runs without a
broker, plus the shared real-Kafka ``bootstrap`` fixture for the integration tier."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from typing import NoReturn

import pytest

from llamatrade_events.bus import EventBus
from llamatrade_events.testing import FakeTransport, PublishRecord
from llamatrade_telemetry import get_metrics

__all__ = [
    "REQUIRE_DOCKER",
    "FakeTransport",
    "PublishRecord",
    "aclose",
    "metric_value",
    "skip_or_fail",
    "take",
]

REQUIRE_DOCKER = os.environ.get("CI_REQUIRE_DOCKER") == "1"


def skip_or_fail(reason: str) -> NoReturn:
    """Skip locally; fail when CI_REQUIRE_DOCKER=1 demands the Docker-gated tests run."""
    if REQUIRE_DOCKER:
        pytest.fail(f"CI_REQUIRE_DOCKER=1: {reason}", pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def bootstrap() -> Iterator[str]:
    """A Kafka broker for the integration-marked tests.

    Prefers a broker provided via ``KAFKA_BOOTSTRAP_SERVERS`` (the CI service
    container); otherwise spins a throwaway ``KafkaContainer`` via testcontainers,
    skipping (failing under ``CI_REQUIRE_DOCKER=1``) when neither is available.
    Session-scoped: one broker serves every integration module; tests isolate via
    per-test topic namespaces.
    """
    provided = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if provided:
        yield provided
        return
    if REQUIRE_DOCKER:
        import testcontainers.kafka as kafka_mod
    else:
        kafka_mod = pytest.importorskip("testcontainers.kafka")
    try:
        container = kafka_mod.KafkaContainer()
        container.start()
    except Exception as exc:  # Docker daemon down / image pull failed
        skip_or_fail(f"Docker/Kafka unavailable: {exc}")
    try:
        yield container.get_bootstrap_server()
    finally:
        container.stop()


async def aclose(agen: AsyncIterator[object]) -> None:
    """Close ``agen`` when it is an async generator (transport tail/consume are)."""
    if isinstance(agen, AsyncGenerator):
        await agen.aclose()


async def take[T](agen: AsyncIterator[T], n: int, *, timeout: float = 30.0) -> list[T]:
    """Pull up to ``n`` items from ``agen`` under ``timeout``, closing it after.

    A draining iterator (the fake) may end early; a blocking one (Kafka) is
    bounded by the timeout.
    """

    async def pull() -> list[T]:
        out: list[T] = []
        async for item in agen:
            out.append(item)
            if len(out) >= n:
                break
        return out

    try:
        return await asyncio.wait_for(pull(), timeout=timeout)
    finally:
        await aclose(agen)


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
