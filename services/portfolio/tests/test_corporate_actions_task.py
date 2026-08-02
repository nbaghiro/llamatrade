"""Corporate-action detection tests — pure, no DB/broker.

Covers the announcement -> planner routing, the held-symbol filter, and the
idempotency rules (a re-polled announcement proposes once; an applied action is
never proposed again).
"""

from __future__ import annotations

import ast
import asyncio
import logging
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from llamatrade_alpaca import CorporateActionType, CorporateAnnouncement
from llamatrade_db.models.ledger import Account, LedgerEventType

from src.ledger import corporate
from src.ledger.projection import AccountProjection, PositionState
from src.ports import BrokerUnavailableError
from src.services.corporate_action_service import _event_id
from src.tasks.corporate_actions import (
    CorporateActionProposal,
    detection_window,
    plan_proposal,
    proposal_id,
    run_detection_pass,
)

TENANT = uuid4()
SINCE, UNTIL = date(2024, 6, 1), date(2024, 6, 8)
SLEEVE_A = uuid4()
SLEEVE_B = uuid4()


def _account() -> Account:
    account = Account(tenant_id=TENANT, credentials_id=uuid4())
    account.id = uuid4()
    return account


def _projection(*holdings: tuple[UUID, str, str, str]) -> AccountProjection:
    """Projection with (sleeve, symbol, qty, cost_basis) holdings."""
    projection = AccountProjection()
    for sleeve_id, symbol, qty, cost_basis in holdings:
        projection.sleeve(str(sleeve_id)).positions[symbol] = PositionState(
            qty=Decimal(qty), cost_basis=Decimal(cost_basis)
        )
    return projection


def _announcement(
    *,
    ca_type: CorporateActionType,
    initiating_symbol: str,
    announcement_id: str = "ann-1",
    ca_sub_type: str = "",
    target_symbol: str = "",
    cash: str | None = None,
    old_rate: str | None = None,
    new_rate: str | None = None,
    corporate_action_id: str = "CA1",
) -> CorporateAnnouncement:
    return CorporateAnnouncement(
        id=announcement_id,
        corporate_action_id=corporate_action_id,
        ca_type=ca_type,
        ca_sub_type=ca_sub_type,
        initiating_symbol=initiating_symbol,
        target_symbol=target_symbol,
        cash=Decimal(cash) if cash is not None else None,
        old_rate=Decimal(old_rate) if old_rate is not None else None,
        new_rate=Decimal(new_rate) if new_rate is not None else None,
    )


def _plan(
    announcement: CorporateAnnouncement,
    projection: AccountProjection,
    account_id: UUID | None = None,
) -> CorporateActionProposal | None:
    return plan_proposal(
        announcement=announcement,
        tenant_id=TENANT,
        account_id=account_id or uuid4(),
        projection=projection,
    )


# Routing: one planner per announcement kind


def test_forward_split_routes_to_split_planner() -> None:
    projection = _projection((SLEEVE_A, "AAPL", "10", "1500"), (SLEEVE_B, "AAPL", "5", "800"))
    proposal = _plan(
        _announcement(
            ca_type=CorporateActionType.SPLIT,
            ca_sub_type="stock_split",
            initiating_symbol="AAPL",
            target_symbol="AAPL",
            old_rate="1",
            new_rate="4",
        ),
        projection,
    )

    assert proposal is not None
    assert proposal.kind == "split"
    assert proposal.symbol == "AAPL"
    assert proposal.ratio == Decimal("4")
    assert proposal.amount is None
    assert {e.sleeve_id for e in proposal.planned_events} == {SLEEVE_A, SLEEVE_B}
    assert all(e.event_type is LedgerEventType.SPLIT_APPLIED for e in proposal.planned_events)
    # qty_delta = qty x (ratio - 1)
    deltas = {e.sleeve_id: Decimal(e.data["qty_delta"]) for e in proposal.planned_events}
    assert deltas == {SLEEVE_A: Decimal("30"), SLEEVE_B: Decimal("15")}


def test_reverse_split_routes_with_fractional_ratio() -> None:
    proposal = _plan(
        _announcement(
            ca_type=CorporateActionType.SPLIT,
            ca_sub_type="reverse_split",
            initiating_symbol="XYZ",
            old_rate="10",
            new_rate="1",
        ),
        _projection((SLEEVE_A, "XYZ", "100", "500")),
    )

    assert proposal is not None
    assert proposal.kind == "split"
    assert proposal.ratio == Decimal("0.1")
    assert Decimal(proposal.planned_events[0].data["qty_delta"]) == Decimal("-90")


def test_cash_dividend_routes_to_dividend_planner() -> None:
    proposal = _plan(
        _announcement(
            ca_type=CorporateActionType.DIVIDEND,
            ca_sub_type="cash",
            initiating_symbol="AAPL",
            target_symbol="AAPL",
            cash="0.25",
        ),
        _projection((SLEEVE_A, "AAPL", "10", "1500"), (SLEEVE_B, "AAPL", "30", "4000")),
    )

    assert proposal is not None
    assert proposal.kind == "dividend"
    # rate x held shares = 0.25 x 40
    assert proposal.amount == Decimal("10.00")
    assert proposal.external_id == "CA1"
    assert all(e.event_type is LedgerEventType.DIVIDEND_RECEIVED for e in proposal.planned_events)
    paid = sum(Decimal(e.data["amount"]) for e in proposal.planned_events)
    assert paid == Decimal("10.00")  # cash conservation across sleeves


def test_symbol_change_routes_to_rename_planner() -> None:
    proposal = _plan(
        _announcement(
            ca_type=CorporateActionType.MERGER,
            ca_sub_type="merger_completion",
            initiating_symbol="FB",
            target_symbol="META",
            old_rate="1",
            new_rate="1",
        ),
        _projection((SLEEVE_A, "FB", "12", "3000")),
    )

    assert proposal is not None
    assert proposal.kind == "symbol_change"
    assert proposal.symbol == "FB"
    assert proposal.new_symbol == "META"
    event = proposal.planned_events[0]
    assert event.event_type is LedgerEventType.SYMBOL_CHANGED
    assert event.data["qty"] == "12"
    assert event.data["cost_basis"] == "3000"


def test_symbol_change_without_rates_still_routes() -> None:
    """Announcements that omit old/new rate are still a 1:1 rename."""
    proposal = _plan(
        _announcement(
            ca_type=CorporateActionType.MERGER,
            initiating_symbol="OLD",
            target_symbol="NEW",
        ),
        _projection((SLEEVE_A, "OLD", "3", "300")),
    )

    assert proposal is not None
    assert proposal.kind == "symbol_change"


def test_stock_dividend_without_cash_is_not_proposed() -> None:
    assert (
        _plan(
            _announcement(
                ca_type=CorporateActionType.DIVIDEND,
                ca_sub_type="stock",
                initiating_symbol="AAPL",
            ),
            _projection((SLEEVE_A, "AAPL", "10", "1500")),
        )
        is None
    )


def test_unmodelled_action_is_not_proposed(caplog: pytest.LogCaptureFixture) -> None:
    """A spinoff has no planner — it is counted and logged, never guessed at."""
    with caplog.at_level(logging.WARNING, logger="src.tasks.corporate_actions"):
        proposal = _plan(
            _announcement(
                ca_type=CorporateActionType.SPINOFF,
                ca_sub_type="spinoff",
                initiating_symbol="PARENT",
                target_symbol="CHILD",
                old_rate="1",
                new_rate="2",
            ),
            _projection((SLEEVE_A, "PARENT", "10", "1000")),
        )

    assert proposal is None
    assert "no ledger planner" in caplog.text


def test_split_with_unusable_rates_is_not_proposed() -> None:
    assert (
        _plan(
            _announcement(
                ca_type=CorporateActionType.SPLIT,
                initiating_symbol="AAPL",
                old_rate="0",
                new_rate="4",
            ),
            _projection((SLEEVE_A, "AAPL", "10", "1500")),
        )
        is None
    )


def test_no_op_split_ratio_is_not_proposed() -> None:
    assert (
        _plan(
            _announcement(
                ca_type=CorporateActionType.SPLIT,
                initiating_symbol="AAPL",
                target_symbol="AAPL",
                old_rate="2",
                new_rate="2",
            ),
            _projection((SLEEVE_A, "AAPL", "10", "1500")),
        )
        is None
    )


# Held-symbol filtering


def test_announcement_for_unheld_symbol_is_ignored() -> None:
    assert (
        _plan(
            _announcement(
                ca_type=CorporateActionType.SPLIT,
                initiating_symbol="TSLA",
                old_rate="1",
                new_rate="3",
            ),
            _projection((SLEEVE_A, "AAPL", "10", "1500")),
        )
        is None
    )


def test_closed_out_position_is_not_a_holder() -> None:
    """A zero-qty position is not a holding — nothing to fan the action across."""
    assert (
        _plan(
            _announcement(
                ca_type=CorporateActionType.DIVIDEND,
                initiating_symbol="AAPL",
                cash="0.25",
            ),
            _projection((SLEEVE_A, "AAPL", "0", "0")),
        )
        is None
    )


def test_short_position_is_not_paid_a_dividend() -> None:
    assert (
        _plan(
            _announcement(
                ca_type=CorporateActionType.DIVIDEND,
                initiating_symbol="AAPL",
                cash="0.25",
            ),
            _projection((SLEEVE_A, "AAPL", "-10", "-1500")),
        )
        is None
    )


# Deterministic identity


def test_proposal_id_is_deterministic_per_account_and_announcement() -> None:
    account_id, other = uuid4(), uuid4()
    assert proposal_id(account_id, "ann-1") == proposal_id(account_id, "ann-1")
    assert proposal_id(account_id, "ann-1") != proposal_id(account_id, "ann-2")
    assert proposal_id(account_id, "ann-1") != proposal_id(other, "ann-1")


def test_planned_event_ids_match_the_apply_path() -> None:
    """The feed and ApplyCorporateAction must derive the same ids, or an applied
    action would be proposed forever."""
    proposal = _plan(
        _announcement(
            ca_type=CorporateActionType.SPLIT,
            initiating_symbol="AAPL",
            old_rate="1",
            new_rate="2",
        ),
        _projection((SLEEVE_A, "AAPL", "10", "1500")),
    )

    assert proposal is not None
    assert proposal.event_ids == [_event_id(e.dedup_key) for e in proposal.planned_events]
    assert proposal.event_ids == [corporate.event_id(e.dedup_key) for e in proposal.planned_events]


def test_detection_window_ends_today() -> None:
    assert detection_window(date(2024, 6, 8), lookback_days=7) == (
        date(2024, 6, 1),
        date(2024, 6, 8),
    )
    assert detection_window(date(2024, 6, 8), lookback_days=0) == (
        date(2024, 6, 8),
        date(2024, 6, 8),
    )
    with pytest.raises(ValueError):
        detection_window(date(2024, 6, 8), lookback_days=-1)


# Pass behavior


class FakeProjector:
    """``ProjectingStore`` returning a preset projection per account."""

    def __init__(self, projection: AccountProjection) -> None:
        self._projection = projection
        self.calls: list[UUID] = []

    async def project_account(self, tenant_id: UUID, account_id: UUID) -> AccountProjection:
        self.calls.append(account_id)
        return self._projection


class FakeSource:
    """``AnnouncementSource`` returning a preset list (or raising)."""

    def __init__(
        self,
        announcements: list[CorporateAnnouncement],
        *,
        fail: bool = False,
        unavailable: bool = False,
        slow: bool = False,
    ) -> None:
        self._announcements = announcements
        self._fail = fail
        self._unavailable = unavailable
        self._slow = slow
        self.symbols_seen: list[list[str]] = []
        self.windows_seen: list[tuple[date, date]] = []

    async def announcements(
        self,
        tenant_id: UUID,
        account: Account,
        symbols: Iterable[str],
        *,
        since: date,
        until: date,
    ) -> list[CorporateAnnouncement]:
        self.symbols_seen.append(list(symbols))
        self.windows_seen.append((since, until))
        if self._unavailable:
            raise BrokerUnavailableError("no active credentials")
        if self._fail:
            raise RuntimeError("announcements unreachable")
        if self._slow:
            await asyncio.sleep(1.0)
        return self._announcements


def _split_announcement(announcement_id: str = "ann-1") -> CorporateAnnouncement:
    return _announcement(
        ca_type=CorporateActionType.SPLIT,
        ca_sub_type="stock_split",
        initiating_symbol="AAPL",
        target_symbol="AAPL",
        announcement_id=announcement_id,
        old_rate="1",
        new_rate="2",
    )


async def _pass(
    *,
    projector: FakeProjector,
    source: FakeSource,
    accounts: list[Account],
    already_applied: Any = None,
    seen: set[UUID] | None = None,
    per_account_timeout: float = 30.0,
) -> list[Any]:
    return await run_detection_pass(
        projector=projector,
        source=source,
        accounts=accounts,
        since=SINCE,
        until=UNTIL,
        already_applied=already_applied,
        seen=seen,
        per_account_timeout=per_account_timeout,
    )


async def test_pass_proposes_detected_action() -> None:
    account = _account()
    projector = FakeProjector(_projection((SLEEVE_A, "AAPL", "10", "1500")))
    source = FakeSource([_split_announcement()])

    results = await _pass(projector=projector, source=source, accounts=[account])

    assert len(results) == 1
    assert results[0].account_id == account.id
    assert [p.kind for p in results[0].proposals] == ["split"]
    assert results[0].error is None
    assert results[0].skipped is False


async def test_pass_queries_only_held_symbols() -> None:
    account = _account()
    projector = FakeProjector(
        _projection((SLEEVE_A, "AAPL", "10", "1500"), (SLEEVE_B, "MSFT", "4", "1200"))
    )
    source = FakeSource([])

    await _pass(projector=projector, source=source, accounts=[account])

    assert source.symbols_seen == [["AAPL", "MSFT"]]
    assert source.windows_seen == [(SINCE, UNTIL)]


async def test_pass_skips_broker_call_for_empty_account() -> None:
    account = _account()
    source = FakeSource([_split_announcement()])

    results = await _pass(
        projector=FakeProjector(AccountProjection()), source=source, accounts=[account]
    )

    assert source.symbols_seen == []  # nothing held, nothing to ask about
    assert results[0].proposals == []


async def test_repoll_proposes_once() -> None:
    """The same announcement seen on two passes yields exactly one proposal."""
    account = _account()
    projector = FakeProjector(_projection((SLEEVE_A, "AAPL", "10", "1500")))
    source = FakeSource([_split_announcement()])
    seen: set[UUID] = set()

    first = await _pass(projector=projector, source=source, accounts=[account], seen=seen)
    second = await _pass(projector=projector, source=source, accounts=[account], seen=seen)

    assert len(first[0].proposals) == 1
    assert second[0].proposals == []
    assert len(seen) == 1


async def test_distinct_announcements_each_propose() -> None:
    account = _account()
    projector = FakeProjector(_projection((SLEEVE_A, "AAPL", "10", "1500")))
    source = FakeSource([_split_announcement("ann-1"), _split_announcement("ann-2")])

    results = await _pass(projector=projector, source=source, accounts=[account])

    assert len(results[0].proposals) == 2


async def test_already_applied_action_is_not_proposed() -> None:
    """Once the operator applied it, the events exist in the log — stop proposing."""
    account = _account()
    projector = FakeProjector(_projection((SLEEVE_A, "AAPL", "10", "1500")))
    source = FakeSource([_split_announcement()])
    checked: list[tuple[UUID, list[UUID]]] = []

    async def applied(tenant_id: UUID, event_ids: Sequence[UUID]) -> bool:
        checked.append((tenant_id, list(event_ids)))
        return True

    results = await _pass(
        projector=projector, source=source, accounts=[account], already_applied=applied
    )

    assert results[0].proposals == []
    assert checked and checked[0][0] == TENANT
    assert len(checked[0][1]) == 1  # the one sleeve's planned event id


async def test_pending_action_survives_the_applied_check() -> None:
    account = _account()
    projector = FakeProjector(_projection((SLEEVE_A, "AAPL", "10", "1500")))

    async def not_applied(tenant_id: UUID, event_ids: Sequence[UUID]) -> bool:
        return False

    results = await _pass(
        projector=projector,
        source=FakeSource([_split_announcement()]),
        accounts=[account],
        already_applied=not_applied,
    )

    assert len(results[0].proposals) == 1


async def test_unreadable_broker_skips_account() -> None:
    account = _account()
    results = await _pass(
        projector=FakeProjector(_projection((SLEEVE_A, "AAPL", "10", "1500"))),
        source=FakeSource([], unavailable=True),
        accounts=[account],
    )

    assert results[0].skipped is True
    assert results[0].error is None
    assert results[0].proposals == []


async def test_pass_isolates_per_account_failure() -> None:
    good, bad = _account(), _account()
    results = await _pass(
        projector=FakeProjector(_projection((SLEEVE_A, "AAPL", "10", "1500"))),
        source=FakeSource([], fail=True),
        accounts=[good, bad],
    )

    assert [r.account_id for r in results] == [good.id, bad.id]
    assert all(r.error == "announcements unreachable" for r in results)


async def test_slow_source_times_out_and_is_isolated() -> None:
    account = _account()
    results = await _pass(
        projector=FakeProjector(_projection((SLEEVE_A, "AAPL", "10", "1500"))),
        source=FakeSource([], slow=True),
        accounts=[account],
        per_account_timeout=0.01,
    )

    assert results[0].error == "timeout"


async def test_pass_empty_accounts_returns_empty() -> None:
    results = await _pass(
        projector=FakeProjector(AccountProjection()), source=FakeSource([]), accounts=[]
    )
    assert results == []


async def test_proposal_log_carries_the_apply_arguments(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The proposal is only surfaced as a log line today, so it must carry
    everything an operator needs to call ApplyCorporateAction."""
    account = _account()
    projector = FakeProjector(_projection((SLEEVE_A, "AAPL", "10", "1500")))

    with caplog.at_level(logging.WARNING, logger="src.tasks.corporate_actions"):
        await _pass(
            projector=projector, source=FakeSource([_split_announcement()]), accounts=[account]
        )

    assert "corporate action PROPOSED" in caplog.text
    assert str(account.id) in caplog.text
    assert str(TENANT) in caplog.text
    assert "AAPL" in caplog.text
    assert "ratio=2" in caplog.text


# Leader election


def _writer_election_calls() -> list[ast.Call]:
    """Every call inside ``ledger_writer_loop``, the leader-only runtime."""
    source = Path(__file__).resolve().parents[1] / "src" / "tasks" / "writer_election.py"
    tree = ast.parse(source.read_text())
    loop = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "ledger_writer_loop"
    )
    return [node for node in ast.walk(loop) if isinstance(node, ast.Call)]


def test_detection_loop_runs_only_on_the_ledger_writer_pod() -> None:
    """The loop is started only inside the election runtime, like the other
    writer-gated loops — every replica running it would spam operators."""
    started = [
        call.func.id
        for call in _writer_election_calls()
        if isinstance(call.func, ast.Name) and call.func.id.endswith("_loop")
    ]
    assert started.count("corporate_actions_loop") == 1  # started exactly once
    assert "reconciliation_loop" in started  # the branch we mirrored

    main_source = Path(__file__).resolve().parents[1] / "src" / "main.py"
    main_tree = ast.parse(main_source.read_text())
    assert not [
        child
        for child in ast.walk(main_tree)
        if isinstance(child, ast.Name) and child.id == "corporate_actions_loop"
    ]  # main.py starts the election, never a sweep directly


def test_writer_gated_loops_all_take_the_leadership_probe() -> None:
    """Each sweep must be handed ``is_leader`` — a loop started without it would
    keep sweeping after the pod lost the lock, which is the failure the election
    exists to prevent."""
    gated = {"reconciliation_loop", "snapshot_loop", "corporate_actions_loop"}
    probed = {
        call.func.id
        for call in _writer_election_calls()
        if isinstance(call.func, ast.Name)
        and call.func.id in gated
        and any(kw.arg == "is_leader" for kw in call.keywords)
    }
    assert probed == gated


# Broker adapter


class _FakeTradingClient:
    """Stand-in for llamatrade_alpaca.TradingClient recording announcement calls."""

    def __init__(self, by_symbol: dict[str, list[CorporateAnnouncement]]) -> None:
        self._by_symbol = by_symbol
        self.symbols: list[str] = []
        self.closed = False

    async def get_corporate_announcements(
        self, *, since: date, until: date, symbol: str, date_type: object
    ) -> list[CorporateAnnouncement]:
        self.symbols.append(symbol)
        return self._by_symbol.get(symbol, [])

    async def close(self) -> None:
        self.closed = True


async def test_announcement_adapter_queries_each_held_symbol_and_dedupes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.clients.alpaca import AlpacaCorporateAnnouncements

    shared = _split_announcement("ann-shared")
    client = _FakeTradingClient({"AAPL": [shared], "MSFT": [shared, _split_announcement("ann-2")]})

    async def fake_client_for(db: object, tenant_id: UUID, account: Account) -> object:
        return client

    monkeypatch.setattr("src.clients.alpaca.trading_client_for", fake_client_for)
    adapter = AlpacaCorporateAnnouncements(cast(Any, object()))

    found = await adapter.announcements(
        TENANT, _account(), ["msft", "AAPL", "AAPL"], since=SINCE, until=UNTIL
    )

    assert client.symbols == ["AAPL", "MSFT"]  # deduped + normalized
    assert sorted(a.id for a in found) == ["ann-2", "ann-shared"]
    assert client.closed is True


async def test_announcement_adapter_without_credentials_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.clients.alpaca import AlpacaCorporateAnnouncements

    async def no_client(db: object, tenant_id: UUID, account: Account) -> object | None:
        return None

    monkeypatch.setattr("src.clients.alpaca.trading_client_for", no_client)
    adapter = AlpacaCorporateAnnouncements(cast(Any, object()))

    with pytest.raises(BrokerUnavailableError):
        await adapter.announcements(TENANT, _account(), ["AAPL"], since=SINCE, until=UNTIL)


async def test_announcement_adapter_skips_broker_call_without_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.clients.alpaca import AlpacaCorporateAnnouncements

    async def unexpected(db: object, tenant_id: UUID, account: Account) -> object:
        raise AssertionError("must not resolve credentials with nothing held")

    monkeypatch.setattr("src.clients.alpaca.trading_client_for", unexpected)
    adapter = AlpacaCorporateAnnouncements(cast(Any, object()))

    assert await adapter.announcements(TENANT, _account(), [], since=SINCE, until=UNTIL) == []
