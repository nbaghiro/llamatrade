"""Operator tool: render one account's ledger history as a readable statement.

The ledger is an append-only, double-entry event log; sleeve cash, positions,
lots and realized P&L are folds over it. Explaining a balance to a user means
rendering that fold, so this walks one account's events and prints: the account
header, opening balances per sleeve, day-by-day activity with running cash,
closing positions with their FIFO lots, account totals, and the conservation
check that ties the sleeve sums back to the account's external funding.

Read-only. All accounting comes from the ledger kernel (``build_postings`` /
``fold_into`` / ``open_lots``); nothing here recomputes a balance. Money is
carried and printed as :class:`~decimal.Decimal`.

Run from the portfolio service directory (needs ``DATABASE_URL``)::

    python -m src.tools.statement --tenant-id UUID --account-id UUID
    python -m src.tools.statement --tenant-id UUID --broker-account-id PA123 \
        --from 2026-03-01 --to 2026-03-31
    python -m src.tools.statement --tenant-id UUID --credentials-id UUID --json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import system_session
from llamatrade_db.models.ledger import Account, LedgerEventType, Sleeve

from src.ledger.invariants import InvariantViolation, check_sleeve_invariants
from src.ledger.postings import Bucket, assert_balanced, build_postings
from src.ledger.projection import (
    AccountProjection,
    LedgerEventLike,
    ReservationState,
    SleeveProjection,
    fold_into,
    open_lots,
)
from src.ledger.writer import LedgerWriter
from src.repositories import SqlSleeveRepository

ZERO = Decimal("0")
CENTS = Decimal("0.01")
_PRICE_STEP = Decimal("0.00000001")
# (cash, reserved, realized) for a sleeve the projection has not seen yet.
_NIL = (ZERO, ZERO, ZERO)

WIDTH = 110
_RULE = "=" * WIDTH
_THIN = "-" * WIDTH
_LABEL = 20
_SUMMARY_LABEL = 52
_DASH = "-"

# Errors the kernel treats as poison while folding; mirrored so the statement's own posting walk skips exactly the events the fold skipped.
_POISON = (KeyError, TypeError, ValueError, ArithmeticError)


class StatementError(Exception):
    """The requested account could not be resolved."""


class StatementEvent(LedgerEventLike, Protocol):
    """A ledger event as the statement needs it (ORM row or test double)."""

    @property
    def occurred_at(self) -> datetime: ...

    @property
    def event_id(self) -> UUID | str: ...


# Rendered model


@dataclass(frozen=True)
class AccountHeader:
    """Identity of the account the statement covers."""

    tenant_id: UUID
    account_id: UUID
    broker_account_id: str | None
    base_currency: str


@dataclass(frozen=True)
class SleeveMeta:
    """Naming/lifecycle metadata for one sleeve (from the sleeve rows)."""

    sleeve_id: str
    name: str
    type: str
    status: str


@dataclass(frozen=True)
class LotLine:
    """One open FIFO lot of a holding."""

    qty: Decimal
    cost_basis: Decimal


@dataclass(frozen=True)
class PositionLine:
    """A sleeve's holding in one symbol, with the lots behind it."""

    symbol: str
    qty: Decimal
    cost_basis: Decimal
    lots: tuple[LotLine, ...]

    @property
    def avg_cost(self) -> Decimal:
        return self.cost_basis / self.qty if self.qty else ZERO


@dataclass(frozen=True)
class SleeveBalance:
    """A sleeve's balances at one point in the statement."""

    sleeve_id: str
    name: str
    type: str
    status: str
    cash: Decimal
    reserved: Decimal
    positions_cost: Decimal
    realized_period: Decimal
    realized_total: Decimal
    positions: tuple[PositionLine, ...]
    violations: tuple[InvariantViolation, ...]

    @property
    def free_cash(self) -> Decimal:
        return self.cash - self.reserved


@dataclass(frozen=True)
class ActivityLine:
    """One ledger event rendered as a statement line."""

    occurred_at: datetime
    event_id: str
    event_type: str
    sleeve_id: str | None
    sleeve_name: str
    label: str
    detail: str
    amount: Decimal | None
    realized: Decimal | None
    skipped: bool


@dataclass(frozen=True)
class DayBlock:
    """One calendar day of activity plus the cash it leaves behind."""

    day: date
    lines: tuple[ActivityLine, ...]
    cash_after: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True)
class InvariantReport:
    """The conservation check that ties sleeve sums to the account."""

    external_funding: Decimal
    realized_total: Decimal
    expected_equity_at_cost: Decimal
    actual_equity_at_cost: Decimal
    poison_events: int
    sleeve_violations: tuple[tuple[str, InvariantViolation], ...]

    @property
    def difference(self) -> Decimal:
        return self.actual_equity_at_cost - self.expected_equity_at_cost

    @property
    def balanced(self) -> bool:
        return self.difference == ZERO

    @property
    def healthy(self) -> bool:
        return self.balanced and self.poison_events == 0 and not self.sleeve_violations


@dataclass(frozen=True)
class Statement:
    """Everything the renderers need; no further accounting happens downstream."""

    account: AccountHeader
    period_start: date | None
    period_end: date | None
    generated_at: datetime
    events_in_period: int
    events_through_end: int
    opening: tuple[SleeveBalance, ...]
    days: tuple[DayBlock, ...]
    closing: tuple[SleeveBalance, ...]
    invariants: InvariantReport

    @property
    def total_cash(self) -> Decimal:
        return sum((s.cash for s in self.closing), ZERO)

    @property
    def total_reserved(self) -> Decimal:
        return sum((s.reserved for s in self.closing), ZERO)

    @property
    def total_positions_cost(self) -> Decimal:
        return sum((s.positions_cost for s in self.closing), ZERO)

    @property
    def total_realized_period(self) -> Decimal:
        return sum((s.realized_period for s in self.closing), ZERO)


# Formatting helpers


def _exponent(value: Decimal) -> int:
    """Decimal exponent as an int (special values report 0)."""
    exponent = value.as_tuple().exponent
    return exponent if isinstance(exponent, int) else 0


def _money(value: Decimal) -> str:
    """Two-decimal money, grouped, rounded on the Decimal (never via float)."""
    return f"{value.quantize(CENTS, rounding=ROUND_HALF_UP):,f}"


def _qty(value: Decimal) -> str:
    """Share quantity without trailing zeros or exponent notation."""
    normalized = value.normalize()
    if _exponent(normalized) > 0:
        normalized = normalized.quantize(Decimal(1))
    return f"{normalized:,f}"


def _price(value: Decimal) -> str:
    """Price with at least 2 and at most 8 decimals."""
    trimmed = value
    if _exponent(trimmed) < -8:
        trimmed = trimmed.quantize(_PRICE_STEP, rounding=ROUND_HALF_UP)
    trimmed = trimmed.normalize()
    if _exponent(trimmed) > -2:
        trimmed = trimmed.quantize(CENTS)
    return f"{trimmed:,f}"


def _opt_money(value: Decimal | None) -> str:
    return _DASH if value is None or value == ZERO else _money(value)


def _fit(text: str, width: int) -> str:
    """Truncate to ``width`` with an ellipsis marker so columns never wrap."""
    return text if len(text) <= width else text[: width - 3] + "..."


def _short(value: str, size: int = 8) -> str:
    return value[:size]


# Event reading helpers


def _event_type(raw: str | LedgerEventType) -> LedgerEventType:
    return raw if isinstance(raw, LedgerEventType) else LedgerEventType(raw)


def _when(event: StatementEvent) -> datetime:
    """Business time of an event, normalized to UTC (naive is read as UTC)."""
    occurred = event.occurred_at
    return occurred.replace(tzinfo=UTC) if occurred.tzinfo is None else occurred.astimezone(UTC)


def _text(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    return None if value is None else str(value)


def _num(data: dict[str, object], key: str) -> Decimal | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None


def _external_funding(events: Iterable[StatementEvent]) -> Decimal:
    """Net cash the account took in from outside (deposits, adopted trades).

    The EXTERNAL bucket is the account boundary, so negating its postings gives
    money that entered the tracked book. Events the fold would skip are skipped
    here too, so both sides of the conservation check see the same stream.
    """
    total = ZERO
    for event in events:
        try:
            postings = build_postings(_event_type(event.event_type), event.data)
            if postings:
                assert_balanced(postings)
        except _POISON:
            continue
        total += sum((-p.amount for p in postings if p.bucket is Bucket.EXTERNAL), ZERO)
    return total


# Statement construction


def _display_order(
    sleeves: Sequence[SleeveMeta], projections: Sequence[AccountProjection]
) -> list[str]:
    """Sleeve ids in metadata order, then any id seen only in the event log."""
    known = [meta.sleeve_id for meta in sleeves]
    seen = set(known)
    extra = sorted({sid for proj in projections for sid in proj.sleeves if sid not in seen})
    return known + extra


def _balances(
    order: Sequence[str],
    metas: dict[str, SleeveMeta],
    projection: AccountProjection,
    *,
    baseline: AccountProjection | None = None,
    events: Sequence[StatementEvent] = (),
    with_lots: bool = False,
) -> tuple[SleeveBalance, ...]:
    """Render each sleeve's balances; ``baseline`` supplies period-start realized."""
    out: list[SleeveBalance] = []
    for sleeve_id in order:
        sleeve = projection.sleeves.get(sleeve_id) or SleeveProjection()
        prior = ZERO
        if baseline is not None:
            before = baseline.sleeves.get(sleeve_id)
            prior = before.realized_pnl if before is not None else ZERO
        meta = metas.get(sleeve_id)
        positions = _positions(sleeve, sleeve_id, events) if with_lots else ()
        out.append(
            SleeveBalance(
                sleeve_id=sleeve_id,
                name=meta.name if meta is not None else _short(sleeve_id),
                type=meta.type if meta is not None else "unknown",
                status=meta.status if meta is not None else "unknown",
                cash=sleeve.cash,
                reserved=sleeve.reserved,
                positions_cost=sum((p.cost_basis for p in sleeve.positions.values()), ZERO),
                realized_period=sleeve.realized_pnl - prior,
                realized_total=sleeve.realized_pnl,
                positions=positions,
                violations=tuple(check_sleeve_invariants(sleeve)),
            )
        )
    return tuple(out)


def _positions(
    sleeve: SleeveProjection, sleeve_id: str, events: Sequence[StatementEvent]
) -> tuple[PositionLine, ...]:
    """Open holdings of one sleeve with their FIFO lots (from the same log)."""
    lines: list[PositionLine] = []
    for symbol in sorted(sleeve.positions):
        state = sleeve.positions[symbol]
        if state.qty == ZERO and state.cost_basis == ZERO:
            continue
        lots = open_lots(events, sleeve_id, symbol)
        lines.append(
            PositionLine(
                symbol=symbol,
                qty=state.qty,
                cost_basis=state.cost_basis,
                lots=tuple(LotLine(qty=lot.qty, cost_basis=lot.cost_basis) for lot in lots),
            )
        )
    return tuple(lines)


def _primary_sleeve(data: dict[str, object], changed: Sequence[str]) -> str | None:
    """The sleeve a line is attributed to: the event's own, else the destination."""
    for key in ("sleeve_id", "to_sleeve_id", "from_sleeve_id"):
        value = _text(data, key)
        if value is not None:
            return value
    return changed[0] if changed else None


def _describe(
    event_type: LedgerEventType, data: dict[str, object], names: dict[str, str]
) -> tuple[str, str]:
    """A short label and a one-line detail for an event."""
    symbol = _text(data, "symbol") or ""
    match event_type:
        case LedgerEventType.ORDER_FILLED:
            side = (_text(data, "side") or "").lower()
            qty = _num(data, "qty") or ZERO
            price = _num(data, "price") or ZERO
            fees = _num(data, "fees") or ZERO
            detail = f"{_qty(qty)} {symbol} @ {_price(price)}"
            if fees != ZERO:
                detail += f" fees {_money(fees)}"
            return ("SELL" if side == "sell" else "BUY", detail)

        case LedgerEventType.ORDER_SUBMITTED:
            side = (_text(data, "side") or "").lower()
            label = "RESERVE" if "reserved" in data else "SUBMIT"
            return (label, f"{side} {symbol} {_order_ref(data)}".strip())

        case LedgerEventType.ORDER_CANCELLED:
            return ("CANCEL", _order_ref(data))

        case LedgerEventType.ORDER_REJECTED:
            return ("REJECT", _order_ref(data))

        case LedgerEventType.ORDER_INTENDED:
            return ("INTENT", f"{symbol} {_order_ref(data)}".strip())

        case LedgerEventType.ORDER_ACCEPTED:
            return ("ACCEPT", _order_ref(data))

        case LedgerEventType.FUNDS_DEPOSITED:
            return ("DEPOSIT", "external cash in")

        case LedgerEventType.FUNDS_WITHDRAWN:
            return ("WITHDRAW", "external cash out")

        case LedgerEventType.CAPITAL_ALLOCATED:
            return ("ALLOCATE", f"from {_name(names, _text(data, 'from_sleeve_id'))}")

        case LedgerEventType.CAPITAL_TRANSFERRED:
            return ("TRANSFER", f"from {_name(names, _text(data, 'from_sleeve_id'))}")

        case LedgerEventType.DIVIDEND_RECEIVED:
            return ("DIVIDEND", symbol or "cash dividend")

        case LedgerEventType.INTEREST_ACCRUED:
            return ("INTEREST", "credit interest")

        case LedgerEventType.FEE_CHARGED:
            return ("FEE", _text(data, "reason") or symbol or "broker fee")

        case LedgerEventType.SPLIT_APPLIED:
            delta = _num(data, "qty_delta") or ZERO
            sign = "+" if delta >= ZERO else ""
            return ("SPLIT", f"{symbol} {sign}{_qty(delta)} shares")

        case LedgerEventType.SYMBOL_CHANGED:
            old = _text(data, "old_symbol") or ""
            new = _text(data, "new_symbol") or ""
            return ("RENAME", f"{old} -> {new} qty {_qty(_num(data, 'qty') or ZERO)}")

        case LedgerEventType.EXTERNAL_TRADE_DETECTED:
            qty = _num(data, "qty") or ZERO
            price = _num(data, "price") or ZERO
            return ("ADOPT", f"{_qty(qty)} {symbol} @ {_price(price)} (drift)")

        case LedgerEventType.DRIFT_CORRECTED:
            return ("DRIFT", _text(data, "reason") or symbol)

        case LedgerEventType.RECONCILIATION_ADJUSTED:
            return ("RECONCILE", _text(data, "reason") or symbol)

        case LedgerEventType.SLEEVE_OPENED:
            return ("OPEN", _text(data, "name") or "sleeve opened")

        case LedgerEventType.SLEEVE_CLOSED:
            positions = data.get("positions")
            count = len(positions) if isinstance(positions, list) else 0
            to_cash = _name(names, _text(data, "to_cash_sleeve_id"))
            if count == 0:
                return ("CLOSE", f"cash -> {to_cash}")
            to_pos = _name(names, _text(data, "to_position_sleeve_id"))
            return ("CLOSE", f"{count} position(s) -> {to_pos}, cash -> {to_cash}")

        case LedgerEventType.SLEEVE_FROZEN:
            return ("FREEZE", _text(data, "reason") or "frozen for review")

        case LedgerEventType.SLEEVE_RESUMED:
            return ("RESUME", _text(data, "reason") or "resumed")

        case _:
            return (event_type.value.upper()[:10], symbol)


def _order_ref(data: dict[str, object]) -> str:
    """The broker order the event belongs to, short enough for the detail column."""
    coid = _text(data, "client_order_id")
    return f"order {_fit(coid, 20)}" if coid else "order -"


def _name(names: dict[str, str], sleeve_id: str | None) -> str:
    if sleeve_id is None:
        return "-"
    return names.get(sleeve_id, _short(sleeve_id))


def _snapshot(projection: AccountProjection) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    """Per-sleeve (cash, reserved, realized) used to diff one folded event."""
    return {sid: (s.cash, s.reserved, s.realized_pnl) for sid, s in projection.sleeves.items()}


def build_statement(
    *,
    account: AccountHeader,
    sleeves: Sequence[SleeveMeta],
    events: Sequence[StatementEvent],
    period_start: date | None = None,
    period_end: date | None = None,
    generated_at: datetime,
) -> Statement:
    """Fold an account's events into a statement over ``[period_start, period_end]``.

    Events are walked in business-time order (ledger order breaks ties), which is
    how a statement reads; opening balances fold everything before the period and
    the closing state folds through its end, so events after it are excluded.
    Each period event is folded one at a time and the projection diffed, so the
    per-line cash, reservation and realized amounts come from the kernel rather
    than from a second interpretation of the payload.
    """
    indexed = sorted(enumerate(events), key=lambda pair: (_when(pair[1]), pair[0]))
    prior: list[StatementEvent] = []
    within: list[StatementEvent] = []
    for _, event in indexed:
        day = _when(event).date()
        if period_start is not None and day < period_start:
            prior.append(event)
        elif period_end is None or day <= period_end:
            within.append(event)
    through_end = prior + within

    metas = {meta.sleeve_id: meta for meta in sleeves}
    names = {meta.sleeve_id: meta.name for meta in sleeves}

    projection = AccountProjection()
    reservations = ReservationState()
    fold_into(projection, reservations, prior)
    opening_state = copy.deepcopy(projection)

    days = _walk_activity(projection, reservations, within, metas, names, sleeves)

    order = _display_order(sleeves, [opening_state, projection])
    opening = _balances(order, metas, opening_state)
    closing = _balances(
        order, metas, projection, baseline=opening_state, events=through_end, with_lots=True
    )

    return Statement(
        account=account,
        period_start=period_start,
        period_end=period_end,
        generated_at=generated_at,
        events_in_period=len(within),
        events_through_end=len(through_end),
        opening=opening,
        days=days,
        closing=closing,
        invariants=_invariants(projection, through_end, closing),
    )


def _walk_activity(
    projection: AccountProjection,
    reservations: ReservationState,
    events: Sequence[StatementEvent],
    metas: dict[str, SleeveMeta],
    names: dict[str, str],
    sleeves: Sequence[SleeveMeta],
) -> tuple[DayBlock, ...]:
    """Fold the period one event at a time, emitting a line per event per day."""
    blocks: list[DayBlock] = []
    lines: list[ActivityLine] = []
    current: date | None = None

    def close_day(day: date) -> None:
        order = _display_order(sleeves, [projection])
        cash_after = tuple(
            (_name(names, sid), (projection.sleeves.get(sid) or SleeveProjection()).cash)
            for sid in order
        )
        blocks.append(DayBlock(day=day, lines=tuple(lines), cash_after=cash_after))
        lines.clear()

    for event in events:
        occurred = _when(event)
        day = occurred.date()
        if current is not None and day != current:
            close_day(current)
        current = day

        before = _snapshot(projection)
        poison_before = projection.poison_events
        fold_into(projection, reservations, [event])
        after = _snapshot(projection)
        skipped = projection.poison_events > poison_before

        raw_type = event.event_type
        try:
            event_type: LedgerEventType | None = _event_type(raw_type)
        except ValueError:
            event_type = None
        data = event.data
        changed = sorted(sid for sid in after if after[sid] != before.get(sid, _NIL))
        sleeve_id = _primary_sleeve(data, changed)
        cash_before, reserved_before, realized_before = before.get(sleeve_id or "", _NIL)
        cash_after, reserved_after, realized_after = after.get(sleeve_id or "", _NIL)
        cash_delta = cash_after - cash_before
        reserved_delta = reserved_after - reserved_before
        realized_delta = realized_after - realized_before

        if skipped or event_type is None:
            label, detail = ("SKIPPED", "unreadable event, excluded from balances")
        else:
            label, detail = _describe(event_type, data, names)

        amount: Decimal | None = None
        if cash_delta != ZERO:
            amount = cash_delta
        elif reserved_delta != ZERO:
            amount = reserved_delta

        lines.append(
            ActivityLine(
                occurred_at=occurred,
                event_id=str(event.event_id),
                event_type=event_type.value if event_type is not None else str(raw_type),
                sleeve_id=sleeve_id,
                sleeve_name=_name(names, sleeve_id),
                label=label,
                detail=detail,
                amount=amount,
                realized=realized_delta or None,
                skipped=skipped,
            )
        )

    if current is not None:
        close_day(current)
    return tuple(blocks)


def _invariants(
    projection: AccountProjection,
    events: Sequence[StatementEvent],
    closing: Sequence[SleeveBalance],
) -> InvariantReport:
    """Tie the sleeve sums back to the account's external funding.

    Every event's postings sum to zero, so across the whole log
    ``Σ cash + Σ position cost == net external funding + Σ realized P&L``. A
    nonzero difference means the sleeve balances no longer reconcile with what
    entered the account, which is the failure an operator has to see.
    """
    realized = sum((s.realized_total for s in closing), ZERO)
    funding = _external_funding(events)
    actual = sum((s.cash for s in closing), ZERO) + sum((s.positions_cost for s in closing), ZERO)
    violations = tuple(
        (balance.name, violation) for balance in closing for violation in balance.violations
    )
    return InvariantReport(
        external_funding=funding,
        realized_total=realized,
        expected_equity_at_cost=funding + realized,
        actual_equity_at_cost=actual,
        poison_events=projection.poison_events,
        sleeve_violations=violations,
    )


# Text rendering


def _row(name: str, kind: str, status: str, cash: str, reserved: str, positions: str) -> str:
    return (
        f"{_fit(name, 24):<24} {_fit(kind, 12):<12} {_fit(status, 8):<8} "
        f"{cash:>16} {reserved:>14} {positions:>18}"
    )


def _balance_table(title: str, balances: Sequence[SleeveBalance]) -> list[str]:
    lines = [_THIN, title, _THIN]
    if not balances:
        lines.append("(no sleeves)")
        return lines
    lines.append(_row("Sleeve", "Type", "Status", "Cash", "Reserved", "Positions@cost"))
    for balance in balances:
        lines.append(
            _row(
                balance.name,
                balance.type,
                balance.status,
                _money(balance.cash),
                _money(balance.reserved),
                _money(balance.positions_cost),
            )
        )
    lines.append(
        _row(
            "TOTAL",
            "",
            "",
            _money(sum((b.cash for b in balances), ZERO)),
            _money(sum((b.reserved for b in balances), ZERO)),
            _money(sum((b.positions_cost for b in balances), ZERO)),
        )
    )
    return lines


def _render_header(statement: Statement) -> list[str]:
    account = statement.account
    start = statement.period_start.isoformat() if statement.period_start else "inception"
    end = statement.period_end.isoformat() if statement.period_end else "latest event"
    return [
        _RULE,
        "LEDGER STATEMENT",
        _RULE,
        f"{'Account':<{_LABEL}}{account.account_id}",
        f"{'Tenant':<{_LABEL}}{account.tenant_id}",
        f"{'Broker account':<{_LABEL}}{account.broker_account_id or _DASH}",
        f"{'Base currency':<{_LABEL}}{account.base_currency}",
        f"{'Period':<{_LABEL}}{start} through {end} (UTC)",
        f"{'Events':<{_LABEL}}{statement.events_in_period} in period, "
        f"{statement.events_through_end} through period end",
        f"{'Generated':<{_LABEL}}{statement.generated_at.isoformat()}",
        "",
    ]


def _activity_row(
    time: str, sleeve: str, label: str, detail: str, amount: str, realized: str, event: str
) -> str:
    return (
        f"  {time:<8} {_fit(sleeve, 18):<18} {_fit(label, 10):<10} {_fit(detail, 32):<32} "
        f"{amount:>14} {realized:>12} {event:<8}"
    ).rstrip()


def _render_activity(statement: Statement) -> list[str]:
    lines = [_THIN, "ACTIVITY", _THIN]
    if not statement.days:
        lines.extend(["No activity in this period.", ""])
        return lines
    for block in statement.days:
        lines.append("")
        lines.append(block.day.isoformat())
        lines.append(
            _activity_row("Time", "Sleeve", "Event", "Detail", "Amount", "Realized", "Event id")
        )
        for line in block.lines:
            lines.append(
                _activity_row(
                    line.occurred_at.strftime("%H:%M:%S"),
                    line.sleeve_name,
                    line.label,
                    line.detail,
                    _opt_money(line.amount),
                    _opt_money(line.realized),
                    _short(line.event_id),
                )
            )
        lines.append(f"  Cash after {block.day.isoformat()}")
        for name, cash in block.cash_after:
            lines.append(_activity_row("", name, "", "", _money(cash), "", ""))
    lines.append("")
    return lines


def _render_closing(statement: Statement) -> list[str]:
    end = statement.period_end.isoformat() if statement.period_end else "the latest event"
    lines = _balance_table(f"CLOSING BALANCES  as of {end}", statement.closing)
    if not statement.closing:
        lines.append("")
        return lines
    for balance in statement.closing:
        lines.append("")
        lines.append(f"{balance.name}  [{balance.type} / {balance.status}]")
        lines.append(f"  {'Cash':<26}{_money(balance.cash):>16}")
        lines.append(f"  {'Reserved':<26}{_money(balance.reserved):>16}")
        lines.append(f"  {'Free cash':<26}{_money(balance.free_cash):>16}")
        lines.append(f"  {'Realized P&L (period)':<26}{_money(balance.realized_period):>16}")
        lines.append(f"  {'Realized P&L (to date)':<26}{_money(balance.realized_total):>16}")
        if not balance.positions:
            lines.append("  Positions: none")
            continue
        lines.append("  Positions")
        lines.append(f"    {'Symbol':<12}{'Qty':>14}{'Cost basis':>18}{'Avg cost':>16}")
        for position in balance.positions:
            lines.append(
                f"    {position.symbol:<12}{_qty(position.qty):>14}"
                f"{_money(position.cost_basis):>18}{_price(position.avg_cost):>16}"
            )
            for index, lot in enumerate(position.lots, start=1):
                unit = lot.cost_basis / lot.qty if lot.qty else ZERO
                lines.append(
                    f"      {'lot ' + str(index):<10}{_qty(lot.qty):>14}"
                    f"{_money(lot.cost_basis):>18}{_price(unit):>16}"
                )
    lines.append("")
    return lines


def _summary_row(label: str, value: str) -> str:
    return f"{_fit(label, _SUMMARY_LABEL):<{_SUMMARY_LABEL}}{value:>20}"


def _render_totals(statement: Statement) -> list[str]:
    end = statement.period_end.isoformat() if statement.period_end else "the latest event"
    rows = [
        ("Cash (all sleeves)", statement.total_cash),
        ("Reserved cash", statement.total_reserved),
        ("Free cash", statement.total_cash - statement.total_reserved),
        ("Positions at cost", statement.total_positions_cost),
        ("Equity at cost", statement.total_cash + statement.total_positions_cost),
        ("Realized P&L (period)", statement.total_realized_period),
        ("Realized P&L (to date)", statement.invariants.realized_total),
    ]
    lines = [_THIN, f"ACCOUNT TOTALS  as of {end}", _THIN]
    lines.extend(_summary_row(label, _money(value)) for label, value in rows)
    lines.append("")
    return lines


def _render_invariants(statement: Statement) -> list[str]:
    report = statement.invariants
    lines = [_THIN, "INVARIANTS", _THIN]
    rows = [
        ("Net external funding into the account", report.external_funding),
        ("Realized P&L (to date)", report.realized_total),
        ("Expected equity at cost (funding + realized)", report.expected_equity_at_cost),
        ("Actual equity at cost (cash + positions)", report.actual_equity_at_cost),
        ("Difference", report.difference),
    ]
    lines.extend(_summary_row(label, _money(value)) for label, value in rows)

    if report.balanced:
        lines.append(_summary_row("Sleeve conservation", "OK"))
    else:
        lines.append(_summary_row("Sleeve conservation", "** MISMATCH **"))
        lines.append(
            f"  Sleeve balances do not tie to the account: exact difference {report.difference}"
        )

    if report.poison_events == 0:
        lines.append(_summary_row("Projection completeness", "OK"))
    else:
        lines.append(_summary_row("Projection completeness", "** INCOMPLETE **"))
        lines.append(
            f"  {report.poison_events} event(s) could not be read and are excluded "
            "from every balance above"
        )

    if not report.sleeve_violations:
        lines.append(_summary_row("Sleeve state checks", "OK"))
    else:
        lines.append(_summary_row("Sleeve state checks", "** VIOLATIONS **"))
        for name, violation in report.sleeve_violations:
            lines.append(f"  {name}: {violation.kind} ({violation.detail})")
    lines.append(_RULE)
    return lines


def render_text(statement: Statement) -> str:
    """The statement as monospace-aligned plain text."""
    start = statement.period_start.isoformat() if statement.period_start else "inception"
    lines = _render_header(statement)
    lines.extend(_balance_table(f"OPENING BALANCES  as of {start}", statement.opening))
    lines.append("")
    lines.extend(_render_activity(statement))
    lines.extend(_render_closing(statement))
    lines.extend(_render_totals(statement))
    lines.extend(_render_invariants(statement))
    return "\n".join(lines) + "\n"


# JSON rendering


def _balance_json(balance: SleeveBalance) -> dict[str, object]:
    return {
        "sleeve_id": balance.sleeve_id,
        "name": balance.name,
        "type": balance.type,
        "status": balance.status,
        "cash": str(balance.cash),
        "reserved": str(balance.reserved),
        "free_cash": str(balance.free_cash),
        "positions_cost": str(balance.positions_cost),
        "realized_pnl_period": str(balance.realized_period),
        "realized_pnl_to_date": str(balance.realized_total),
        "positions": [
            {
                "symbol": position.symbol,
                "qty": str(position.qty),
                "cost_basis": str(position.cost_basis),
                "avg_cost": str(position.avg_cost),
                "lots": [
                    {"qty": str(lot.qty), "cost_basis": str(lot.cost_basis)}
                    for lot in position.lots
                ],
            }
            for position in balance.positions
        ],
        "violations": [{"kind": v.kind, "detail": v.detail} for v in balance.violations],
    }


def statement_to_dict(statement: Statement) -> dict[str, object]:
    """The same content as the text render, as JSON-ready primitives."""
    report = statement.invariants
    return {
        "account": {
            "account_id": str(statement.account.account_id),
            "tenant_id": str(statement.account.tenant_id),
            "broker_account_id": statement.account.broker_account_id,
            "base_currency": statement.account.base_currency,
        },
        "period": {
            "start": statement.period_start.isoformat() if statement.period_start else None,
            "end": statement.period_end.isoformat() if statement.period_end else None,
            "generated_at": statement.generated_at.isoformat(),
            "events_in_period": statement.events_in_period,
            "events_through_end": statement.events_through_end,
        },
        "opening": [_balance_json(b) for b in statement.opening],
        "activity": [
            {
                "day": block.day.isoformat(),
                "lines": [
                    {
                        "occurred_at": line.occurred_at.isoformat(),
                        "event_id": line.event_id,
                        "event_type": line.event_type,
                        "sleeve_id": line.sleeve_id,
                        "sleeve_name": line.sleeve_name,
                        "label": line.label,
                        "detail": line.detail,
                        "amount": str(line.amount) if line.amount is not None else None,
                        "realized_pnl": str(line.realized) if line.realized is not None else None,
                        "skipped": line.skipped,
                    }
                    for line in block.lines
                ],
                "cash_after": [
                    {"sleeve": name, "cash": str(cash)} for name, cash in block.cash_after
                ],
            }
            for block in statement.days
        ],
        "closing": [_balance_json(b) for b in statement.closing],
        "totals": {
            "cash": str(statement.total_cash),
            "reserved": str(statement.total_reserved),
            "positions_cost": str(statement.total_positions_cost),
            "equity_at_cost": str(statement.total_cash + statement.total_positions_cost),
            "realized_pnl_period": str(statement.total_realized_period),
            "realized_pnl_to_date": str(report.realized_total),
        },
        "invariants": {
            "external_funding": str(report.external_funding),
            "expected_equity_at_cost": str(report.expected_equity_at_cost),
            "actual_equity_at_cost": str(report.actual_equity_at_cost),
            "difference": str(report.difference),
            "balanced": report.balanced,
            "poison_events": report.poison_events,
            "healthy": report.healthy,
            "sleeve_violations": [
                {"sleeve": name, "kind": v.kind, "detail": v.detail}
                for name, v in report.sleeve_violations
            ],
        },
    }


def render_json(statement: Statement) -> str:
    return json.dumps(statement_to_dict(statement), indent=2) + "\n"


# Database shell


async def _resolve_account(
    repo: SqlSleeveRepository,
    tenant_id: UUID,
    account_id: UUID | None,
    broker_account_id: str | None,
    credentials_id: UUID | None,
) -> Account:
    if account_id is not None:
        account = await repo.get_account(tenant_id, account_id)
        selector = f"account_id={account_id}"
    elif broker_account_id is not None:
        account = await repo.get_account_by_broker_id(tenant_id, broker_account_id)
        selector = f"broker_account_id={broker_account_id}"
    else:
        account = await repo.get_account_by_credentials(tenant_id, cast("UUID", credentials_id))
        selector = f"credentials_id={credentials_id}"
    if account is None:
        raise StatementError(f"no ledger account for tenant {tenant_id} with {selector}")
    return account


def _sleeve_meta(sleeves: Sequence[Sleeve]) -> list[SleeveMeta]:
    return [
        SleeveMeta(
            sleeve_id=str(sleeve.id), name=sleeve.name, type=sleeve.type, status=sleeve.status
        )
        for sleeve in sleeves
    ]


async def load_statement(
    *,
    tenant_id: UUID,
    account_id: UUID | None = None,
    broker_account_id: str | None = None,
    credentials_id: UUID | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    generated_at: datetime | None = None,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> Statement:
    """Read one account's ledger and build its statement.

    Opens an audited system session: the tool serves support across tenants and
    must read an account it was pointed at by id, so it takes the RLS bypass with
    a reason naming the tool and the account, and still filters every query by
    ``tenant_id``.
    """
    selector = account_id or broker_account_id or credentials_id
    reason = f"ledger statement tool: account {selector} (tenant {tenant_id})"
    async with system_session(session_maker, reason=reason) as db:
        repo = SqlSleeveRepository(db)
        account = await _resolve_account(
            repo, tenant_id, account_id, broker_account_id, credentials_id
        )
        sleeves = await repo.list_sleeves(tenant_id, account.id)
        rows = await LedgerWriter(db).read_account_events(tenant_id, account.id)
        return build_statement(
            account=AccountHeader(
                tenant_id=tenant_id,
                account_id=account.id,
                broker_account_id=account.alpaca_account_id,
                base_currency=account.base_currency,
            ),
            sleeves=_sleeve_meta(sleeves),
            events=cast("list[StatementEvent]", rows),
            period_start=period_start,
            period_end=period_end,
            generated_at=generated_at or datetime.now(UTC),
        )


# CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.tools.statement",
        description="Render an account's ledger history as a readable statement.",
    )
    parser.add_argument("--tenant-id", type=UUID, required=True, help="Owning tenant id")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--account-id", type=UUID, help="Ledger account id")
    selector.add_argument("--broker-account-id", help="Broker (Alpaca) account id")
    selector.add_argument("--credentials-id", type=UUID, help="Broker credentials row id")
    parser.add_argument(
        "--from", dest="start", type=date.fromisoformat, help="Period start (YYYY-MM-DD, UTC)"
    )
    parser.add_argument(
        "--to", dest="end", type=date.fromisoformat, help="Period end (YYYY-MM-DD, UTC)"
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of text")
    return parser


async def run(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, render to stdout, and return the process exit code."""
    args = build_parser().parse_args(argv)
    tenant_id: UUID = args.tenant_id
    account_id: UUID | None = args.account_id
    broker_account_id: str | None = args.broker_account_id
    credentials_id: UUID | None = args.credentials_id
    start: date | None = args.start
    end: date | None = args.end
    as_json: bool = args.json

    if start is not None and end is not None and end < start:
        sys.stderr.write(f"error: --to {end} precedes --from {start}\n")
        return 2

    try:
        statement = await load_statement(
            tenant_id=tenant_id,
            account_id=account_id,
            broker_account_id=broker_account_id,
            credentials_id=credentials_id,
            period_start=start,
            period_end=end,
        )
    except StatementError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    sys.stdout.write(render_json(statement) if as_json else render_text(statement))
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
