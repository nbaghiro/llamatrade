"""Celery application configuration for backtest workers."""

import os

from celery import Celery

# This module is the -A entrypoint, so every Celery process registers here.
from src.worker_telemetry import register_signals

register_signals()

# Redis URL for broker and result backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "backtest",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.workers.celery_tasks"],
)

# Time limits are env-configurable: long backtests (years of intraday bars) can need > 10 min.
TASK_SOFT_TIME_LIMIT = int(os.getenv("BACKTEST_TASK_SOFT_TIME_LIMIT", "1800"))
TASK_TIME_LIMIT = int(os.getenv("BACKTEST_TASK_TIME_LIMIT", "3600"))

# Concurrency defaults to 2 to match the worker's 2-CPU limit; the manifest also
# pins --concurrency so a config drift cannot oversubscribe the pod.
WORKER_CONCURRENCY = int(os.getenv("BACKTEST_WORKER_CONCURRENCY", "2"))

# How often the reaper sweeps for orphaned RUNNING/PENDING runs.
REAPER_INTERVAL_SECONDS = int(os.getenv("BACKTEST_REAPER_INTERVAL", "300"))

# Celery configuration
celery_app.conf.update(
    # Task execution settings
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT,
    task_time_limit=TASK_TIME_LIMIT,
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,  # Reject if worker dies
    # With acks_late a task is redelivered if it outlives the broker visibility
    # timeout. Kombu's default equals task_time_limit (3600s), so a task still
    # running at the hour mark is handed to a second worker and the backtest runs
    # twice. Set the timeout past the hard limit so a live task is never
    # redelivered; Celery kills it at task_time_limit anyway.
    broker_transport_options={"visibility_timeout": TASK_TIME_LIMIT * 2},
    # Retry settings
    task_default_retry_delay=60,  # Wait 60s before retry
    task_max_retries=3,
    # Result settings
    result_expires=86400,  # Results expire after 24 hours
    result_extended=True,  # Store task args in result
    # Worker settings
    worker_prefetch_multiplier=1,  # Only fetch one task at a time (for fair scheduling)
    worker_concurrency=WORKER_CONCURRENCY,  # Number of concurrent workers
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
)

# Task routing for different queues. The reaper runs on a dedicated maintenance
# queue so it is never starved behind long-running backtests on the main queue.
TASK_ROUTES: dict[str, dict[str, str]] = {
    "src.workers.celery_tasks.run_backtest_task": {"queue": "backtest"},
    "src.workers.celery_tasks.reap_stale_backtests_task": {"queue": "backtest_maintenance"},
    "src.workers.celery_tasks.evict_stale_datasets_task": {"queue": "backtest_maintenance"},
}
celery_app.conf.task_routes = TASK_ROUTES

# The queue named by each route is also the Redis list key the broker enqueues to.
WORKER_QUEUES: tuple[str, ...] = tuple(sorted({r["queue"] for r in TASK_ROUTES.values()}))

# The queue that holds runs waiting for a backtest worker; the autoscaling signal.
EXECUTION_QUEUE = TASK_ROUTES["src.workers.celery_tasks.run_backtest_task"]["queue"]

# Beat schedule: periodically reap orphaned RUNNING/PENDING runs.
celery_app.conf.beat_schedule = {
    "reap-stale-backtests": {
        "task": "src.workers.celery_tasks.reap_stale_backtests_task",
        "schedule": float(REAPER_INTERVAL_SECONDS),
    },
    "evict-stale-datasets": {
        "task": "src.workers.celery_tasks.evict_stale_datasets_task",
        "schedule": float(int(os.getenv("BACKTEST_DATASET_JANITOR_INTERVAL", "86400"))),
    },
}
