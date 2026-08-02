"""Dual-path ledger emission: stream path + REST-sync path collapse to one event.

The same order can emit a ``LedgerFill`` twice — once from the runner's
trade-stream loop and once from the executor's REST recovery sync
(``sync_order_status``). Both paths are driven here against ONE real
``FillEvents`` publisher over the in-memory ``FakeTransport``, and the test
asserts both records ride the same stream, keyed by account, carrying the SAME
deterministic envelope event id — the key the portfolio writer dedups on, so
exactly one ledger row can ever result (the fold half of the proof runs in
``services/portfolio/tests/test_invariant_freeze_e2e.py``).
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from llamatrade_alpaca import MockBarStream, MockTradeStream, TradingClient
from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import OrderSide as AlpacaOrderSide
from llamatrade_alpaca import OrderStatus as AlpacaOrderStatus
from llamatrade_alpaca import OrderType as AlpacaOrderType
from llamatrade_alpaca import TimeInForce as AlpacaTimeInForce
from llamatrade_alpaca.models import FillData, TradeEvent, TradeEventType
from llamatrade_db.models.trading import Order
from llamatrade_events import (
    EventBus,
    FillEvents,
    LedgerFill,
    OrderEvents,
    PositionEvents,
    decode_envelope,
    derive_event_id,
)
from llamatrade_events.testing import FakeTransport, PublishRecord
from llamatrade_proto.generated import events_pb2
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)

from src.executor.order_executor import OrderExecutor
from src.risk.risk_manager import RiskManager
from src.runner.runner import RunnerConfig, StrategyRunner
from src.streaming.publisher import TradingEventPublisher

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
SLEEVE_ID = UUID("33333333-3333-3333-3333-333333333333")
SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
CLIENT_ORDER_ID = "lt-dualpath0001"
FILLED_AT = datetime(2026, 7, 20, 14, 30, tzinfo=UTC)
LEDGER_STREAM = "ledger:fills"


def _publisher(transport: FakeTransport) -> TradingEventPublisher:
    """A real publisher whose every channel rides the shared fake transport."""
    bus = EventBus(transport)
    return TradingEventPublisher(
        orders_events=OrderEvents(bus=bus),
        positions_events=PositionEvents(bus=bus),
        fills=FillEvents(bus=bus),
    )


def _runner(publisher: TradingEventPublisher) -> StrategyRunner:
    config = RunnerConfig(
        tenant_id=TENANT_ID,
        execution_id=SESSION_ID,
        strategy_id=uuid4(),
        symbols=["SPY"],
        timeframe="1min",
        warmup_bars=5,
        sleeve_id=SLEEVE_ID,
        account_id=ACCOUNT_ID,
    )
    return StrategyRunner(
        config=config,
        strategy_fn=MagicMock(return_value=None),
        bar_stream=MockBarStream(bars={"SPY": []}),
        trade_stream=MockTradeStream(),
        order_executor=cast(OrderExecutor, AsyncMock()),
        risk_manager=cast(RiskManager, AsyncMock()),
        ledger_publisher=publisher,
    )


def _fill_trade_event() -> TradeEvent:
    fill = FillData(
        order_id="alpaca-1",
        client_order_id=CLIENT_ORDER_ID,
        symbol="SPY",
        side="buy",
        fill_qty=Decimal("50"),
        fill_price=Decimal("480.00"),
        total_filled_qty=Decimal("50"),
        remaining_qty=Decimal("0"),
        timestamp=FILLED_AT,
    )
    return TradeEvent(
        event_type=TradeEventType.FILL,
        order_id="alpaca-1",
        client_order_id=CLIENT_ORDER_ID,
        symbol="SPY",
        side="buy",
        order_type="market",
        qty=Decimal("50"),
        filled_qty=Decimal("50"),
        filled_avg_price=Decimal("480.00"),
        timestamp=FILLED_AT,
        fill=fill,
    )


def _db_order() -> Order:
    order = Order(
        tenant_id=TENANT_ID,
        session_id=SESSION_ID,
        client_order_id=CLIENT_ORDER_ID,
        symbol="SPY",
        side=ORDER_SIDE_BUY,
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
        qty=Decimal("50"),
        status=ORDER_STATUS_SUBMITTED,
        filled_qty=Decimal("0"),
        sleeve_id=SLEEVE_ID,
        account_id=ACCOUNT_ID,
    )
    order.id = uuid4()
    order.alpaca_order_id = "alpaca-1"
    return order


class _SingleOrderDB:
    """AsyncSession double serving one Order row to the sync path."""

    def __init__(self, order: Order) -> None:
        self._order = order

    async def execute(self, stmt: Select[tuple[Order]]) -> MagicMock:
        await asyncio.sleep(0)
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._order
        return result

    async def commit(self) -> None:
        await asyncio.sleep(0)

    async def refresh(self, obj: Order) -> None:
        await asyncio.sleep(0)

    async def close(self) -> None:
        return None


class _FilledBroker:
    """Broker double reporting the order terminal-FILLED via REST."""

    async def get_order(self, order_id: str) -> AlpacaOrder:
        await asyncio.sleep(0)
        return AlpacaOrder(
            id=order_id,
            client_order_id=CLIENT_ORDER_ID,
            symbol="SPY",
            qty=Decimal("50"),
            filled_qty=Decimal("50"),
            side=AlpacaOrderSide.BUY,
            order_type=AlpacaOrderType.MARKET,
            status=AlpacaOrderStatus.FILLED,
            time_in_force=AlpacaTimeInForce.DAY,
            filled_avg_price=Decimal("480.00"),
            created_at=FILLED_AT,
            filled_at=FILLED_AT,
        )


def _executor(order: Order, publisher: TradingEventPublisher) -> OrderExecutor:
    return OrderExecutor(
        db=cast(AsyncSession, _SingleOrderDB(order)),
        alpaca_client=cast(TradingClient, _FilledBroker()),
        risk_manager=cast(RiskManager, AsyncMock()),
        event_publisher=publisher,
    )


def _ledger_records(transport: FakeTransport) -> list[PublishRecord]:
    return [r for r in transport.records if r.stream == LEDGER_STREAM]


class TestDualPathEmission:
    """Stream + REST paths for the SAME order share one idempotency key."""

    async def _drive_both_paths(self, transport: FakeTransport) -> Order:
        publisher = _publisher(transport)
        runner = _runner(publisher)
        await runner._handle_trade_event(_fill_trade_event())

        order = _db_order()
        executor = _executor(order, publisher)
        synced = await executor.sync_order_status(order.id, TENANT_ID)
        assert synced is not None
        return order

    async def test_both_paths_publish_the_same_ledger_event_id(self) -> None:
        transport = FakeTransport()
        await self._drive_both_paths(transport)

        records = _ledger_records(transport)
        assert len(records) == 2  # one publish per path
        envelopes = [decode_envelope(r.value) for r in records]
        assert {env.id for env in envelopes} == {derive_event_id(CLIENT_ORDER_ID)}
        assert all(env.type == events_pb2.EVENT_TYPE_LEDGER_FILL for env in envelopes)

    async def test_both_paths_key_by_account_and_agree_on_economics(self) -> None:
        transport = FakeTransport()
        await self._drive_both_paths(transport)

        records = _ledger_records(transport)
        assert {r.key for r in records} == {str(ACCOUNT_ID)}
        fills = [cast(LedgerFill, FillEvents.payload(decode_envelope(r.value))) for r in records]
        for fill in fills:
            assert fill.client_order_id == CLIENT_ORDER_ID
            assert fill.sleeve_id == str(SLEEVE_ID)
            assert fill.side == "buy"
            assert fill.qty == "50"
            assert fill.price == "480.00"

    async def test_writer_dedup_on_event_id_folds_both_records_to_one(self) -> None:
        """The writer-side contract in miniature: applying each record once,
        keyed on its envelope event id, yields exactly one ledger event."""
        transport = FakeTransport()
        await self._drive_both_paths(transport)

        applied: dict[str, LedgerFill] = {}
        for record in _ledger_records(transport):
            envelope = decode_envelope(record.value)
            applied.setdefault(envelope.id, cast(LedgerFill, FillEvents.payload(envelope)))
        assert len(applied) == 1
        (only_fill,) = applied.values()
        assert only_fill.qty == "50"

    async def test_resync_of_already_terminal_order_publishes_nothing_new(self) -> None:
        """A second REST sync sees no status transition, so the ledger stream
        stays at the two original records (no unbounded re-publishing)."""
        transport = FakeTransport()
        order = await self._drive_both_paths(transport)

        executor = _executor(order, _publisher(transport))
        await executor.sync_order_status(order.id, TENANT_ID)

        assert len(_ledger_records(transport)) == 2
