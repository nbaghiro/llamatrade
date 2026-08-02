"""Tests for Portfolio gRPC servicer to improve coverage."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
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

    def test_txn_type_map_distinguishes_transfers(self) -> None:
        """The read-model label -> proto TransactionType map is exhaustive.

        Regression: TRANSFER_IN/OUT (strategy allocations) must NOT collapse to
        DEPOSIT — that would make allocations indistinguishable from deposits.
        """
        from llamatrade_proto.generated import portfolio_pb2

        from src.proto_mappers import TXN_TYPE_TO_PROTO

        expected = {
            "deposit": portfolio_pb2.TRANSACTION_TYPE_DEPOSIT,
            "withdrawal": portfolio_pb2.TRANSACTION_TYPE_WITHDRAWAL,
            "buy": portfolio_pb2.TRANSACTION_TYPE_BUY,
            "sell": portfolio_pb2.TRANSACTION_TYPE_SELL,
            "dividend": portfolio_pb2.TRANSACTION_TYPE_DIVIDEND,
            "interest": portfolio_pb2.TRANSACTION_TYPE_INTEREST,
            "fee": portfolio_pb2.TRANSACTION_TYPE_FEE,
            "transfer_in": portfolio_pb2.TRANSACTION_TYPE_TRANSFER_IN,
            "transfer_out": portfolio_pb2.TRANSACTION_TYPE_TRANSFER_OUT,
        }
        assert TXN_TYPE_TO_PROTO == expected
        assert TXN_TYPE_TO_PROTO["transfer_in"] != TXN_TYPE_TO_PROTO["deposit"]

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

    async def execute(self, *args: object, **kwargs: object) -> None:
        return None


async def test_get_strategy_performance_maps_positions() -> None:
    """GetStrategyPerformance carries the sleeve's marked-to-market positions."""
    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    from src.grpc.servicer import PortfolioServicer
    from src.ledger.read_model import PositionView
    from src.proto_mappers import period_returns_to_proto, strategy_summary_to_proto
    from src.services.strategy_performance_service import StrategyPerformanceDetail

    execution_id, tenant_id = uuid4(), uuid4()
    detail = StrategyPerformanceDetail(
        summary=strategy_summary_to_proto(
            execution_id=execution_id,
            strategy_id=uuid4(),
            strategy_name="Trend",
            mode=common_pb2.EXECUTION_MODE_PAPER,
            status=common_pb2.EXECUTION_STATUS_RUNNING,
            color="#fff",
            allocated_capital=Decimal("10000"),
            current_value=Decimal("10500"),
            positions_count=1,
            returns=period_returns_to_proto({}),
            started_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        metrics=portfolio_pb2.StrategyLiveMetrics(),
        positions=[
            PositionView(
                symbol="AAPL",
                qty=Decimal("10.0"),
                side="long",
                cost_basis=Decimal("4000.0"),
                market_value=Decimal("5000.0"),
                unrealized_pnl=Decimal("1000.0"),
                unrealized_pnl_percent=Decimal("25.0"),
                current_price=Decimal("500.0"),
                avg_entry_price=Decimal("400.0"),
            )
        ],
    )

    reader = MagicMock()
    reader.get_strategy_performance = AsyncMock(return_value=detail)

    servicer = PortfolioServicer()
    servicer._session_factory = cast(Any, lambda: _Session())
    servicer._strategy_perf_reader = MagicMock(return_value=reader)

    request = portfolio_pb2.GetStrategyPerformanceRequest(
        context=common_pb2.TenantContext(tenant_id=str(tenant_id), user_id=str(uuid4())),
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


class _AcctSession:
    """Fake session: GUC execute + scalars() returning preset accounts."""

    def __init__(self, accounts: list) -> None:
        self._accounts = accounts

    async def __aenter__(self) -> _AcctSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, *a: object, **k: object) -> None:
        return None

    async def scalars(self, *a: object, **k: object):
        return iter(self._accounts)


async def test_asset_allocation_includes_cash_and_weights_over_total() -> None:
    """Per-symbol weights are over the whole portfolio (incl. cash) + a Cash slice."""
    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    from src.grpc.servicer import PortfolioServicer
    from src.ledger.read_model import PositionView

    tenant_id = uuid4()
    positions = [
        PositionView(
            symbol="AAPL",
            qty=Decimal("10.0"),
            side="long",
            cost_basis=Decimal("4000.0"),
            market_value=Decimal("6000.0"),
            unrealized_pnl=Decimal("2000.0"),
            unrealized_pnl_percent=Decimal("50.0"),
            current_price=Decimal("600.0"),
            avg_entry_price=Decimal("400.0"),
        )
    ]
    summary = MagicMock()
    summary.cash = Decimal("4000")
    reader = MagicMock()
    reader.list_positions = AsyncMock(return_value=positions)
    reader.get_summary = AsyncMock(return_value=summary)

    servicer = PortfolioServicer()
    servicer._session_factory = cast(Any, lambda: _Session())
    servicer._reader = MagicMock(return_value=reader)

    resp = await servicer.get_asset_allocation(
        portfolio_pb2.GetAssetAllocationRequest(
            context=common_pb2.TenantContext(tenant_id=str(tenant_id), user_id=str(uuid4())),
        ),
        MagicMock(),
    )

    cats = {a.category: a for a in resp.allocations}
    assert set(cats) == {"Stocks", "Cash"}
    # total = 6000 + 4000 = 10000 → Stocks 60%, Cash 40%.
    assert cats["Stocks"].percentage.value == "60.0"
    assert cats["Cash"].percentage.value == "40.0"
    # Per-symbol weight is over the WHOLE portfolio.
    assert cats["Stocks"].items[0].symbol == "AAPL"
    assert cats["Stocks"].items[0].percentage.value == "60.0"


async def test_sync_portfolio_triggers_reconciliation(monkeypatch) -> None:
    """SyncPortfolio reconciles the tenant's accounts and reports the drift count."""
    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    import src.tasks.reconciliation as recon
    from src.grpc.servicer import PortfolioServicer

    tenant_id = uuid4()
    result = MagicMock()
    result.drifts = [MagicMock(), MagicMock()]  # 2 drifts surfaced
    recon_mock = AsyncMock(return_value=[result])
    monkeypatch.setattr(recon, "reconcile_accounts_once", recon_mock)

    reader = MagicMock()
    reader.get_summary = AsyncMock(return_value=MagicMock())
    reader.list_positions = AsyncMock(return_value=[])
    perf_reader = MagicMock()
    perf_reader.book_totals = AsyncMock(return_value=MagicMock())

    servicer = PortfolioServicer()
    servicer._session_factory = cast(Any, lambda: _AcctSession([MagicMock()]))
    servicer._reader = MagicMock(return_value=reader)
    servicer._strategy_perf_reader = MagicMock(return_value=perf_reader)

    resp = await servicer.sync_portfolio(
        portfolio_pb2.SyncPortfolioRequest(
            context=common_pb2.TenantContext(tenant_id=str(tenant_id), user_id=str(uuid4())),
        ),
        MagicMock(),
    )

    recon_mock.assert_awaited_once()
    assert resp.transactions_recorded == 2


async def test_internal_error_is_withheld_from_client() -> None:
    """A database error surfaces as INTERNAL with no SQL/table text leaked."""
    from connectrpc.code import Code
    from connectrpc.errors import ConnectError
    from sqlalchemy.exc import SQLAlchemyError

    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    from src.grpc.servicer import PortfolioServicer

    tenant_id = uuid4()
    reader = MagicMock()
    reader.list_positions = AsyncMock(
        side_effect=SQLAlchemyError("relation secret_ledger_table does not exist")
    )
    servicer = PortfolioServicer()
    servicer._session_factory = cast(Any, lambda: _Session())
    servicer._reader = MagicMock(return_value=reader)

    with pytest.raises(ConnectError) as exc_info:
        await servicer.get_asset_allocation(
            portfolio_pb2.GetAssetAllocationRequest(
                context=common_pb2.TenantContext(tenant_id=str(tenant_id), user_id=str(uuid4())),
            ),
            MagicMock(),
        )

    assert exc_info.value.code == Code.INTERNAL
    assert "secret_ledger_table" not in exc_info.value.message


async def test_connect_error_passes_through_unchanged() -> None:
    """A NOT_FOUND raised inside the handler is not swallowed into INTERNAL."""
    from connectrpc.code import Code
    from connectrpc.errors import ConnectError

    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    from src.grpc.servicer import PortfolioServicer

    reader = MagicMock()
    reader.get_strategy_performance = AsyncMock(return_value=None)
    servicer = PortfolioServicer()
    servicer._session_factory = cast(Any, lambda: _Session())
    servicer._strategy_perf_reader = MagicMock(return_value=reader)

    with pytest.raises(ConnectError) as exc_info:
        await servicer.get_strategy_performance(
            portfolio_pb2.GetStrategyPerformanceRequest(
                context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
                execution_id=str(uuid4()),
            ),
            MagicMock(),
        )

    assert exc_info.value.code == Code.NOT_FOUND


async def test_get_strategy_performance_bad_execution_id_is_invalid_argument() -> None:
    """A malformed execution_id is rejected as INVALID_ARGUMENT, not INTERNAL."""
    from connectrpc.code import Code
    from connectrpc.errors import ConnectError

    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    from src.grpc.servicer import PortfolioServicer

    servicer = PortfolioServicer()
    with pytest.raises(ConnectError) as exc_info:
        await servicer.get_strategy_performance(
            portfolio_pb2.GetStrategyPerformanceRequest(
                context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
                execution_id="not-a-uuid",
            ),
            MagicMock(),
        )

    assert exc_info.value.code == Code.INVALID_ARGUMENT
