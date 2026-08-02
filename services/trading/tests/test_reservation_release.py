"""Reservation release on reject/expiry — both emission paths, on the real wire.

A sleeve-attributed order that dies at the broker must release its §4 cash
reservation: the runner releases for stream-observed REJECTED/EXPIRED events,
and the executor releases when the submit call itself is rejected. Both paths
are driven against a real ``FillEvents`` publisher over ``FakeTransport`` and
asserted at the wire: a ``LedgerReservation`` with the right lifecycle kind,
keyed by account, under the deterministic ``client_order_id:kind`` event id the
portfolio translation dedups on. The projection half (reserved returns to 0
when the release folds) runs in
``services/portfolio/tests/test_invariant_freeze_e2e.py``.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import NoReturn, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from llamatrade_alpaca import AlpacaError, MockBarStream, MockTradeStream, TradingClient
from llamatrade_alpaca.models import TradeEvent, TradeEventType
from llamatrade_db.models.trading import Order
from llamatrade_events import (
    EventBus,
    FillEvents,
    LedgerFill,
    LedgerReservation,
    OrderEvents,
    PositionEvents,
    decode_envelope,
    derive_event_id,
)
from llamatrade_events.testing import FakeTransport, PublishRecord
from llamatrade_proto.generated import events_pb2
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_STATUS_REJECTED,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)

from src.executor.order_executor import OrderExecutor
from src.models import OrderCreate, RiskCheckResult
from src.risk.risk_manager import RiskManager
from src.runner.runner import RunnerConfig, StrategyRunner
from src.streaming.publisher import TradingEventPublisher

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
SLEEVE_ID = UUID("33333333-3333-3333-3333-333333333333")
SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
CLIENT_ORDER_ID = "lt-release000001"
EVENT_TS = datetime(2026, 7, 20, 14, 30, tzinfo=UTC)
LEDGER_STREAM = "ledger:fills"


def _publisher(transport: FakeTransport) -> TradingEventPublisher:
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


def _trade_event(
    event_type: TradeEventType,
    *,
    filled_qty: str = "0",
    filled_avg_price: str | None = None,
) -> TradeEvent:
    return TradeEvent(
        event_type=event_type,
        order_id="alpaca-1",
        client_order_id=CLIENT_ORDER_ID,
        symbol="SPY",
        side="buy",
        order_type="market",
        qty=Decimal("50"),
        filled_qty=Decimal(filled_qty),
        filled_avg_price=Decimal(filled_avg_price) if filled_avg_price else None,
        timestamp=EVENT_TS,
    )


def _ledger_records(transport: FakeTransport) -> list[PublishRecord]:
    return [r for r in transport.records if r.stream == LEDGER_STREAM]


def _reservations(transport: FakeTransport) -> list[tuple[PublishRecord, LedgerReservation]]:
    out: list[tuple[PublishRecord, LedgerReservation]] = []
    for record in _ledger_records(transport):
        envelope = decode_envelope(record.value)
        if envelope.type == events_pb2.EVENT_TYPE_LEDGER_RESERVATION:
            out.append((record, cast(LedgerReservation, FillEvents.payload(envelope))))
    return out


class TestRunnerReleasesOnTerminalEvents:
    """Stream path: REJECTED/EXPIRED trade events publish the §4 release."""

    async def test_rejected_event_publishes_order_rejected_release(self) -> None:
        transport = FakeTransport()
        runner = _runner(_publisher(transport))

        await runner._handle_trade_event(_trade_event(TradeEventType.REJECTED))

        releases = _reservations(transport)
        assert len(releases) == 1
        record, release = releases[0]
        assert release.event_type == "order_rejected"
        assert release.client_order_id == CLIENT_ORDER_ID
        assert release.sleeve_id == str(SLEEVE_ID)
        assert record.key == str(ACCOUNT_ID)
        envelope = decode_envelope(record.value)
        assert envelope.id == derive_event_id(CLIENT_ORDER_ID, "order_rejected")

    async def test_expired_event_publishes_order_cancelled_release(self) -> None:
        transport = FakeTransport()
        runner = _runner(_publisher(transport))

        await runner._handle_trade_event(_trade_event(TradeEventType.EXPIRED))

        releases = _reservations(transport)
        assert len(releases) == 1
        record, release = releases[0]
        assert release.event_type == "order_cancelled"
        assert record.key == str(ACCOUNT_ID)
        assert decode_envelope(record.value).id == derive_event_id(
            CLIENT_ORDER_ID, "order_cancelled"
        )
        # A rejection with nothing filled emits no fill payload — release only.
        assert len(_ledger_records(transport)) == 1

    async def test_expiry_with_partial_fill_publishes_fill_then_release(self) -> None:
        transport = FakeTransport()
        runner = _runner(_publisher(transport))

        await runner._handle_trade_event(
            _trade_event(TradeEventType.EXPIRED, filled_qty="20", filled_avg_price="480")
        )

        records = _ledger_records(transport)
        assert len(records) == 2
        first = decode_envelope(records[0].value)
        assert first.type == events_pb2.EVENT_TYPE_LEDGER_FILL
        assert cast(LedgerFill, FillEvents.payload(first)).qty == "20"
        _, release = _reservations(transport)[0]
        assert release.event_type == "order_cancelled"

    async def test_unattributed_session_releases_nothing(self) -> None:
        transport = FakeTransport()
        publisher = _publisher(transport)
        config = RunnerConfig(
            tenant_id=TENANT_ID,
            execution_id=SESSION_ID,
            strategy_id=uuid4(),
            symbols=["SPY"],
            timeframe="1min",
            warmup_bars=5,
            sleeve_id=None,
            account_id=None,
        )
        runner = StrategyRunner(
            config=config,
            strategy_fn=MagicMock(return_value=None),
            bar_stream=MockBarStream(bars={"SPY": []}),
            trade_stream=MockTradeStream(),
            order_executor=cast(OrderExecutor, AsyncMock()),
            risk_manager=cast(RiskManager, AsyncMock()),
            ledger_publisher=publisher,
        )

        await runner._handle_trade_event(_trade_event(TradeEventType.REJECTED))

        assert _ledger_records(transport) == []


class _RecordingDB:
    """AsyncSession double: persists rows in memory, serves client-id lookups."""

    def __init__(self) -> None:
        self.rows: list[Order] = []
        self._pending: list[Order] = []

    def add(self, obj: Order) -> None:
        self._pending.append(obj)

    async def execute(self, stmt: Select[tuple[Order]]) -> MagicMock:
        await asyncio.sleep(0)
        params = stmt.compile().params
        client_id = next(
            (value for key, value in params.items() if key.startswith("client_order_id")), None
        )
        matches = [row for row in self.rows if row.client_order_id == client_id]
        result = MagicMock()
        result.scalar_one_or_none.return_value = matches[0] if matches else None
        return result

    async def commit(self) -> None:
        await asyncio.sleep(0)
        self.rows.extend(self._pending)
        self._pending.clear()

    async def refresh(self, obj: Order) -> None:
        if obj.id is None:
            obj.id = uuid4()

    async def close(self) -> None:
        return None


class _RejectingBroker:
    """Broker double whose submit call always rejects."""

    async def submit_order(
        self,
        symbol: str,
        qty: Decimal,
        side: str,
        order_type: str,
        time_in_force: str,
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> NoReturn:
        await asyncio.sleep(0)
        raise AlpacaError("insufficient buying power")

    async def get_order_by_client_id(self, client_order_id: str) -> None:
        await asyncio.sleep(0)
        return None


class TestExecutorReleasesOnSubmitRejection:
    """Executor path: an Alpaca submit rejection publishes the release."""

    def _executor(self, transport: FakeTransport) -> tuple[OrderExecutor, _RecordingDB]:
        db = _RecordingDB()
        risk = AsyncMock()
        risk.check_order = AsyncMock(return_value=RiskCheckResult(passed=True, violations=[]))
        executor = OrderExecutor(
            db=cast(AsyncSession, db),
            alpaca_client=cast(TradingClient, _RejectingBroker()),
            risk_manager=cast(RiskManager, risk),
            event_publisher=_publisher(transport),
        )
        return executor, db

    def _order_create(self) -> OrderCreate:
        return OrderCreate(
            symbol="SPY",
            side=ORDER_SIDE_BUY,
            qty=Decimal("50"),
            order_type=ORDER_TYPE_MARKET,
            time_in_force=TIME_IN_FORCE_DAY,
            sleeve_id=SLEEVE_ID,
            account_id=ACCOUNT_ID,
            est_price=Decimal("480"),
        )

    async def test_submit_rejection_publishes_order_rejected_release(self) -> None:
        transport = FakeTransport()
        executor, db = self._executor(transport)

        with pytest.raises(ValueError, match="Failed to submit order"):
            await executor.submit_order(
                TENANT_ID, SESSION_ID, self._order_create(), signal_timestamp=EVENT_TS
            )

        releases = _reservations(transport)
        assert len(releases) == 1
        record, release = releases[0]
        assert release.event_type == "order_rejected"
        assert release.sleeve_id == str(SLEEVE_ID)
        assert record.key == str(ACCOUNT_ID)
        assert decode_envelope(record.value).id == derive_event_id(
            release.client_order_id, "order_rejected"
        )
        # The order never reached the broker: no reservation was ever taken, so
        # the release is the only ledger record; the row lands REJECTED.
        assert len(_ledger_records(transport)) == 1
        assert db.rows[0].status == ORDER_STATUS_REJECTED

    async def test_unattributed_order_rejection_releases_nothing(self) -> None:
        transport = FakeTransport()
        executor, _db = self._executor(transport)
        order = OrderCreate(
            symbol="SPY",
            side=ORDER_SIDE_BUY,
            qty=Decimal("50"),
            order_type=ORDER_TYPE_MARKET,
            time_in_force=TIME_IN_FORCE_DAY,
        )

        with pytest.raises(ValueError, match="Failed to submit order"):
            await executor.submit_order(TENANT_ID, SESSION_ID, order, signal_timestamp=EVENT_TS)

        assert _ledger_records(transport) == []
