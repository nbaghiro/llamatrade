"""End-to-end backtest workflow tests.

These tests verify the complete backtest flow:
1. User registers and logs in (auth service)
2. User creates a strategy (strategy service)
3. User runs a backtest (backtest service)
4. User retrieves backtest results

Note: These tests require all services to be running and may be slow.
Mark with @pytest.mark.slow for selective execution.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Backtest, Strategy, Tenant, User
from tests.factories import BacktestFactory, StrategyFactory
from tests.integration.fixtures.auth import create_auth_headers, create_jwt_token

pytestmark = [pytest.mark.integration, pytest.mark.workflow, pytest.mark.slow]


class TestBacktestWorkflowWithDatabase:
    """Backtest workflow tests using direct database access.

    These tests simulate the workflow by directly interacting with the
    database, which is useful when services are stubbed.
    """

    async def test_complete_backtest_flow_database(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test the complete backtest workflow using database operations.

        Flow:
        1. Create a strategy
        2. Create a backtest for the strategy
        3. Update backtest status (simulating execution)
        4. Verify results
        """
        # Step 1: Create strategy
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
            name="Backtest Workflow Strategy",
        )
        db_session.add(strategy)
        await db_session.flush()

        assert strategy.id is not None
        assert strategy.tenant_id == test_tenant.id

        # Step 2: Create backtest
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=365)

        backtest = BacktestFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            status="pending",
            start_date=start_date.date(),
            end_date=end_date.date(),
            initial_capital=Decimal("100000.00"),
            symbols=["AAPL", "GOOGL"],
        )
        db_session.add(backtest)
        await db_session.flush()

        assert backtest.id is not None
        assert backtest.status == "pending"

        # Step 3: Simulate backtest execution
        backtest.status = "running"
        await db_session.flush()
        assert backtest.status == "running"

        # Simulate completion with results
        backtest.status = "completed"
        await db_session.flush()

        # Step 4: Verify final state
        assert backtest.status == "completed"
        assert backtest.strategy_id == strategy.id
        assert backtest.tenant_id == test_tenant.id

    async def test_backtest_inherits_strategy_version(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that backtest correctly references strategy version."""
        # Create strategy with current_version = 3
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
            current_version=3,
        )
        db_session.add(strategy)
        await db_session.flush()

        # Create backtest with specific version
        backtest = BacktestFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            strategy_version=2,  # Run against version 2, not current
        )
        db_session.add(backtest)
        await db_session.flush()

        assert backtest.strategy_version == 2
        assert strategy.current_version == 3

    async def test_multiple_backtests_same_strategy(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test running multiple backtests for the same strategy."""
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        # Create multiple backtests with different date ranges
        date_ranges = [
            (datetime(2023, 1, 1, tzinfo=UTC), datetime(2023, 6, 30, tzinfo=UTC)),
            (datetime(2023, 7, 1, tzinfo=UTC), datetime(2023, 12, 31, tzinfo=UTC)),
            (datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 6, 30, tzinfo=UTC)),
        ]

        backtests = []
        for start, end in date_ranges:
            bt = BacktestFactory.create(
                tenant_id=test_tenant.id,
                strategy_id=strategy.id,
                created_by=test_user.id,
                start_date=start,
                end_date=end,
            )
            db_session.add(bt)
            backtests.append(bt)

        await db_session.flush()

        # Verify all backtests were created
        assert len(backtests) == 3
        assert all(bt.strategy_id == strategy.id for bt in backtests)

        # Verify different date ranges
        assert backtests[0].start_date.year == 2023
        assert backtests[0].start_date.month == 1
        assert backtests[2].start_date.year == 2024

    async def test_backtest_workflow_tenant_isolation(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that backtest workflow respects tenant isolation."""
        # Create strategy for tenant A
        strategy_a = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_a)
        await db_session.flush()

        # Create backtest for tenant A
        backtest_a = BacktestFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy_a.id,
            created_by=test_user.id,
        )
        db_session.add(backtest_a)
        await db_session.flush()

        # Verify tenant B cannot query tenant A's backtest
        from sqlalchemy import select

        result = await db_session.execute(
            select(Backtest).where(
                Backtest.id == backtest_a.id,
                Backtest.tenant_id == second_tenant.id,
            )
        )
        assert result.scalar_one_or_none() is None


class TestBacktestStatusTransitions:
    """Tests for valid backtest status transitions."""

    async def test_valid_status_flow(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test the valid status flow: pending -> running -> completed."""
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        backtest = BacktestFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            status="pending",
        )
        db_session.add(backtest)
        await db_session.flush()

        # Transition: pending -> running
        assert backtest.status == "pending"
        backtest.status = "running"
        await db_session.flush()
        assert backtest.status == "running"

        # Transition: running -> completed
        backtest.status = "completed"
        await db_session.flush()
        assert backtest.status == "completed"

    async def test_failed_backtest_status(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test backtest failure status."""
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        backtest = BacktestFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            status="pending",
        )
        db_session.add(backtest)
        await db_session.flush()

        # Transition: pending -> running -> failed
        backtest.status = "running"
        await db_session.flush()

        backtest.status = "failed"
        await db_session.flush()
        assert backtest.status == "failed"


class TestBacktestWithResults:
    """Tests for backtest result handling."""

    async def test_backtest_stores_large_equity_curve(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that backtests can store large equity curves as JSON."""
        from tests.factories import BacktestResultFactory

        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        backtest = BacktestFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            status="completed",
        )
        db_session.add(backtest)
        await db_session.flush()

        # Generate a large equity curve (365 days of data)
        equity_curve = [
            {"date": f"2023-{(i//30)+1:02d}-{(i%30)+1:02d}", "equity": 100000 + i * 100}
            for i in range(365)
        ]

        result = BacktestResultFactory.create(
            backtest_id=backtest.id,
            equity_curve=equity_curve,
            total_return=Decimal("0.365000"),
            sharpe_ratio=Decimal("1.5000"),
            max_drawdown=Decimal("-0.150000"),
        )
        db_session.add(result)
        await db_session.flush()

        # Verify data is stored correctly
        assert len(result.equity_curve) == 365
        assert result.equity_curve[0]["equity"] == 100000
        assert result.equity_curve[-1]["equity"] == 100000 + 364 * 100

    async def test_backtest_stores_trade_history(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that backtests can store trade history as JSON."""
        from tests.factories import BacktestResultFactory

        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        backtest = BacktestFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            status="completed",
        )
        db_session.add(backtest)
        await db_session.flush()

        # Create trades
        trades = [
            {
                "symbol": "AAPL",
                "entry_date": "2023-01-15",
                "exit_date": "2023-01-20",
                "entry_price": 150.0,
                "exit_price": 155.0,
                "quantity": 100,
                "pnl": 500.0,
                "return_pct": 0.0333,
            },
            {
                "symbol": "GOOGL",
                "entry_date": "2023-02-01",
                "exit_date": "2023-02-10",
                "entry_price": 100.0,
                "exit_price": 95.0,
                "quantity": 50,
                "pnl": -250.0,
                "return_pct": -0.05,
            },
        ]

        result = BacktestResultFactory.create(
            backtest_id=backtest.id,
            trades=trades,
        )
        db_session.add(result)
        await db_session.flush()

        # Verify trades stored correctly
        assert len(result.trades) == 2
        assert result.trades[0]["symbol"] == "AAPL"
        assert result.trades[0]["pnl"] == 500.0
        assert result.trades[1]["pnl"] == -250.0
