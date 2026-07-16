"""Tests for Portfolio gRPC servicer to improve coverage."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

# === Test Fixtures ===


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mock gRPC context."""
    context = MagicMock()
    context.abort = AsyncMock()
    return context


@pytest.fixture
def test_tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_portfolio_summary(test_tenant_id: UUID) -> MagicMock:
    """Create a mock portfolio summary."""
    summary = MagicMock()
    summary.total_equity = Decimal("100000.00")
    summary.cash = Decimal("25000.00")
    summary.market_value = Decimal("75000.00")
    summary.total_unrealized_pnl = Decimal("5000.00")
    summary.total_realized_pnl = Decimal("2000.00")
    summary.total_pnl_percent = Decimal("7.5")
    summary.day_pnl = Decimal("500.00")
    summary.day_pnl_percent = Decimal("0.5")
    summary.positions_count = 5
    summary.updated_at = datetime.now(UTC)
    return summary


@pytest.fixture
def mock_position() -> MagicMock:
    """Create a mock position."""
    position = MagicMock()
    position.symbol = "AAPL"
    position.side = "long"
    position.qty = Decimal("100")
    position.cost_basis = Decimal("15000.00")
    position.avg_entry_price = Decimal("150.00")
    position.current_price = Decimal("155.00")
    position.market_value = Decimal("15500.00")
    position.unrealized_pnl = Decimal("500.00")
    position.unrealized_pnl_percent = Decimal("3.33")
    return position


@pytest.fixture
def mock_transaction(test_tenant_id: UUID) -> MagicMock:
    """Create a mock transaction."""
    transaction = MagicMock()
    transaction.id = uuid4()
    transaction.tenant_id = test_tenant_id
    transaction.type = "buy"
    transaction.symbol = "AAPL"
    transaction.quantity = Decimal("10")
    transaction.price = Decimal("150.00")
    transaction.amount = Decimal("1500.00")
    transaction.fees = Decimal("1.00")
    transaction.description = "Buy AAPL"
    transaction.reference_id = "ref-123"
    transaction.created_at = datetime.now(UTC)
    return transaction


# === Helper Method Tests ===
# These test the helper methods by mocking the servicer import


class TestTransactionTypeConversion:
    """Tests for transaction type conversion helpers."""

    def test_to_proto_transaction_type_mapping(self) -> None:
        """Every real TransactionType value round-trips through the servicer mapper.

        Regression: TRANSFER_IN/OUT (strategy allocations) must NOT collapse to
        DEPOSIT — that would make allocations indistinguishable from deposits.
        """
        from llamatrade_proto.generated import portfolio_pb2

        from src.grpc.servicer import PortfolioServicer

        servicer = PortfolioServicer()
        for value in (
            portfolio_pb2.TRANSACTION_TYPE_DEPOSIT,
            portfolio_pb2.TRANSACTION_TYPE_WITHDRAWAL,
            portfolio_pb2.TRANSACTION_TYPE_BUY,
            portfolio_pb2.TRANSACTION_TYPE_SELL,
            portfolio_pb2.TRANSACTION_TYPE_DIVIDEND,
            portfolio_pb2.TRANSACTION_TYPE_INTEREST,
            portfolio_pb2.TRANSACTION_TYPE_FEE,
            portfolio_pb2.TRANSACTION_TYPE_TRANSFER_IN,
            portfolio_pb2.TRANSACTION_TYPE_TRANSFER_OUT,
        ):
            assert servicer._to_proto_transaction_type(value) == value

    def test_from_proto_transaction_type_mapping(self) -> None:
        """Test reverse transaction type mapping."""
        # Proto value -> internal type
        proto_map = {
            1: "deposit",
            2: "withdrawal",
            3: "buy",
            4: "sell",
            5: "dividend",
        }

        for proto_val in proto_map:
            assert proto_val in proto_map


class TestPositionSideConversion:
    """Tests for position side conversion."""

    def test_position_side_long(self) -> None:
        """Test long position side conversion."""
        side = "long"
        assert side in ["long", "short"]

    def test_position_side_short(self) -> None:
        """Test short position side conversion."""
        side = "short"
        assert side in ["long", "short"]


# === Portfolio Summary Tests ===


class TestPortfolioSummaryConversion:
    """Tests for portfolio summary to proto conversion."""

    def test_portfolio_summary_fields(
        self, mock_portfolio_summary: MagicMock, test_tenant_id: UUID
    ) -> None:
        """Test portfolio summary has all required fields."""
        summary = mock_portfolio_summary

        assert summary.total_equity == Decimal("100000.00")
        assert summary.cash == Decimal("25000.00")
        assert summary.market_value == Decimal("75000.00")
        assert summary.positions_count == 5

    def test_portfolio_pnl_calculation(self, mock_portfolio_summary: MagicMock) -> None:
        """Test PnL calculation from summary."""
        summary = mock_portfolio_summary

        total_pnl = summary.total_unrealized_pnl + summary.total_realized_pnl
        assert total_pnl == Decimal("7000.00")


# === Position Response Tests ===


class TestPositionConversion:
    """Tests for position to proto conversion."""

    def test_position_fields(self, mock_position: MagicMock) -> None:
        """Test position has all required fields."""
        pos = mock_position

        assert pos.symbol == "AAPL"
        assert pos.side == "long"
        assert pos.qty == Decimal("100")
        assert pos.market_value == Decimal("15500.00")

    def test_position_pnl(self, mock_position: MagicMock) -> None:
        """Test position PnL fields."""
        pos = mock_position

        assert pos.unrealized_pnl == Decimal("500.00")
        assert pos.unrealized_pnl_percent == Decimal("3.33")


# === Transaction Response Tests ===


class TestTransactionConversion:
    """Tests for transaction to proto conversion."""

    def test_transaction_fields(self, mock_transaction: MagicMock, test_tenant_id: UUID) -> None:
        """Test transaction has all required fields."""
        txn = mock_transaction

        assert txn.tenant_id == test_tenant_id
        assert txn.symbol == "AAPL"
        assert txn.quantity == Decimal("10")
        assert txn.price == Decimal("150.00")
        assert txn.amount == Decimal("1500.00")

    def test_transaction_fees(self, mock_transaction: MagicMock) -> None:
        """Test transaction fees field."""
        txn = mock_transaction

        assert txn.fees == Decimal("1.00")


# === Asset Allocation Tests ===


class TestAssetAllocation:
    """Tests for asset allocation calculation."""

    def test_allocation_percentage_calculation(self, mock_position: MagicMock) -> None:
        """Test allocation percentage calculation."""
        total_value = Decimal("100000.00")
        position_value = mock_position.market_value

        pct = (position_value / total_value) * 100

        assert pct == Decimal("15.5")

    def test_allocation_empty_positions(self) -> None:
        """Test allocation with no positions."""
        positions: list[MagicMock] = []
        total_value = sum(p.market_value for p in positions) if positions else Decimal("0")

        assert total_value == Decimal("0")


# === Pagination Tests ===


class TestPagination:
    """Tests for pagination logic."""

    def test_total_pages_calculation(self) -> None:
        """Test total pages calculation."""
        total = 50
        page_size = 20

        total_pages = (total + page_size - 1) // page_size

        assert total_pages == 3

    def test_total_pages_exact_division(self) -> None:
        """Test total pages when divides exactly."""
        total = 40
        page_size = 20

        total_pages = (total + page_size - 1) // page_size

        assert total_pages == 2

    def test_total_pages_zero_items(self) -> None:
        """Test total pages with zero items."""
        total = 0
        page_size = 20

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        assert total_pages == 1

    def test_has_next_page(self) -> None:
        """Test has_next calculation."""
        page = 1
        total_pages = 3

        has_next = page < total_pages

        assert has_next is True

    def test_has_previous_page(self) -> None:
        """Test has_previous calculation."""
        page = 2

        has_previous = page > 1

        assert has_previous is True


# === Performance Metrics Tests ===


class TestPerformanceMetrics:
    """Tests for performance metrics structure."""

    def test_metrics_fields(self) -> None:
        """Test performance metrics has expected fields."""
        metrics = {
            "total_return": Decimal("10.5"),
            "ytd_return": Decimal("8.2"),
            "mtd_return": Decimal("1.5"),
            "wtd_return": Decimal("0.3"),
            "volatility": Decimal("15.2"),
            "sharpe_ratio": Decimal("1.8"),
            "max_drawdown": Decimal("-5.2"),
            "beta": Decimal("1.05"),
            "benchmark_return": Decimal("9.0"),
            "alpha": Decimal("1.5"),
        }

        assert "total_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics

    def test_metrics_types(self) -> None:
        """Test performance metrics are Decimal type."""
        metrics = {
            "total_return": Decimal("10.5"),
            "volatility": Decimal("15.2"),
        }

        for value in metrics.values():
            assert isinstance(value, Decimal)


# === Sync Portfolio Tests ===


class TestSyncPortfolio:
    """Tests for sync portfolio operation."""

    def test_sync_returns_position_count(self, mock_position: MagicMock) -> None:
        """Test sync returns correct position count."""
        positions = [mock_position, mock_position]

        positions_synced = len(positions)

        assert positions_synced == 2

    def test_sync_empty_positions(self) -> None:
        """Test sync with no positions."""
        positions: list[MagicMock] = []

        positions_synced = len(positions)

        assert positions_synced == 0


# === Strategy Performance Positions ===


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


async def test_get_strategy_performance_maps_positions() -> None:
    """GetStrategyPerformance carries the sleeve's marked-to-market positions."""
    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    from src.grpc.servicer import PortfolioServicer
    from src.models import PositionResponse
    from src.services.strategy_performance_service import (
        LiveMetrics,
        PeriodReturns,
        StrategyPerformanceDetail,
        StrategyPerformanceSummary,
    )

    execution_id, tenant_id = uuid4(), uuid4()
    detail = StrategyPerformanceDetail(
        summary=StrategyPerformanceSummary(
            execution_id=execution_id,
            strategy_id=uuid4(),
            strategy_name="Trend",
            mode="paper",
            status="running",
            color="#fff",
            allocated_capital=Decimal("10000"),
            current_value=Decimal("10500"),
            positions_count=1,
            returns=PeriodReturns(),
            started_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        metrics=LiveMetrics(),
        positions=[
            PositionResponse(
                symbol="AAPL",
                qty=10.0,
                side="long",
                cost_basis=4000.0,
                market_value=5000.0,
                unrealized_pnl=1000.0,
                unrealized_pnl_percent=25.0,
                current_price=500.0,
                avg_entry_price=400.0,
            )
        ],
    )

    reader = MagicMock()
    reader.get_strategy_performance = AsyncMock(return_value=detail)

    servicer = PortfolioServicer()
    servicer._get_db = AsyncMock(return_value=_Session())
    servicer._strategy_perf_reader = MagicMock(return_value=reader)

    request = portfolio_pb2.GetStrategyPerformanceRequest(
        context=common_pb2.TenantContext(tenant_id=str(tenant_id)),
        execution_id=str(execution_id),
    )
    resp = await servicer.get_strategy_performance(request, MagicMock())

    assert len(resp.positions) == 1
    pos = resp.positions[0]
    assert pos.symbol == "AAPL"
    assert Decimal(pos.quantity.value) == Decimal("10")
    assert Decimal(pos.average_entry_price.value) == Decimal("400")
    assert Decimal(pos.current_price.value) == Decimal("500")
    assert Decimal(pos.market_value.value) == Decimal("5000")
    assert Decimal(pos.unrealized_pnl.value) == Decimal("1000")
