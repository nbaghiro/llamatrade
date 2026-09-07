"""The dashboard read RPCs against real Postgres.

These six handlers are what the dashboard and portfolio pages render, and until
now none of them executed a query in a test: the unit suite mocks the read
services, and one test asserted a compiled SQL string rather than running it. Here
the ledger servicer seeds real events (deposit, allocate, fill) and the portfolio
servicer reads them back through the projector, so a broken predicate, join, or
period filter fails instead of passing on a mock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_proto.generated import common_pb2, ledger_pb2, portfolio_pb2
from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_RUNNING

pytestmark = pytest.mark.integration


def _ctx() -> Any:
    return cast(Any, None)


def _dec(value: str) -> common_pb2.Decimal:
    return common_pb2.Decimal(value=value)


def _tenant_ctx(tenant: str) -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=tenant, user_id=str(uuid4()))


def _ledger_servicer(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    from src.grpc.ledger_servicer import LedgerServicer

    servicer = LedgerServicer()
    servicer._session_factory = session_factory
    return servicer


def _portfolio_servicer(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> Any:
    """The read servicer with market data stubbed out (prices are not under test)."""

    class _StubMarketData:
        async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
            return {symbol: Decimal("100") for symbol in symbols}

    monkeypatch.setattr("src.grpc.servicer.get_market_data_client", lambda: _StubMarketData())

    from src.grpc.servicer import PortfolioServicer

    servicer = PortfolioServicer()
    servicer._session_factory = session_factory
    return servicer


async def _seed_execution(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: UUID, name: str
) -> UUID:
    """A strategy + running execution, the identity half of the performance join."""
    from llamatrade_db.models.strategy import Strategy, StrategyExecution

    async with session_factory() as db:
        strategy = Strategy(tenant_id=tenant_id, name=name, created_by=uuid4())
        db.add(strategy)
        await db.flush()
        execution = StrategyExecution(
            tenant_id=tenant_id,
            strategy_id=strategy.id,
            version=1,
            mode="paper",
            status=EXECUTION_STATUS_RUNNING,
            started_at=datetime.now(UTC),
            allocated_capital=Decimal("40000"),
        )
        db.add(execution)
        await db.commit()
        return execution.id


async def _link_execution_to_sleeve(
    session_factory: async_sessionmaker[AsyncSession],
    execution_id: UUID,
    account_id: str,
    sleeve_id: str,
) -> None:
    """Attach the ledger identity the strategy service writes when it funds."""
    from llamatrade_db.models.strategy import StrategyExecution

    async with session_factory() as db:
        execution = await db.get(StrategyExecution, execution_id)
        assert execution is not None
        execution.account_id = UUID(account_id)
        execution.sleeve_id = UUID(sleeve_id)
        await db.commit()


async def _funded_account(
    ledger: Any,
    ctx: common_pb2.TenantContext,
    *,
    deposit: str = "100000",
    execution_id: str | None = None,
) -> tuple[str, str]:
    """An account with cash deposited and a funded strategy sleeve."""
    account = await ledger.get_or_create_account(
        ledger_pb2.GetOrCreateAccountRequest(context=ctx, credentials_id=str(uuid4())),
        _ctx(),
    )
    account_id = account.account.id
    await ledger.deposit_funds(
        ledger_pb2.DepositFundsRequest(
            request_id=f"read-deposit-{uuid4()}",
            context=ctx,
            account_id=account_id,
            amount=_dec(deposit),
        ),
        _ctx(),
    )
    sleeve = await ledger.allocate_capital(
        ledger_pb2.AllocateCapitalRequest(
            request_id=f"read-allocate-{uuid4()}",
            context=ctx,
            account_id=account_id,
            to_sleeve_id="",
            strategy_execution_id=execution_id or str(uuid4()),
            amount=_dec("40000"),
            sleeve_name="Reads",
        ),
        _ctx(),
    )
    return account_id, sleeve.sleeve.id


class TestListPortfolios:
    async def test_lists_the_tenants_account_after_a_deposit(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ledger = _ledger_servicer(session_factory)
        ctx = _tenant_ctx(str(uuid4()))
        await _funded_account(ledger, ctx)

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        resp = await portfolio.list_portfolios(
            portfolio_pb2.ListPortfoliosRequest(context=ctx), _ctx()
        )

        assert len(resp.portfolios) == 1
        assert Decimal(resp.portfolios[0].total_value.value) == Decimal("100000")

    async def test_another_tenant_sees_none_of_it(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The read path is tenant-scoped by its own predicate, not only by RLS."""
        ledger = _ledger_servicer(session_factory)
        mine = _tenant_ctx(str(uuid4()))
        await _funded_account(ledger, mine)

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        other = _tenant_ctx(str(uuid4()))
        resp = await portfolio.list_portfolios(
            portfolio_pb2.ListPortfoliosRequest(context=other), _ctx()
        )

        # One synthesized portfolio per tenant, but carrying none of mine.
        assert [p.tenant_id for p in resp.portfolios] == [other.tenant_id]
        assert all(Decimal(p.total_value.value) == Decimal("0") for p in resp.portfolios)


class TestGetPerformance:
    async def test_default_range_resolves_against_real_rows(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A broken window filter would raise here rather than pass on a mock."""
        ledger = _ledger_servicer(session_factory)
        ctx = _tenant_ctx(str(uuid4()))
        await _funded_account(ledger, ctx)

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        resp = await portfolio.get_performance(
            portfolio_pb2.GetPerformanceRequest(context=ctx), _ctx()
        )

        # A cash-only account has nothing invested, so the metrics must say so
        # rather than carrying values left over from another tenant's rows.
        assert resp.metrics.total_positions == 0
        assert Decimal(resp.metrics.total_return.value) == Decimal("0")

    async def test_explicit_window_is_accepted(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ledger = _ledger_servicer(session_factory)
        ctx = _tenant_ctx(str(uuid4()))
        await _funded_account(ledger, ctx)

        now = int(datetime.now(UTC).timestamp())
        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        resp = await portfolio.get_performance(
            portfolio_pb2.GetPerformanceRequest(
                context=ctx,
                time_range=common_pb2.TimeRange(
                    start=common_pb2.Timestamp(seconds=now - 86_400 * 30),
                    end=common_pb2.Timestamp(seconds=now),
                ),
            ),
            _ctx(),
        )

        assert resp.metrics.total_positions == 0
        assert resp is not None and resp.HasField("metrics")


class TestGetAssetAllocation:
    async def test_cash_only_account_allocates_to_nothing(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ledger = _ledger_servicer(session_factory)
        ctx = _tenant_ctx(str(uuid4()))
        await _funded_account(ledger, ctx)

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        resp = await portfolio.get_asset_allocation(
            portfolio_pb2.GetAssetAllocationRequest(context=ctx), _ctx()
        )

        categories = {a.category: Decimal(a.percentage.value) for a in resp.allocations}
        assert categories == {"Cash": Decimal("100")}


class TestListTransactions:
    async def test_deposit_and_allocation_surface_as_rows(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ledger = _ledger_servicer(session_factory)
        ctx = _tenant_ctx(str(uuid4()))
        await _funded_account(ledger, ctx)

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        resp = await portfolio.list_transactions(
            portfolio_pb2.ListTransactionsRequest(context=ctx), _ctx()
        )

        assert len(resp.transactions) >= 1
        assert any(Decimal(t.amount.value) == Decimal("100000") for t in resp.transactions)

    async def test_pagination_bounds_the_page(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ledger = _ledger_servicer(session_factory)
        ctx = _tenant_ctx(str(uuid4()))
        await _funded_account(ledger, ctx)

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        resp = await portfolio.list_transactions(
            portfolio_pb2.ListTransactionsRequest(
                context=ctx, pagination=common_pb2.PaginationRequest(page=1, page_size=1)
            ),
            _ctx(),
        )

        assert len(resp.transactions) <= 1


class TestStrategyPerformanceReads:
    async def test_list_strategy_performance_runs_its_join(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Retires the compiled-SQL assertion: the join executes against real rows.

        Identity comes from ``StrategyExecution`` and the money from the ledger
        sleeve, so both sides have to exist for a card to appear.
        """
        ledger = _ledger_servicer(session_factory)
        ctx = _tenant_ctx(str(uuid4()))
        tenant_id = UUID(ctx.tenant_id)
        execution_id = await _seed_execution(session_factory, tenant_id, "Read Path")
        await _funded_account(ledger, ctx, execution_id=str(execution_id))

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        resp = await portfolio.list_strategy_performance(
            portfolio_pb2.ListStrategyPerformanceRequest(context=ctx), _ctx()
        )

        assert [s.execution_id for s in resp.strategies] == [str(execution_id)]
        assert resp.strategies[0].strategy_name == "Read Path"
        assert Decimal(resp.total_allocated.value) == Decimal("40000")

    async def test_another_tenants_execution_is_not_listed(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The join is tenant-scoped on both sides, not only on the ledger side."""
        ledger = _ledger_servicer(session_factory)
        mine = _tenant_ctx(str(uuid4()))
        execution_id = await _seed_execution(session_factory, UUID(mine.tenant_id), "Mine")
        await _funded_account(ledger, mine, execution_id=str(execution_id))

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        resp = await portfolio.list_strategy_performance(
            portfolio_pb2.ListStrategyPerformanceRequest(context=_tenant_ctx(str(uuid4()))),
            _ctx(),
        )

        assert list(resp.strategies) == []

    async def test_equity_curve_window_filters_in_sql(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The window bound is applied by the database, not by the caller.

        The unit test for this asserted that the compiled SQL contained
        ``created_at >=``, which restates the query rather than running it. Here
        three snapshots straddle the requested window and only the in-window one
        may come back.
        """
        from llamatrade_db.models.ledger import SleeveSnapshot

        ledger = _ledger_servicer(session_factory)
        ctx = _tenant_ctx(str(uuid4()))
        tenant_id = UUID(ctx.tenant_id)
        execution_id = await _seed_execution(session_factory, tenant_id, "Windowed")
        account_id, sleeve_id = await _funded_account(ledger, ctx, execution_id=str(execution_id))
        await _link_execution_to_sleeve(session_factory, execution_id, account_id, sleeve_id)

        now = datetime.now(UTC)
        stamps = {
            "before": now - timedelta(days=10),
            "inside": now - timedelta(days=2),
            "after": now + timedelta(days=10),
        }
        async with session_factory() as db:
            for sequence, (_label, created) in enumerate(stamps.items(), start=100):
                db.add(
                    SleeveSnapshot(
                        tenant_id=tenant_id,
                        sleeve_id=UUID(sleeve_id),
                        as_of_sequence=sequence,
                        cash_balance=Decimal("0"),
                        reserved_cash=Decimal("0"),
                        equity=Decimal(str(sequence)),
                        created_at=created,
                    )
                )
            await db.commit()

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        resp = await portfolio.get_strategy_equity_curve(
            portfolio_pb2.GetStrategyEquityCurveRequest(
                context=ctx,
                execution_id=str(execution_id),
                time_range=common_pb2.TimeRange(
                    start=common_pb2.Timestamp(seconds=int((now - timedelta(days=5)).timestamp())),
                    end=common_pb2.Timestamp(seconds=int((now + timedelta(days=1)).timestamp())),
                ),
            ),
            _ctx(),
        )

        equities = [Decimal(p.equity.value) for p in resp.equity_curve]
        assert Decimal("101") in equities, "the in-window snapshot is missing"
        assert Decimal("100") not in equities, "a snapshot before the window leaked in"
        assert Decimal("102") not in equities, "a snapshot after the window leaked in"

    async def test_equity_curve_for_an_unknown_execution_is_not_found(
        self, session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An execution the tenant does not own is refused, never silently empty."""
        from connectrpc.errors import ConnectError

        ledger = _ledger_servicer(session_factory)
        ctx = _tenant_ctx(str(uuid4()))
        await _funded_account(ledger, ctx)

        portfolio = _portfolio_servicer(session_factory, monkeypatch)
        with pytest.raises(ConnectError, match="not found"):
            await portfolio.get_strategy_equity_curve(
                portfolio_pb2.GetStrategyEquityCurveRequest(context=ctx, execution_id=str(uuid4())),
                _ctx(),
            )
