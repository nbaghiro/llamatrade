"""Write-time sleeve invariants — defense-in-depth over the projection.

Fund ops already refuse to overdraw (the planners check free cash before
appending), so the only way a sleeve can reach an *impossible* state — negative
cash, negative (short) position the ledger never opened, or more cash reserved
than it holds — is a fill that slipped past trading's reservation/risk guard, an
oversell, or a concurrent capital op that raced the free-cash read. These pure
checks run at every writing path: the async fill path freezes the sleeve, while
a synchronous op (fund/close/corporate) refuses the write, so a corrupt balance
the dollar checksum can't catch (a single event still balances; it's the running
total that's impossible) never lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.ledger.projection import AccountProjection, SleeveProjection

ZERO = Decimal("0")


class LedgerInvariantError(Exception):
    """A write would drive a sleeve or account into an impossible state.

    Raised by synchronous writing paths (fund ops, sleeve close, corporate
    actions) so the transaction rolls back instead of committing a corrupt
    balance; the async fill path freezes the sleeve instead of raising.
    """


@dataclass(frozen=True)
class InvariantViolation:
    """A way a projected sleeve (or account) has reached an impossible state."""

    kind: str  # negative_cash | negative_position | reserved_exceeds_cash | negative_account_cash
    detail: str


def check_sleeve_invariants(sleeve: SleeveProjection) -> list[InvariantViolation]:
    """Return the invariants a projected sleeve violates (empty = healthy)."""
    violations: list[InvariantViolation] = []
    if sleeve.cash < ZERO:
        violations.append(InvariantViolation("negative_cash", f"cash={sleeve.cash}"))
    # Reserved cash earmarks free cash; reserved exceeding held cash means an open order can overdraw (a zero reservation can't, and negative cash is flagged above).
    if sleeve.reserved > ZERO and sleeve.reserved > sleeve.cash:
        violations.append(
            InvariantViolation(
                "reserved_exceeds_cash", f"reserved={sleeve.reserved} cash={sleeve.cash}"
            )
        )
    for symbol, pos in sleeve.positions.items():
        if pos.qty < ZERO:
            violations.append(InvariantViolation("negative_position", f"{symbol} qty={pos.qty}"))
    return violations


def check_account_invariants(projection: AccountProjection) -> list[InvariantViolation]:
    """Return the account-level invariants a projection violates (empty = healthy).

    The account can never hold negative total cash: the sum across every sleeve
    is external money that entered the book, so a negative sum is impossible.
    """
    total = sum((s.cash for s in projection.sleeves.values()), ZERO)
    if total < ZERO:
        return [InvariantViolation("negative_account_cash", f"total_cash={total}")]
    return []


def assert_write_invariants(projection: AccountProjection, *sleeve_ids: str) -> None:
    """Assert the given sleeves and the account are healthy, else raise.

    Used by synchronous writing paths after they reproject: an op that drove any
    named sleeve, or the account as a whole, into an impossible state is refused
    (the transaction rolls back) rather than committed.
    """
    violations: list[InvariantViolation] = []
    for sleeve_id in sleeve_ids:
        violations.extend(check_sleeve_invariants(projection.sleeve(sleeve_id)))
    violations.extend(check_account_invariants(projection))
    if violations:
        detail = "; ".join(f"{v.kind}({v.detail})" for v in violations)
        raise LedgerInvariantError(detail)
