"""End-to-end trading↔ledger contract test over a real stream (12A).

A proto ``LedgerFill`` published exactly as trading publishes it round-trips
through the real Redis Streams transport (fakeredis-backed) — publish → XADD →
consumer-group XREADGROUP → decode → translate — into the portfolio ingestion.
This exercises the transport + proto codec + translation together, which the
mock-based ingestion tests skip.
"""

from uuid import UUID, uuid4

import pytest
from fakeredis import aioredis

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import EventBus, FillEvents, LedgerFill, RedisStreamsTransport

from src.ledger.ingestion import LedgerAppend
from src.tasks.fill_ingestion import (
    CURSOR_BEGIN,
    LEDGER_FILLS_STREAM,
    PORTFOLIO_LEDGER_GROUP,
    _decode_message,
    process_stream_entry,
)

pytestmark = pytest.mark.asyncio


async def test_ledger_fill_contract_roundtrips_through_stream() -> None:
    tenant, account, sleeve = str(uuid4()), str(uuid4()), str(uuid4())
    fills = FillEvents(bus=EventBus(RedisStreamsTransport(redis_client=aioredis.FakeRedis())))

    fill = LedgerFill(
        tenant_id=tenant,
        account_id=account,
        sleeve_id=sleeve,
        client_order_id="co-xyz",
        symbol="AAPL",
        side="buy",
        qty="10",
        price="150.25",
    )
    await fills.publish_fill(fill)  # the trading side of the contract

    appends: list[LedgerAppend] = []

    async def handler(a: LedgerAppend) -> None:
        appends.append(a)

    async for _entry_id, raw in fills.bus.consume_raw(
        LEDGER_FILLS_STREAM,
        PORTFOLIO_LEDGER_GROUP,
        "test-consumer",
        group_start_id=CURSOR_BEGIN,
    ):
        message = _decode_message(raw)
        assert message is not None
        assert await process_stream_entry(handler, message) == "ack"
        break

    await fills.close()

    assert len(appends) == 1
    a = appends[0]
    assert a.tenant_id == UUID(tenant)
    assert a.account_id == UUID(account)
    assert a.sleeve_id == UUID(sleeve)
    assert a.event_type == LedgerEventType.ORDER_FILLED
    assert a.data["symbol"] == "AAPL"
    assert a.data["side"] == "buy"
    assert a.data["qty"] == "10"
    assert a.data["price"] == "150.25"
