"""Tests for the Celery trace seam: enqueue-side header injection and the
worker-side task_prerun/task_postrun span lifecycle.

Spans are asserted against the tracer provider ``init_telemetry`` configured at
import (no exporter, recording only). Injected parents use a sampled
``traceparent`` so the parent-based sampler records deterministically; header
absence must degrade to a clean root span (the reaper re-enqueue path).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest
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
from opentelemetry.trace import StatusCode, format_trace_id

from llamatrade_telemetry.tracing import span as telemetry_span

from src import worker_telemetry
from src.services.backtest_service import _enqueue_run_backtest

BACKTEST_ID = "44444444-4444-4444-4444-444444444444"
TENANT_ID = "11111111-1111-1111-1111-111111111111"

TRACE_ID_HEX = "0af7651916cd43dd8448eb211c80319c"
PARENT_SPAN_HEX = "00f067aa0ba902b7"
SAMPLED_TRACEPARENT = f"00-{TRACE_ID_HEX}-{PARENT_SPAN_HEX}-01"

RUN_TASK_NAME = "src.workers.celery_tasks.run_backtest_task"


@pytest.fixture(autouse=True)
def _isolate_otel_context():
    """End leftover task spans and restore the ambient OTel context per test."""
    token = otel_context.attach(otel_context.get_current())
    yield
    while worker_telemetry._task_spans:
        task_id = next(iter(worker_telemetry._task_spans))
        worker_telemetry._on_task_postrun(task_id=task_id, state=states.SUCCESS, retval=None)
    otel_context.detach(token)


def _task(name: str = RUN_TASK_NAME, headers: dict[str, str] | None = None) -> SimpleNamespace:
    request = SimpleNamespace()
    if headers is not None:
        request.headers = headers
    return SimpleNamespace(name=name, request=request)


class TestEnqueueInjection:
    def test_active_span_context_rides_in_headers(self) -> None:
        with patch("src.workers.celery_tasks.run_backtest_task") as task:
            task.apply_async.return_value.id = "task-123"
            with telemetry_span("test-enqueue") as current:
                result = _enqueue_run_backtest(UUID(BACKTEST_ID), UUID(TENANT_ID))

        assert result == "task-123"
        kwargs = task.apply_async.call_args.kwargs
        assert kwargs["args"] == (BACKTEST_ID, TENANT_ID)
        traceparent = kwargs["headers"]["traceparent"]
        assert format_trace_id(current.get_span_context().trace_id) in traceparent

    def test_no_active_span_sends_empty_headers(self) -> None:
        with patch("src.workers.celery_tasks.run_backtest_task") as task:
            task.apply_async.return_value.id = "task-456"
            result = _enqueue_run_backtest(UUID(BACKTEST_ID), UUID(TENANT_ID))

        assert result == "task-456"
        assert task.apply_async.call_args.kwargs["headers"] == {}


class TestTaskSpanLifecycle:
    def test_prerun_links_injected_parent_and_postrun_closes(self) -> None:
        task = _task(headers={"traceparent": SAMPLED_TRACEPARENT})
        worker_telemetry._on_task_prerun(task_id="t-1", task=task, args=(BACKTEST_ID, TENANT_ID))

        span, _token = worker_telemetry._task_spans["t-1"][-1]
        context = span.get_span_context()
        assert context.trace_id == int(TRACE_ID_HEX, 16)
        assert span.parent is not None
        assert span.parent.span_id == int(PARENT_SPAN_HEX, 16)
        assert span.attributes is not None
        assert span.attributes["celery.task_id"] == "t-1"
        assert span.attributes["backtest.id"] == BACKTEST_ID
        # The span is current while the task runs, so nested spans parent to it.
        assert trace.get_current_span().get_span_context().span_id == context.span_id

        worker_telemetry._on_task_postrun(task_id="t-1", state=states.SUCCESS, retval=None)

        assert "t-1" not in worker_telemetry._task_spans
        assert span.end_time is not None
        assert span.status.status_code is StatusCode.UNSET
        assert trace.get_current_span().get_span_context().span_id != context.span_id

    def test_protocol2_flattened_traceparent_is_extracted(self) -> None:
        task = _task(headers=None)
        task.request.traceparent = SAMPLED_TRACEPARENT

        worker_telemetry._on_task_prerun(task_id="t-2", task=task, args=(BACKTEST_ID,))
        span, _token = worker_telemetry._task_spans["t-2"][-1]
        assert span.get_span_context().trace_id == int(TRACE_ID_HEX, 16)
        worker_telemetry._on_task_postrun(task_id="t-2", state=states.SUCCESS, retval=None)

    def test_failure_marks_error_status(self) -> None:
        task = _task(headers={"traceparent": SAMPLED_TRACEPARENT})
        worker_telemetry._on_task_prerun(task_id="t-3", task=task, args=(BACKTEST_ID,))
        span, _token = worker_telemetry._task_spans["t-3"][-1]

        boom = ValueError("bad strategy")
        worker_telemetry._on_task_postrun(task_id="t-3", state=states.FAILURE, retval=boom)

        assert span.status.status_code is StatusCode.ERROR
        assert any(event.name == "exception" for event in span.events)
        assert span.end_time is not None

    def test_absent_headers_yield_a_clean_root_span(self) -> None:
        task = _task(name="src.workers.celery_tasks.reap_stale_backtests_task", headers=None)

        worker_telemetry._on_task_prerun(task_id="t-4", task=task, args=())
        assert "t-4" in worker_telemetry._task_spans
        worker_telemetry._on_task_postrun(task_id="t-4", state=states.SUCCESS, retval=None)
        assert "t-4" not in worker_telemetry._task_spans

    def test_concurrent_tasks_do_not_collide(self) -> None:
        first = _task(headers={"traceparent": SAMPLED_TRACEPARENT})
        second = _task(headers=None)
        worker_telemetry._on_task_prerun(task_id="t-5", task=first, args=(BACKTEST_ID,))
        worker_telemetry._on_task_prerun(task_id="t-6", task=second, args=(BACKTEST_ID,))

        span_a, _ = worker_telemetry._task_spans["t-5"][-1]
        span_b, _ = worker_telemetry._task_spans["t-6"][-1]
        assert span_a is not span_b

        worker_telemetry._on_task_postrun(task_id="t-5", state=states.SUCCESS, retval=None)
        assert "t-6" in worker_telemetry._task_spans
        worker_telemetry._on_task_postrun(task_id="t-6", state=states.SUCCESS, retval=None)
        assert worker_telemetry._task_spans == {}

    def test_eager_retry_reenters_the_same_task_id_without_leaking(self) -> None:
        task = _task(headers={"traceparent": SAMPLED_TRACEPARENT})
        worker_telemetry._on_task_prerun(task_id="t-r", task=task, args=(BACKTEST_ID,))
        outer, _ = worker_telemetry._task_spans["t-r"][-1]
        worker_telemetry._on_task_prerun(task_id="t-r", task=task, args=(BACKTEST_ID,))
        inner, _ = worker_telemetry._task_spans["t-r"][-1]
        assert inner is not outer

        worker_telemetry._on_task_postrun(task_id="t-r", state=states.SUCCESS, retval=None)
        assert inner.end_time is not None
        assert outer.end_time is None
        worker_telemetry._on_task_postrun(task_id="t-r", state=states.SUCCESS, retval=None)
        assert outer.end_time is not None
        assert worker_telemetry._task_spans == {}
        assert trace.get_current_span().get_span_context().trace_id != int(TRACE_ID_HEX, 16)

    def test_missing_task_id_or_unknown_postrun_is_a_noop(self) -> None:
        worker_telemetry._on_task_prerun(task_id=None, task=_task())
        worker_telemetry._on_task_prerun(task_id="t-7", task=None)
        assert worker_telemetry._task_spans == {}
        worker_telemetry._on_task_postrun(task_id="never-started", state=states.SUCCESS)


class TestSignalWiring:
    """The -A entrypoint's register_signals() must leave the hooks connected."""

    @staticmethod
    def _connected(signal, handler) -> bool:
        return any(receiver is handler for receiver in signal._live_receivers(None))

    def test_init_hooks_cover_worker_pool_and_beat(self) -> None:
        worker_telemetry.register_signals()

        for signal in (worker_init, worker_process_init, beat_init):
            assert self._connected(signal, worker_telemetry._init_worker_telemetry)

    def test_task_span_hooks_are_connected(self) -> None:
        assert self._connected(task_prerun, worker_telemetry._on_task_prerun)
        assert self._connected(task_postrun, worker_telemetry._on_task_postrun)

    def test_worker_init_is_idempotent(self) -> None:
        worker_telemetry._init_worker_telemetry()
        worker_telemetry._init_worker_telemetry(sender=object())
