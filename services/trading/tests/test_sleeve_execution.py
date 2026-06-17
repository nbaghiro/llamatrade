"""Sleeve-aware execution tests (CONTRACTS.md).

Covers drift-tolerance sizing, sleeve equity sync, free-cash fit, sleeve
buying-power risk checks, and cash-reservation lifecycle publishing.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from llamatrade_alpaca import MockBarStream, MockTradeStream
from llamatrade_db.models.trading import Order
from llamatrade_proto.clients.ledger import LedgerClient, SleeveDetail
from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_PAPER
from llamatrade_proto.generated.ledger_pb2 import SLEEVE_STATUS_ACTIVE, SLEEVE_TYPE_STRATEGY
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
)

from src.clients.portfolio_client import PortfolioLedgerClient
from src.executor.order_executor import OrderExecutor
from src.models import OrderCreate, RiskCheckResult
from src.risk.risk_manager import RiskManager
from src.runner.runner import Position, RunnerConfig, Signal, StrategyRunner

from llamatrade_proto.clients.ledger import (  # isort: skip
    LotInfo,
    SleeveCashInfo,
    SleeveInfo,
)

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT_ID = UUID("22222222-2222-2222-2222-222222222222")
SLEEVE_ID = UUID("33333333-3333-3333-3333-333333333333")

SIMPLE_STRATEGY = """(strategy "Always SPY"
  :rebalance daily
  :benchmark SPY
  (asset SPY :weight 100))"""


def _sleeve_detail(
    *,
    balance: str = "40000",
    reserved: str = "0",
    lots: list[LotInfo] | None = None,
    status: int = SLEEVE_STATUS_ACTIVE,
) -> SleeveDetail:
    return SleeveDetail(
        sleeve=SleeveInfo(
            id=str(SLEEVE_ID),
            tenant_id=str(TENANT_ID),
            account_id=str(ACCOUNT_ID),
            type=SLEEVE_TYPE_STRATEGY,
            status=status,
            name="Strategy A",
            strategy_execution_id=str(uuid4()),
            allocated_capital=Decimal("40000"),
            cash=SleeveCashInfo(
                balance=Decimal(balance), reserved=Decimal(reserved), unsettled=Decimal("0")
            ),
        ),
        lots=lots or [],
    )


def _lot(symbol: str = "SPY", qty: str = "50", avg_price: str = "480") -> LotInfo:
    return LotInfo(
        id=str(uuid4()),
        sleeve_id=str(SLEEVE_ID),
        symbol=symbol,
        side=1,
        qty=Decimal(qty),
        avg_price=Decimal(avg_price),
        cost_basis=Decimal(qty) * Decimal(avg_price),
        realized_pnl=Decimal("0"),
        is_open=True,
        opened_by_order_id="order-1",
    )


def _position(qty: float, entry: float = 480.0) -> Position:
    return Position(
        symbol="SPY", side="long", quantity=qty, entry_price=entry, entry_date=datetime.now(UTC)
    )


# Note: drift/binary weight->order sizing now lives in llamatrade_compiler.size_orders and
# is covered by libs/compiler/tests/test_sizing.py (the sizing logic is shared by live and
# backtest). The tests below cover the trading-service integration around it.


def _runner(portfolio_client: PortfolioLedgerClient | None = None) -> StrategyRunner:
    config = RunnerConfig(
        tenant_id=TENANT_ID,
        execution_id=uuid4(),
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
        order_executor=AsyncMock(),
        risk_manager=AsyncMock(),
        portfolio_client=portfolio_client,
    )


class TestSleeveEquitySync:
    """Runner sizes against sleeve equity, never the whole account."""

    @pytest.mark.asyncio
    async def test_sleeve_equity_from_cash_and_lots(self) -> None:
        client = AsyncMock(spec=PortfolioLedgerClient)
        client.get_sleeve.return_value = _sleeve_detail(
            balance="16000", reserved="1000", lots=[_lot(qty="50", avg_price="480")]
        )
        runner = _runner(portfolio_client=client)

        await runner._sync_equity()

        # equity = free cash (15000) + 50 × 480 (no live bar yet → avg price)
        assert runner._equity == pytest.approx(15000 + 24000)
        assert runner._free_cash == pytest.approx(15000)

    @pytest.mark.asyncio
    async def test_sleeve_fetch_failure_keeps_last_equity(self) -> None:
        """Never silently falls back to whole-account equity."""
        client = AsyncMock(spec=PortfolioLedgerClient)
        client.get_sleeve.side_effect = ConnectionError("portfolio down")
        runner = _runner(portfolio_client=client)
        runner.alpaca_client = AsyncMock()
        runner._equity = 40000.0

        await runner._sync_equity()

        assert runner._equity == pytest.approx(40000.0)
        runner.alpaca_client.get_account.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_closed_sleeve_stops_the_runner(self) -> None:
        """A retired sleeve (closed on stop/archive) winds the runner down."""
        from llamatrade_proto.generated.ledger_pb2 import SLEEVE_STATUS_CLOSED

        client = AsyncMock(spec=PortfolioLedgerClient)
        client.get_sleeve.return_value = _sleeve_detail(status=SLEEVE_STATUS_CLOSED)
        runner = _runner(portfolio_client=client)
        runner._running = True

        handled = await runner._sync_sleeve_equity()

        assert handled is True  # do not fall back to whole-account equity
        assert runner._running is False  # loops exit on next iteration


class TestFreeCashFit:
    """Buys are scaled to the sleeve's free cash, not rejected outright."""

    @pytest.mark.asyncio
    async def test_buy_scaled_down_to_free_cash(self) -> None:
        runner = _runner()
        runner._free_cash = 4800.0
        runner.risk_manager.check_order = AsyncMock(
            return_value=RiskCheckResult(passed=True, violations=[])
        )

        await runner._process_signal(Signal(type="buy", symbol="SPY", quantity=100, price=480.0))

        submitted = runner.order_executor.submit_order.await_args.kwargs["order"]
        assert submitted.qty == pytest.approx(10.0)  # 4800 / 480

    @pytest.mark.asyncio
    async def test_buy_skipped_when_free_cash_exhausted(self) -> None:
        runner = _runner()
        runner._free_cash = 0.0

        await runner._process_signal(Signal(type="buy", symbol="SPY", quantity=10, price=480.0))

        runner.order_executor.submit_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sells_never_clamped(self) -> None:
        runner = _runner()
        runner._free_cash = 0.0
        runner.risk_manager.check_order = AsyncMock(
            return_value=RiskCheckResult(passed=True, violations=[])
        )

        await runner._process_signal(Signal(type="sell", symbol="SPY", quantity=10, price=480.0))

        submitted = runner.order_executor.submit_order.await_args.kwargs["order"]
        assert submitted.qty == pytest.approx(10.0)


class TestSleeveBuyingPower:
    """RiskManager rejects buys exceeding sleeve free cash."""

    def _risk(self, detail: SleeveDetail | Exception) -> RiskManager:
        client = AsyncMock(spec=PortfolioLedgerClient)
        if isinstance(detail, Exception):
            client.get_sleeve.side_effect = detail
        else:
            client.get_sleeve.return_value = detail
        return RiskManager(portfolio_client=client)

    @pytest.mark.asyncio
    async def test_buy_within_free_cash_passes(self) -> None:
        risk = self._risk(_sleeve_detail(balance="40000"))
        violation = await risk._check_sleeve(TENANT_ID, SLEEVE_ID, "buy", 24000.0)
        assert violation is None

    @pytest.mark.asyncio
    async def test_buy_exceeding_free_cash_violates(self) -> None:
        risk = self._risk(_sleeve_detail(balance="40000", reserved="20000"))
        violation = await risk._check_sleeve(TENANT_ID, SLEEVE_ID, "buy", 24000.0)
        assert violation is not None
        assert "free cash" in violation

    @pytest.mark.asyncio
    async def test_fetch_failure_fails_safe(self) -> None:
        risk = self._risk(ConnectionError("portfolio down"))
        violation = await risk._check_sleeve(TENANT_ID, SLEEVE_ID, "buy", 100.0)
        assert violation is not None

    @pytest.mark.asyncio
    async def test_frozen_sleeve_blocks_buys(self) -> None:
        from llamatrade_proto.generated.ledger_pb2 import SLEEVE_STATUS_FROZEN

        risk = self._risk(_sleeve_detail(balance="40000", status=SLEEVE_STATUS_FROZEN))
        violation = await risk._check_sleeve(TENANT_ID, SLEEVE_ID, "buy", 1.0)
        assert violation is not None
        assert "frozen" in violation

    @pytest.mark.asyncio
    async def test_frozen_sleeve_blocks_sells_too(self) -> None:
        from llamatrade_proto.generated.ledger_pb2 import SLEEVE_STATUS_FROZEN

        risk = self._risk(_sleeve_detail(status=SLEEVE_STATUS_FROZEN))
        violation = await risk._check_sleeve(TENANT_ID, SLEEVE_ID, "sell", 1.0)
        assert violation is not None
        assert "frozen" in violation

    @pytest.mark.asyncio
    async def test_active_sleeve_sell_passes_without_cash_check(self) -> None:
        risk = self._risk(_sleeve_detail(balance="0"))
        violation = await risk._check_sleeve(TENANT_ID, SLEEVE_ID, "sell", 1e9)
        assert violation is None

    @pytest.mark.asyncio
    async def test_closed_sleeve_blocks_buys(self) -> None:
        from llamatrade_proto.generated.ledger_pb2 import SLEEVE_STATUS_CLOSED

        risk = self._risk(_sleeve_detail(balance="40000", status=SLEEVE_STATUS_CLOSED))
        violation = await risk._check_sleeve(TENANT_ID, SLEEVE_ID, "buy", 1.0)
        assert violation is not None
        assert "closed" in violation

    @pytest.mark.asyncio
    async def test_closed_sleeve_blocks_sells_too(self) -> None:
        from llamatrade_proto.generated.ledger_pb2 import SLEEVE_STATUS_CLOSED

        risk = self._risk(_sleeve_detail(status=SLEEVE_STATUS_CLOSED))
        violation = await risk._check_sleeve(TENANT_ID, SLEEVE_ID, "sell", 1.0)
        assert violation is not None
        assert "closed" in violation


class TestReservationPublishing:
    """§4 reservation lifecycle from the executor."""

    def _executor(self, publisher: AsyncMock | None) -> OrderExecutor:
        return OrderExecutor(
            db=AsyncMock(),
            alpaca_client=AsyncMock(),
            risk_manager=AsyncMock(),
            event_publisher=publisher,
        )

    def _db_order(self, *, attributed: bool = True) -> Order:
        order = Order(
            tenant_id=TENANT_ID,
            session_id=uuid4(),
            client_order_id="lt-abc123",
            symbol="SPY",
            side=ORDER_SIDE_BUY,
            order_type=ORDER_TYPE_LIMIT,
            time_in_force=1,
            qty=Decimal("50"),
            status=1,
            filled_qty=Decimal("0"),
            sleeve_id=SLEEVE_ID if attributed else None,
            account_id=ACCOUNT_ID if attributed else None,
        )
        order.id = uuid4()
        return order

    def test_limit_buy_reserves_notional(self) -> None:
        order = OrderCreate(
            symbol="SPY",
            side=ORDER_SIDE_BUY,
            qty=50,
            order_type=ORDER_TYPE_LIMIT,
            limit_price=480.0,
        )
        assert OrderExecutor._reservation_amount(order) == Decimal("24000.0")

    def test_market_buy_reserves_nothing(self) -> None:
        order = OrderCreate(symbol="SPY", side=ORDER_SIDE_BUY, qty=50, order_type=ORDER_TYPE_MARKET)
        assert OrderExecutor._reservation_amount(order) is None

    def test_sell_reserves_nothing(self) -> None:
        order = OrderCreate(
            symbol="SPY",
            side=ORDER_SIDE_SELL,
            qty=50,
            order_type=ORDER_TYPE_LIMIT,
            limit_price=480.0,
        )
        assert OrderExecutor._reservation_amount(order) is None

    @pytest.mark.asyncio
    async def test_lifecycle_published_when_flag_on(self) -> None:
        publisher = AsyncMock()
        executor = self._executor(publisher)

        await executor._publish_ledger_lifecycle(
            self._db_order(), "order_submitted", reserved=Decimal("24000")
        )

        publisher.publish_ledger_fill.assert_awaited_once()
        (payload,) = publisher.publish_ledger_fill.await_args.args
        assert payload.event_type == "order_submitted"
        assert payload.reserved == "24000"
        assert payload.client_order_id == "lt-abc123"

    @pytest.mark.asyncio
    async def test_lifecycle_skipped_for_unattributed_orders(self) -> None:
        publisher = AsyncMock()
        executor = self._executor(publisher)

        await executor._publish_ledger_lifecycle(
            self._db_order(attributed=False), "order_cancelled"
        )

        publisher.publish_ledger_fill.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_publish_failure_never_raises(self) -> None:
        publisher = AsyncMock()
        publisher.publish_ledger_fill.side_effect = ConnectionError("redis down")
        executor = self._executor(publisher)

        await executor._publish_ledger_lifecycle(self._db_order(), "order_cancelled")


class TestPortfolioLedgerClientCache:
    """Short-TTL caching of sleeve reads."""

    @pytest.mark.asyncio
    async def test_cached_within_ttl(self) -> None:
        ledger = AsyncMock(spec=LedgerClient)
        ledger.get_sleeve.return_value = _sleeve_detail()
        client = PortfolioLedgerClient(ledger=ledger, cache_ttl_seconds=60)

        await client.get_sleeve(TENANT_ID, "", SLEEVE_ID)
        await client.get_sleeve(TENANT_ID, "", SLEEVE_ID)

        assert ledger.get_sleeve.await_count == 1

    @pytest.mark.asyncio
    async def test_invalidate_forces_refetch(self) -> None:
        ledger = AsyncMock(spec=LedgerClient)
        ledger.get_sleeve.return_value = _sleeve_detail()
        client = PortfolioLedgerClient(ledger=ledger, cache_ttl_seconds=60)

        await client.get_sleeve(TENANT_ID, "", SLEEVE_ID)
        client.invalidate(SLEEVE_ID)
        await client.get_sleeve(TENANT_ID, "", SLEEVE_ID)

        assert ledger.get_sleeve.await_count == 2


class TestLedgerOwnedReconciliation:
    """For sleeve-attributed sessions the runner's reconciliation is read-only."""

    def _broker_position(self, symbol: str = "SPY", qty: float = 60.0) -> MagicMock:
        pos = MagicMock()
        pos.symbol = symbol
        pos.side = "long"
        pos.qty = qty
        pos.cost_basis = qty * 480.0
        return pos

    @pytest.mark.asyncio
    async def test_missing_local_not_auto_added(self) -> None:
        runner = _runner()
        runner.alerts = AsyncMock()
        runner.alpaca_client = AsyncMock()
        runner.alpaca_client.get_positions.return_value = [self._broker_position()]

        await runner._sync_positions()

        assert "SPY" not in runner._positions  # portfolio owns reconciliation
        runner.alerts.on_position_drift.assert_awaited_once()
        assert runner.alerts.on_position_drift.await_args.kwargs["action"] == "alerted"

    @pytest.mark.asyncio
    async def test_qty_drift_not_auto_corrected(self) -> None:
        runner = _runner()
        runner.alpaca_client = AsyncMock()
        runner._positions["SPY"] = _position(59.0)  # small drift vs broker 60
        runner.alpaca_client.get_positions.return_value = [self._broker_position(qty=60.0)]

        await runner._sync_positions()

        assert runner._positions["SPY"].quantity == pytest.approx(59.0)  # untouched


class TestLedgerAlerts:
    """New alert types for ledger reconciliation drift and sleeve freezes."""

    @pytest.mark.asyncio
    async def test_reconciliation_drift_alert(self) -> None:
        from src.services.alert_service import AlertService, AlertType

        service = AlertService()
        sent = []
        service.send = AsyncMock(side_effect=lambda alert: sent.append(alert))

        await service.on_reconciliation_drift(
            tenant_id=TENANT_ID,
            account_id=ACCOUNT_ID,
            symbol="SPY",
            drift_kind="missing_at_broker",
            ledger_qty=60.0,
            broker_qty=0.0,
        )

        alert = sent[0]
        assert alert.alert_type == AlertType.RECONCILIATION_DRIFT
        assert alert.priority.value == "critical"
        assert alert.metadata["drift_kind"] == "missing_at_broker"

    @pytest.mark.asyncio
    async def test_qty_mismatch_is_high_priority(self) -> None:
        from src.services.alert_service import AlertService

        service = AlertService()
        sent = []
        service.send = AsyncMock(side_effect=lambda alert: sent.append(alert))

        await service.on_reconciliation_drift(
            tenant_id=TENANT_ID,
            account_id=ACCOUNT_ID,
            symbol="SPY",
            drift_kind="qty_mismatch",
            ledger_qty=60.0,
            broker_qty=61.0,
        )

        assert sent[0].priority.value == "high"

    @pytest.mark.asyncio
    async def test_sleeve_frozen_alert(self) -> None:
        from src.services.alert_service import AlertService, AlertType

        service = AlertService()
        sent = []
        service.send = AsyncMock(side_effect=lambda alert: sent.append(alert))

        await service.on_sleeve_frozen(
            tenant_id=TENANT_ID, sleeve_id=SLEEVE_ID, reason="material unexplained drift"
        )

        alert = sent[0]
        assert alert.alert_type == AlertType.SLEEVE_FROZEN
        assert alert.priority.value == "critical"
        assert alert.metadata["sleeve_id"] == str(SLEEVE_ID)


class TestSessionPnlFromLedger:
    """Session realized P&L comes from the sleeve projection when attributed."""

    def _session(self, *, sleeve: bool = True) -> MagicMock:
        from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_RUNNING

        s = MagicMock()
        s.id = uuid4()
        s.tenant_id = TENANT_ID
        s.strategy_id = uuid4()
        s.mode = EXECUTION_MODE_PAPER
        s.status = EXECUTION_STATUS_RUNNING
        s.started_at = datetime.now(UTC)
        s.created_at = datetime.now(UTC)
        s.stopped_at = None
        s.name = "Sleeve Session"
        s.sleeve_id = SLEEVE_ID if sleeve else None
        s.account_id = ACCOUNT_ID if sleeve else None
        return s

    @pytest.mark.asyncio
    async def test_realized_pnl_overridden_from_sleeve(self) -> None:
        from unittest.mock import patch

        from src.services.session_service import SessionService

        service = SessionService(AsyncMock())
        detail = _sleeve_detail()
        detail.sleeve.realized_pnl = Decimal("1234.56")
        client = AsyncMock(spec=PortfolioLedgerClient)
        client.get_sleeve.return_value = detail

        with (
            patch.object(service, "get_session_pnl", AsyncMock(return_value=(100.0, 50.0))),
            patch.object(service, "get_trades_count", AsyncMock(return_value=7)),
            patch(
                "src.clients.portfolio_client.get_portfolio_ledger_client",
                return_value=client,
            ),
        ):
            response = await service._to_response_with_pnl(self._session())

        # ledger realized (1234.56) + local unrealized (50), NOT local realized
        assert response.pnl == pytest.approx(1284.56)

    @pytest.mark.asyncio
    async def test_flag_off_uses_local_pnl(self) -> None:
        from unittest.mock import patch

        from src.services.session_service import SessionService

        service = SessionService(AsyncMock())

        with (
            patch.object(service, "get_session_pnl", AsyncMock(return_value=(100.0, 50.0))),
            patch.object(service, "get_trades_count", AsyncMock(return_value=7)),
        ):
            response = await service._to_response_with_pnl(self._session())

        assert response.pnl == pytest.approx(150.0)

    @pytest.mark.asyncio
    async def test_ledger_failure_falls_back_to_local(self) -> None:
        from unittest.mock import patch

        from src.services.session_service import SessionService

        service = SessionService(AsyncMock())
        client = AsyncMock(spec=PortfolioLedgerClient)
        client.get_sleeve.side_effect = ConnectionError("portfolio down")

        with (
            patch.object(service, "get_session_pnl", AsyncMock(return_value=(100.0, 50.0))),
            patch.object(service, "get_trades_count", AsyncMock(return_value=7)),
            patch(
                "src.clients.portfolio_client.get_portfolio_ledger_client",
                return_value=client,
            ),
        ):
            response = await service._to_response_with_pnl(self._session())

        assert response.pnl == pytest.approx(150.0)


class TestRestSyncLedgerEmission:
    """Fix for the crash/disconnect window: REST sync emits ledger events."""

    def _executor_for_sync(self, publisher: AsyncMock | None) -> OrderExecutor:
        return OrderExecutor(
            db=AsyncMock(),
            alpaca_client=AsyncMock(),
            risk_manager=AsyncMock(),
            event_publisher=publisher,
        )

    def _terminal_order(self, *, status: int, filled_qty: str, avg_price: str | None) -> Order:
        from datetime import datetime

        order = Order(
            tenant_id=TENANT_ID,
            session_id=uuid4(),
            client_order_id="lt-sync-1",
            symbol="SPY",
            side=ORDER_SIDE_BUY,
            order_type=ORDER_TYPE_LIMIT,
            time_in_force=1,
            qty=Decimal("50"),
            status=status,
            filled_qty=Decimal(filled_qty),
            filled_avg_price=Decimal(avg_price) if avg_price else None,
            sleeve_id=SLEEVE_ID,
            account_id=ACCOUNT_ID,
        )
        order.id = uuid4()
        order.filled_at = datetime.now(UTC)
        return order

    @pytest.mark.asyncio
    async def test_synced_fill_publishes_ledger_fill(self) -> None:
        from llamatrade_proto.generated.trading_pb2 import (
            ORDER_STATUS_FILLED,
            ORDER_STATUS_SUBMITTED,
        )

        publisher = AsyncMock()
        executor = self._executor_for_sync(publisher)
        order = self._terminal_order(status=ORDER_STATUS_FILLED, filled_qty="50", avg_price="480")

        await executor._publish_ledger_events_for_sync(order, ORDER_STATUS_SUBMITTED)

        publisher.publish_ledger_fill.assert_awaited_once()
        (payload,) = publisher.publish_ledger_fill.await_args.args
        assert payload.qty == "50"
        assert payload.client_order_id == "lt-sync-1"

    @pytest.mark.asyncio
    async def test_synced_cancel_with_partial_publishes_fill_and_release(self) -> None:
        from llamatrade_proto.generated.trading_pb2 import (
            ORDER_STATUS_CANCELLED,
            ORDER_STATUS_PARTIAL,
        )

        publisher = AsyncMock()
        executor = self._executor_for_sync(publisher)
        order = self._terminal_order(
            status=ORDER_STATUS_CANCELLED, filled_qty="20", avg_price="480"
        )

        await executor._publish_ledger_events_for_sync(order, ORDER_STATUS_PARTIAL)

        assert publisher.publish_ledger_fill.await_count == 2
        fill_payload = publisher.publish_ledger_fill.await_args_list[0].args[0]
        release_payload = publisher.publish_ledger_fill.await_args_list[1].args[0]
        assert fill_payload.qty == "20"
        assert release_payload.event_type == "order_cancelled"

    @pytest.mark.asyncio
    async def test_no_transition_publishes_nothing(self) -> None:
        from llamatrade_proto.generated.trading_pb2 import ORDER_STATUS_FILLED

        publisher = AsyncMock()
        executor = self._executor_for_sync(publisher)
        order = self._terminal_order(status=ORDER_STATUS_FILLED, filled_qty="50", avg_price="480")

        # Same status (already synced before) → idempotent skip, no publish
        await executor._publish_ledger_events_for_sync(order, ORDER_STATUS_FILLED)

        publisher.publish_ledger_fill.assert_not_awaited()

    def test_order_payload_builder_skips_open_orders(self) -> None:
        from llamatrade_proto.generated.trading_pb2 import ORDER_STATUS_SUBMITTED

        from src.ledger_events import build_ledger_fill_payload_from_order

        order = self._terminal_order(status=ORDER_STATUS_SUBMITTED, filled_qty="0", avg_price=None)
        assert build_ledger_fill_payload_from_order(order) is None

    def test_order_payload_builder_skips_cancel_without_fill(self) -> None:
        from llamatrade_proto.generated.trading_pb2 import ORDER_STATUS_CANCELLED

        from src.ledger_events import build_ledger_fill_payload_from_order

        order = self._terminal_order(status=ORDER_STATUS_CANCELLED, filled_qty="0", avg_price=None)
        assert build_ledger_fill_payload_from_order(order) is None


class TestMarketBuyReservation:
    """Market buys reserve via the signal's est_price."""

    def test_market_buy_with_est_price_reserves(self) -> None:
        order = OrderCreate(
            symbol="SPY",
            side=ORDER_SIDE_BUY,
            qty=50,
            order_type=ORDER_TYPE_MARKET,
            est_price=480.0,
        )
        assert OrderExecutor._reservation_amount(order) == Decimal("24000.0")

    def test_runner_threads_signal_price_as_est_price(self) -> None:
        runner = _runner()
        order = runner._signal_to_order(Signal(type="buy", symbol="SPY", quantity=50, price=480.0))
        assert order.est_price == pytest.approx(480.0)
        assert order.sleeve_id == SLEEVE_ID


class TestSessionIdentityAndGuards:
    """execution_id threading + one-active-session-per-sleeve."""

    def _service(self):
        from src.services.live_session_service import LiveSessionService

        return LiveSessionService(
            db=AsyncMock(),
            runner_manager=MagicMock(),
            order_executor=AsyncMock(),
            risk_manager=AsyncMock(),
            alpaca_client=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_execution_id_resolves_exact_execution(self) -> None:
        service = self._service()
        execution = MagicMock()
        execution.strategy_id = uuid4()
        execution.sleeve_id = SLEEVE_ID
        execution.account_id = ACCOUNT_ID
        service.db.scalar = AsyncMock(return_value=execution)

        sleeve_id, account_id = await service._resolve_ledger_identity(
            TENANT_ID, execution.strategy_id, uuid4()
        )

        assert sleeve_id == SLEEVE_ID
        assert account_id == ACCOUNT_ID

    @pytest.mark.asyncio
    async def test_execution_for_wrong_strategy_rejected(self) -> None:
        service = self._service()
        execution = MagicMock()
        execution.strategy_id = uuid4()
        service.db.scalar = AsyncMock(return_value=execution)

        with pytest.raises(ValueError, match="different strategy"):
            await service._resolve_ledger_identity(TENANT_ID, uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_unknown_execution_rejected(self) -> None:
        service = self._service()
        service.db.scalar = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await service._resolve_ledger_identity(TENANT_ID, uuid4(), uuid4())

    @pytest.mark.asyncio
    async def test_sleeve_in_use_blocks_second_session(self) -> None:
        service = self._service()
        active = MagicMock()
        active.id = uuid4()
        service.db.scalar = AsyncMock(return_value=active)

        with pytest.raises(ValueError, match="already traded"):
            await service._ensure_sleeve_not_in_use(TENANT_ID, SLEEVE_ID)

    @pytest.mark.asyncio
    async def test_free_sleeve_passes_guard(self) -> None:
        service = self._service()
        service.db.scalar = AsyncMock(return_value=None)

        await service._ensure_sleeve_not_in_use(TENANT_ID, SLEEVE_ID)  # no raise


class TestShortsRejection:
    """Ledger accounting is long-only: shorts rejected for attributed sessions."""

    @pytest.mark.asyncio
    async def test_short_signal_rejected_under_ledger_execution(self) -> None:
        runner = _runner()

        await runner._process_signal(Signal(type="short", symbol="SPY", quantity=10, price=480.0))

        runner.order_executor.submit_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_short_signal_allowed_for_legacy_sessions(self) -> None:
        runner = _runner()
        runner.config.sleeve_id = None  # unfunded/legacy session
        runner.risk_manager.check_order = AsyncMock(
            return_value=RiskCheckResult(passed=True, violations=[])
        )

        await runner._process_signal(Signal(type="short", symbol="SPY", quantity=10, price=480.0))

        runner.order_executor.submit_order.assert_awaited_once()
