"""Ledger incidents that affect a tenant's money must dispatch tenant alerts."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from llamatrade_proto.generated import events_pb2

from src.ledger.ingestion import FillQuarantineError
from src.tasks.fill_ingestion import process_stream_entry


def _fill() -> events_pb2.LedgerFill:
    return events_pb2.LedgerFill(
        tenant_id=str(uuid4()),
        account_id=str(uuid4()),
        sleeve_id=str(uuid4()),
        client_order_id="lt-abc123",
        symbol="SPY",
        side="sell",
        qty="10",
        price="100",
        filled_at="2026-07-28T14:30:00Z",
    )


@pytest.mark.asyncio
async def test_quarantine_dispatches_tenant_alert() -> None:
    async def handler(append: object) -> None:
        raise FillQuarantineError("sell exceeds open lots")

    dispatcher = AsyncMock()
    with patch("src.alerts.get_ledger_alert_dispatcher", return_value=dispatcher):
        verdict = await process_stream_entry(handler, _fill())

    assert verdict == "drop"
    dispatcher.dispatch.assert_awaited_once()
    _, incident = dispatcher.dispatch.await_args.args
    assert incident.kind == "fill_quarantined"
    assert incident.context["client_order_id"] == "lt-abc123"


@pytest.mark.asyncio
async def test_alert_failure_does_not_change_verdict() -> None:
    async def handler(append: object) -> None:
        raise FillQuarantineError("sell exceeds open lots")

    dispatcher = AsyncMock()
    dispatcher.dispatch = AsyncMock(side_effect=RuntimeError("webhook store down"))
    with patch("src.alerts.get_ledger_alert_dispatcher", return_value=dispatcher):
        verdict = await process_stream_entry(handler, _fill())

    assert verdict == "drop"
