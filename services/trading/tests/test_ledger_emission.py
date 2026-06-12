"""Ledger fill emission tests (CONTRACTS.md §1/§4).

Covers the pure payload builders and the runner's terminal-state-only
publishing: exactly one ledger fill per order — cumulative on ``fill``, the
filled portion on cancel/expiry — and never on partial fills.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from llamatrade_alpaca import MockBarStream, MockTradeStream
from llamatrade_alpaca.models import FillData, TradeEvent, TradeEventType

from src.ledger_events import build_ledger_fill_payload, build_ledger_lifecycle_payload
from src.runner.runner import RunnerConfig, StrategyRunner

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
SLEEVE_ID = UUID("33333333-3333-3333-3333-333333333333")
FILLED_AT = datetime(2026, 6, 11, 14, 30, tzinfo=UTC)


def _event(
    event_type: TradeEventType,
    *,
    filled_qty: str = "50",
    filled_avg_price: str | None = "480.00",
    with_fill_data: bool = False,
) -> TradeEvent:
    fill = None
    if with_fill_data:
        fill = FillData(
            order_id="alpaca-1",
            client_order_id="lt-abc123",
            symbol="SPY",
            side="buy",
            fill_qty=Decimal(filled_qty),
            fill_price=Decimal(filled_avg_price or "0"),
            total_filled_qty=Decimal(filled_qty),
            remaining_qty=Decimal("0"),
            timestamp=FILLED_AT,
        )
    return TradeEvent(
        event_type=event_type,
        order_id="alpaca-1",
        client_order_id="lt-abc123",
        symbol="SPY",
        side="buy",
        order_type="market",
        qty=Decimal("50"),
        filled_qty=Decimal(filled_qty),
        filled_avg_price=Decimal(filled_avg_price) if filled_avg_price else None,
        timestamp=FILLED_AT,
        fill=fill,
    )


class TestBuildLedgerFillPayload:
    """Pure payload builder: one payload per order, at terminal state."""

    def _build(self, event: TradeEvent) -> dict[str, str] | None:
        return build_ledger_fill_payload(
            tenant_id=TENANT_ID, account_id=ACCOUNT_ID, sleeve_id=SLEEVE_ID, event=event
        )

    def test_fill_uses_cumulative_qty_and_avg_price(self) -> None:
        payload = self._build(_event(TradeEventType.FILL))
        assert payload is not None
        assert payload["qty"] == "50"
        assert payload["price"] == "480.00"
        assert payload["client_order_id"] == "lt-abc123"
        assert payload["side"] == "buy"
        assert payload["filled_at"] == FILLED_AT.isoformat()
        # cost_basis/realized_pnl are resolved by the portfolio at ingestion
        assert "cost_basis" not in payload
        assert "realized_pnl" not in payload

    def test_partial_fill_never_publishes(self) -> None:
        assert self._build(_event(TradeEventType.PARTIAL_FILL)) is None

    def test_canceled_with_partial_fill_publishes_filled_portion(self) -> None:
        payload = self._build(_event(TradeEventType.CANCELED, filled_qty="20"))
        assert payload is not None
        assert payload["qty"] == "20"

    def test_canceled_without_fill_publishes_nothing(self) -> None:
        assert self._build(_event(TradeEventType.CANCELED, filled_qty="0")) is None

    def test_expired_with_partial_fill_publishes(self) -> None:
        payload = self._build(_event(TradeEventType.EXPIRED, filled_qty="5"))
        assert payload is not None
        assert payload["qty"] == "5"

    def test_rejected_publishes_nothing(self) -> None:
        assert self._build(_event(TradeEventType.REJECTED, filled_qty="0")) is None

    def test_fill_without_avg_price_is_skipped(self) -> None:
        assert self._build(_event(TradeEventType.FILL, filled_avg_price=None)) is None


class TestBuildLifecyclePayload:
    """Reservation lifecycle payloads (§4)."""

    def test_submitted_carries_reservation(self) -> None:
        payload = build_ledger_lifecycle_payload(
            kind="order_submitted",
            tenant_id=TENANT_ID,
            account_id=ACCOUNT_ID,
            sleeve_id=SLEEVE_ID,
            client_order_id="lt-abc123",
            symbol="SPY",
            side="buy",
            reserved=Decimal("24000"),
        )
        assert payload["event_type"] == "order_submitted"
        assert payload["reserved"] == "24000"
        assert payload["sleeve_id"] == str(SLEEVE_ID)

    def test_cancelled_has_no_reservation_amount(self) -> None:
        payload = build_ledger_lifecycle_payload(
            kind="order_cancelled",
            tenant_id=TENANT_ID,
            account_id=ACCOUNT_ID,
            sleeve_id=SLEEVE_ID,
            client_order_id="lt-abc123",
            symbol="SPY",
            side="buy",
        )
        assert payload["event_type"] == "order_cancelled"
        assert "reserved" not in payload


def _runner(
    *,
    sleeve_id: UUID | None = SLEEVE_ID,
    account_id: UUID | None = ACCOUNT_ID,
    publisher: AsyncMock | None = None,
) -> StrategyRunner:
    config = RunnerConfig(
        tenant_id=TENANT_ID,
        execution_id=uuid4(),
        strategy_id=uuid4(),
        symbols=["SPY"],
        timeframe="1min",
        warmup_bars=5,
        sleeve_id=sleeve_id,
        account_id=account_id,
    )
    strategy_fn = MagicMock(return_value=None)
    return StrategyRunner(
        config=config,
        strategy_fn=strategy_fn,
        bar_stream=MockBarStream(bars={"SPY": []}),
        trade_stream=MockTradeStream(),
        order_executor=AsyncMock(),
        risk_manager=AsyncMock(),
        ledger_publisher=publisher,
    )


class TestRunnerLedgerEmission:
    """Terminal-state-only emission from the trade event loop."""

    @pytest.mark.asyncio
    async def test_fill_publishes_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LEDGER_SHADOW_MODE", "1")
        publisher = AsyncMock()
        runner = _runner(publisher=publisher)

        await runner._handle_trade_event(_event(TradeEventType.FILL, with_fill_data=True))

        publisher.publish_ledger_fill.assert_awaited_once()
        account_arg, payload = publisher.publish_ledger_fill.await_args.args
        assert account_arg == ACCOUNT_ID
        assert payload["qty"] == "50"
        assert payload["sleeve_id"] == str(SLEEVE_ID)

    @pytest.mark.asyncio
    async def test_partial_then_fill_publishes_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LEDGER_SHADOW_MODE", "1")
        publisher = AsyncMock()
        runner = _runner(publisher=publisher)

        await runner._handle_trade_event(
            _event(TradeEventType.PARTIAL_FILL, filled_qty="20", with_fill_data=True)
        )
        await runner._handle_trade_event(_event(TradeEventType.FILL, with_fill_data=True))

        assert publisher.publish_ledger_fill.await_count == 1
        _, payload = publisher.publish_ledger_fill.await_args.args
        assert payload["qty"] == "50"  # cumulative, not the last partial

    @pytest.mark.asyncio
    async def test_cancel_with_partial_publishes_filled_portion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LEDGER_SHADOW_MODE", "1")
        publisher = AsyncMock()
        runner = _runner(publisher=publisher)

        await runner._handle_trade_event(_event(TradeEventType.CANCELED, filled_qty="20"))

        publisher.publish_ledger_fill.assert_awaited_once()
        _, payload = publisher.publish_ledger_fill.await_args.args
        assert payload["qty"] == "20"

    @pytest.mark.asyncio
    async def test_flag_off_publishes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LEDGER_SHADOW_MODE", raising=False)
        publisher = AsyncMock()
        runner = _runner(publisher=publisher)

        await runner._handle_trade_event(_event(TradeEventType.FILL, with_fill_data=True))

        publisher.publish_ledger_fill.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unattributed_session_publishes_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LEDGER_SHADOW_MODE", "1")
        publisher = AsyncMock()
        runner = _runner(sleeve_id=None, account_id=None, publisher=publisher)

        await runner._handle_trade_event(_event(TradeEventType.FILL, with_fill_data=True))

        publisher.publish_ledger_fill.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_publish_failure_never_breaks_fill_processing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LEDGER_SHADOW_MODE", "1")
        publisher = AsyncMock()
        publisher.publish_ledger_fill.side_effect = ConnectionError("redis down")
        runner = _runner(publisher=publisher)

        await runner._handle_trade_event(_event(TradeEventType.FILL, with_fill_data=True))

        assert runner.metrics["fills_processed"] == 1


class TestStreamDualWrite:
    """STREAMS_LEDGER_FILLS: payloads also XADD to the global durable stream."""

    def _publisher(self):
        from src.streaming.publisher import TradingEventPublisher

        bus = AsyncMock()
        publisher = TradingEventPublisher(event_bus=bus)
        publisher._redis = AsyncMock()  # pub/sub leg
        publisher._redis.publish = AsyncMock(return_value=1)
        return publisher, bus, publisher._redis

    @pytest.mark.asyncio
    async def test_flag_on_dual_writes_stream_and_pubsub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.streaming.publisher import LEDGER_FILLS_MAXLEN, LEDGER_FILLS_STREAM

        monkeypatch.setenv("STREAMS_LEDGER_FILLS", "1")
        publisher, bus, redis = self._publisher()
        payload = {"client_order_id": "lt-1", "account_id": str(ACCOUNT_ID)}

        await publisher.publish_ledger_fill(ACCOUNT_ID, payload)

        bus.publish.assert_awaited_once_with(
            LEDGER_FILLS_STREAM, payload, maxlen=LEDGER_FILLS_MAXLEN
        )
        redis.publish.assert_awaited_once()  # pub/sub stays primary during soak

    @pytest.mark.asyncio
    async def test_flag_off_skips_stream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("STREAMS_LEDGER_FILLS", raising=False)
        publisher, bus, redis = self._publisher()

        await publisher.publish_ledger_fill(ACCOUNT_ID, {"client_order_id": "lt-1"})

        bus.publish.assert_not_awaited()
        redis.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stream_failure_never_blocks_pubsub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STREAMS_LEDGER_FILLS", "1")
        publisher, bus, redis = self._publisher()
        bus.publish.side_effect = ConnectionError("stream down")

        result = await publisher.publish_ledger_fill(ACCOUNT_ID, {"client_order_id": "lt-1"})

        assert result == 1  # pub/sub delivery succeeded regardless
        redis.publish.assert_awaited_once()
