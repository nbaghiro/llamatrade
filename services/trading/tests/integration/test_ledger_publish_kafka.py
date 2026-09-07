"""Ledger fill publishing over a real Kafka broker.

Publishes through ``TradingEventPublisher`` onto a real broker and asserts the
consumed envelope (type, idempotency event id, payload fields), the PRODUCER
span the publish path opens, and the failure-status metric when the broker is
unreachable — the real publish stack end to end, no transport mocks.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from llamatrade_events import (
    CURSOR_BEGIN,
    EventBus,
    EventEnvelope,
    FillEvents,
    LedgerFill,
    derive_event_id,
)
from llamatrade_events.channels import LEDGER_FILLS
from llamatrade_events.transport.kafka import KafkaTransport
from llamatrade_proto.generated import events_pb2
from llamatrade_telemetry import tracing as tracing_module
from tests.metrics_util import sample_metric

from src.ledger_events import build_fill_payload
from src.streaming.publisher import TradingEventPublisher

pytestmark = pytest.mark.integration

LEDGER_METRIC = "llamatrade_trading_ledger_events_published_total"


async def _read_first_envelope(bus: EventBus, *, timeout: float = 30.0) -> EventEnvelope:
    async def _collect() -> EventEnvelope:
        async for _cursor, envelope in bus.tail_envelopes(
            LEDGER_FILLS.key(), from_cursor=CURSOR_BEGIN
        ):
            return envelope
        raise AssertionError("stream ended without an envelope")

    return await asyncio.wait_for(_collect(), timeout=timeout)


@pytest.fixture
def span_exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing_module, "get_tracer", provider.get_tracer)
    return exporter


async def test_publish_delivers_envelope_and_opens_a_producer_span(
    kafka_bootstrap: str, span_exporter: InMemorySpanExporter
) -> None:
    namespace = f"trd{uuid4().hex[:12]}"
    client_order_id = f"lt-{uuid4().hex[:16]}"
    account_id = uuid4()
    fill = build_fill_payload(
        tenant_id=uuid4(),
        account_id=account_id,
        sleeve_id=uuid4(),
        client_order_id=client_order_id,
        symbol="SPY",
        side="buy",
        qty=Decimal("5"),
        price=Decimal("100.50"),
        filled_at=datetime(2026, 6, 12, 14, 30, tzinfo=UTC),
        order_id=uuid4(),
    )
    success_before = sample_metric(LEDGER_METRIC, kind="order_filled", status="success")

    bus = EventBus(KafkaTransport(kafka_bootstrap, namespace=namespace))
    publisher = TradingEventPublisher(fills=FillEvents(bus=bus))
    try:
        cursor = await publisher.publish_ledger_fill(fill)
        assert cursor

        envelope = await _read_first_envelope(bus)
        assert envelope.type == events_pb2.EVENT_TYPE_LEDGER_FILL
        assert envelope.id == derive_event_id(client_order_id)
        payload = FillEvents.payload(envelope)
        assert isinstance(payload, LedgerFill)
        assert payload.client_order_id == client_order_id
        assert payload.account_id == str(account_id)
        assert payload.symbol == "SPY"
        assert payload.qty == "5"
        assert payload.price == "100.50"
    finally:
        await bus.close()

    assert sample_metric(LEDGER_METRIC, kind="order_filled", status="success") == (
        success_before + 1
    )

    producer_spans: list[ReadableSpan] = [
        s for s in span_exporter.get_finished_spans() if s.name == "publish ledger:fills"
    ]
    assert len(producer_spans) == 1
    span = producer_spans[0]
    assert span.kind == SpanKind.PRODUCER
    assert span.attributes is not None
    assert span.attributes["messaging.system"] == "kafka"
    assert span.attributes["ledger.event_kind"] == "order_filled"
    assert span.attributes["order.client_order_id"] == client_order_id
    assert span.attributes["account.id"] == str(account_id)


async def test_unreachable_broker_records_the_failure_metric(
    span_exporter: InMemorySpanExporter,
) -> None:
    fill = build_fill_payload(
        tenant_id=uuid4(),
        account_id=uuid4(),
        sleeve_id=uuid4(),
        client_order_id=f"lt-{uuid4().hex[:16]}",
        symbol="SPY",
        side="buy",
        qty=Decimal("1"),
        price=Decimal("10"),
        filled_at=datetime(2026, 6, 12, 14, 30, tzinfo=UTC),
        order_id=None,
    )
    failure_before = sample_metric(LEDGER_METRIC, kind="order_filled", status="failure")

    bus = EventBus(
        KafkaTransport(
            "127.0.0.1:1",
            namespace=f"trd{uuid4().hex[:12]}",
            client_start_timeout_seconds=3.0,
        )
    )
    publisher = TradingEventPublisher(fills=FillEvents(bus=bus))
    try:
        with pytest.raises(Exception):
            await publisher.publish_ledger_fill(fill)
    finally:
        await bus.close()

    assert sample_metric(LEDGER_METRIC, kind="order_filled", status="failure") == (
        failure_before + 1
    )
