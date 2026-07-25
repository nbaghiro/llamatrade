"""RuntimeObserver — the lifecycle-event seam.

The runtime emits every meaningful event (tick, fill, trade, rejection, completion) to an
observer. Backtest wires a progress-stream publisher here (live progress + partial metrics);
live trading wires trade/telemetry emission. ``NullObserver`` is the default no-op.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from llamatrade_runtime.models import Fill, RejectedSignal, Trade

if TYPE_CHECKING:
    from llamatrade_runtime.result import RunResult


class RuntimeObserver(Protocol):
    """Observes a run. All methods are optional to act on (see ``NullObserver``)."""

    def on_start(self, total_ticks: int | None) -> None: ...

    def on_tick(self, index: int, total: int | None, date: datetime, equity: float) -> None: ...

    def on_fill(self, fill: Fill) -> None: ...

    def on_trade(self, trade: Trade) -> None: ...

    def on_reject(self, rejected: RejectedSignal) -> None: ...

    def on_complete(self, result: RunResult) -> None: ...


class NullObserver:
    """Default observer that ignores every event."""

    def on_start(self, total_ticks: int | None) -> None:
        return None

    def on_tick(self, index: int, total: int | None, date: datetime, equity: float) -> None:
        return None

    def on_fill(self, fill: Fill) -> None:
        return None

    def on_trade(self, trade: Trade) -> None:
        return None

    def on_reject(self, rejected: RejectedSignal) -> None:
        return None

    def on_complete(self, result: RunResult) -> None:
        return None
