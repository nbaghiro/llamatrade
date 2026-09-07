"""A strategy session has no inbound request, so the runner roots its own traces.

Without these roots the broker call and each ledger publish start separate
traces, and nothing ties them to the evaluation that caused them.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from llamatrade_alpaca import TradeEvent, TradeEventType
from llamatrade_telemetry import span, tracing
from tests.session_util import hold_session
from tests.test_runner import _bar_at, _build_runner

from src.runner.runner import RunnerConfig


@pytest.fixture
def config() -> RunnerConfig:
    return RunnerConfig(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        strategy_id=uuid4(),
        symbols=["AAPL"],
        timeframe="1min",
        warmup_bars=10,
    )


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    saved_provider, saved_configured = tracing._provider, tracing._configured
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracing._provider, tracing._configured = provider, True
    yield exporter
    tracing._provider, tracing._configured = saved_provider, saved_configured


def _named(exporter: InMemorySpanExporter, name: str):
    return [s for s in exporter.get_finished_spans() if s.name == name]


async def test_bar_evaluation_roots_a_trace_that_downstream_work_joins(config, spans) -> None:
    runner = _build_runner(config, hold_session("AAPL"), AsyncMock(), AsyncMock())

    # Stand in for the work a tick does: the broker call and the ledger publish
    # both open spans of their own further down.
    async def _inside(bar) -> None:
        with span("alpaca submit_order"):
            pass

    runner._process_bar_traced = _inside

    await runner._process_bar(_bar_at(datetime.now(UTC)))

    evaluate = _named(spans, "evaluate AAPL")
    downstream = _named(spans, "alpaca submit_order")
    assert evaluate, "the tick did not open a root span"
    assert downstream, "downstream work did not run"
    assert evaluate[0].parent is None, "the tick must root its own trace"
    assert downstream[0].context.trace_id == evaluate[0].context.trace_id
    assert downstream[0].parent.span_id == evaluate[0].context.span_id


async def test_evaluate_span_carries_the_execution_and_symbol(config, spans) -> None:
    runner = _build_runner(config, hold_session("AAPL"), AsyncMock(), AsyncMock())
    runner._process_bar_traced = AsyncMock()

    await runner._process_bar(_bar_at(datetime.now(UTC)))

    attributes = _named(spans, "evaluate AAPL")[0].attributes
    assert attributes["llamatrade.symbol"] == "AAPL"
    assert attributes["llamatrade.execution_id"] == str(config.execution_id)


async def test_a_fill_is_its_own_trace_not_a_child_of_the_tick(config, spans) -> None:
    """A fill arrives long after the tick that placed the order."""
    runner = _build_runner(config, hold_session("AAPL"), AsyncMock(), AsyncMock())
    runner._process_bar_traced = AsyncMock()
    runner._handle_trade_event_traced = AsyncMock()

    await runner._process_bar(_bar_at(datetime.now(UTC)))
    await runner._handle_trade_event(
        TradeEvent(
            event_type=TradeEventType.FILL,
            symbol="AAPL",
            order_id="6d2a11bf-90c4-4f0e-a3d7-5b8e1c02f4a9",
            client_order_id="lt-8f21c4de",
            side="buy",
            order_type="market",
            qty=Decimal("25"),
            filled_qty=Decimal("25"),
            filled_avg_price=Decimal("150.00"),
            timestamp=datetime.now(UTC),
        )
    )

    evaluate = _named(spans, "evaluate AAPL")[0]
    fill = _named(spans, "trade-event fill AAPL")[0]
    assert fill.parent is None
    assert fill.context.trace_id != evaluate.context.trace_id


async def test_runtime_loop_order_also_roots_a_trace(config, spans) -> None:
    """The runtime feed drives evaluation itself, so _process_bar never runs."""
    runner = _build_runner(config, hold_session("AAPL"), AsyncMock(), AsyncMock())
    runner._process_signal = AsyncMock()

    await runner._submit_runtime_order("buy", "AAPL", 25.0, 150.0, datetime.now(UTC))

    evaluate = _named(spans, "evaluate AAPL")
    assert evaluate, "the runtime path did not open a root span"
    assert evaluate[0].parent is None
