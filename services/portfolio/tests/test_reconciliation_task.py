"""Reconciliation-pass tests — pure, no DB/broker.

Exercises ``run_reconciliation_pass`` with fakes: it must reconcile every
account, surface drift, and isolate per-account failures so one bad account
never aborts the pass.
"""

import asyncio
from decimal import Decimal
from uuid import uuid4

from llamatrade_db.models.ledger import Account

from src.ledger.reconciliation import Drift, DriftKind
from src.ports import BrokerUnavailableError
from src.tasks.reconciliation import run_reconciliation_pass

TENANT = uuid4()


def _account() -> Account:
    acct = Account(tenant_id=TENANT, credentials_id=uuid4())
    acct.id = uuid4()
    return acct


class FakeBroker:
    """``ports.BrokerPositions`` returning a preset qty map (or raising)."""

    def __init__(
        self, positions: dict[str, Decimal], *, fail: bool = False, unavailable: bool = False
    ) -> None:
        self._positions = positions
        self._fail = fail
        self._unavailable = unavailable
        self.calls: list = []

    async def positions(self, tenant_id, account) -> dict[str, Decimal]:
        self.calls.append((tenant_id, account.id))
        if self._unavailable:
            raise BrokerUnavailableError("no active credentials")
        if self._fail:
            raise RuntimeError("broker unreachable")
        return self._positions


class FakeProjector:
    """Returns a preset drift list per call, recording the broker positions seen."""

    def __init__(self, drifts: list[Drift]) -> None:
        self._drifts = drifts
        self.seen: list = []

    async def reconcile_account(self, tenant_id, account_id, broker_positions) -> list[Drift]:
        self.seen.append((account_id, broker_positions))
        return self._drifts


async def test_pass_clean_account_is_ok() -> None:
    acct = _account()
    results = await run_reconciliation_pass(
        projector=FakeProjector([]),
        broker=FakeBroker({"AAPL": Decimal("10")}),
        accounts=[acct],
    )
    assert len(results) == 1
    assert results[0].account_id == acct.id
    assert results[0].ok is True
    assert results[0].drifts == []


async def test_pass_surfaces_drift() -> None:
    acct = _account()
    drift = Drift(
        symbol="AAPL",
        ledger_qty=Decimal("10"),
        broker_qty=Decimal("12"),
        kind=DriftKind.QTY_MISMATCH,
    )
    results = await run_reconciliation_pass(
        projector=FakeProjector([drift]),
        broker=FakeBroker({"AAPL": Decimal("12")}),
        accounts=[acct],
    )
    assert results[0].ok is False
    assert results[0].drifts == [drift]
    assert results[0].error is None


async def test_pass_passes_broker_positions_to_projector() -> None:
    acct = _account()
    projector = FakeProjector([])
    broker = FakeBroker({"MSFT": Decimal("5")})
    await run_reconciliation_pass(projector=projector, broker=broker, accounts=[acct])
    assert projector.seen == [(acct.id, {"MSFT": Decimal("5")})]
    assert broker.calls == [(TENANT, acct.id)]


async def test_pass_isolates_per_account_failure() -> None:
    good, bad = _account(), _account()
    # Broker fails for all, but each account is independently captured.
    results = await run_reconciliation_pass(
        projector=FakeProjector([]),
        broker=FakeBroker({}, fail=True),
        accounts=[good, bad],
    )
    assert len(results) == 2
    assert all(r.error == "broker unreachable" for r in results)
    assert all(r.ok is False for r in results)
    assert {r.account_id for r in results} == {good.id, bad.id}


async def test_unreadable_broker_skips_account_without_freezing() -> None:
    """A BrokerUnavailableError read must SKIP the account — never reconcile against an
    empty map (which would flag every holding MISSING_AT_BROKER and freeze it)."""
    acct = _account()
    projector = FakeProjector(
        [Drift("AAPL", Decimal("10"), Decimal("0"), DriftKind.MISSING_AT_BROKER)]
    )
    handler = _DriftRecorder()

    results = await run_reconciliation_pass(
        projector=projector,
        broker=FakeBroker({}, unavailable=True),
        accounts=[acct],
        on_material_drift=handler,
    )

    assert results[0].skipped is True
    assert results[0].error is None
    assert results[0].ok is False
    assert projector.seen == []  # never reconciled against an empty broker map
    assert handler.calls == []  # so nothing was frozen


class _SlowBroker:
    """Broker whose read exceeds the per-account timeout."""

    async def positions(self, tenant_id, account) -> dict[str, Decimal]:
        await asyncio.sleep(1.0)
        return {}


async def test_slow_broker_times_out_and_is_isolated() -> None:
    """A broker read past the per-account timeout fails just that account; the
    pass returns a timeout error rather than hanging."""
    acct = _account()
    results = await run_reconciliation_pass(
        projector=FakeProjector([]),
        broker=_SlowBroker(),
        accounts=[acct],
        per_account_timeout=0.01,
    )
    assert results[0].error == "timeout"
    assert results[0].ok is False


async def test_pass_processes_all_accounts_concurrently() -> None:
    """Bounded fan-out still returns one result per account, in account order."""
    accounts = [_account() for _ in range(5)]
    results = await run_reconciliation_pass(
        projector=FakeProjector([]),
        broker=FakeBroker({"AAPL": Decimal("1")}),
        accounts=accounts,
        concurrency=3,
    )
    assert [r.account_id for r in results] == [a.id for a in accounts]
    assert all(r.ok for r in results)


async def test_pass_empty_accounts_returns_empty() -> None:
    results = await run_reconciliation_pass(
        projector=FakeProjector([]), broker=FakeBroker({}), accounts=[]
    )
    assert results == []


class _DriftRecorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list = []
        self._fail = fail

    async def __call__(self, account, drift) -> None:
        self.calls.append((account.id, drift))
        if self._fail:
            raise RuntimeError("alert pathway down")


async def test_material_drift_forwarded_to_handler() -> None:
    acct = _account()
    material = Drift(
        symbol="SPY",
        ledger_qty=Decimal("60"),
        broker_qty=Decimal("61"),
        kind=DriftKind.QTY_MISMATCH,
    )
    dust = Drift(
        symbol="QQQ",
        ledger_qty=Decimal("10"),
        broker_qty=Decimal("10.00001"),
        kind=DriftKind.DUST,
    )
    handler = _DriftRecorder()

    await run_reconciliation_pass(
        projector=FakeProjector([material, dust]),
        broker=FakeBroker({"SPY": Decimal("61")}),
        accounts=[acct],
        on_material_drift=handler,
    )

    # Only the material drift reaches the alert handler; dust is log-only.
    assert [d.symbol for _, d in handler.calls] == ["SPY"]
    assert handler.calls[0][0] == acct.id


async def test_handler_failure_never_aborts_pass() -> None:
    acct_one, acct_two = _account(), _account()
    drift = Drift(
        symbol="SPY",
        ledger_qty=Decimal("60"),
        broker_qty=Decimal("0"),
        kind=DriftKind.MISSING_AT_BROKER,
    )

    results = await run_reconciliation_pass(
        projector=FakeProjector([drift]),
        broker=FakeBroker({}),
        accounts=[acct_one, acct_two],
        on_material_drift=_DriftRecorder(fail=True),
    )

    # Both accounts still reconciled despite the handler blowing up.
    assert [r.account_id for r in results] == [acct_one.id, acct_two.id]
    assert all(r.error is None for r in results)
