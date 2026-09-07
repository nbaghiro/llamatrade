"""Tests for Portfolio gRPC servicer to improve coverage."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


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


# --- read RPCs (list_portfolios / get_positions / get_performance / list perf) ---


def _summary_view(*, positions_count: int = 1) -> Any:
    from src.ledger.read_model import SummaryView

    return SummaryView(
        total_equity=Decimal("10000"),
        cash=Decimal("4000"),
        market_value=Decimal("6000"),
        total_unrealized_pnl=Decimal("500"),
        total_realized_pnl=Decimal("100"),
        day_pnl=Decimal("50"),
        day_pnl_percent=Decimal("0.5"),
        total_pnl_percent=Decimal("6"),
        positions_count=positions_count,
    )


def _position_view() -> Any:
    from src.ledger.read_model import PositionView

    return PositionView(
        symbol="AAPL",
        qty=Decimal("10"),
        side="long",
        cost_basis=Decimal("4000"),
        market_value=Decimal("6000"),
        unrealized_pnl=Decimal("2000"),
        unrealized_pnl_percent=Decimal("50"),
        current_price=Decimal("600"),
        avg_entry_price=Decimal("400"),
    )


def _book_totals(*, has_strategies: bool = False) -> Any:
    from src.services.strategy_performance_service import BookTotals

    return BookTotals(
        day_pnl=Decimal("20"),
        day_pnl_percent=Decimal("0.2"),
        total_return=Decimal("300"),
        total_return_percent=Decimal("3"),
        has_strategies=has_strategies,
    )


def _read_servicer(reader: MagicMock, perf_reader: MagicMock | None = None) -> Any:
    from src.grpc.servicer import PortfolioServicer

    servicer = PortfolioServicer()
    servicer._session_factory = cast(Any, lambda: _Session())
    servicer._reader = MagicMock(return_value=reader)
    if perf_reader is not None:
        servicer._strategy_perf_reader = MagicMock(return_value=perf_reader)
    return servicer


async def test_list_portfolios_returns_the_single_tenant_portfolio() -> None:
    """ListPortfolios maps the ledger summary to one portfolio with pagination."""
    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    reader = MagicMock()
    reader.get_summary = AsyncMock(return_value=_summary_view())
    perf_reader = MagicMock()
    perf_reader.book_totals = AsyncMock(return_value=_book_totals())

    servicer = _read_servicer(reader, perf_reader)
    resp = await servicer.list_portfolios(
        portfolio_pb2.ListPortfoliosRequest(
            context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        ),
        MagicMock(),
    )

    assert len(resp.portfolios) == 1
    assert Decimal(resp.portfolios[0].total_value.value) == Decimal("10000")
    assert Decimal(resp.portfolios[0].cash_balance.value) == Decimal("4000")
    assert resp.pagination.total_items == 1


async def test_get_positions_maps_position_views() -> None:
    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    reader = MagicMock()
    reader.list_positions = AsyncMock(return_value=[_position_view()])

    servicer = _read_servicer(reader)
    resp = await servicer.get_positions(
        portfolio_pb2.GetPositionsRequest(
            context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        ),
        MagicMock(),
    )

    assert len(resp.positions) == 1
    assert resp.positions[0].symbol == "AAPL"
    assert Decimal(resp.positions[0].market_value.value) == Decimal("6000")


async def test_get_performance_defaults_period_and_sets_total_positions() -> None:
    """Without a time range the metrics read defaults to 1M; the servicer fills
    total_positions from the summary."""
    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    reader = MagicMock()
    reader.get_summary = AsyncMock(return_value=_summary_view(positions_count=7))
    reader.get_metrics = AsyncMock(return_value=portfolio_pb2.PerformanceMetrics())

    servicer = _read_servicer(reader)
    resp = await servicer.get_performance(
        portfolio_pb2.GetPerformanceRequest(
            context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        ),
        MagicMock(),
    )

    assert reader.get_metrics.await_args is not None
    assert reader.get_metrics.await_args.kwargs["period"] == "1M"
    assert resp.metrics.total_positions == 7


@pytest.mark.parametrize(
    ("days", "expected_period"),
    [(1, "1D"), (7, "1W"), (30, "1M"), (90, "3M"), (180, "6M"), (365, "1Y"), (400, "ALL")],
)
async def test_get_performance_maps_time_range_to_period(days: int, expected_period: str) -> None:
    from llamatrade_proto.generated import common_pb2, portfolio_pb2
    from llamatrade_proto.timestamps import to_proto_timestamp

    reader = MagicMock()
    reader.get_summary = AsyncMock(return_value=_summary_view())
    reader.get_metrics = AsyncMock(return_value=portfolio_pb2.PerformanceMetrics())

    end = datetime(2026, 6, 1, tzinfo=UTC)
    request = portfolio_pb2.GetPerformanceRequest(
        context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        time_range=common_pb2.TimeRange(
            start=to_proto_timestamp(end - timedelta(days=days)),
            end=to_proto_timestamp(end),
        ),
    )
    servicer = _read_servicer(reader)
    await servicer.get_performance(request, MagicMock())

    assert reader.get_metrics.await_args is not None
    assert reader.get_metrics.await_args.kwargs["period"] == expected_period


async def test_list_strategy_performance_maps_totals_and_filters() -> None:
    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    from src.services.strategy_performance_service import ListPerformanceResult

    result = ListPerformanceResult(
        strategies=[portfolio_pb2.StrategyPerformanceSummary(strategy_name="Trend")],
        total_allocated=Decimal("1000"),
        total_current_value=Decimal("1100"),
        combined_return=Decimal("0.1"),
        total=1,
    )
    perf_reader = MagicMock()
    perf_reader.list_strategy_performance = AsyncMock(return_value=result)

    servicer = _read_servicer(MagicMock(), perf_reader)
    resp = await servicer.list_strategy_performance(
        portfolio_pb2.ListStrategyPerformanceRequest(
            context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
            mode=common_pb2.EXECUTION_MODE_PAPER,
        ),
        MagicMock(),
    )

    assert [s.strategy_name for s in resp.strategies] == ["Trend"]
    assert Decimal(resp.total_allocated.value) == Decimal("1000")
    assert Decimal(resp.total_current_value.value) == Decimal("1100")
    assert Decimal(resp.combined_return.value) == Decimal("0.1")
    assert resp.pagination.total_items == 1
    call = perf_reader.list_strategy_performance.await_args
    assert call is not None
    assert call.kwargs["filters"].mode == common_pb2.EXECUTION_MODE_PAPER
    assert call.kwargs["filters"].status is None


async def test_list_strategy_performance_none_combined_return_reports_zero() -> None:
    """An all-unfunded book (combined_return None) must serialize as "0", not crash."""
    from llamatrade_proto.generated import common_pb2, portfolio_pb2

    from src.services.strategy_performance_service import ListPerformanceResult

    result = ListPerformanceResult(
        strategies=[],
        total_allocated=Decimal("0"),
        total_current_value=Decimal("0"),
        combined_return=None,
        total=0,
    )
    perf_reader = MagicMock()
    perf_reader.list_strategy_performance = AsyncMock(return_value=result)

    servicer = _read_servicer(MagicMock(), perf_reader)
    resp = await servicer.list_strategy_performance(
        portfolio_pb2.ListStrategyPerformanceRequest(
            context=common_pb2.TenantContext(tenant_id=str(uuid4()), user_id=str(uuid4())),
        ),
        MagicMock(),
    )

    assert resp.combined_return.value == "0"
    assert list(resp.strategies) == []
