"""Reconciliation-pass tests — pure, no DB/broker.

Exercises ``run_reconciliation_pass`` with fakes: it must reconcile every
account, surface drift, and isolate per-account failures so one bad account
never aborts the pass.
"""

from decimal import Decimal
from uuid import uuid4

from llamatrade_db.models.ledger import Account

from src.ledger.reconciliation import Drift, DriftKind
from src.tasks.reconciliation import run_reconciliation_pass

TENANT = uuid4()


def _account() -> Account:
    acct = Account(tenant_id=TENANT, credentials_id=uuid4())
    acct.id = uuid4()
    return acct


class FakeBroker:
    """``ports.BrokerPositions`` returning a preset qty map (or raising)."""

    def __init__(self, positions: dict[str, Decimal], *, fail: bool = False) -> None:
        self._positions = positions
        self._fail = fail
        self.calls: list = []

    async def positions(self, tenant_id, account) -> dict[str, Decimal]:
        self.calls.append((tenant_id, account.id))
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


async def test_pass_empty_accounts_returns_empty() -> None:
    results = await run_reconciliation_pass(
        projector=FakeProjector([]), broker=FakeBroker({}), accounts=[]
    )
    assert results == []
