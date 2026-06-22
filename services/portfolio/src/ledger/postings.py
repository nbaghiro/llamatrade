"""Double-entry postings for the portfolio ledger.

Each ledger event expands into a set of **balanced** postings whose signed
dollar amounts sum to zero — the conservation checksum that guarantees value is
neither created nor destroyed within the system. Buckets:

- ``CASH``     — a sleeve's cash balance
- ``POSITION`` — a sleeve's position value at cost (carries a signed share qty)
- ``PNL``      — realized P&L recognized into sleeve equity (balancing leg)
- ``EXTERNAL`` — money entering/leaving the account (deposits/withdrawals)

A sleeve's realized P&L equals ``-Σ(PNL posting amounts)``: a sell for more than
cost produces ``cash_in - cost_out > 0``, balanced by a negative PNL leg.

See .docs/portfolio-ledger.md
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import cast

from llamatrade_db.models.ledger import LedgerEventType

ZERO = Decimal("0")


class Bucket(StrEnum):
    """Accounting bucket a posting moves value into/out of."""

    CASH = "cash"
    POSITION = "position"
    PNL = "pnl"
    EXTERNAL = "external"


@dataclass(frozen=True)
class Posting:
    """A single signed leg of a double-entry event."""

    sleeve_id: str | None  # None only for EXTERNAL (account boundary)
    bucket: Bucket
    amount: Decimal  # signed dollars
    symbol: str | None = None  # set for POSITION
    qty: Decimal | None = None  # signed share delta (POSITION only)


class UnbalancedEventError(ValueError):
    """Raised when an event's postings do not sum to zero."""


def assert_balanced(postings: list[Posting]) -> None:
    """Assert conservation: postings sum to zero dollars, and no POSITION leg
    moves shares opposite to its cost.

    The dollar checksum alone can't catch a leg that *adds* shares while
    *removing* cost (or vice versa) — a sign inconsistency that would corrupt a
    sleeve's average cost. A zero-dollar position move (a split) is exempt: it
    legitimately changes qty at no incremental cost.
    """
    total = sum((p.amount for p in postings), ZERO)
    if total != ZERO:
        raise UnbalancedEventError(f"postings sum to {total}, expected 0")
    for p in postings:
        if p.bucket is Bucket.POSITION and p.qty is not None:
            if (p.amount > ZERO and p.qty < ZERO) or (p.amount < ZERO and p.qty > ZERO):
                raise UnbalancedEventError(
                    f"position leg {p.symbol!r} has opposite-signed "
                    f"qty={p.qty} and amount={p.amount}"
                )


def _d(data: dict[str, object], key: str) -> Decimal:
    """Read a Decimal field from an event payload (accepts str/int/float/Decimal)."""
    val = data[key]
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (str, int)):
        return Decimal(val)
    if isinstance(val, float):
        return Decimal(str(val))
    raise TypeError(f"field {key!r} is not numeric: {val!r}")


def build_postings(event_type: LedgerEventType, data: dict[str, object]) -> list[Posting]:
    """Expand a ledger event into balanced postings.

    Non-economic events (sleeve lifecycle, order intent/submit/accept, corporate
    metadata) carry no value movement and return an empty list. Callers should
    pass the event's ``data`` payload using the documented keys.
    """
    match event_type:
        case LedgerEventType.CAPITAL_ALLOCATED | LedgerEventType.CAPITAL_TRANSFERRED:
            amount = _d(data, "amount")
            frm = str(data["from_sleeve_id"])
            to = str(data["to_sleeve_id"])
            return [
                Posting(frm, Bucket.CASH, -amount),
                Posting(to, Bucket.CASH, amount),
            ]

        case LedgerEventType.FUNDS_DEPOSITED:
            amount = _d(data, "amount")
            sleeve = str(data["sleeve_id"])
            return [
                Posting(None, Bucket.EXTERNAL, -amount),
                Posting(sleeve, Bucket.CASH, amount),
            ]

        case LedgerEventType.FUNDS_WITHDRAWN:
            amount = _d(data, "amount")
            sleeve = str(data["sleeve_id"])
            return [
                Posting(sleeve, Bucket.CASH, -amount),
                Posting(None, Bucket.EXTERNAL, amount),
            ]

        case LedgerEventType.ORDER_FILLED:
            return _order_filled_postings(data)

        case LedgerEventType.DIVIDEND_RECEIVED | LedgerEventType.INTEREST_ACCRUED:
            amount = _d(data, "amount")
            sleeve = str(data["sleeve_id"])
            return [
                Posting(sleeve, Bucket.CASH, amount),
                Posting(sleeve, Bucket.PNL, -amount),
            ]

        case LedgerEventType.FEE_CHARGED:
            amount = _d(data, "amount")
            sleeve = str(data["sleeve_id"])
            return [
                Posting(sleeve, Bucket.CASH, -amount),
                Posting(sleeve, Bucket.PNL, amount),
            ]

        case LedgerEventType.SPLIT_APPLIED:
            # A stock split adds (or removes, on a reverse split) shares at zero
            # incremental cost — cost basis is preserved, only qty changes. The
            # single zero-dollar POSITION leg keeps cash conservation intact;
            # ``qty_delta`` is the signed share change for THIS sleeve (the
            # corporate-action planner computes it per holding sleeve).
            sleeve = str(data["sleeve_id"])
            symbol = str(data["symbol"])
            qty_delta = _d(data, "qty_delta")
            return [Posting(sleeve, Bucket.POSITION, ZERO, symbol=symbol, qty=qty_delta)]

        case LedgerEventType.SYMBOL_CHANGED:
            # A ticker rename moves a sleeve's lot from the old symbol to the new
            # one, carrying qty and cost basis across unchanged. Two POSITION legs
            # (close old, open new) at equal cost net to zero dollars.
            sleeve = str(data["sleeve_id"])
            old_symbol = str(data["old_symbol"])
            new_symbol = str(data["new_symbol"])
            qty = _d(data, "qty")
            cost = _d(data, "cost_basis")
            return [
                Posting(sleeve, Bucket.POSITION, -cost, symbol=old_symbol, qty=-qty),
                Posting(sleeve, Bucket.POSITION, cost, symbol=new_symbol, qty=qty),
            ]

        case LedgerEventType.EXTERNAL_TRADE_DETECTED:
            # An externally-originated fill we attribute to the Unmanaged sleeve.
            # Funded from outside the tracked book (EXTERNAL leg).
            sleeve = str(data["sleeve_id"])
            symbol = str(data["symbol"])
            qty = _d(data, "qty")
            price = _d(data, "price")
            notional = qty * price
            return [
                Posting(None, Bucket.EXTERNAL, -notional),
                Posting(sleeve, Bucket.POSITION, notional, symbol=symbol, qty=qty),
            ]

        case LedgerEventType.SLEEVE_CLOSED:
            return _sleeve_closed_postings(data)

        case _:
            return []


def _order_filled_postings(data: dict[str, object]) -> list[Posting]:
    sleeve = str(data["sleeve_id"])
    symbol = str(data["symbol"])
    side = str(data["side"]).lower()
    qty = _d(data, "qty")
    price = _d(data, "price")
    fees = _d(data, "fees") if "fees" in data else ZERO
    notional = qty * price

    if side == "buy":
        # cash out (notional + fees); position in (at cost); fees reduce equity.
        return [
            Posting(sleeve, Bucket.CASH, -(notional + fees)),
            Posting(sleeve, Bucket.POSITION, notional, symbol=symbol, qty=qty),
            Posting(sleeve, Bucket.PNL, fees),
        ]

    if side == "sell":
        # Fail-closed: a sell MUST carry a resolved cost basis (the consumer
        # enriches via FIFO at ingestion). Defaulting to notional would fabricate
        # zero realized P&L and silently corrupt the remaining lots' basis, so we
        # refuse to build postings for a basis-less sell — the writer rejects it
        # and the fill is quarantined rather than recorded wrong-but-balanced.
        if "cost_basis" not in data:
            raise ValueError("sell ORDER_FILLED missing cost_basis (FIFO enrichment did not run)")
        cost = _d(data, "cost_basis")
        realized = notional - cost - fees
        return [
            Posting(sleeve, Bucket.POSITION, -cost, symbol=symbol, qty=-qty),
            Posting(sleeve, Bucket.CASH, notional - fees),
            Posting(sleeve, Bucket.PNL, -realized),
        ]

    raise ValueError(f"unknown order side: {side!r}")


def _sleeve_closed_postings(data: dict[str, object]) -> list[Posting]:
    """Re-home a closing sleeve's holdings, then retire it.

    Open positions move to the Unmanaged sleeve and free cash to Unallocated.
    Each position is two balanced POSITION legs (close on the source, open on
    the target, carrying qty + cost basis — a re-home is not a sale, so no PNL
    leg), and cash is two balanced CASH legs, so the whole close nets to zero
    dollars. An already-empty sleeve yields no postings; the ``SLEEVE_CLOSED``
    event is then a pure lifecycle marker. Mirrors the two-leg position move in
    ``SYMBOL_CHANGED``, but across sleeves rather than across symbols.
    """
    frm = str(data["sleeve_id"])
    postings: list[Posting] = []

    raw_positions = data.get("positions")
    if raw_positions:
        to_positions = str(data["to_position_sleeve_id"])
        for entry in cast("list[dict[str, object]]", raw_positions):
            symbol = str(entry["symbol"])
            qty = _d(entry, "qty")
            cost = _d(entry, "cost_basis")
            postings.append(Posting(frm, Bucket.POSITION, -cost, symbol=symbol, qty=-qty))
            postings.append(Posting(to_positions, Bucket.POSITION, cost, symbol=symbol, qty=qty))

    cash = _d(data, "cash") if "cash" in data else ZERO
    if cash != ZERO:
        to_cash = str(data["to_cash_sleeve_id"])
        postings.append(Posting(frm, Bucket.CASH, -cash))
        postings.append(Posting(to_cash, Bucket.CASH, cash))

    return postings
