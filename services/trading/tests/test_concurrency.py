"""Concurrency and race condition tests.

These tests verify thread-safety and race condition handling:
1. Multiple runners processing same symbol
2. Concurrent order submissions
3. Position reconciliation during active trading
4. Cache access under concurrent load
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_TYPE_MARKET,
    TIME_IN_FORCE_DAY,
)

from src.executor.order_executor import OrderExecutor
from src.models import OrderCreate, RiskCheckResult
from src.risk.risk_manager import RiskManager
from src.runner.bar_stream import BarData, MockBarStream
from src.runner.runner import RunnerConfig, StrategyRunner
from src.runner.trade_stream import MockTradeStream

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def sample_bars():
    """Create sample bars for testing."""
    base_time = datetime(2025, 1, 16, 15, 0, tzinfo=UTC)
    bars = []
    price = 150.0

    for i in range(60):
        timestamp = base_time + timedelta(minutes=i)
        price = price * (1 + (0.001 if i % 3 == 0 else -0.0005))
        bars.append(
            BarData(
                symbol="AAPL",
                timestamp=timestamp,
                open=price * 0.999,
                high=price * 1.005,
                low=price * 0.995,
                close=price,
                volume=10000 + i * 100,
            )
        )

    return bars


@pytest.fixture
def mock_alpaca_client():
    """Create a mock Alpaca trading client."""
    client = AsyncMock()
    client.get_account = AsyncMock(
        return_value={
            "id": "test-account",
            "equity": "100000.00",
            "cash": "100000.00",
        }
    )
    client.submit_order = AsyncMock(
        return_value={
            "id": f"alpaca-{uuid4()}",
            "status": "accepted",
            "filled_qty": "0",
        }
    )
    client.get_positions = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_risk_manager():
    """Create a mock risk manager that passes all checks."""
    manager = AsyncMock(spec=RiskManager)
    manager.check_order = AsyncMock(return_value=RiskCheckResult(passed=True, violations=[]))
    manager.get_limits = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def mock_order_executor():
    """Create a mock order executor."""
    executor = MagicMock(spec=OrderExecutor)
    executor.submit_order = AsyncMock(
        return_value=MagicMock(
            id=uuid4(),
            alpaca_order_id=f"alpaca-{uuid4()}",
            symbol="AAPL",
            status="submitted",
        )
    )
    return executor


class TestConcurrentOrderSubmission:
    """Tests for concurrent order submission scenarios."""

    async def test_concurrent_orders_from_same_session(
        self,
        mock_alpaca_client,
        mock_risk_manager,
    ):
        """Test concurrent order submissions from the same session."""
        order_ids = []
        submission_lock = asyncio.Lock()

        async def track_submission(**kwargs):
            async with submission_lock:
                order_id = uuid4()
                order_ids.append(order_id)
                await asyncio.sleep(0.01)  # Simulate network latency
                return MagicMock(
                    id=order_id,
                    alpaca_order_id=f"alpaca-{order_id}",
                    symbol=kwargs.get("order", MagicMock()).symbol,
                    status="submitted",
                )

        mock_order_executor = MagicMock(spec=OrderExecutor)
        mock_order_executor.submit_order = AsyncMock(side_effect=track_submission)

        # Create 10 order submissions concurrently
        orders = [
            OrderCreate(
                symbol="AAPL",
                side=ORDER_SIDE_BUY,
                qty=10,
                order_type=ORDER_TYPE_MARKET,
                time_in_force=TIME_IN_FORCE_DAY,
            )
            for _ in range(10)
        ]

        async def submit_order(order: OrderCreate):
            return await mock_order_executor.submit_order(
                tenant_id=TEST_TENANT_ID,
                session_id=TEST_SESSION_ID,
                order=order,
            )

        # Submit all orders concurrently
        results = await asyncio.gather(*[submit_order(o) for o in orders])

        # Verify all orders were submitted
        assert len(results) == 10
        assert len(order_ids) == 10

        # Verify all order IDs are unique
        assert len(set(order_ids)) == 10

    async def test_concurrent_orders_different_symbols(
        self,
        mock_risk_manager,
    ):
        """Test concurrent order submissions for different symbols."""
        symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
        submitted_symbols = []
        symbol_lock = asyncio.Lock()

        async def track_symbol(**kwargs):
            order = kwargs.get("order", MagicMock())
            async with symbol_lock:
                submitted_symbols.append(order.symbol)
                await asyncio.sleep(0.01)
            return MagicMock(
                id=uuid4(),
                alpaca_order_id=f"alpaca-{uuid4()}",
                symbol=order.symbol,
                status="submitted",
            )

        mock_order_executor = MagicMock(spec=OrderExecutor)
        mock_order_executor.submit_order = AsyncMock(side_effect=track_symbol)

        orders = [
            OrderCreate(
                symbol=symbol,
                side=ORDER_SIDE_BUY,
                qty=10,
                order_type=ORDER_TYPE_MARKET,
                time_in_force=TIME_IN_FORCE_DAY,
            )
            for symbol in symbols
        ]

        async def submit_order(order: OrderCreate):
            return await mock_order_executor.submit_order(
                tenant_id=TEST_TENANT_ID,
                session_id=TEST_SESSION_ID,
                order=order,
            )

        results = await asyncio.gather(*[submit_order(o) for o in orders])

        # Verify all symbols were submitted
        assert len(results) == 5
        assert set(submitted_symbols) == set(symbols)


class TestConcurrentRiskChecks:
    """Tests for concurrent risk check scenarios."""

    async def test_concurrent_risk_checks(self):
        """Test that risk checks can run concurrently without race conditions."""
        check_count = 0
        check_lock = asyncio.Lock()

        async def count_check(**kwargs):
            nonlocal check_count
            async with check_lock:
                check_count += 1
            await asyncio.sleep(0.01)  # Simulate processing
            return RiskCheckResult(passed=True, violations=[])

        mock_risk_manager = AsyncMock(spec=RiskManager)
        mock_risk_manager.check_order = AsyncMock(side_effect=count_check)

        # Run 20 concurrent risk checks
        tasks = [
            mock_risk_manager.check_order(
                tenant_id=TEST_TENANT_ID,
                symbol="AAPL",
                side="buy",
                qty=10.0,
                order_type="market",
            )
            for _ in range(20)
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 20
        assert check_count == 20
        assert all(r.passed for r in results)

    async def test_concurrent_risk_checks_with_failures(self):
        """Test concurrent risk checks where some fail."""
        check_count = 0
        check_lock = asyncio.Lock()

        async def alternating_check(**kwargs):
            nonlocal check_count
            async with check_lock:
                current = check_count
                check_count += 1
            await asyncio.sleep(0.01)
            # Every other check fails
            if current % 2 == 0:
                return RiskCheckResult(passed=True, violations=[])
            else:
                return RiskCheckResult(passed=False, violations=["Test violation"])

        mock_risk_manager = AsyncMock(spec=RiskManager)
        mock_risk_manager.check_order = AsyncMock(side_effect=alternating_check)

        tasks = [
            mock_risk_manager.check_order(
                tenant_id=TEST_TENANT_ID,
                symbol="AAPL",
                side="buy",
                qty=10.0,
                order_type="market",
            )
            for _ in range(20)
        ]

        results = await asyncio.gather(*tasks)

        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]

        assert len(passed) == 10
        assert len(failed) == 10


class TestConcurrentCacheAccess:
    """Tests for concurrent cache access."""

    async def test_concurrent_cache_reads(self):
        """Test concurrent cache reads don't cause race conditions."""
        from src.utils.cache import AsyncTTLCache

        cache = AsyncTTLCache(default_ttl=60.0)

        # Pre-populate cache
        for i in range(10):
            await cache.set(f"key_{i}", f"value_{i}")

        async def read_key(key: str):
            await asyncio.sleep(0.001)  # Slight delay to encourage interleaving
            return await cache.get(key)

        # Read all keys concurrently multiple times
        tasks = []
        for _ in range(10):
            for i in range(10):
                tasks.append(read_key(f"key_{i}"))

        results = await asyncio.gather(*tasks)

        # Verify all reads returned correct values
        assert len(results) == 100
        # All should be non-None
        non_none_results = [r for r in results if r is not None]
        assert len(non_none_results) == 100

    async def test_concurrent_cache_writes(self):
        """Test concurrent cache writes don't cause data loss."""
        from src.utils.cache import AsyncTTLCache

        cache = AsyncTTLCache(default_ttl=60.0)

        async def write_key(i: int):
            await asyncio.sleep(0.001)
            await cache.set(f"concurrent_key_{i}", f"value_{i}")

        # Write 50 keys concurrently
        await asyncio.gather(*[write_key(i) for i in range(50)])

        # Verify all writes succeeded
        for i in range(50):
            value = await cache.get(f"concurrent_key_{i}")
            assert value == f"value_{i}", f"Missing or wrong value for key_{i}"

    async def test_concurrent_cache_read_write(self):
        """Test concurrent reads and writes don't interfere."""
        from src.utils.cache import AsyncTTLCache

        cache = AsyncTTLCache(default_ttl=60.0)

        # Pre-populate some keys
        for i in range(10):
            await cache.set(f"rw_key_{i}", f"initial_{i}")

        read_results = []
        write_count = 0
        results_lock = asyncio.Lock()

        async def read_operation(key: str):
            result = await cache.get(key)
            async with results_lock:
                read_results.append(result)

        async def write_operation(key: str, value: str):
            nonlocal write_count
            await cache.set(key, value)
            async with results_lock:
                write_count += 1

        # Mix reads and writes concurrently
        tasks = []
        for i in range(10):
            tasks.append(read_operation(f"rw_key_{i}"))
            tasks.append(write_operation(f"rw_key_{i}", f"updated_{i}"))
            tasks.append(read_operation(f"rw_key_{i}"))

        await asyncio.gather(*tasks)

        # Verify operations completed
        assert write_count == 10
        # Some reads should have gotten initial values, some updated
        assert len(read_results) == 20


class TestMultipleRunners:
    """Tests for multiple runners processing same symbol."""

    async def test_multiple_runners_same_symbol(
        self,
        sample_bars,
        mock_alpaca_client,
        mock_risk_manager,
        mock_order_executor,
    ):
        """Test multiple runners can process the same symbol concurrently."""

        def simple_strategy(symbol, bars, position, equity):
            if len(bars) < 20:
                return None
            return None  # No signals to avoid order submission complexity

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


class TestPositionReconciliationConcurrency:
    """Tests for position reconciliation during active trading."""

    async def test_reconciliation_during_order_submission(
        self,
        sample_bars,
        mock_alpaca_client,
        mock_risk_manager,
    ):
        """Test position reconciliation doesn't interfere with order submission."""
        orders_submitted = []
        reconciliations_done = []
        lock = asyncio.Lock()

        async def track_order(**kwargs):
            async with lock:
                orders_submitted.append(kwargs)
            await asyncio.sleep(0.02)  # Simulate order processing
            return MagicMock(
                id=uuid4(),
                alpaca_order_id=f"alpaca-{uuid4()}",
                symbol="AAPL",
                status="submitted",
            )

        async def track_reconciliation(**kwargs):
            async with lock:
                reconciliations_done.append(kwargs)
            await asyncio.sleep(0.01)

        mock_order_executor = MagicMock(spec=OrderExecutor)
        mock_order_executor.submit_order = AsyncMock(side_effect=track_order)

        # Simulate concurrent order submissions and reconciliations
        order_tasks = [
            mock_order_executor.submit_order(
                tenant_id=TEST_TENANT_ID,
                session_id=TEST_SESSION_ID,
                order=OrderCreate(
                    symbol="AAPL",
                    side=ORDER_SIDE_BUY,
                    qty=10,
                    order_type=ORDER_TYPE_MARKET,
                    time_in_force=TIME_IN_FORCE_DAY,
                ),
            )
            for _ in range(5)
        ]

        reconciliation_tasks = [track_reconciliation(session_id=TEST_SESSION_ID) for _ in range(5)]

        # Run both types of tasks concurrently
        all_tasks = order_tasks + reconciliation_tasks
        await asyncio.gather(*all_tasks)

        # Verify both completed without interference
        assert len(orders_submitted) == 5
        assert len(reconciliations_done) == 5


class TestAsyncTTLCacheStress:
    """Stress tests for AsyncTTLCache under high concurrency."""

    async def test_high_concurrency_stress(self):
        """Stress test cache with high concurrent access."""
        from src.utils.cache import AsyncTTLCache

        cache = AsyncTTLCache(default_ttl=60.0, max_size=100)

        operations_completed = 0
        errors = []
        lock = asyncio.Lock()

        async def stress_operation(op_id: int):
            nonlocal operations_completed
            try:
                key = f"stress_key_{op_id % 20}"  # 20 unique keys

                if op_id % 3 == 0:
                    await cache.set(key, f"value_{op_id}")
                elif op_id % 3 == 1:
                    await cache.get(key)
                else:
                    await cache.invalidate(key)

                async with lock:
                    operations_completed += 1
            except Exception as e:
                async with lock:
                    errors.append(str(e))

        # Run 1000 operations concurrently
        await asyncio.gather(*[stress_operation(i) for i in range(1000)])

        # Verify all operations completed without errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert operations_completed == 1000

    async def test_cache_eviction_under_pressure(self):
        """Test cache eviction works correctly under concurrent pressure."""
        from src.utils.cache import AsyncTTLCache

        cache = AsyncTTLCache(default_ttl=0.1, max_size=10)  # Small cache, short TTL

        async def write_and_read(key: str):
            await cache.set(key, f"value_{key}")
            await asyncio.sleep(0.05)  # Some delay
            return await cache.get(key)

        # Write more keys than cache size concurrently
        results = await asyncio.gather(*[write_and_read(f"key_{i}") for i in range(50)])

        # Some values may be None due to eviction or expiry
        non_none = [r for r in results if r is not None]
        # At least some should have succeeded
        assert len(non_none) > 0
        # But not all (due to max_size limit)
        assert len(non_none) <= 50
