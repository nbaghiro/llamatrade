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

# Celery configuration
# pyright: reportUnknownMemberType=false
celery_app.conf.update(  # type: ignore[union-attr]
    # Task execution settings
    task_soft_time_limit=300,  # 5 minutes soft limit
    task_time_limit=600,  # 10 minutes hard limit
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

# Task routing for different queues
celery_app.conf.task_routes = {  # type: ignore[union-attr]
    "src.workers.celery_tasks.run_backtest_task": {"queue": "backtest"},
    "src.workers.celery_tasks.run_symbol_chunk": {"queue": "backtest"},
    "src.workers.celery_tasks.merge_results": {"queue": "backtest"},
}
