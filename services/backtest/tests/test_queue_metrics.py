"""Tests for the API-side samplers: Celery queue depth and DB job states.

Assertions go against the unified telemetry exposition (``get_metrics()``)
rather than prometheus_client internals, so they verify the real
``llamatrade_celery_queue_depth`` and ``llamatrade_backtest_jobs`` series
operators consume.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.sql.elements import TextClause

from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
)
from llamatrade_telemetry import conventions, get_metrics

from src.celery_app import EXECUTION_QUEUE, TASK_ROUTES, WORKER_QUEUES
from src.queue_metrics import (
    JOB_STATE_WINDOW_SECONDS,
    JobStateSampler,
    QueueDepthSampler,
    _RedisBroker,
)

METRIC = "llamatrade_celery_queue_depth"
JOBS_METRIC = "llamatrade_backtest_jobs"


def _exposition() -> str:
    """Render the current Prometheus exposition output."""
    return get_metrics().decode()


def _sample(text: str, name: str, **labels: str) -> float | None:
    """Return the value of a single Prometheus sample, or ``None`` if absent."""
    label_parts = {f'{k}="{v}"' for k, v in labels.items()}
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        head, _, value = line.rpartition(" ")
        if head != name and not head.startswith(name + "{"):
            continue
        if "{" in head:
            inner = head[head.index("{") + 1 : head.rindex("}")]
            line_labels = {part for part in inner.split(",") if part}
            if not label_parts.issubset(line_labels):
                continue
        elif label_parts:
            continue
        return float(value)
    return None


def _labels_of(text: str, name: str, **labels: str) -> set[str]:
    """Return the label pairs on the first matching sample line."""
    label_parts = {f'{k}="{v}"' for k, v in labels.items()}
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        head, _, _value = line.rpartition(" ")
        if not head.startswith(name + "{"):
            continue
        inner = head[head.index("{") + 1 : head.rindex("}")]
        line_labels = {part for part in inner.split(",") if part}
        if label_parts.issubset(line_labels):
            return line_labels
    return set()


class FakeBroker:
    """In-memory stand-in for the async Redis broker client."""

    def __init__(self, depths: dict[str, int] | None = None) -> None:
        self.depths = depths or {}
        self.calls: list[str] = []
        self.closed = False
        self.fail_with: Exception | None = None

    async def llen(self, name: str) -> int:
        self.calls.append(name)
        if self.fail_with is not None:
            raise self.fail_with
        return self.depths.get(name, 0)

    async def aclose(self) -> None:
        self.closed = True


class TestQueueCoverage:
    """The sampler must cover every queue a worker consumes."""

    def test_worker_queues_match_routing_config(self) -> None:
        routed = {route["queue"] for route in TASK_ROUTES.values()}
        assert set(WORKER_QUEUES) == routed
        assert WORKER_QUEUES == tuple(sorted(routed))

    def test_execution_queue_is_the_run_backtest_queue(self) -> None:
        assert EXECUTION_QUEUE == "backtest"
        assert EXECUTION_QUEUE in WORKER_QUEUES

    async def test_every_routed_queue_is_sampled(self) -> None:
        broker = FakeBroker()
        depths = await QueueDepthSampler(broker=broker).sample_once()
        assert set(depths) == set(WORKER_QUEUES)
        assert broker.calls == list(WORKER_QUEUES)


class TestSampleOnce:
    async def test_publishes_depth_per_queue(self) -> None:
        broker = FakeBroker({"backtest": 7, "backtest_maintenance": 2})
        await QueueDepthSampler(broker=broker).sample_once()

        text = _exposition()
        assert _sample(text, METRIC, queue="backtest") == 7.0
        assert _sample(text, METRIC, queue="backtest_maintenance") == 2.0

    async def test_empty_queue_reports_zero(self) -> None:
        await QueueDepthSampler(broker=FakeBroker({"backtest": 4})).sample_once()
        await QueueDepthSampler(broker=FakeBroker({"backtest": 0})).sample_once()

        assert _sample(_exposition(), METRIC, queue="backtest") == 0.0

    async def test_sample_reflects_latest_depth(self) -> None:
        broker = FakeBroker({"backtest": 1})
        sampler = QueueDepthSampler(broker=broker)
        await sampler.sample_once()
        broker.depths["backtest"] = 42
        await sampler.sample_once()

        assert _sample(_exposition(), METRIC, queue="backtest") == 42.0

    async def test_broker_failure_propagates_and_leaves_gauge_untouched(self) -> None:
        broker = FakeBroker({"backtest": 9})
        sampler = QueueDepthSampler(broker=broker)
        await sampler.sample_once()

        broker.fail_with = ConnectionError("broker down")
        with pytest.raises(ConnectionError):
            await sampler.sample_once()

        assert _sample(_exposition(), METRIC, queue="backtest") == 9.0


class TestConventions:
    """The gauge must stay scrape-safe: bounded labels, no tenant dimension."""

    def test_name_and_label_key_are_allowed(self) -> None:
        conventions.validate_metric_name(METRIC)
        conventions.validate_label_keys(["queue"])

    async def test_series_carries_only_the_queue_label(self) -> None:
        await QueueDepthSampler(broker=FakeBroker({"backtest": 3})).sample_once()

        labels = _labels_of(_exposition(), METRIC, queue="backtest")
        # The OTel exporter may append otel_scope_* labels; only ours matter.
        assert {part for part in labels if not part.startswith("otel_scope_")} == {
            'queue="backtest"'
        }


class TestSamplingLoop:
    async def test_start_samples_then_keeps_sampling(self) -> None:
        broker = FakeBroker({"backtest": 5})
        sampler = QueueDepthSampler(broker=broker, interval_seconds=0.001)
        await sampler.start()
        try:
            for _ in range(200):
                if broker.calls.count("backtest") >= 2:
                    break
                await asyncio.sleep(0.005)
        finally:
            await sampler.stop()

        assert broker.calls.count("backtest") >= 2
        assert _sample(_exposition(), METRIC, queue="backtest") == 5.0

    async def test_start_is_idempotent(self) -> None:
        sampler = QueueDepthSampler(broker=FakeBroker(), interval_seconds=60)
        await sampler.start()
        first = sampler._task
        await sampler.start()
        try:
            assert sampler._task is first
        finally:
            await sampler.stop()

    async def test_start_survives_an_unreachable_broker(self) -> None:
        broker = FakeBroker()
        broker.fail_with = ConnectionError("broker down")
        sampler = QueueDepthSampler(broker=broker, interval_seconds=0.001)

        await sampler.start()
        try:
            await asyncio.sleep(0.02)
        finally:
            await sampler.stop()

        assert broker.calls, "the loop must keep polling through broker failures"

    async def test_loop_recovers_after_failure(self) -> None:
        broker = FakeBroker({"backtest": 11})
        broker.fail_with = ConnectionError("broker down")
        sampler = QueueDepthSampler(broker=broker, interval_seconds=0.001)

        await sampler.start()
        try:
            broker.fail_with = None
            for _ in range(200):
                if _sample(_exposition(), METRIC, queue="backtest") == 11.0:
                    break
                await asyncio.sleep(0.005)
        finally:
            await sampler.stop()

        assert _sample(_exposition(), METRIC, queue="backtest") == 11.0

    async def test_stop_closes_the_broker_and_clears_the_task(self) -> None:
        broker = FakeBroker()
        sampler = QueueDepthSampler(broker=broker, interval_seconds=60)
        await sampler.start()
        await sampler.stop()

        assert broker.closed is True
        assert sampler._task is None

    async def test_stop_without_start_is_a_no_op(self) -> None:
        sampler = QueueDepthSampler(broker=FakeBroker())
        await sampler.stop()

    async def test_defaults_to_a_reused_redis_broker(self) -> None:
        sampler = QueueDepthSampler(redis_url="redis://localhost:6379/0")
        broker = sampler._client()
        try:
            assert isinstance(broker, _RedisBroker)
            assert sampler._client() is broker
        finally:
            await sampler.stop()


NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


class FakeJobSession:
    """In-memory stand-in for an AsyncSession seeded with grouped status counts."""

    def __init__(
        self,
        rows: list[tuple[int, int]] | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.fail_with = fail_with
        self.statements: list[object] = []

    async def execute(self, stmt: object, params: object | None = None) -> MagicMock:
        self.statements.append(stmt)
        if isinstance(stmt, TextClause):
            return MagicMock()
        if self.fail_with is not None:
            raise self.fail_with
        result = MagicMock()
        result.all.return_value = self.rows
        return result


class _FakeSessionCM:
    def __init__(self, session: FakeJobSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeJobSession:
        return self._session

    async def __aexit__(self, *exc: object) -> None:
        return None


def _job_sampler(session: FakeJobSession, **kwargs: float) -> JobStateSampler:
    return JobStateSampler(session_maker=lambda: _FakeSessionCM(session), **kwargs)


class TestJobStateSampler:
    async def test_publishes_counts_per_state(self) -> None:
        session = FakeJobSession(
            rows=[
                (BACKTEST_STATUS_RUNNING, 3),
                (BACKTEST_STATUS_PENDING, 1),
                (BACKTEST_STATUS_COMPLETED, 5),
                (BACKTEST_STATUS_FAILED, 2),
            ]
        )
        counts = await _job_sampler(session).sample_once(now=NOW)

        assert counts == {"running": 3, "pending": 1, "completed": 5, "failed": 2}
        text = _exposition()
        assert _sample(text, JOBS_METRIC, state="running") == 3.0
        assert _sample(text, JOBS_METRIC, state="pending") == 1.0
        assert _sample(text, JOBS_METRIC, state="completed") == 5.0
        assert _sample(text, JOBS_METRIC, state="failed") == 2.0

    async def test_absent_states_publish_zero(self) -> None:
        await _job_sampler(FakeJobSession(rows=[(BACKTEST_STATUS_RUNNING, 9)])).sample_once()
        await _job_sampler(FakeJobSession(rows=[])).sample_once()

        text = _exposition()
        for state in ("running", "pending", "completed", "failed"):
            assert _sample(text, JOBS_METRIC, state=state) == 0.0

    async def test_rls_bypass_is_bound_before_the_count_query(self) -> None:
        session = FakeJobSession()
        await _job_sampler(session).sample_once(now=NOW)

        assert len(session.statements) == 2
        assert isinstance(session.statements[0], TextClause)
        assert "set_config" in str(session.statements[0])

    async def test_query_scopes_terminal_states_to_the_window(self) -> None:
        session = FakeJobSession()
        await _job_sampler(session).sample_once(now=NOW)

        stmt = session.statements[-1]
        rendered = str(stmt)
        assert "backtests" in rendered
        assert "GROUP BY" in rendered

        flat: list[object] = []
        for value in stmt.compile().params.values():
            if isinstance(value, (list, tuple)):
                flat.extend(value)
            else:
                flat.append(value)
        assert NOW - timedelta(seconds=JOB_STATE_WINDOW_SECONDS) in flat
        for status in (
            BACKTEST_STATUS_RUNNING,
            BACKTEST_STATUS_PENDING,
            BACKTEST_STATUS_COMPLETED,
            BACKTEST_STATUS_FAILED,
        ):
            assert status in flat

    async def test_db_failure_propagates_and_leaves_gauges_untouched(self) -> None:
        await _job_sampler(FakeJobSession(rows=[(BACKTEST_STATUS_RUNNING, 7)])).sample_once()

        with pytest.raises(ConnectionError):
            await _job_sampler(FakeJobSession(fail_with=ConnectionError("db down"))).sample_once()

        assert _sample(_exposition(), JOBS_METRIC, state="running") == 7.0

    async def test_start_stop_lifecycle(self) -> None:
        sampler = _job_sampler(FakeJobSession(), interval_seconds=60)
        await sampler.start()
        try:
            assert sampler._task is not None
        finally:
            await sampler.stop()
        assert sampler._task is None


class TestJobStateConventions:
    """The gauge must stay scrape-safe: bounded labels, no tenant dimension."""

    def test_name_and_label_key_are_allowed(self) -> None:
        conventions.validate_metric_name(JOBS_METRIC)
        conventions.validate_label_keys(["state"])

    async def test_series_carries_only_the_state_label(self) -> None:
        await _job_sampler(FakeJobSession(rows=[(BACKTEST_STATUS_RUNNING, 4)])).sample_once()

        labels = _labels_of(_exposition(), JOBS_METRIC, state="running")
        assert {part for part in labels if not part.startswith("otel_scope_")} == {
            'state="running"'
        }

    def test_main_wires_both_samplers(self) -> None:
        from src.main import job_state_sampler, queue_depth_sampler

        assert isinstance(job_state_sampler, JobStateSampler)
        assert isinstance(queue_depth_sampler, QueueDepthSampler)
