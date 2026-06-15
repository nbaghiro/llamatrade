"""Celery worker metrics: task lifecycle, queue depth, and wait time."""

from __future__ import annotations

from llamatrade_telemetry import registry

TASKS_TOTAL = registry.counter(
    "llamatrade_celery_tasks_total",
    ["task", "state"],
    "Celery tasks by terminal state (success/failure/retry/revoked)",
)
TASK_DURATION = registry.histogram(
    "llamatrade_celery_task_duration_seconds",
    ["task"],
    "Celery task execution duration",
)
TASK_QUEUE_WAIT = registry.histogram(
    "llamatrade_celery_task_queue_wait_seconds",
    ["task"],
    "Time a task waited in queue before a worker picked it up",
)
TASK_RETRIES_TOTAL = registry.counter(
    "llamatrade_celery_task_retries_total",
    ["task"],
    "Celery task retries",
)
QUEUE_DEPTH = registry.gauge(
    "llamatrade_celery_queue_depth",
    ["queue"],
    "Pending tasks in a Celery queue",
)
WORKERS_ACTIVE = registry.gauge(
    "llamatrade_celery_workers_active",
    (),
    "Active Celery workers",
)


def record_task(task: str, state: str) -> None:
    TASKS_TOTAL.labels(task=task, state=state).inc()


def observe_task_duration(task: str, seconds: float) -> None:
    TASK_DURATION.labels(task=task).observe(seconds)


def observe_queue_wait(task: str, seconds: float) -> None:
    TASK_QUEUE_WAIT.labels(task=task).observe(seconds)


def record_retry(task: str) -> None:
    TASK_RETRIES_TOTAL.labels(task=task).inc()


def set_queue_depth(queue: str, depth: int) -> None:
    QUEUE_DEPTH.labels(queue=queue).set(depth)


def set_workers_active(count: int) -> None:
    WORKERS_ACTIVE.set(count)
