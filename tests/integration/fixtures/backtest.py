"""Backtest fixtures for integration tests.

Provides fixtures for creating test backtests and results.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Backtest, BacktestResult, Strategy, Tenant, User
from tests.factories import (
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
    BacktestFactory,
    BacktestResultFactory,
)


@pytest.fixture
async def test_backtest(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
    test_strategy: Strategy,
) -> Backtest:
    """Create a test backtest in PENDING state.

    Returns:
        Backtest model instance (not yet started)
    """
    backtest = BacktestFactory.create(
        tenant_id=test_tenant.id,
        strategy_id=test_strategy.id,
        created_by=test_user.id,
        name="Test Backtest",
        status=BACKTEST_STATUS_PENDING,
        initial_capital=Decimal("100000.00"),
        symbols=["AAPL", "GOOGL"],
    )
    db_session.add(backtest)
    await db_session.flush()
    await db_session.refresh(backtest)
    return backtest


@pytest.fixture
async def running_backtest(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
    test_strategy: Strategy,
) -> Backtest:
    """Create a backtest in RUNNING state.

    Returns:
        Backtest model instance that's currently running
    """
    backtest = BacktestFactory.create(
        tenant_id=test_tenant.id,
        strategy_id=test_strategy.id,
        created_by=test_user.id,
        name="Running Backtest",
        status=BACKTEST_STATUS_RUNNING,
        initial_capital=Decimal("50000.00"),
    )
    backtest.started_at = datetime.now(UTC)
    db_session.add(backtest)
    await db_session.flush()
    await db_session.refresh(backtest)
    return backtest


@pytest.fixture
async def completed_backtest(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
    test_strategy: Strategy,
) -> Backtest:
    """Create a completed backtest with results.

    Returns:
        Backtest model instance with associated BacktestResult
    """
    backtest = BacktestFactory.create(
        tenant_id=test_tenant.id,
        strategy_id=test_strategy.id,
        created_by=test_user.id,
        name="Completed Backtest",
        status=BACKTEST_STATUS_COMPLETED,
        initial_capital=Decimal("100000.00"),
        symbols=["AAPL"],
    )
    backtest.started_at = datetime.now(UTC) - timedelta(minutes=5)
    backtest.completed_at = datetime.now(UTC)
    db_session.add(backtest)
    await db_session.flush()

    # Add backtest results
    result = BacktestResultFactory.create(
        backtest_id=backtest.id,
        total_return=Decimal("0.150000"),  # 15% return
        annual_return=Decimal("0.120000"),  # 12% annualized
        sharpe_ratio=Decimal("1.5000"),
        sortino_ratio=Decimal("2.0000"),
        max_drawdown=Decimal("-0.080000"),  # -8%
        win_rate=Decimal("0.5500"),  # 55%
        profit_factor=Decimal("1.8000"),
        total_trades=50,
        winning_trades=27,
        losing_trades=23,
        final_equity=Decimal("115000.00"),
    )
    db_session.add(result)
    await db_session.flush()
    await db_session.refresh(backtest)
    return backtest


@pytest.fixture
async def failed_backtest(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
    test_strategy: Strategy,
) -> Backtest:
    """Create a failed backtest with error message.

    Returns:
        Backtest model instance in FAILED status
    """
    backtest = BacktestFactory.create(
        tenant_id=test_tenant.id,
        strategy_id=test_strategy.id,
        created_by=test_user.id,
        name="Failed Backtest",
        status=BACKTEST_STATUS_FAILED,
        initial_capital=Decimal("100000.00"),
    )
    backtest.started_at = datetime.now(UTC) - timedelta(minutes=1)
    backtest.error_message = "Insufficient market data for the selected date range"
    db_session.add(backtest)
    await db_session.flush()
    await db_session.refresh(backtest)
    return backtest


@pytest.fixture
async def multiple_backtests(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
    test_strategy: Strategy,
) -> list[Backtest]:
    """Create multiple backtests for pagination testing.

    Returns:
        List of 5 Backtest model instances with various states
    """
    statuses = [
        BACKTEST_STATUS_PENDING,
        BACKTEST_STATUS_RUNNING,
        BACKTEST_STATUS_COMPLETED,
        BACKTEST_STATUS_COMPLETED,
        BACKTEST_STATUS_FAILED,
    ]
    backtests = []

    for i, status in enumerate(statuses):
        backtest = BacktestFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=test_strategy.id,
            created_by=test_user.id,
            name=f"Backtest {i + 1}",
            status=status,
            initial_capital=Decimal(str(50000 + i * 10000)),
        )
        db_session.add(backtest)
        backtests.append(backtest)

    await db_session.flush()
    for backtest in backtests:
        await db_session.refresh(backtest)

    return backtests


@pytest.fixture
async def backtest_with_detailed_results(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
    test_strategy: Strategy,
) -> Backtest:
    """Create a completed backtest with detailed results including equity curve.

    Returns:
        Backtest model instance with comprehensive result data
    """
    backtest = BacktestFactory.create(
        tenant_id=test_tenant.id,
        strategy_id=test_strategy.id,
        created_by=test_user.id,
        name="Detailed Backtest",
        status=BACKTEST_STATUS_COMPLETED,
        initial_capital=Decimal("100000.00"),
        symbols=["AAPL", "GOOGL", "MSFT"],
    )
    backtest.started_at = datetime.now(UTC) - timedelta(minutes=10)
    backtest.completed_at = datetime.now(UTC)
    db_session.add(backtest)
    await db_session.flush()

    # Generate sample equity curve
    equity_curve = []
    equity = 100000.0
    for day in range(30):
        # Simulate daily returns
        daily_return = 0.001 * (day % 5 - 2)  # Small daily fluctuations
        equity *= 1 + daily_return
        equity_curve.append(
            {
                "date": (datetime.now(UTC) - timedelta(days=30 - day)).isoformat(),
                "equity": round(equity, 2),
                "drawdown": min(0, (equity - 100000) / 100000),
            }
        )

    # Generate sample trades
    trades = [
        {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10,
            "price": 175.50,
            "pnl": 50.00,
            "timestamp": (datetime.now(UTC) - timedelta(days=25)).isoformat(),
        },
        {
            "symbol": "AAPL",
            "side": "sell",
            "qty": 10,
            "price": 180.50,
            "pnl": 50.00,
            "timestamp": (datetime.now(UTC) - timedelta(days=20)).isoformat(),
        },
        {
            "symbol": "GOOGL",
            "side": "buy",
            "qty": 5,
            "price": 140.00,
            "pnl": -25.00,
            "timestamp": (datetime.now(UTC) - timedelta(days=15)).isoformat(),
        },
    ]

    result = BacktestResultFactory.create(
        backtest_id=backtest.id,
        total_return=Decimal("0.080000"),
        annual_return=Decimal("0.250000"),
        sharpe_ratio=Decimal("1.8000"),
        sortino_ratio=Decimal("2.3000"),
        max_drawdown=Decimal("-0.050000"),
        max_drawdown_duration=5,
        win_rate=Decimal("0.6000"),
        profit_factor=Decimal("2.1000"),
        exposure_time=Decimal("75.00"),
        total_trades=30,
        winning_trades=18,
        losing_trades=12,
        avg_trade_return=Decimal("0.002667"),
        final_equity=Decimal("108000.00"),
        equity_curve=equity_curve,
        trades=trades,
        daily_returns=[0.001, 0.002, -0.001, 0.003, 0.0, -0.002],
        monthly_returns={"2024-01": 0.05, "2024-02": 0.03},
    )
    db_session.add(result)
    await db_session.flush()
    await db_session.refresh(backtest)
    return backtest


@pytest.fixture
async def second_tenant_backtest(
    db_session: AsyncSession,
    second_tenant: Tenant,
    second_tenant_user: User,
    second_tenant_strategy: Strategy,
) -> Backtest:
    """Create a backtest belonging to the second tenant.

    Used for tenant isolation testing.
    """
    backtest = BacktestFactory.create(
        tenant_id=second_tenant.id,
        strategy_id=second_tenant_strategy.id,
        created_by=second_tenant_user.id,
        name="Other Tenant Backtest",
        status=BACKTEST_STATUS_COMPLETED,
    )
    db_session.add(backtest)
    await db_session.flush()
    await db_session.refresh(backtest)
    return backtest


@pytest.fixture
async def backtest_result(
    db_session: AsyncSession,
    completed_backtest: Backtest,
) -> BacktestResult:
    """Get the backtest result from a completed backtest.

    Returns:
        BacktestResult model instance
    """
    from sqlalchemy import select

    result = await db_session.execute(
        select(BacktestResult).where(BacktestResult.backtest_id == completed_backtest.id)
    )
    return result.scalar_one()
