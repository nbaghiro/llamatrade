"""Shadow reconciliation: ledger aggregate vs. broker truth.

The broker is authoritative for *aggregate* reality (one position per symbol);
the ledger is authoritative for *attribution*. Reconciliation asserts the
invariant ``Σ sleeve_qty(symbol) == broker_qty(symbol)`` and classifies any
drift so the consumer can resolve it (own-fill catch-up, external trade →
Unmanaged, corporate action, fractional dust, or material → alert/freeze).

This module is pure (no IO): it computes the drift list; the consuming service
decides how to act on each kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from src.ledger.projection import AccountProjection

ZERO = Decimal("0")
DEFAULT_DUST_TOLERANCE = Decimal("0.0001")


class DriftKind(StrEnum):
    """Classification of a per-symbol reconciliation discrepancy."""

    OK = "ok"  # within tolerance — no action
    DUST = "dust"  # tiny fractional rounding — auto-absorb
    MISSING_AT_BROKER = "missing_at_broker"  # ledger has qty the broker doesn't
    MISSING_IN_LEDGER = "missing_in_ledger"  # broker has qty the ledger doesn't
    QTY_MISMATCH = "qty_mismatch"  # both have the symbol, quantities differ


@dataclass(frozen=True)
class Drift:
    """A single per-symbol discrepancy between ledger and broker."""

    symbol: str
    ledger_qty: Decimal
    broker_qty: Decimal
    kind: DriftKind

    @property
    def delta(self) -> Decimal:
        """broker - ledger (positive means the broker has more)."""
        return self.broker_qty - self.ledger_qty


def reconcile(
    projection: AccountProjection,
    broker_positions: dict[str, Decimal],
    *,
    dust_tolerance: Decimal = DEFAULT_DUST_TOLERANCE,
) -> list[Drift]:
    """Compare the ledger's aggregate positions against broker truth.

    Returns one :class:`Drift` per symbol that is **not** an exact match
    (matches are omitted). ``broker_positions`` maps symbol -> aggregate qty.
    """
    ledger_positions = projection.account_positions()
    symbols = set(ledger_positions) | set(broker_positions)

    drifts: list[Drift] = []
    for symbol in sorted(symbols):
        ledger_qty = ledger_positions.get(symbol, ZERO)
        broker_qty = broker_positions.get(symbol, ZERO)
        delta = broker_qty - ledger_qty

        if delta == ZERO:
            continue
        if abs(delta) <= dust_tolerance:
            kind = DriftKind.DUST
        elif ledger_qty == ZERO:
            kind = DriftKind.MISSING_IN_LEDGER
        elif broker_qty == ZERO:
            kind = DriftKind.MISSING_AT_BROKER
        else:
            kind = DriftKind.QTY_MISMATCH

        drifts.append(Drift(symbol=symbol, ledger_qty=ledger_qty, broker_qty=broker_qty, kind=kind))
    return drifts
