"""Celery application configuration for backtest workers."""

import os

from celery import Celery

# Redis URL for broker and result backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "backtest",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.workers.celery_tasks"],
)

# Time limits are env-configurable: long backtests (years of intraday bars)
# legitimately exceed the old 10-minute hard kill
TASK_SOFT_TIME_LIMIT = int(os.getenv("BACKTEST_TASK_SOFT_TIME_LIMIT", "1800"))
TASK_TIME_LIMIT = int(os.getenv("BACKTEST_TASK_TIME_LIMIT", "3600"))

# How often the reaper sweeps for orphaned RUNNING/PENDING runs (1A).
REAPER_INTERVAL_SECONDS = int(os.getenv("BACKTEST_REAPER_INTERVAL", "300"))

# Celery configuration
celery_app.conf.update(
    # Task execution settings
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT,
    task_time_limit=TASK_TIME_LIMIT,
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,  # Reject if worker dies
    # Retry settings
    task_default_retry_delay=60,  # Wait 60s before retry
    task_max_retries=3,
    # Result settings
    result_expires=86400,  # Results expire after 24 hours
    result_extended=True,  # Store task args in result
    # Worker settings
    worker_prefetch_multiplier=1,  # Only fetch one task at a time (for fair scheduling)
    worker_concurrency=4,  # Number of concurrent workers
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
celery_app.conf.task_routes = {
    "src.workers.celery_tasks.run_backtest_task": {"queue": "backtest"},
    "src.workers.celery_tasks.reap_stale_backtests_task": {"queue": "backtest_maintenance"},
}

# Beat schedule: periodically reap orphaned RUNNING/PENDING runs (1A).
celery_app.conf.beat_schedule = {
    "reap-stale-backtests": {
        "task": "src.workers.celery_tasks.reap_stale_backtests_task",
        "schedule": float(REAPER_INTERVAL_SECONDS),
    },
}
