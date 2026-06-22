"""Write-time sleeve invariants — defense-in-depth over the projection.

Fund ops already refuse to overdraw (the planners check free cash before
appending), so the only way a sleeve can reach an *impossible* state — negative
cash, or a negative (short) position the ledger never opened — is a fill that
slipped past trading's reservation/risk guard, or an oversell. These pure checks
run after each fill so such a sleeve is frozen for review rather than silently
carrying a corrupt balance the dollar checksum can't catch (a single event still
balances; it's the running total that's impossible).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.ledger.projection import SleeveProjection

ZERO = Decimal("0")


@dataclass(frozen=True)
class InvariantViolation:
    """A way a projected sleeve has reached an impossible state."""

    kind: str  # "negative_cash" | "negative_position"
    detail: str


def check_sleeve_invariants(sleeve: SleeveProjection) -> list[InvariantViolation]:
    """Return the invariants a projected sleeve violates (empty = healthy)."""
    violations: list[InvariantViolation] = []
    if sleeve.cash < ZERO:
        violations.append(InvariantViolation("negative_cash", f"cash={sleeve.cash}"))
    for symbol, pos in sleeve.positions.items():
        if pos.qty < ZERO:
            violations.append(InvariantViolation("negative_position", f"{symbol} qty={pos.qty}"))
    return violations
