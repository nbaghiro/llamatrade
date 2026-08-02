"""Celery worker metrics: queue depth (consumed by the backtest autoscaler)."""

from __future__ import annotations

from llamatrade_telemetry import registry

QUEUE_DEPTH = registry.gauge(
    "llamatrade_celery_queue_depth",
    ["queue"],
    "Pending tasks in a Celery queue",
)


def set_queue_depth(queue: str, depth: int) -> None:
    QUEUE_DEPTH.labels(queue=queue).set(depth)
