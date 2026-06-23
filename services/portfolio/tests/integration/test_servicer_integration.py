"""Full-stack ledger/portfolio servicer tests against real Postgres.

Drives the real servicers (with their session factory pointed at the test DB) so
the RPC handlers, fund/lifecycle services, projector folding, and read services
are all exercised end-to-end — the layer the unit suite mocks out.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
from connectrpc.errors import ConnectError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_proto.generated import common_pb2, ledger_pb2, portfolio_pb2

pytestmark = pytest.mark.integration


def _ctx() -> Any:
    return cast(Any, None)  # servicers read request.context, never ctx


def _dec(value: str) -> common_pb2.Decimal:
    return common_pb2.Decimal(value=value)


def _tenant_ctx(tenant: str, user: str = "") -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=tenant, user_id=user or str(uuid4()))


def _ledger_servicer(session_factory: async_sessionmaker[AsyncSession]) -> Any:
    from src.grpc.ledger_servicer import LedgerServicer

    servicer = LedgerServicer()
    servicer._session_factory = session_factory  # point at the test DB
    return servicer


async def _bootstrap_account(servicer: Any, ctx: common_pb2.TenantContext) -> str:
    resp = await servicer.get_or_create_account(
        ledger_pb2.GetOrCreateAccountRequest(context=ctx, credentials_id=str(uuid4())),
        _ctx(),
    )
    return resp.account.id


async def test_fund_and_close_sleeve_roundtrip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    servicer = _ledger_servicer(session_factory)
    ctx = _tenant_ctx(str(uuid4()))

    # 1. bootstrap: account + the singleton base sleeves
    account_resp = await servicer.get_or_create_account(
        ledger_pb2.GetOrCreateAccountRequest(context=ctx, credentials_id=str(uuid4())),
        _ctx(),
    )
    account_id = account_resp.account.id
    assert len(account_resp.base_sleeves) == 3  # unallocated / manual / unmanaged

    # 2. deposit external cash into Unallocated
    await servicer.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=ctx, account_id=account_id, amount=_dec("100000")),
        _ctx(),
    )

    # 3. open + fund a strategy sleeve (open-and-fund)
    alloc = await servicer.allocate_capital(
        ledger_pb2.AllocateCapitalRequest(
            context=ctx,
            account_id=account_id,
            to_sleeve_id="",
            strategy_execution_id=str(uuid4()),
            amount=_dec("40000"),
            sleeve_name="Strat A",
        ),
        _ctx(),
    )
    sleeve_id = alloc.sleeve.id
    assert Decimal(alloc.sleeve.cash.balance.value) == Decimal("40000")

    # 4. get_sleeve reflects the funded balance (projected from the event log)
    got = await servicer.get_sleeve(
        ledger_pb2.GetSleeveRequest(context=ctx, sleeve_id=sleeve_id), _ctx()
    )
    assert Decimal(got.sleeve.cash.balance.value) == Decimal("40000")
    assert got.sleeve.status == ledger_pb2.SLEEVE_STATUS_ACTIVE

    # 5. close: free cash re-homed to Unallocated, sleeve CLOSED + drained
    closed = await servicer.close_sleeve(
        ledger_pb2.CloseSleeveRequest(
            context=ctx, account_id=account_id, sleeve_id=sleeve_id, reason="execution stopped"
        ),
        _ctx(),
    )
    assert closed.already_closed is False
    assert Decimal(closed.rehomed_cash.value) == Decimal("40000")

    after = await servicer.get_sleeve(
        ledger_pb2.GetSleeveRequest(context=ctx, sleeve_id=sleeve_id), _ctx()
    )
    assert after.sleeve.status == ledger_pb2.SLEEVE_STATUS_CLOSED
    assert Decimal(after.sleeve.cash.balance.value) == Decimal("0")

    # idempotent re-close
    again = await servicer.close_sleeve(
        ledger_pb2.CloseSleeveRequest(
            context=ctx, account_id=account_id, sleeve_id=sleeve_id, reason="retry"
        ),
        _ctx(),
    )
    assert again.already_closed is True


async def test_foreign_tenant_cannot_read_sleeve(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Tenant isolation: another tenant can't resolve this sleeve."""
    servicer = _ledger_servicer(session_factory)
    owner = _tenant_ctx(str(uuid4()))
    account_id = await _bootstrap_account(servicer, owner)
    # Fund Unallocated, then open-and-fund a strategy sleeve (allocate requires a
    # positive amount against available free cash).
    await servicer.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=owner, account_id=account_id, amount=_dec("1000")),
        _ctx(),
    )
    alloc = await servicer.allocate_capital(
        ledger_pb2.AllocateCapitalRequest(
            context=owner,
            account_id=account_id,
            to_sleeve_id="",
            strategy_execution_id=str(uuid4()),
            amount=_dec("1000"),
            sleeve_name="Strat",
        ),
        _ctx(),
    )

    intruder = _tenant_ctx(str(uuid4()))
    with pytest.raises(ConnectError):  # NOT_FOUND — tenant-scoped lookup misses
        await servicer.get_sleeve(
            ledger_pb2.GetSleeveRequest(context=intruder, sleeve_id=alloc.sleeve.id), _ctx()
        )


async def test_foreign_tenant_cannot_mutate_account(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Tenant isolation across mutations: an intruder can't deposit/withdraw/
    allocate against another tenant's account (the account's base sleeves are
    tenant-scoped, so the lookups miss)."""
    servicer = _ledger_servicer(session_factory)
    owner = _tenant_ctx(str(uuid4()))
    account_id = await _bootstrap_account(servicer, owner)
    await servicer.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=owner, account_id=account_id, amount=_dec("5000")),
        _ctx(),
    )

    intruder = _tenant_ctx(str(uuid4()))
    with pytest.raises(ConnectError):
        await servicer.deposit_funds(
            ledger_pb2.DepositFundsRequest(
                context=intruder, account_id=account_id, amount=_dec("100")
            ),
            _ctx(),
        )
    with pytest.raises(ConnectError):
        await servicer.withdraw_funds(
            ledger_pb2.WithdrawFundsRequest(
                context=intruder, account_id=account_id, amount=_dec("100")
            ),
            _ctx(),
        )
    with pytest.raises(ConnectError):
        await servicer.allocate_capital(
            ledger_pb2.AllocateCapitalRequest(
                context=intruder,
                account_id=account_id,
                to_sleeve_id="",
                strategy_execution_id=str(uuid4()),
                amount=_dec("100"),
                sleeve_name="Intrusion",
            ),
            _ctx(),
        )


async def test_cannot_allocate_to_sleeve_in_another_account(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Even within one tenant, a sleeve is bound to its account: funding account A
    with a to_sleeve_id that lives in account B is rejected."""
    servicer = _ledger_servicer(session_factory)
    owner = _tenant_ctx(str(uuid4()))
    account_a = await _bootstrap_account(servicer, owner)
    account_b = await _bootstrap_account(servicer, owner)

    # Open a funded sleeve in account B.
    await servicer.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=owner, account_id=account_b, amount=_dec("1000")),
        _ctx(),
    )
    sleeve_b = (
        await servicer.allocate_capital(
            ledger_pb2.AllocateCapitalRequest(
                context=owner,
                account_id=account_b,
                to_sleeve_id="",
                strategy_execution_id=str(uuid4()),
                amount=_dec("1000"),
                sleeve_name="B",
            ),
            _ctx(),
        )
    ).sleeve.id

    # Fund account A, then try to allocate A's cash into account B's sleeve.
    await servicer.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=owner, account_id=account_a, amount=_dec("1000")),
        _ctx(),
    )
    with pytest.raises(ConnectError):
        await servicer.allocate_capital(
            ledger_pb2.AllocateCapitalRequest(
                context=owner,
                account_id=account_a,
                to_sleeve_id=sleeve_b,
                amount=_dec("500"),
            ),
            _ctx(),
        )


async def test_oversell_fill_freezes_sleeve(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A fill that drives a sleeve into an impossible state (here an oversell →
    negative position) freezes it for review rather than silently recording it."""
    import hashlib
    from datetime import UTC, datetime
    from uuid import UUID

    from llamatrade_db.models.ledger import LedgerEventType

    from src.ledger.ingestion import LedgerAppend
    from src.tasks.fill_ingestion import persist_append

    servicer = _ledger_servicer(session_factory)
    ctx = _tenant_ctx(str(uuid4()))
    account_id = await _bootstrap_account(servicer, ctx)
    await servicer.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=ctx, account_id=account_id, amount=_dec("1000")),
        _ctx(),
    )
    sleeve_id = (
        await servicer.allocate_capital(
            ledger_pb2.AllocateCapitalRequest(
                context=ctx,
                account_id=account_id,
                to_sleeve_id="",
                strategy_execution_id=str(uuid4()),
                amount=_dec("1000"),
                sleeve_name="S",
            ),
            _ctx(),
        )
    ).sleeve.id

    # Sell 5 shares the sleeve never held (cost_basis supplied, so it isn't
    # quarantined) → position qty goes negative → sleeve must be frozen.
    append = LedgerAppend(
        tenant_id=UUID(ctx.tenant_id),
        account_id=UUID(account_id),
        sleeve_id=UUID(sleeve_id),
        event_type=LedgerEventType.ORDER_FILLED,
        data={
            "sleeve_id": sleeve_id,
            "symbol": "SPY",
            "side": "sell",
            "qty": "5",
            "price": "100",
            "cost_basis": "400",
        },
        event_id=UUID(bytes=hashlib.sha256(b"oversell-1").digest()[:16]),
        occurred_at=datetime.now(UTC),
    )
    async with session_factory() as db:
        await persist_append(db, append)

    got = await servicer.get_sleeve(
        ledger_pb2.GetSleeveRequest(context=ctx, sleeve_id=sleeve_id), _ctx()
    )
    assert got.sleeve.status == ledger_pb2.SLEEVE_STATUS_FROZEN


class _RecordingPrices:
    """PriceProvider that records each get_prices call (for batching assertions)."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        self.calls.append(list(symbols))
        return {s: Decimal("100") for s in symbols}

    async def get_daily_closes(self, symbol: str, start: Any, end: Any) -> dict[Any, float]:
        return {}


async def test_snapshot_pass_batches_prices_across_accounts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """One snapshot pass fetches prices for the UNION of all accounts' symbols in
    a single call, not one call per account."""
    import hashlib
    from datetime import UTC, datetime
    from uuid import UUID

    from llamatrade_db.models.ledger import LedgerEventType

    from src.ledger.ingestion import LedgerAppend
    from src.tasks.equity_snapshot import run_snapshot_pass
    from src.tasks.fill_ingestion import persist_append

    servicer = _ledger_servicer(session_factory)

    async def _account_holding(symbol: str) -> None:
        ctx = _tenant_ctx(str(uuid4()))
        account_id = await _bootstrap_account(servicer, ctx)
        await servicer.deposit_funds(
            ledger_pb2.DepositFundsRequest(context=ctx, account_id=account_id, amount=_dec("1000")),
            _ctx(),
        )
        sleeve_id = (
            await servicer.allocate_capital(
                ledger_pb2.AllocateCapitalRequest(
                    context=ctx,
                    account_id=account_id,
                    to_sleeve_id="",
                    strategy_execution_id=str(uuid4()),
                    amount=_dec("1000"),
                    sleeve_name=symbol,
                ),
                _ctx(),
            )
        ).sleeve.id
        async with session_factory() as db:
            await persist_append(
                db,
                LedgerAppend(
                    tenant_id=UUID(ctx.tenant_id),
                    account_id=UUID(account_id),
                    sleeve_id=UUID(sleeve_id),
                    event_type=LedgerEventType.ORDER_FILLED,
                    data={
                        "sleeve_id": sleeve_id,
                        "symbol": symbol,
                        "side": "buy",
                        "qty": "5",
                        "price": "100",
                    },
                    event_id=UUID(bytes=hashlib.sha256(f"buy-{symbol}".encode()).digest()[:16]),
                    occurred_at=datetime.now(UTC),
                ),
            )

    await _account_holding("SPY")
    await _account_holding("TSLA")

    prices = _RecordingPrices()
    rows = await run_snapshot_pass(session_factory, prices)

    assert rows >= 2  # at least one snapshot row per account
    assert len(prices.calls) == 1  # ONE batched fetch, not one per account
    assert prices.calls[0] == ["SPY", "TSLA"]  # union, sorted


async def test_dual_delivery_fill_is_deduped(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A fill delivered twice (pub/sub + stream, or a retry) persists exactly one
    ledger event — the writer's ON CONFLICT dedup on the deterministic event_id."""
    import hashlib
    from datetime import UTC, datetime
    from uuid import UUID

    from sqlalchemy import func, select

    from llamatrade_db.models.ledger import LedgerEvent, LedgerEventType

    from src.ledger.ingestion import LedgerAppend
    from src.tasks.fill_ingestion import persist_append

    servicer = _ledger_servicer(session_factory)
    ctx = _tenant_ctx(str(uuid4()))
    account_id = await _bootstrap_account(servicer, ctx)
    await servicer.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=ctx, account_id=account_id, amount=_dec("1000")),
        _ctx(),
    )
    sleeve_id = (
        await servicer.allocate_capital(
            ledger_pb2.AllocateCapitalRequest(
                context=ctx,
                account_id=account_id,
                to_sleeve_id="",
                strategy_execution_id=str(uuid4()),
                amount=_dec("1000"),
                sleeve_name="S",
            ),
            _ctx(),
        )
    ).sleeve.id

    append = LedgerAppend(
        tenant_id=UUID(ctx.tenant_id),
        account_id=UUID(account_id),
        sleeve_id=UUID(sleeve_id),
        event_type=LedgerEventType.ORDER_FILLED,
        data={"sleeve_id": sleeve_id, "symbol": "SPY", "side": "buy", "qty": "5", "price": "100"},
        event_id=UUID(bytes=hashlib.sha256(b"dual-delivery").digest()[:16]),
        occurred_at=datetime.now(UTC),
    )
    for _ in range(2):  # the same fill arrives twice
        async with session_factory() as db:
            await persist_append(db, append)

    async with session_factory() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(LedgerEvent)
            .where(LedgerEvent.event_id == append.event_id)
        )
    assert count == 1  # deduped: one event despite two deliveries


async def test_advisory_lock_enforces_single_active_consumer(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The fill-consumer advisory lock admits exactly one active consumer; a
    second pod gets None (read-only standby) until the holder releases (failover)."""
    from src.tasks.fill_ingestion import acquire_fill_consumer_lock, release_fill_consumer_lock

    first = await acquire_fill_consumer_lock(session_factory)
    assert first is not None
    try:
        second = await acquire_fill_consumer_lock(session_factory)
        assert second is None  # single active consumer
    finally:
        await release_fill_consumer_lock(first)

    # After the holder releases (e.g. its pod died), a standby can take over.
    third = await acquire_fill_consumer_lock(session_factory)
    assert third is not None
    await release_fill_consumer_lock(third)


async def test_incremental_projection_matches_full_fold(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The incremental (checkpoint + delta) projection equals a full fold after
    each append — the cache stays consistent as events arrive (real DB)."""
    import hashlib
    from datetime import UTC, datetime
    from uuid import UUID

    from llamatrade_db.models.ledger import LedgerEventType

    from src.ledger.ingestion import LedgerAppend
    from src.ledger.projector import LedgerProjector
    from src.tasks.fill_ingestion import persist_append

    servicer = _ledger_servicer(session_factory)
    ctx = _tenant_ctx(str(uuid4()))
    account_id = await _bootstrap_account(servicer, ctx)
    tenant, account = UUID(ctx.tenant_id), UUID(account_id)

    async def _assert_incremental_equals_full() -> None:
        async with session_factory() as db:
            incremental = await LedgerProjector(db).project_account_incremental(tenant, account)
        async with session_factory() as db:
            full = await LedgerProjector(db).project_account(tenant, account)
        assert incremental == full

    await _assert_incremental_equals_full()  # fresh account
    await servicer.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=ctx, account_id=account_id, amount=_dec("1000")),
        _ctx(),
    )
    await _assert_incremental_equals_full()  # after deposit
    sleeve_id = (
        await servicer.allocate_capital(
            ledger_pb2.AllocateCapitalRequest(
                context=ctx,
                account_id=account_id,
                to_sleeve_id="",
                strategy_execution_id=str(uuid4()),
                amount=_dec("1000"),
                sleeve_name="S",
            ),
            _ctx(),
        )
    ).sleeve.id
    await _assert_incremental_equals_full()  # after allocate

    async with session_factory() as db:
        await persist_append(
            db,
            LedgerAppend(
                tenant_id=tenant,
                account_id=account,
                sleeve_id=UUID(sleeve_id),
                event_type=LedgerEventType.ORDER_FILLED,
                data={
                    "sleeve_id": sleeve_id,
                    "symbol": "SPY",
                    "side": "buy",
                    "qty": "5",
                    "price": "100",
                },
                event_id=UUID(bytes=hashlib.sha256(b"incr-fill").digest()[:16]),
                occurred_at=datetime.now(UTC),
            ),
        )
    await _assert_incremental_equals_full()  # delta folded onto the checkpoint


async def test_portfolio_read_reflects_deposit(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deposit shows up through the PortfolioServicer read path (no market data)."""

    class _StubMarketData:
        async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
            return {}

    monkeypatch.setattr("src.grpc.servicer.get_market_data_client", lambda: _StubMarketData())

    ledger = _ledger_servicer(session_factory)
    ctx = _tenant_ctx(str(uuid4()))
    account_id = await _bootstrap_account(ledger, ctx)
    await ledger.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=ctx, account_id=account_id, amount=_dec("100000")),
        _ctx(),
    )

    from src.grpc.servicer import PortfolioServicer

    pf = PortfolioServicer()
    pf._session_factory = session_factory
    resp = await pf.get_portfolio(portfolio_pb2.GetPortfolioRequest(context=ctx), _ctx())
    assert Decimal(resp.portfolio.total_value.value) == Decimal("100000")
    assert list(resp.positions) == []
