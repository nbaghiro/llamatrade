"""Reconciliation-pass tests — pure, no DB/broker.

Exercises ``run_reconciliation_pass`` with fakes: it must reconcile every
account, surface drift, and isolate per-account failures so one bad account
never aborts the pass.
"""

import asyncio
import logging
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db.models.ledger import Account

from src.ledger.projection import AccountProjection, PositionState
from src.ledger.reconciliation import Drift, DriftKind, cash_drift, ledger_cash
from src.ports import BrokerUnavailableError
from src.tasks.reconciliation import (
    AccountReconResult,
    _freeze_sustained_cash_drift,
    reconciliation_loop,
    run_reconciliation_pass,
    update_cash_drift_streaks,
    update_staleness,
)

TENANT = uuid4()


def _account() -> Account:
    acct = Account(tenant_id=TENANT, credentials_id=uuid4())
    acct.id = uuid4()
    return acct


class FakeBroker:
    """``ports.BrokerPositions`` returning a preset qty map (or raising)."""

    def __init__(
        self,
        positions: dict[str, Decimal],
        *,
        cash: Decimal = Decimal("0"),
        fail: bool = False,
        unavailable: bool = False,
        cash_fail: bool = False,
    ) -> None:
        self._positions = positions
        self._cash = cash
        self._fail = fail
        self._unavailable = unavailable
        self._cash_fail = cash_fail
        self.calls: list = []

    async def positions(self, tenant_id, account) -> dict[str, Decimal]:
        self.calls.append((tenant_id, account.id))
        if self._unavailable:
            raise BrokerUnavailableError("no active credentials")
        if self._fail:
            raise RuntimeError("broker unreachable")
        return self._positions

    async def cash(self, tenant_id, account) -> Decimal:
        if self._cash_fail:
            raise RuntimeError("cash endpoint down")
        return self._cash


class FakeProjector:
    """Returns a preset drift list per call, recording the broker positions/cash seen."""

    def __init__(self, drifts: list[Drift], cash_drift: Decimal | None = None) -> None:
        self._drifts = drifts
        self._cash_drift = cash_drift
        self.seen: list = []
        self.cash_seen: list = []

    async def reconcile_account(
        self, tenant_id, account_id, broker_positions, broker_cash=None
    ) -> tuple[list[Drift], Decimal | None]:
        self.seen.append((account_id, broker_positions))
        self.cash_seen.append(broker_cash)
        return self._drifts, self._cash_drift


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


async def test_pass_passes_broker_cash_to_projector() -> None:
    acct = _account()
    projector = FakeProjector([])
    broker = FakeBroker({}, cash=Decimal("500"))
    await run_reconciliation_pass(projector=projector, broker=broker, accounts=[acct])
    assert projector.cash_seen == [Decimal("500")]


def test_cash_drift_is_broker_minus_ledger() -> None:
    proj = AccountProjection()
    proj.sleeve("s1").cash = Decimal("1000")
    proj.sleeve("s2").cash = Decimal("200")
    proj.sleeve("s2").positions["AAPL"] = PositionState(qty=Decimal("1"))
    assert ledger_cash(proj) == Decimal("1200")
    assert cash_drift(proj, Decimal("1300")) == Decimal("100")
    assert cash_drift(proj, Decimal("1200")) == Decimal("0")


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

    async def cash(self, tenant_id, account) -> Decimal:
        await asyncio.sleep(1.0)
        return Decimal("0")


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


def _result(
    account_id: UUID, *, error: str | None = None, skipped: bool = False
) -> AccountReconResult:
    return AccountReconResult(account_id=account_id, drifts=[], error=error, skipped=skipped)


def test_staleness_success_resets_clock_and_reports_none_stale() -> None:
    account_id = uuid4()
    last_success: dict[UUID, float] = {account_id: 0.0}

    stale = update_staleness(
        [_result(account_id)], last_success, interval_seconds=300.0, now=10_000.0
    )

    assert stale == []
    assert last_success[account_id] == 10_000.0


def test_staleness_first_sighting_starts_clock() -> None:
    account_id = uuid4()
    last_success: dict[UUID, float] = {}

    stale = update_staleness(
        [_result(account_id, error="boom")], last_success, interval_seconds=300.0, now=50.0
    )

    assert stale == []  # the clock starts now; not yet stale
    assert last_success[account_id] == 50.0


def test_staleness_skip_and_error_leave_clock_running() -> None:
    skipped_id, errored_id = uuid4(), uuid4()
    last_success: dict[UUID, float] = {skipped_id: 100.0, errored_id: 200.0}

    update_staleness(
        [_result(skipped_id, skipped=True), _result(errored_id, error="boom")],
        last_success,
        interval_seconds=300.0,
        now=500.0,
    )

    assert last_success[skipped_id] == 100.0
    assert last_success[errored_id] == 200.0


def test_staleness_flags_account_beyond_three_intervals(
    caplog: pytest.LogCaptureFixture,
) -> None:
    account_id = uuid4()
    last_success: dict[UUID, float] = {account_id: 0.0}

    with caplog.at_level(logging.WARNING, logger="src.tasks.reconciliation"):
        stale = update_staleness(
            [_result(account_id, skipped=True)], last_success, interval_seconds=300.0, now=901.0
        )

    assert stale == [account_id]
    assert str(account_id) in caplog.text  # the account is named, not just counted


def test_staleness_within_three_intervals_not_flagged() -> None:
    account_id = uuid4()
    last_success: dict[UUID, float] = {account_id: 0.0}

    stale = update_staleness(
        [_result(account_id, skipped=True)], last_success, interval_seconds=300.0, now=899.0
    )

    assert stale == []


def test_staleness_prunes_vanished_accounts() -> None:
    gone_id, present_id = uuid4(), uuid4()
    last_success: dict[UUID, float] = {gone_id: 0.0, present_id: 0.0}

    stale = update_staleness(
        [_result(present_id)], last_success, interval_seconds=300.0, now=10_000.0
    )

    assert gone_id not in last_success  # deleted account no longer counts as stale
    assert stale == []


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


async def test_cash_read_failure_keeps_position_reconciliation() -> None:
    """A broker cash-read fault reconciles positions anyway; cash check is skipped."""
    acct = _account()
    projector = FakeProjector([])
    results = await run_reconciliation_pass(
        projector=projector,
        broker=FakeBroker({"AAPL": Decimal("10")}, cash_fail=True),
        accounts=[acct],
    )
    assert results[0].ok is True
    assert results[0].cash_drift is None
    assert projector.seen == [(acct.id, {"AAPL": Decimal("10")})]
    assert projector.cash_seen == [None]  # cash reconciliation skipped, not zeroed


# --- cash-drift streaks ---


def _cash_result(account_id: UUID, drift: Decimal | None) -> AccountReconResult:
    return AccountReconResult(account_id=account_id, drifts=[], cash_drift=drift)


def test_cash_streak_freezes_only_after_sustained_passes() -> None:
    account_id = uuid4()
    streaks: dict[UUID, int] = {}

    for _ in range(2):
        candidates = update_cash_drift_streaks(
            [_cash_result(account_id, Decimal("5"))],
            streaks,
            threshold=Decimal("1"),
            sustained_passes=3,
        )
        assert candidates == []
    candidates = update_cash_drift_streaks(
        [_cash_result(account_id, Decimal("5"))],
        streaks,
        threshold=Decimal("1"),
        sustained_passes=3,
    )
    assert candidates == [account_id]
    assert (
        streaks[account_id] == 0
    )  # reset: a still-persisting drift needs a human, not a re-freeze


def test_cash_streak_resets_when_drift_subsides() -> None:
    account_id = uuid4()
    streaks: dict[UUID, int] = {account_id: 2}

    candidates = update_cash_drift_streaks(
        [_cash_result(account_id, Decimal("0.50"))],
        streaks,
        threshold=Decimal("1"),
        sustained_passes=3,
    )

    assert candidates == []
    assert streaks[account_id] == 0


def test_cash_streak_at_threshold_does_not_count() -> None:
    """Drift must EXCEED the dollar threshold; exactly-at-threshold resets."""
    account_id = uuid4()
    streaks: dict[UUID, int] = {account_id: 2}

    update_cash_drift_streaks(
        [_cash_result(account_id, Decimal("1"))],
        streaks,
        threshold=Decimal("1"),
        sustained_passes=3,
    )

    assert streaks[account_id] == 0


def test_cash_streak_counts_drift_magnitude() -> None:
    """Negative drift (ledger above broker) counts the same as positive."""
    account_id = uuid4()
    streaks: dict[UUID, int] = {}

    update_cash_drift_streaks(
        [_cash_result(account_id, Decimal("-5"))],
        streaks,
        threshold=Decimal("1"),
        sustained_passes=3,
    )

    assert streaks[account_id] == 1


def test_unread_cash_leaves_streak_unchanged() -> None:
    """A skip/error pass (cash_drift None) neither triggers nor clears the streak."""
    account_id = uuid4()
    streaks: dict[UUID, int] = {account_id: 2}

    candidates = update_cash_drift_streaks(
        [_cash_result(account_id, None)],
        streaks,
        threshold=Decimal("1"),
        sustained_passes=3,
    )

    assert candidates == []
    assert streaks[account_id] == 2


def test_cash_streaks_prune_vanished_accounts() -> None:
    gone_id, present_id = uuid4(), uuid4()
    streaks: dict[UUID, int] = {gone_id: 2, present_id: 1}

    update_cash_drift_streaks(
        [_cash_result(present_id, Decimal("5"))],
        streaks,
        threshold=Decimal("1"),
        sustained_passes=3,
    )

    assert gone_id not in streaks
    assert streaks[present_id] == 2


# --- sustained-cash-drift freeze orchestration ---


class _FreezeRecorder:
    def __init__(self, *, fail_for: set[UUID] | None = None) -> None:
        self.calls: list[tuple[UUID, Decimal]] = []
        self._fail_for = fail_for or set()

    async def __call__(self, account: Account, cash_drift: Decimal) -> None:
        self.calls.append((account.id, cash_drift))
        if account.id in self._fail_for:
            raise RuntimeError("freeze transaction failed")


@pytest.fixture
def _single_pass_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make one drifting pass a freeze candidate (threshold $1, 1 sustained pass)."""
    import src.tasks.reconciliation as recon

    monkeypatch.setattr(recon, "CASH_DRIFT_FREEZE_DOLLARS", Decimal("1"))
    monkeypatch.setattr(recon, "CASH_DRIFT_FREEZE_PASSES", 1)


async def test_sustained_cash_drift_invokes_freeze(_single_pass_freeze: None) -> None:
    acct = _account()
    freeze = _FreezeRecorder()

    await _freeze_sustained_cash_drift([_cash_result(acct.id, Decimal("42"))], [acct], {}, freeze)

    assert freeze.calls == [(acct.id, Decimal("42"))]


async def test_freeze_below_threshold_is_not_invoked(_single_pass_freeze: None) -> None:
    acct = _account()
    freeze = _FreezeRecorder()

    await _freeze_sustained_cash_drift([_cash_result(acct.id, Decimal("0.50"))], [acct], {}, freeze)

    assert freeze.calls == []


async def test_freeze_fault_never_aborts_the_pass(
    _single_pass_freeze: None, caplog: pytest.LogCaptureFixture
) -> None:
    first, second = _account(), _account()
    freeze = _FreezeRecorder(fail_for={first.id})

    with caplog.at_level(logging.ERROR, logger="src.tasks.reconciliation"):
        await _freeze_sustained_cash_drift(
            [_cash_result(first.id, Decimal("10")), _cash_result(second.id, Decimal("20"))],
            [first, second],
            {},
            freeze,
        )

    # The first freeze blew up, was logged, and the second still ran.
    assert [account_id for account_id, _ in freeze.calls] == [first.id, second.id]
    assert "cash-drift freeze failed" in caplog.text


async def test_freeze_candidate_without_account_row_is_skipped(
    _single_pass_freeze: None,
) -> None:
    """A result for an account deleted mid-pass cannot be frozen — skip, don't crash."""
    freeze = _FreezeRecorder()

    await _freeze_sustained_cash_drift([_cash_result(uuid4(), Decimal("10"))], [], {}, freeze)

    assert freeze.calls == []


# --- election loss ---


def _poisoned_session_factory() -> async_sessionmaker[AsyncSession]:
    def factory() -> AsyncSession:
        raise AssertionError("session factory must not be touched after election loss")

    return cast(async_sessionmaker[AsyncSession], factory)


async def test_reconciliation_loop_exits_on_election_loss_before_pass() -> None:
    """Top-of-loop leadership loss returns immediately — no session, no sweep."""

    async def lost_leadership() -> bool:
        return False

    await asyncio.wait_for(
        reconciliation_loop(
            _poisoned_session_factory(),
            interval_seconds=60.0,
            stop_event=asyncio.Event(),
            is_leader=lost_leadership,
        ),
        timeout=2.0,
    )


async def test_reconciliation_loop_exits_on_stop_event() -> None:
    stop = asyncio.Event()
    stop.set()

    await asyncio.wait_for(
        reconciliation_loop(
            _poisoned_session_factory(),
            interval_seconds=60.0,
            stop_event=stop,
        ),
        timeout=2.0,
    )
