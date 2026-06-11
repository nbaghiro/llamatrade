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
    """Assert the conservation invariant: postings sum to zero dollars."""
    total = sum((p.amount for p in postings), ZERO)
    if total != ZERO:
        raise UnbalancedEventError(f"postings sum to {total}, expected 0")


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
        # Cost basis of the closed quantity is provided by the lot selector.
        cost = _d(data, "cost_basis") if "cost_basis" in data else notional
        realized = notional - cost - fees
        return [
            Posting(sleeve, Bucket.POSITION, -cost, symbol=symbol, qty=-qty),
            Posting(sleeve, Bucket.CASH, notional - fees),
            Posting(sleeve, Bucket.PNL, -realized),
        ]

    raise ValueError(f"unknown order side: {side!r}")
