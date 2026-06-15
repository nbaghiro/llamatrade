"""Idempotency primitives.

``derive_event_id`` centralizes the ``sha256(parts…)`` pattern hand-rolled across
trading and portfolio (fill = ``sha256(client_order_id)``, reservation =
``sha256(client_order_id:event_type)``, sleeve close = ``sha256(sleeve_id:close)``,
drift = ``sha256(account_id:adopt:symbol)``). ``DedupStore`` is the consumer-side
"have I applied this event id?" seam (Postgres-backed in services).
"""

from __future__ import annotations

import hashlib
from typing import Protocol


def derive_event_id(*parts: str, length: int = 16) -> str:
    """Deterministic event id from stable parts (the dedup key).

    The same inputs always yield the same id, so at-least-once delivery +
    consumer dedupe = effective-once. ``length`` is the hex prefix length
    (16 matches the ledger's ``event_id`` convention).
    """
    digest = hashlib.sha256(":".join(parts).encode()).hexdigest()
    return digest[:length]


class DedupStore(Protocol):
    """Consumer-side dedupe seam (e.g. the ledger's event_id table)."""

    async def seen(self, event_id: str) -> bool:
        """True if ``event_id`` has already been applied."""
        ...

    async def mark(self, event_id: str) -> None:
        """Record ``event_id`` as applied."""
        ...


class InMemoryDedupStore:
    """A process-local DedupStore — for tests and single-instance use."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    async def seen(self, event_id: str) -> bool:
        return event_id in self._seen

    async def mark(self, event_id: str) -> None:
        self._seen.add(event_id)
