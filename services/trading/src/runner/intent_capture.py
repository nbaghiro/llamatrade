"""Order-intent capture — one JSON line per evaluation, written by either live loop.

Setting ``TRADING_INTENT_CAPTURE_DIR`` records what a session's strategy asked for at each
evaluation, taken after sizing and before risk checks and submission: the session, the evaluation
timestamp, which loop produced it, the book it sized against (equity and held quantities), the
ordered intents (symbol, side, quantity, reference price) and the deterministic client order ids
they would submit under. The hand-rolled loop records an evaluation in one call; the runtime loop
stages the book when it reads the portfolio and each order as the runtime executes it, then commits
the set when the tick completes, so both loops emit the same record for the same evaluation and
two runs are comparable with ``python -m src.tools.parity_diff``. Nothing is constructed and no
work is done per evaluation when the variable is unset.
"""

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from llamatrade_runtime import NullObserver

from src.executor.order_executor import generate_deterministic_order_id
from src.models import order_side_to_str, signal_type_to_order_side

CAPTURE_DIR_ENV = "TRADING_INTENT_CAPTURE_DIR"

LOOP_HAND_ROLLED = "hand_rolled"
LOOP_RUNTIME = "runtime"


@dataclass(frozen=True, slots=True)
class OrderIntent:
    """One sized order a strategy asked for, before risk checks and submission."""

    symbol: str
    side: str
    quantity: float
    price: float


@dataclass(frozen=True, slots=True)
class BookContext:
    """The book an evaluation sized against: sleeve equity and held quantities.

    Two pods running the same strategy hold different books, so this is diagnostic
    context for a divergence, never a parity criterion.
    """

    equity: float
    holdings: Mapping[str, float] = field(default_factory=dict)

    def encode(self) -> dict[str, object]:
        return {"equity": self.equity, "holdings": dict(sorted(self.holdings.items()))}


class IntentCapture:
    """Appends one JSON line per evaluation to a capture file."""

    def __init__(self, path: Path, session_id: UUID, loop: str) -> None:
        self.path = path
        self.session_id = session_id
        self.loop = loop
        self._sequence = 0
        self._staged: list[OrderIntent] = []
        self._staged_book: BookContext | None = None

    def record(
        self, timestamp: datetime, intents: Sequence[OrderIntent], book: BookContext
    ) -> None:
        """Append the intent set one evaluation produced; an empty set is still a record."""
        ts = _as_utc(timestamp)
        self._sequence += 1
        line = json.dumps(
            {
                "session": str(self.session_id),
                "loop": self.loop,
                "sequence": self._sequence,
                "timestamp": ts.isoformat(),
                "book": book.encode(),
                "intents": [self._encode(intent, ts) for intent in intents],
            },
            separators=(",", ":"),
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")

    def stage(self, intent: OrderIntent) -> None:
        """Hold an intent until the evaluation that produced it completes."""
        self._staged.append(intent)

    def stage_book(self, book: BookContext) -> None:
        """Hold the book the runtime is about to size against."""
        self._staged_book = book

    def commit(self, timestamp: datetime) -> None:
        """Record the staged intents and book as one evaluation and clear them."""
        assert self._staged_book is not None, "the runtime stages the book before every tick"
        staged, self._staged = self._staged, []
        book, self._staged_book = self._staged_book, None
        self.record(timestamp, staged, book)

    def _encode(self, intent: OrderIntent, timestamp: datetime) -> dict[str, str | float]:
        return {
            "symbol": intent.symbol,
            "side": intent.side,
            "quantity": intent.quantity,
            "price": intent.price,
            "order_id": generate_deterministic_order_id(
                session_id=self.session_id,
                symbol=intent.symbol.upper(),
                side=order_side_to_str(signal_type_to_order_side(intent.side)),
                signal_timestamp=timestamp,
            ),
        }


class CaptureObserver(NullObserver):
    """Commits the runtime loop's staged intents once its tick finishes."""

    def __init__(self, capture: IntentCapture) -> None:
        self._capture = capture

    def on_tick(self, index: int, total: int | None, date: datetime, equity: float) -> None:
        self._capture.commit(date)


def capture_from_env(session_id: UUID, loop: str) -> IntentCapture | None:
    """Build a capture writer when the capture directory is configured, else None."""
    directory = os.getenv(CAPTURE_DIR_ENV, "").strip()
    if not directory:
        return None
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    return IntentCapture(root / f"intents-{loop}-{session_id}.jsonl", session_id, loop)


def _as_utc(timestamp: datetime) -> datetime:
    """UTC instant for ``timestamp``; a naive value is read as UTC, matching the bar streams."""
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)
