"""Telemetry for Celery worker/beat processes: init signals + per-task spans.

Worker and beat processes have no ASGI app, so ``init_telemetry`` runs off
Celery lifecycle signals rather than module import: ``worker_init`` covers the
worker main process (which also hosts embedded beat under ``worker -B``),
``worker_process_init`` covers each pool child, and ``beat_init`` covers a
standalone beat. None of these signals fire in the API process, which wires
telemetry itself in ``src.main``.

Task tracing: the enqueue side injects the W3C context into the message
headers (``apply_async(headers=...)``); ``task_prerun`` extracts it and opens
a CONSUMER span per task, ``task_postrun`` closes it. A message with no trace
headers (a reaper re-enqueue, a beat-scheduled task) extracts an empty context
and the span becomes a new root.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextvars import Token

from celery import states
from celery.signals import (
    beat_init,
    task_postrun,
    task_prerun,
    worker_init,
    worker_process_init,
)
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import SpanKind, Status, StatusCode

from llamatrade_telemetry import extract_context, get_tracer, init_telemetry

WORKER_SERVICE_NAME = "backtest-worker"

_RUN_TASK_SUFFIX = "run_backtest_task"

# task_id -> stack of (span, context token). Keyed per task so concurrent tasks
# in one worker never collide; a stack because an eager retry re-enters the
# signals with the same task id before the outer postrun fires.
_task_spans: dict[str, list[tuple[trace.Span, Token[Context]]]] = {}


def _init_worker_telemetry(**_kwargs: object) -> None:
    """Give every Celery process JSON logs, the tracer, and the runtime monitor."""
    init_telemetry(service=WORKER_SERVICE_NAME)


def _trace_carrier(request: object) -> dict[str, str]:
    """W3C carrier from a task request: message headers, else flattened attributes.

    Depending on the task protocol, custom headers arrive either as the
    ``headers`` mapping on the request or flattened onto the request itself;
    both shapes are read so extraction survives either. An empty carrier is
    valid and extracts to an empty context.
    """
    carrier: dict[str, str] = {}
    headers = getattr(request, "headers", None)
    if isinstance(headers, Mapping):
        carrier.update(
            {str(key): value for key, value in headers.items() if isinstance(value, str)}
        )
    for key in ("traceparent", "tracestate"):
        value = getattr(request, key, None)
        if key not in carrier and isinstance(value, str):
            carrier[key] = value
    return carrier


def _on_task_prerun(
    *,
    task_id: str | None = None,
    task: object | None = None,
    args: Sequence[object] | None = None,
    **_kwargs: object,
) -> None:
    if task_id is None or task is None:
        return
    name = str(getattr(task, "name", "celery.task"))
    ctx = extract_context(_trace_carrier(getattr(task, "request", None)))
    span = get_tracer("llamatrade.backtest.worker").start_span(
        name, context=ctx, kind=SpanKind.CONSUMER
    )
    span.set_attribute("celery.task_id", task_id)
    if args and name.endswith(_RUN_TASK_SUFFIX):
        span.set_attribute("backtest.id", str(args[0]))
    token = otel_context.attach(trace.set_span_in_context(span))
    _task_spans.setdefault(task_id, []).append((span, token))


def _on_task_postrun(
    *,
    task_id: str | None = None,
    state: str | None = None,
    retval: object | None = None,
    **_kwargs: object,
) -> None:
    stack = _task_spans.get(task_id) if task_id is not None else None
    if not stack or task_id is None:
        return
    span, token = stack.pop()
    if not stack:
        del _task_spans[task_id]
    if state == states.FAILURE:
        if isinstance(retval, BaseException):
            span.record_exception(retval)
        span.set_status(Status(StatusCode.ERROR, str(retval)))
    otel_context.detach(token)
    span.end()


def register_signals() -> None:
    """Idempotent: Celery's Signal.connect deduplicates receivers."""
    worker_init.connect(_init_worker_telemetry)
    worker_process_init.connect(_init_worker_telemetry)
    beat_init.connect(_init_worker_telemetry)
    task_prerun.connect(_on_task_prerun)
    task_postrun.connect(_on_task_postrun)
