"""Core value objects for the strategy runtime (shared by backtest and live).

The intended-order type is the compiler's ``IntendedOrder``; the types below are the
execution-side domain objects the compiler has no notion of.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Fill:
    """A single executed fill — one open ('buy') or close ('sell') leg."""

    date: datetime
    symbol: str
    side: str
    price: float
    quantity: float
    commission: float


@dataclass
class Trade:
    """A completed round-trip (entry → exit). Long-only."""

    entry_date: datetime
    exit_date: datetime
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    commission: float = 0.0

    @property
    def pnl(self) -> float:
        gross_pnl = (self.exit_price - self.entry_price) * self.quantity
        return gross_pnl - self.commission

    @property
    def pnl_percent(self) -> float:
        denominator = self.entry_price * self.quantity
        if denominator == 0:
            return 0.0
        return (self.pnl / denominator) * 100


@dataclass
class Position:
    """An open long position in the in-memory book."""

    symbol: str
    side: str
    entry_price: float
    quantity: float
    entry_date: datetime
    # Entry commission not yet allocated to a close; apportioned to exits so it's counted once.
    entry_commission_remaining: float = 0.0


@dataclass
class RejectedSignal:
    """An order the execution layer could not fill, with a human-readable reason."""

    date: datetime
    symbol: str
    signal_type: str
    quantity: float
    price: float
    reason: str


@dataclass
class ExecutionOutcome:
    """The result of executing one order: a fill and/or a completed trade, or a rejection."""

    fill: Fill | None = None
    trade: Trade | None = None
    rejected: RejectedSignal | None = None
