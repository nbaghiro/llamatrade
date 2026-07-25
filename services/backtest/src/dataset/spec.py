"""DatasetSpec — the content-addressable identity of a materialized bar dataset.

Two runs whose spec hashes match request byte-identical bars, so their snapshot is shared and
their prepare coalesces. The hash is stable across processes (canonical JSON + SHA-256).
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DatasetSpec:
    """Identifies the exact bar set a run needs: symbols × timeframe × fetch window × adjustment.

    `fetch_start` is the warm-up-padded start actually fetched (not the backtest window start),
    so the snapshot contains the indicator warm-up bars the sim replays.
    """

    symbols: tuple[str, ...]
    timeframe: str
    fetch_start: date
    end: date
    adjustment: str = "raw"

    @classmethod
    def create(
        cls,
        symbols: Iterable[str],
        timeframe: str,
        fetch_start: date,
        end: date,
        adjustment: str = "raw",
    ) -> DatasetSpec:
        """Build a spec with symbols normalized (sorted + deduped) so order never affects the hash."""
        return cls(
            symbols=tuple(sorted({s.upper() for s in symbols})),
            timeframe=timeframe,
            fetch_start=fetch_start,
            end=end,
            adjustment=adjustment,
        )

    @property
    def dataset_hash(self) -> str:
        """A stable 32-char content hash of the normalized spec."""
        payload = json.dumps(
            {
                "symbols": list(self.symbols),
                "timeframe": self.timeframe,
                "fetch_start": self.fetch_start.isoformat(),
                "end": self.end.isoformat(),
                "adjustment": self.adjustment,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    @property
    def object_key(self) -> str:
        """Store path/key for this dataset's snapshot (timeframe-partitioned)."""
        return f"{self.timeframe}/{self.dataset_hash}.parquet"
