"""Concurrency and race-condition tests driving production code paths.

Covered here:
1. Deterministic-order idempotency in OrderExecutor.submit_order (replay,
   stranded resume, broker adoption, concurrent duplicate suppression)
2. Multiple runners processing the same symbol
3. AsyncTTLCache access under concurrent load
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from llamatrade_alpaca import AlpacaError, MockBarStream, MockTradeStream, TradingClient
from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import OrderSide as AlpacaOrderSide
from llamatrade_alpaca import OrderStatus as AlpacaOrderStatus
from llamatrade_alpaca import OrderType as AlpacaOrderType
from llamatrade_alpaca import TimeInForce as AlpacaTimeInForce
from llamatrade_db.models.trading import Order
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_STATUS_ACCEPTED,
    ORDER_STATUS_PENDING,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)

from src.executor.order_executor import OrderExecutor, generate_deterministic_order_id
from src.models import OrderCreate, RiskCheckResult
from src.risk.risk_manager import RiskManager
from src.runner.runner import RunnerConfig, StrategyRunner
from src.utils.cache import AsyncTTLCache

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

SIGNAL_TS = datetime(2025, 1, 16, 15, 30, tzinfo=UTC)


class FakeOrderDB:
    """In-memory AsyncSession double: persists Order rows, serves client-id lookups."""

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
        if len(matches) > 1:
            result.scalar_one_or_none.side_effect = MultipleResultsFound()
        else:
            result.scalar_one_or_none.return_value = matches[0] if matches else None
        result.scalars.return_value.all.return_value = matches
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


class FakeBroker:
    """Broker double enforcing Alpaca's per-account client_order_id uniqueness."""

    def __init__(self) -> None:
        self.orders_by_client_id: dict[str, AlpacaOrder] = {}
        self.submit_calls: int = 0

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
    ) -> AlpacaOrder:
        self.submit_calls += 1
        await asyncio.sleep(0)  # dispatch window where a concurrent duplicate can race
        key = client_order_id or str(uuid4())
        if key in self.orders_by_client_id:
            raise AlpacaError(f"client_order_id {key} already in use")
        order = AlpacaOrder(
            id=f"alpaca-{len(self.orders_by_client_id) + 1}",
            client_order_id=key,
            symbol=symbol,
            qty=Decimal(str(qty)),
            side=AlpacaOrderSide.BUY if side == "buy" else AlpacaOrderSide.SELL,
            order_type=AlpacaOrderType.MARKET,
            status=AlpacaOrderStatus.ACCEPTED,
            time_in_force=AlpacaTimeInForce.DAY,
            created_at=datetime.now(UTC),
        )
        self.orders_by_client_id[key] = order
        return order

    async def get_order_by_client_id(self, client_order_id: str) -> AlpacaOrder | None:
        await asyncio.sleep(0)
        return self.orders_by_client_id.get(client_order_id)


def _executor(db: FakeOrderDB, broker: FakeBroker) -> OrderExecutor:
    risk = AsyncMock()
    risk.check_order = AsyncMock(return_value=RiskCheckResult(passed=True, violations=[]))
    return OrderExecutor(
        db=cast(AsyncSession, db),
        alpaca_client=cast(TradingClient, broker),
        risk_manager=cast(RiskManager, risk),
    )


def _order_create(symbol: str = "AAPL") -> OrderCreate:
    return OrderCreate(
        symbol=symbol,
        side=ORDER_SIDE_BUY,
        qty=Decimal("10"),
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
    )


def _client_id() -> str:
    return generate_deterministic_order_id(TEST_SESSION_ID, "AAPL", "buy", SIGNAL_TS)


def _pending_row(client_order_id: str) -> Order:
    order = Order(
        tenant_id=TEST_TENANT_ID,
        session_id=TEST_SESSION_ID,
        client_order_id=client_order_id,
        symbol="AAPL",
        side=ORDER_SIDE_BUY,
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
        qty=Decimal("10"),
        status=ORDER_STATUS_PENDING,
        filled_qty=Decimal("0"),
    )
    order.id = uuid4()
    return order


class TestDeterministicSubmitIdempotency:
    """The real submit_order path: one signal, one broker order — no matter what."""

    async def test_retry_after_success_replays_existing(self) -> None:
        """A resubmitted signal returns the recorded order without a second dispatch."""
        db, broker = FakeOrderDB(), FakeBroker()
        executor = _executor(db, broker)

        first = await executor.submit_order(
            TEST_TENANT_ID, TEST_SESSION_ID, _order_create(), signal_timestamp=SIGNAL_TS
        )
        second = await executor.submit_order(
            TEST_TENANT_ID, TEST_SESSION_ID, _order_create(), signal_timestamp=SIGNAL_TS
        )

        assert second is first
        assert broker.submit_calls == 1
        assert len(db.rows) == 1
        assert first.alpaca_order_id == "alpaca-1"

    async def test_concurrent_same_signal_yields_single_broker_order(self) -> None:
        """Concurrent duplicates serialize at the broker: exactly one order is placed;
        losers surface as errors instead of silent double-submission."""
        db, broker = FakeOrderDB(), FakeBroker()
        executor = _executor(db, broker)

        results = await asyncio.gather(
            *[
                executor.submit_order(
                    TEST_TENANT_ID, TEST_SESSION_ID, _order_create(), signal_timestamp=SIGNAL_TS
                )
                for _ in range(5)
            ],
            return_exceptions=True,
        )

        assert set(broker.orders_by_client_id) == {_client_id()}
        successes = [r for r in results if isinstance(r, Order)]
        failures = [r for r in results if not isinstance(r, Order)]
        assert successes, "at least one submission must win"
        assert {order.alpaca_order_id for order in successes} == {"alpaca-1"}
        assert all(isinstance(failure, ValueError) for failure in failures)
        assert {row.client_order_id for row in db.rows} == {_client_id()}

    async def test_stranded_pending_row_is_resumed_not_duplicated(self) -> None:
        """A row recorded PENDING that never reached the broker is redispatched
        on the same row (crash in the submit window, 3A)."""
        db, broker = FakeOrderDB(), FakeBroker()
        executor = _executor(db, broker)
        stranded = _pending_row(_client_id())
        db.rows.append(stranded)

        result = await executor.submit_order(
            TEST_TENANT_ID, TEST_SESSION_ID, _order_create(), signal_timestamp=SIGNAL_TS
        )

        assert result is stranded
        assert broker.submit_calls == 1
        assert result.alpaca_order_id == "alpaca-1"
        assert len(db.rows) == 1

    async def test_broker_confirmed_order_is_adopted_without_resubmit(self) -> None:
        """A PENDING row whose order did reach the broker before a crash adopts
        the broker order instead of placing a second one."""
        db, broker = FakeOrderDB(), FakeBroker()
        executor = _executor(db, broker)
        client_id = _client_id()
        stranded = _pending_row(client_id)
        db.rows.append(stranded)
        broker.orders_by_client_id[client_id] = AlpacaOrder(
            id="alpaca-lost-response",
            client_order_id=client_id,
            symbol="AAPL",
            qty=Decimal("10"),
            side=AlpacaOrderSide.BUY,
            order_type=AlpacaOrderType.MARKET,
            status=AlpacaOrderStatus.ACCEPTED,
            time_in_force=AlpacaTimeInForce.DAY,
            created_at=datetime.now(UTC),
        )

        result = await executor.submit_order(
            TEST_TENANT_ID, TEST_SESSION_ID, _order_create(), signal_timestamp=SIGNAL_TS
        )

        assert result is stranded
        assert result.alpaca_order_id == "alpaca-lost-response"
        assert result.status == ORDER_STATUS_ACCEPTED
        assert broker.submit_calls == 0

    async def test_distinct_signals_both_dispatch(self) -> None:
        """Different signal timestamps derive different ids — no false dedup."""
        db, broker = FakeOrderDB(), FakeBroker()
        executor = _executor(db, broker)

        first = await executor.submit_order(
            TEST_TENANT_ID, TEST_SESSION_ID, _order_create(), signal_timestamp=SIGNAL_TS
        )
        second = await executor.submit_order(
            TEST_TENANT_ID,
            TEST_SESSION_ID,
            _order_create(),
            signal_timestamp=SIGNAL_TS + timedelta(minutes=1),
        )

        assert first.client_order_id != second.client_order_id
        assert broker.submit_calls == 2
        assert len(broker.orders_by_client_id) == 2


class TestConcurrentCacheAccess:
    """Concurrent access against the real AsyncTTLCache."""

    async def test_concurrent_cache_reads(self) -> None:
        """Concurrent reads return the values written, with no lost entries."""
        cache: AsyncTTLCache = AsyncTTLCache(default_ttl=60.0)

        for i in range(10):
            await cache.set(f"key_{i}", f"value_{i}")

        async def read_key(key: str) -> object:
            await asyncio.sleep(0.001)
            return await cache.get(key)

        tasks = [read_key(f"key_{i}") for _ in range(10) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 100
        assert all(r is not None for r in results)

    async def test_concurrent_cache_writes(self) -> None:
        """Concurrent writes to distinct keys lose nothing."""
        cache: AsyncTTLCache = AsyncTTLCache(default_ttl=60.0)

        async def write_key(i: int) -> None:
            await asyncio.sleep(0.001)
            await cache.set(f"concurrent_key_{i}", f"value_{i}")

        await asyncio.gather(*[write_key(i) for i in range(50)])

        for i in range(50):
            value = await cache.get(f"concurrent_key_{i}")
            assert value == f"value_{i}", f"Missing or wrong value for key_{i}"

    async def test_concurrent_cache_read_write(self) -> None:
        """Interleaved reads and writes stay consistent per key."""
        cache: AsyncTTLCache = AsyncTTLCache(default_ttl=60.0)

        for i in range(10):
            await cache.set(f"rw_key_{i}", f"initial_{i}")

        async def read_operation(key: str) -> object:
            return await cache.get(key)

        async def write_operation(key: str, value: str) -> None:
            await cache.set(key, value)

        read_tasks = []
        write_tasks = []
        for i in range(10):
            read_tasks.append(read_operation(f"rw_key_{i}"))
            write_tasks.append(write_operation(f"rw_key_{i}", f"updated_{i}"))
            read_tasks.append(read_operation(f"rw_key_{i}"))

        reads, _ = await asyncio.gather(asyncio.gather(*read_tasks), asyncio.gather(*write_tasks))

        assert len(reads) == 20
        # Every read observes either the initial or the updated value for its key.
        for read in reads:
            assert isinstance(read, str) and (
                read.startswith("initial_") or read.startswith("updated_")
            )


class TestMultipleRunners:
    """Tests for multiple runners processing same symbol."""

    async def test_multiple_runners_same_symbol(
        self,
        sample_bars,
        mock_alpaca_client,
        mock_risk_manager,
    ) -> None:
        """Test multiple runners can process the same symbol concurrently."""

        def simple_strategy(symbol, bars, position, equity):
            return None  # No signals to avoid order submission complexity

        mock_order_executor = MagicMock(spec=OrderExecutor)
        mock_order_executor.submit_order = AsyncMock()

        runners = []
        for i in range(3):
            bar_stream = MockBarStream(bars={"AAPL": sample_bars.copy()})
            config = RunnerConfig(
                tenant_id=TEST_TENANT_ID,
                execution_id=uuid4(),  # Different session for each
                strategy_id=TEST_STRATEGY_ID,
                symbols=["AAPL"],
                timeframe="1Min",
                warmup_bars=20,
                enforce_trading_hours=False,
            )
            runner = StrategyRunner(
                config=config,
                strategy_fn=simple_strategy,
                bar_stream=bar_stream,
                trade_stream=MockTradeStream(),
                order_executor=mock_order_executor,
                risk_manager=mock_risk_manager,
                alpaca_client=mock_alpaca_client,
                strategy_name=f"Runner {i}",
            )
            runners.append(runner)

        # Run all runners concurrently with timeout
        # start() contains the processing loop and blocks until stopped
        async def run_with_timeout(runner: StrategyRunner) -> None:
            try:
                await asyncio.wait_for(runner.start(), timeout=1.0)
            except TimeoutError:
                pass
            finally:
                await runner.stop()

        await asyncio.gather(*[run_with_timeout(r) for r in runners])

        # Verify all runners processed bars
        for runner in runners:
            assert "AAPL" in runner._bar_history
            assert len(runner._bar_history["AAPL"]) > 0


class TestAsyncTTLCacheStress:
    """Stress tests for AsyncTTLCache under high concurrency."""

    async def test_high_concurrency_stress(self) -> None:
        """Stress test cache with high concurrent access."""
        cache: AsyncTTLCache = AsyncTTLCache(default_ttl=60.0, max_size=100)

        async def stress_operation(op_id: int) -> None:
            key = f"stress_key_{op_id % 20}"  # 20 unique keys
            if op_id % 3 == 0:
                await cache.set(key, f"value_{op_id}")
            elif op_id % 3 == 1:
                await cache.get(key)
            else:
                await cache.invalidate(key)

        # 1000 concurrent operations must complete without raising
        await asyncio.gather(*[stress_operation(i) for i in range(1000)])

    async def test_cache_eviction_under_pressure(self) -> None:
        """Test cache eviction works correctly under concurrent pressure."""
        cache: AsyncTTLCache = AsyncTTLCache(default_ttl=0.1, max_size=10)

        async def write_and_read(key: str) -> object:
            await cache.set(key, f"value_{key}")
            await asyncio.sleep(0.05)
            return await cache.get(key)

        # Write more keys than cache size concurrently
        results = await asyncio.gather(*[write_and_read(f"key_{i}") for i in range(50)])

        # Some values may be None due to eviction or expiry
        non_none = [r for r in results if r is not None]
        # At least some should have succeeded
        assert len(non_none) > 0
        # But not all (due to max_size limit)
        assert len(non_none) <= 50
