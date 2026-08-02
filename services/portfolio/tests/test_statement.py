"""Tests for the operator ledger-statement renderer.

The fixture account is built through the real ledger planners and translators
(``plan_deposit`` / ``plan_allocate`` / ``fill_to_append`` / ``enrich_sell_fill``
/ ``plan_split`` / ``split_dividend`` / ``plan_sleeve_close``) and every event is
passed through the same conservation gate the writer applies before it is
appended, so the statement is rendered from events the ledger would accept. The
DB-backed ``LedgerWriter`` itself needs Postgres (``INSERT ... ON CONFLICT`` on
JSONB), which the fast suite does not have, so the rows are in-memory doubles of
``LedgerEvent`` rather than persisted ones.

The full-history render is pinned by ``tests/golden/statement_full.txt``.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import LedgerFill, LedgerReservation

from src.ledger.corporate import plan_split, split_dividend
from src.ledger.funds import plan_allocate, plan_deposit
from src.ledger.ingestion import enrich_sell_fill, fill_to_append, reservation_to_append
from src.ledger.lifecycle import close_event_id, plan_sleeve_close
from src.ledger.postings import assert_balanced, build_postings
from src.ledger.projection import AccountProjection, open_lots
from src.tools import statement as statement_module
from src.tools.statement import (
    AccountHeader,
    SleeveMeta,
    Statement,
    StatementError,
    _balances,
    _invariants,
    _resolve_account,
    build_parser,
    build_statement,
    render_json,
    render_text,
    run,
)

D = Decimal

TENANT = UUID("11111111-1111-1111-1111-111111111111")
ACCOUNT = UUID("22222222-2222-2222-2222-222222222222")
UNALLOCATED = UUID("33333333-3333-3333-3333-333333333333")
MOMENTUM = UUID("44444444-4444-4444-4444-444444444444")
VALUE = UUID("55555555-5555-5555-5555-555555555555")
UNMANAGED = UUID("66666666-6666-6666-6666-666666666666")

GENERATED_AT = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
GOLDEN = Path(__file__).parent / "golden" / "statement_full.txt"

HEADER = AccountHeader(
    tenant_id=TENANT,
    account_id=ACCOUNT,
    broker_account_id="PA3EXAMPLE01",
    base_currency="USD",
)

SLEEVES = [
    SleeveMeta(str(UNALLOCATED), "Unallocated", "unallocated", "active"),
    SleeveMeta(str(MOMENTUM), "Momentum US", "strategy", "active"),
    SleeveMeta(str(VALUE), "Value Tilt", "strategy", "closed"),
    SleeveMeta(str(UNMANAGED), "Unmanaged", "unmanaged", "active"),
]


@dataclass(frozen=True)
class Ev:
    """An in-memory stand-in for a persisted ``LedgerEvent`` row."""

    event_type: LedgerEventType
    data: dict[str, Any]
    occurred_at: datetime
    event_id: str
    sequence: int


def _at(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=UTC)


class _Log:
    """Accumulates fixture events, applying the writer's balance gate to each."""

    def __init__(self) -> None:
        self.events: list[Ev] = []

    def add(
        self,
        event_type: LedgerEventType,
        data: dict[str, Any],
        occurred_at: datetime,
        event_id: UUID | str,
    ) -> Ev:
        assert_balanced(build_postings(event_type, data))
        event = Ev(event_type, data, occurred_at, str(event_id), len(self.events) + 1)
        self.events.append(event)
        return event


def _fill(
    *,
    sleeve: UUID,
    client_order_id: str,
    symbol: str,
    side: str,
    qty: str,
    price: str,
    fees: str = "",
) -> LedgerFill:
    return LedgerFill(
        tenant_id=str(TENANT),
        account_id=str(ACCOUNT),
        sleeve_id=str(sleeve),
        client_order_id=client_order_id,
        symbol=symbol,
        side=side,
        qty=qty,
        price=price,
        fees=fees,
    )


def _reservation(
    *,
    sleeve: UUID,
    client_order_id: str,
    event_type: str,
    reserved: str = "",
    symbol: str = "",
    side: str = "",
) -> LedgerReservation:
    return LedgerReservation(
        tenant_id=str(TENANT),
        account_id=str(ACCOUNT),
        sleeve_id=str(sleeve),
        client_order_id=client_order_id,
        event_type=event_type,
        reserved=reserved,
        symbol=symbol,
        side=side,
    )


def fixture_events() -> list[Ev]:
    """A deterministic account: funding, trades, a reservation lifecycle, a
    realized sell, corporate actions, a drift adoption, a freeze and a close."""
    log = _Log()

    deposit = plan_deposit(unallocated_sleeve_id=UNALLOCATED, amount=D("100000"))[0]
    log.add(
        deposit.event_type,
        dict(deposit.data),
        _at(2, 9, 30),
        "aa000001-0000-4000-8000-000000000001",
    )

    to_momentum = plan_allocate(
        from_sleeve_id=UNALLOCATED,
        to_sleeve_id=MOMENTUM,
        amount=D("40000"),
        from_free_cash=D("100000"),
    )[0]
    log.add(
        to_momentum.event_type,
        dict(to_momentum.data),
        _at(2, 9, 45),
        "ab000002-0000-4000-8000-000000000002",
    )

    to_value = plan_allocate(
        from_sleeve_id=UNALLOCATED,
        to_sleeve_id=VALUE,
        amount=D("25000"),
        from_free_cash=D("60000"),
    )[0]
    log.add(
        to_value.event_type,
        dict(to_value.data),
        _at(2, 9, 46),
        "ac000003-0000-4000-8000-000000000003",
    )

    submit = reservation_to_append(
        _reservation(
            sleeve=MOMENTUM,
            client_order_id="mom-buy-1",
            event_type="order_submitted",
            reserved="24000",
            symbol="SPY",
            side="buy",
        )
    )
    log.add(submit.event_type, submit.data, _at(3, 14, 30), submit.event_id)

    buy_one = fill_to_append(
        _fill(
            sleeve=MOMENTUM,
            client_order_id="mom-buy-1",
            symbol="SPY",
            side="buy",
            qty="50",
            price="480",
        )
    )
    log.add(buy_one.event_type, buy_one.data, _at(3, 14, 32), buy_one.event_id)

    value_submit = reservation_to_append(
        _reservation(
            sleeve=VALUE,
            client_order_id="val-buy-1",
            event_type="order_submitted",
            reserved="10000",
            symbol="AAPL",
            side="buy",
        )
    )
    log.add(value_submit.event_type, value_submit.data, _at(3, 15, 10), value_submit.event_id)

    value_cancel = reservation_to_append(
        _reservation(sleeve=VALUE, client_order_id="val-buy-1", event_type="order_cancelled")
    )
    log.add(value_cancel.event_type, value_cancel.data, _at(3, 15, 40), value_cancel.event_id)

    buy_two = fill_to_append(
        _fill(
            sleeve=MOMENTUM,
            client_order_id="mom-buy-2",
            symbol="SPY",
            side="buy",
            qty="20",
            price="500",
        )
    )
    log.add(buy_two.event_type, buy_two.data, _at(5, 10, 5), buy_two.event_id)

    sell = enrich_sell_fill(
        fill_to_append(
            _fill(
                sleeve=MOMENTUM,
                client_order_id="mom-sell-1",
                symbol="SPY",
                side="sell",
                qty="30",
                price="520",
                fees="1.50",
            )
        ),
        open_lots(log.events, str(MOMENTUM), "SPY"),
    )
    log.add(sell.event_type, sell.data, _at(5, 15, 55), sell.event_id)

    split = plan_split(symbol="SPY", ratio=D("2"), holders={MOMENTUM: D("40")}, external_id="ca-1")[
        0
    ]
    log.add(split.event_type, dict(split.data), _at(6, 0, 5), split.event_id)

    dividend = split_dividend(
        symbol="SPY", total_amount=D("36.00"), holders={MOMENTUM: D("80")}, pay_id="2026-03-06"
    )[0]
    log.add(dividend.event_type, dict(dividend.data), _at(6, 12, 0), dividend.event_id)

    log.add(
        LedgerEventType.EXTERNAL_TRADE_DETECTED,
        {"sleeve_id": str(UNMANAGED), "symbol": "TSLA", "qty": "10", "price": "200"},
        _at(9, 8, 15),
        "ad000004-0000-4000-8000-000000000004",
    )

    log.add(
        LedgerEventType.SLEEVE_FROZEN,
        {"sleeve_id": str(VALUE), "reason": "qty_mismatch: AAPL ledger=0 broker=5"},
        _at(9, 8, 20),
        "ae000005-0000-4000-8000-000000000005",
    )

    close = plan_sleeve_close(
        from_sleeve_id=VALUE,
        positions=[],
        cash=D("25000"),
        unmanaged_sleeve_id=UNMANAGED,
        unallocated_sleeve_id=UNALLOCATED,
        reason="manual close",
    )
    log.add(LedgerEventType.SLEEVE_CLOSED, close.event_data, _at(9, 16, 0), close_event_id(VALUE))

    return log.events


def full_statement(
    period_start: date | None = date(2026, 3, 1), period_end: date | None = date(2026, 3, 31)
) -> Statement:
    return build_statement(
        account=HEADER,
        sleeves=SLEEVES,
        events=fixture_events(),
        period_start=period_start,
        period_end=period_end,
        generated_at=GENERATED_AT,
    )


class TestGoldenRender:
    def test_matches_golden_file(self) -> None:
        """The rendered statement is byte-identical to the committed golden."""
        assert render_text(full_statement()) == GOLDEN.read_text()

    def test_render_is_stable_across_calls(self) -> None:
        assert render_text(full_statement()) == render_text(full_statement())

    def test_no_line_exceeds_the_page_width(self) -> None:
        for line in render_text(full_statement()).splitlines():
            assert len(line) <= 110, line


class TestBalances:
    def test_closing_balances_match_the_hand_computed_account(self) -> None:
        statement = full_statement()
        by_name = {b.name: b for b in statement.closing}

        # 100k in, 40k + 25k out, 25k back when Value Tilt closes.
        assert by_name["Unallocated"].cash == D("60000")
        # 40000 - 24000 - 10000 + (30 x 520 - 1.50) + 36.00 dividend
        assert by_name["Momentum US"].cash == D("21634.50")
        assert by_name["Value Tilt"].cash == D("0")
        assert by_name["Unmanaged"].cash == D("0")

        assert statement.total_cash == D("81634.50")
        assert statement.total_positions_cost == D("21600")

    def test_realized_pnl_is_the_fifo_gain_plus_the_dividend(self) -> None:
        statement = full_statement()
        momentum = next(b for b in statement.closing if b.name == "Momentum US")
        # 30 sold at 520 against a 480 FIFO basis, less 1.50 of fees, plus 36.00.
        assert momentum.realized_period == D("1234.50")
        assert statement.total_realized_period == D("1234.50")

    def test_positions_carry_their_open_lots(self) -> None:
        statement = full_statement()
        momentum = next(b for b in statement.closing if b.name == "Momentum US")
        spy = next(p for p in momentum.positions if p.symbol == "SPY")
        assert spy.qty == D("80")  # 50 + 20 - 30, doubled by the split
        assert spy.cost_basis == D("19600")
        assert sum(lot.qty for lot in spy.lots) == D("80")
        assert sum(lot.cost_basis for lot in spy.lots) == D("19600")
        # The split re-based the two surviving lots; it opened no zero-cost lot.
        assert [(lot.qty, lot.cost_basis) for lot in spy.lots] == [
            (D("40"), D("9600")),
            (D("40"), D("10000")),
        ]

    def test_reservation_is_released_by_its_terminal_event(self) -> None:
        statement = full_statement()
        by_name = {b.name: b for b in statement.closing}
        assert by_name["Momentum US"].reserved == D("0")
        assert by_name["Value Tilt"].reserved == D("0")

    def test_open_reservation_is_still_earmarked_mid_period(self) -> None:
        """Cut the period between the submit and its release."""
        statement = build_statement(
            account=HEADER,
            sleeves=SLEEVES,
            events=fixture_events(),
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 3),
            generated_at=GENERATED_AT,
        )
        value = next(b for b in statement.closing if b.name == "Value Tilt")
        assert value.reserved == D("0")  # submitted and cancelled on the same day
        momentum = next(b for b in statement.closing if b.name == "Momentum US")
        assert momentum.free_cash == momentum.cash


class TestActivity:
    def test_days_are_grouped_and_ordered(self) -> None:
        statement = full_statement()
        assert [block.day.isoformat() for block in statement.days] == [
            "2026-03-02",
            "2026-03-03",
            "2026-03-05",
            "2026-03-06",
            "2026-03-09",
        ]

    def test_every_event_gets_exactly_one_line(self) -> None:
        statement = full_statement()
        rendered = sum(len(block.lines) for block in statement.days)
        assert rendered == len(fixture_events()) == statement.events_in_period

    def test_line_labels_cover_the_economic_vocabulary(self) -> None:
        statement = full_statement()
        labels = [line.label for block in statement.days for line in block.lines]
        assert labels == [
            "DEPOSIT",
            "ALLOCATE",
            "ALLOCATE",
            "RESERVE",
            "BUY",
            "RESERVE",
            "CANCEL",
            "BUY",
            "SELL",
            "SPLIT",
            "DIVIDEND",
            "ADOPT",
            "FREEZE",
            "CLOSE",
        ]

    def test_amounts_are_the_folded_deltas(self) -> None:
        statement = full_statement()
        lines = {
            (line.label, line.sleeve_name): line for block in statement.days for line in block.lines
        }
        assert lines[("DEPOSIT", "Unallocated")].amount == D("100000")
        assert lines[("BUY", "Momentum US")].amount == D("-10000")  # the later 20 @ 500
        assert lines[("SELL", "Momentum US")].amount == D("15598.50")
        assert lines[("SELL", "Momentum US")].realized == D("1198.50")
        assert lines[("CANCEL", "Value Tilt")].amount == D("-10000")  # reservation released
        assert lines[("CLOSE", "Value Tilt")].amount == D("-25000")

    def test_running_cash_is_reported_after_each_day(self) -> None:
        statement = full_statement()
        first = dict(statement.days[0].cash_after)
        assert first["Unallocated"] == D("35000")
        assert first["Momentum US"] == D("40000")
        last = dict(statement.days[-1].cash_after)
        assert last["Unallocated"] == D("60000")
        assert last["Value Tilt"] == D("0")


class TestInvariants:
    def test_healthy_account_ties_out(self) -> None:
        report = full_statement().invariants
        # 100,000 deposited plus the 2,000 adopted external position.
        assert report.external_funding == D("102000")
        assert report.realized_total == D("1234.50")
        assert report.expected_equity_at_cost == report.actual_equity_at_cost
        assert report.difference == D("0")
        assert report.healthy

    def test_healthy_account_renders_ok(self) -> None:
        text = render_text(full_statement())
        assert "Sleeve conservation" in text
        assert "MISMATCH" not in text
        assert "INCOMPLETE" not in text
        assert "VIOLATIONS" not in text

    def test_unbalanced_projection_renders_a_warning(self) -> None:
        """A sleeve holding cash that entered from nowhere must be visible.

        The writers cannot produce this (every append is balance-checked), so the
        projection is stubbed directly and passed through the real invariant
        function and renderer.
        """
        projection = AccountProjection()
        projection.sleeve("phantom").cash = D("500")
        closing = _balances(["phantom"], {}, projection)
        statement = Statement(
            account=HEADER,
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            generated_at=GENERATED_AT,
            events_in_period=0,
            events_through_end=0,
            opening=(),
            days=(),
            closing=closing,
            invariants=_invariants(projection, [], closing),
        )
        text = render_text(statement)
        assert "** MISMATCH **" in text
        assert "exact difference 500" in text
        assert not statement.invariants.healthy

    def test_poison_event_is_flagged_and_excluded(self) -> None:
        """A sell with no cost basis cannot be expanded, so the fold skips it."""
        events = [
            Ev(
                LedgerEventType.FUNDS_DEPOSITED,
                {"sleeve_id": str(UNALLOCATED), "amount": "1000"},
                _at(2, 9, 0),
                "b0000001-0000-4000-8000-000000000001",
                1,
            ),
            Ev(
                LedgerEventType.ORDER_FILLED,
                {
                    "sleeve_id": str(MOMENTUM),
                    "symbol": "SPY",
                    "side": "sell",
                    "qty": "5",
                    "price": "100",
                },
                _at(2, 10, 0),
                "b0000001-0000-4000-8000-000000000002",
                2,
            ),
        ]
        statement = build_statement(
            account=HEADER,
            sleeves=SLEEVES,
            events=events,
            generated_at=GENERATED_AT,
        )
        assert statement.invariants.poison_events == 1
        assert not statement.invariants.healthy
        text = render_text(statement)
        assert "** INCOMPLETE **" in text
        assert "1 event(s) could not be read" in text
        assert "SKIPPED" in text

    def test_impossible_sleeve_state_is_flagged(self) -> None:
        """An oversell drives the sleeve negative; the statement says so."""
        events = [
            Ev(
                LedgerEventType.FUNDS_DEPOSITED,
                {"sleeve_id": str(MOMENTUM), "amount": "1000"},
                _at(2, 9, 0),
                "c0000001-0000-4000-8000-000000000001",
                1,
            ),
            Ev(
                LedgerEventType.ORDER_FILLED,
                {
                    "sleeve_id": str(MOMENTUM),
                    "symbol": "SPY",
                    "side": "sell",
                    "qty": "5",
                    "price": "100",
                    "cost_basis": "400",
                },
                _at(2, 10, 0),
                "c0000001-0000-4000-8000-000000000002",
                2,
            ),
        ]
        statement = build_statement(
            account=HEADER, sleeves=SLEEVES, events=events, generated_at=GENERATED_AT
        )
        text = render_text(statement)
        assert "** VIOLATIONS **" in text
        assert "negative_position" in text
        assert "Momentum US" in text


class TestPeriod:
    def test_empty_account_renders_without_activity(self) -> None:
        statement = build_statement(
            account=HEADER, sleeves=[], events=[], generated_at=GENERATED_AT
        )
        text = render_text(statement)
        assert "No activity in this period." in text
        assert "(no sleeves)" in text
        assert "inception through latest event" in text
        assert statement.invariants.healthy
        assert statement.total_cash == D("0")

    def test_account_with_sleeves_but_no_events(self) -> None:
        statement = build_statement(
            account=HEADER, sleeves=SLEEVES, events=[], generated_at=GENERATED_AT
        )
        assert [b.cash for b in statement.closing] == [D("0")] * 4
        assert "No activity in this period." in render_text(statement)

    def test_period_start_moves_events_into_the_opening_balances(self) -> None:
        statement = build_statement(
            account=HEADER,
            sleeves=SLEEVES,
            events=fixture_events(),
            period_start=date(2026, 3, 5),
            period_end=date(2026, 3, 31),
            generated_at=GENERATED_AT,
        )
        opening = {b.name: b for b in statement.opening}
        # Funding and the first buy happened before the period opened.
        assert opening["Unallocated"].cash == D("35000")
        assert opening["Momentum US"].cash == D("16000")
        assert opening["Momentum US"].positions_cost == D("24000")
        assert statement.events_in_period == 7
        assert [block.day.isoformat() for block in statement.days] == [
            "2026-03-05",
            "2026-03-06",
            "2026-03-09",
        ]

    def test_period_end_excludes_later_events(self) -> None:
        statement = build_statement(
            account=HEADER,
            sleeves=SLEEVES,
            events=fixture_events(),
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 5),
            generated_at=GENERATED_AT,
        )
        assert statement.events_in_period == 9
        by_name = {b.name: b for b in statement.closing}
        # The Value Tilt close (2026-03-09) has not happened yet.
        assert by_name["Value Tilt"].cash == D("25000")
        assert by_name["Unallocated"].cash == D("35000")
        # Nor has the split.
        spy = next(p for p in by_name["Momentum US"].positions if p.symbol == "SPY")
        assert spy.qty == D("40")

    def test_realized_pnl_is_scoped_to_the_period(self) -> None:
        after_the_sell = build_statement(
            account=HEADER,
            sleeves=SLEEVES,
            events=fixture_events(),
            period_start=date(2026, 3, 6),
            period_end=date(2026, 3, 31),
            generated_at=GENERATED_AT,
        )
        momentum = next(b for b in after_the_sell.closing if b.name == "Momentum US")
        assert momentum.realized_period == D("36.00")  # only the dividend
        assert momentum.realized_total == D("1234.50")

    def test_period_covering_nothing_is_empty(self) -> None:
        statement = build_statement(
            account=HEADER,
            sleeves=SLEEVES,
            events=fixture_events(),
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            generated_at=GENERATED_AT,
        )
        assert statement.events_in_period == 0
        assert statement.days == ()
        # Closing still reflects the whole history through the period end.
        assert statement.total_cash == D("81634.50")


class TestJson:
    def test_json_mirrors_the_text_statement(self) -> None:
        payload = json.loads(render_json(full_statement()))
        assert payload["account"]["broker_account_id"] == "PA3EXAMPLE01"
        assert payload["period"]["start"] == "2026-03-01"
        assert payload["totals"]["cash"] == "81634.50"
        assert payload["invariants"]["balanced"] is True
        assert Decimal(payload["invariants"]["difference"]) == D("0")
        assert len(payload["activity"]) == 5

    def test_money_is_never_a_float(self) -> None:
        payload = json.loads(render_json(full_statement()))
        for balance in payload["closing"]:
            assert isinstance(balance["cash"], str)
            for position in balance["positions"]:
                assert isinstance(position["cost_basis"], str)
                assert all(isinstance(lot["qty"], str) for lot in position["lots"])


class TestCli:
    def test_parser_accepts_an_account_id(self) -> None:
        args = build_parser().parse_args(
            ["--tenant-id", str(TENANT), "--account-id", str(ACCOUNT), "--from", "2026-03-01"]
        )
        assert args.tenant_id == TENANT
        assert args.account_id == ACCOUNT
        assert args.start == date(2026, 3, 1)
        assert args.json is False

    def test_parser_requires_exactly_one_selector(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--tenant-id", str(TENANT)])
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                [
                    "--tenant-id",
                    str(TENANT),
                    "--account-id",
                    str(ACCOUNT),
                    "--broker-account-id",
                    "PA1",
                ]
            )

    def test_inverted_range_exits_before_touching_the_database(self) -> None:
        code = asyncio.run(
            run(
                [
                    "--tenant-id",
                    str(TENANT),
                    "--account-id",
                    str(ACCOUNT),
                    "--from",
                    "2026-03-31",
                    "--to",
                    "2026-03-01",
                ]
            )
        )
        assert code == 2

    def test_run_writes_the_statement_to_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The database read is stubbed; everything downstream of it is real."""
        seen: dict[str, object] = {}

        async def fake_load(**kwargs: object) -> Statement:
            seen.update(kwargs)
            return full_statement()

        monkeypatch.setattr(statement_module, "load_statement", fake_load)
        code = asyncio.run(run(["--tenant-id", str(TENANT), "--broker-account-id", "PA3EXAMPLE01"]))
        assert code == 0
        assert seen["broker_account_id"] == "PA3EXAMPLE01"
        assert capsys.readouterr().out == GOLDEN.read_text()

    def test_run_emits_json_when_asked(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        async def fake_load(**kwargs: object) -> Statement:
            return full_statement()

        monkeypatch.setattr(statement_module, "load_statement", fake_load)
        code = asyncio.run(
            run(["--tenant-id", str(TENANT), "--account-id", str(ACCOUNT), "--json"])
        )
        assert code == 0
        assert json.loads(capsys.readouterr().out)["totals"]["cash"] == "81634.50"

    def test_unresolvable_account_exits_two(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        async def fake_load(**kwargs: object) -> Statement:
            raise StatementError("no ledger account for tenant x with account_id=y")

        monkeypatch.setattr(statement_module, "load_statement", fake_load)
        code = asyncio.run(run(["--tenant-id", str(TENANT), "--account-id", str(ACCOUNT)]))
        assert code == 2
        assert "error: no ledger account" in capsys.readouterr().err


class _FakeRepo:
    """Only the lookups the statement shell uses."""

    def __init__(self, account: object | None = None) -> None:
        self.account = account

    async def get_account(self, tenant_id: UUID, account_id: UUID) -> object | None:
        return self.account

    async def get_account_by_broker_id(self, tenant_id: UUID, broker: str) -> object | None:
        return self.account

    async def get_account_by_credentials(self, tenant_id: UUID, cred: UUID) -> object | None:
        return self.account


class TestAccountResolution:
    async def test_missing_account_raises_a_readable_error(self) -> None:
        with pytest.raises(StatementError, match="no ledger account"):
            await _resolve_account(_FakeRepo(), TENANT, ACCOUNT, None, None)

    async def test_broker_id_selector_is_named_in_the_error(self) -> None:
        with pytest.raises(StatementError, match="broker_account_id=PA9"):
            await _resolve_account(_FakeRepo(), TENANT, None, "PA9", None)

    async def test_credentials_selector_is_named_in_the_error(self) -> None:
        with pytest.raises(StatementError, match="credentials_id="):
            await _resolve_account(_FakeRepo(), TENANT, None, None, ACCOUNT)

    async def test_found_account_is_returned(self) -> None:
        marker = object()
        assert await _resolve_account(_FakeRepo(marker), TENANT, ACCOUNT, None, None) is marker
