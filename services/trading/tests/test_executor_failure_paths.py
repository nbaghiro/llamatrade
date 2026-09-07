"""Executor broker-read failures, the sync-path ledger swallow, and the factory.

Covers: a broker lookup failure inside the stranded-order sweep (the failing
order is left for the next pass, the rest reconcile), a per-order broker fetch
failure inside the bulk sync (one bad order cannot abort the pass), the
ledger-publish swallow on the REST-sync emission path, and the
``create_order_executor`` factory's credential/ownership contract.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import llamatrade_alpaca
import llamatrade_db.session as db_session_module
from llamatrade_alpaca import AlpacaError, TradingClient
from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import OrderSide as AlpacaOrderSide
from llamatrade_alpaca import OrderStatus as AlpacaOrderStatus
from llamatrade_alpaca import OrderType as AlpacaOrderType
from llamatrade_alpaca import TimeInForce as AlpacaTimeInForce
from llamatrade_db.models.trading import Order
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)

import src.credentials as credentials_module
import src.providers as providers_module
from src.executor.order_executor import OrderExecutor, create_order_executor
from src.streaming.publisher import TradingEventPublisher


def _db_order(
    *,
    status: int = ORDER_STATUS_PENDING,
    alpaca_order_id: str | None = None,
    client_order_id: str | None = None,
) -> Order:
    return Order(
        id=uuid4(),
        tenant_id=uuid4(),
        session_id=uuid4(),
        client_order_id=client_order_id or f"lt-{uuid4().hex[:16]}",
        symbol="AAPL",
        side=ORDER_SIDE_BUY,
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
        qty=Decimal("10"),
        status=status,
        filled_qty=Decimal("0"),
        alpaca_order_id=alpaca_order_id,
    )


def _filled_alpaca_order(order_id: str) -> AlpacaOrder:
    return AlpacaOrder(
        id=order_id,
        symbol="AAPL",
        qty=Decimal("10"),
        side=AlpacaOrderSide.BUY,
        order_type=AlpacaOrderType.MARKET,
        status=AlpacaOrderStatus.FILLED,
        time_in_force=AlpacaTimeInForce.DAY,
        filled_qty=Decimal("10"),
        filled_avg_price=Decimal("150.00"),
        created_at=datetime.now(UTC),
        filled_at=datetime.now(UTC),
    )


def _rows_result(rows: list[Order]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.fixture
def broker() -> AsyncMock:
    return AsyncMock(spec=TradingClient)


@pytest.fixture
def executor(mock_db, broker, mock_risk_manager) -> OrderExecutor:
    return OrderExecutor(db=mock_db, alpaca_client=broker, risk_manager=mock_risk_manager)


class TestStrandedSweepBrokerFailure:
    async def test_broker_lookup_failure_skips_that_order_and_reconciles_the_rest(
        self, executor, mock_db, broker
    ):
        """One raising lookup leaves its order PENDING for the next pass while
        the others still reconcile (reject or adopt)."""
        unreachable = _db_order()
        never_placed = _db_order()
        placed = _db_order()
        mock_db.execute = AsyncMock(return_value=_rows_result([unreachable, never_placed, placed]))
        broker.get_order_by_client_id = AsyncMock(
            side_effect=[AlpacaError("broker down"), None, _filled_alpaca_order("a-3")]
        )

        reconciled = await executor.recover_stranded_orders(
            unreachable.tenant_id, unreachable.session_id
        )

        assert reconciled == 2
        assert unreachable.status == ORDER_STATUS_PENDING
        assert unreachable.alpaca_order_id is None
        assert never_placed.status == ORDER_STATUS_REJECTED
        assert never_placed.failed_at is not None
        assert never_placed.metadata_ is not None
        assert "never submitted" in never_placed.metadata_["error"]
        assert placed.status == ORDER_STATUS_FILLED
        assert placed.alpaca_order_id == "a-3"
        assert placed.filled_avg_price == Decimal("150.00")
        mock_db.commit.assert_awaited()

    async def test_no_stranded_orders_short_circuits(self, executor, mock_db, broker):
        mock_db.execute = AsyncMock(return_value=_rows_result([]))

        assert await executor.recover_stranded_orders(uuid4(), uuid4()) == 0
        broker.get_order_by_client_id.assert_not_awaited()


class TestBulkSyncBrokerFailure:
    async def test_one_failing_fetch_does_not_abort_the_pass(self, executor, mock_db, broker):
        broken = _db_order(status=ORDER_STATUS_SUBMITTED, alpaca_order_id="a-1")
        healthy = _db_order(status=ORDER_STATUS_SUBMITTED, alpaca_order_id="a-2")
        mock_db.execute = AsyncMock(return_value=_rows_result([broken, healthy]))
        broker.get_order = AsyncMock(
            side_effect=[AlpacaError("fetch failed"), _filled_alpaca_order("a-2")]
        )

        updated = await executor.sync_all_pending_orders(broken.tenant_id, broken.session_id)

        assert updated == 1
        assert broken.status == ORDER_STATUS_SUBMITTED
        assert healthy.status == ORDER_STATUS_FILLED
        assert healthy.filled_qty == Decimal("10")
        mock_db.commit.assert_awaited()


class TestSyncPathLedgerPublishSwallow:
    async def test_publish_failure_is_logged_never_raised(self, mock_db, broker, mock_risk_manager):
        publisher = AsyncMock(spec=TradingEventPublisher)
        publisher.publish_ledger_fill = AsyncMock(side_effect=RuntimeError("kafka down"))
        executor = OrderExecutor(
            db=mock_db,
            alpaca_client=broker,
            risk_manager=mock_risk_manager,
            event_publisher=publisher,
        )
        order = _db_order(status=ORDER_STATUS_FILLED, alpaca_order_id="a-1")
        order.sleeve_id = uuid4()
        order.account_id = uuid4()
        order.filled_qty = Decimal("10")
        order.filled_avg_price = Decimal("150.00")
        order.filled_at = datetime.now(UTC)

        await executor._emit_ledger_for_terminal(order)

        publisher.publish_ledger_fill.assert_awaited_once()


class TestCreateOrderExecutorFactory:
    @pytest.fixture
    def factory_db(self) -> AsyncMock:
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def seams(self, factory_db: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
        session_broker = AsyncMock(spec=TradingClient)
        singleton_broker = AsyncMock(spec=TradingClient)
        mocks = {
            "session_maker": MagicMock(return_value=MagicMock(return_value=factory_db)),
            "bind_guc": MagicMock(),
            "resolve_creds": AsyncMock(return_value=MagicMock()),
            "build_client": MagicMock(return_value=session_broker),
            "singleton_client": MagicMock(return_value=singleton_broker),
        }
        monkeypatch.setattr(db_session_module, "get_session_maker", mocks["session_maker"])
        monkeypatch.setattr(db_session_module, "bind_tenant_guc", mocks["bind_guc"])
        monkeypatch.setattr(
            credentials_module, "resolve_session_credentials", mocks["resolve_creds"]
        )
        monkeypatch.setattr(providers_module, "build_trading_client", mocks["build_client"])
        monkeypatch.setattr(llamatrade_alpaca, "get_trading_client", mocks["singleton_client"])
        mocks["session_broker"] = session_broker
        mocks["singleton_broker"] = singleton_broker
        return mocks

    async def test_requires_a_tenant_id(self):
        with pytest.raises(ValueError, match="requires a tenant_id"):
            await create_order_executor()

    async def test_session_path_without_credentials_closes_db_and_raises(self, seams, factory_db):
        seams["resolve_creds"].return_value = None

        with pytest.raises(ValueError, match="No active Alpaca credentials"):
            await create_order_executor(session_id=uuid4(), tenant_id=uuid4())

        factory_db.close.assert_awaited_once()

    async def test_session_path_builds_owned_client_from_session_credentials(
        self, seams, factory_db
    ):
        tenant_id = uuid4()
        executor = await create_order_executor(session_id=uuid4(), tenant_id=tenant_id)

        assert executor.alpaca is seams["session_broker"]
        seams["build_client"].assert_called_once_with(seams["resolve_creds"].return_value)
        seams["bind_guc"].assert_called_once_with(factory_db, tenant_id)

        await executor.aclose()
        factory_db.close.assert_awaited_once()
        seams["session_broker"].close.assert_awaited_once()

    async def test_tenant_only_path_uses_the_shared_client_and_never_closes_it(
        self, seams, factory_db
    ):
        executor = await create_order_executor(tenant_id=uuid4())

        assert executor.alpaca is seams["singleton_broker"]
        seams["resolve_creds"].assert_not_awaited()

        await executor.aclose()
        factory_db.close.assert_awaited_once()
        seams["singleton_broker"].close.assert_not_awaited()

    async def test_aclose_contains_a_failing_owned_client_close(self, seams, factory_db):
        seams["session_broker"].close = AsyncMock(side_effect=RuntimeError("socket gone"))
        executor = await create_order_executor(session_id=uuid4(), tenant_id=uuid4())

        await executor.aclose()

        factory_db.close.assert_awaited_once()
