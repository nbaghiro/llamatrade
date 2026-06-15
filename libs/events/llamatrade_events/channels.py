"""The channel registry — every stream the system uses, defined once.

Centralizes what was scattered (and duplicated — ``LEDGER_FILLS_STREAM`` lived in
both trading and portfolio). Each channel declares its key template, retention
bound, delivery shape, and whether it carries the full envelope or a raw payload
(high-volume bars skip the envelope).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Delivery(Enum):
    TAIL = "tail"  # independent fan-out (UI streams, bars)
    CONSUME = "consume"  # durable consumer group (ledger fills)


@dataclass(frozen=True)
class Channel:
    """A logical stream + its wire policy."""

    key_template: str  # e.g. "trading:orders:{session_id}" or "ledger:fills"
    maxlen: int
    delivery: Delivery = Delivery.TAIL
    enveloped: bool = True  # False → raw payload bytes (no EventEnvelope)

    def key(self, **params: object) -> str:
        """Resolve the concrete stream key (fills any ``{placeholder}``).

        Accepts non-str params (e.g. a ``UUID`` session id) — ``str.format``
        stringifies them, so callers needn't coerce.
        """
        return self.key_template.format(**params)


# --- Trading UI (per-session, tail fan-out) ---
ORDERS = Channel("trading:orders:{session_id}", maxlen=1_000)
POSITIONS = Channel("trading:positions:{session_id}", maxlen=1_000)

# --- Ledger fills (one global stream, durable consumer group) ---
LEDGER_FILLS = Channel("ledger:fills", maxlen=10_000, delivery=Delivery.CONSUME)

# --- Backtest progress (per-backtest, short, tail-replay) ---
BACKTEST_PROGRESS = Channel("backtest:progress:{backtest_id}", maxlen=256)

# --- Market data live bars (one global stream, high-volume, raw payload) ---
BARS = Channel("market:bars:1m", maxlen=50_000, enveloped=False)
