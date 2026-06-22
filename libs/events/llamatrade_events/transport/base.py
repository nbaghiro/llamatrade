"""The transport seam — swap Redis Streams for Kafka by writing one adapter.

An ``EventTransport`` moves **opaque bytes** between services with an **opaque
cursor** and an optional partition **key**. It knows nothing about proto or the
event envelope (the codec owns that), and nothing about domains (the catalog
owns that). That narrowness is what makes the backend swappable: the bus, codec,
catalog, consumer, and fan-out all sit above this interface unchanged.

Two delivery shapes the system needs (see redis-streams-migration.md §4):
- :meth:`tail` — independent fan-out (every caller sees the full stream; reconnect
  replays from a stored cursor). Redis ``XREAD`` / Kafka *own-group*.
- :meth:`consume` — durable competing consumption (each group gets every entry
  once; survives restart; reclaims a dead consumer's work). Redis ``XREADGROUP``
  + ``XAUTOCLAIM`` / Kafka *shared-group*.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

# A transport cursor (Redis entry id "1697-0" / Kafka "partition:offset"). Opaque:
# callers persist it for replay but never parse it.
Cursor = str

# Special cursors understood by every adapter.
CURSOR_NEW = "$"  # tail: only entries after now
CURSOR_BEGIN = "0"  # tail: replay from the start


@runtime_checkable
class EventTransport(Protocol):
    """Backend-neutral stream transport over opaque byte values."""

    async def publish(
        self,
        stream: str,
        value: bytes,
        *,
        key: str | None = None,
        maxlen: int | None = None,
    ) -> Cursor:
        """Append ``value`` to ``stream``; return the assigned cursor.

        ``key`` is the partition/ordering key (Kafka needs it; Redis single-stream
        ignores it). ``maxlen`` bounds the stream where the backend supports
        per-publish trimming (Redis ``MAXLEN``); backends that retain by config
        (Kafka) treat it as advisory.
        """
        ...

    def tail(
        self,
        stream: str,
        *,
        from_cursor: Cursor = CURSOR_NEW,
        block_ms: int = 5000,
        count: int = 100,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        """Independent fan-out. Yields ``(cursor, value)``; reconnect-safe."""
        ...

    async def ensure_group(self, stream: str, group: str, *, start_id: str = CURSOR_NEW) -> None:
        """Idempotently create the consumer group (no-op if it exists)."""
        ...

    def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        block_ms: int = 5000,
        count: int = 10,
        claim_min_idle_ms: int = 60_000,
        group_start_id: str = CURSOR_NEW,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        """Durable competing consumption. Yields ``(cursor, value)``; caller MUST
        :meth:`ack`. ``claim_min_idle_ms`` governs dead-consumer reclaim where the
        backend needs it explicitly (Redis); ignored where failover is automatic
        (Kafka rebalance). ``group_start_id`` is where a *brand-new* group begins
        (``CURSOR_BEGIN`` = never miss pre-existing entries; ``CURSOR_NEW`` =
        only-new); ignored once the group exists."""
        ...

    async def ack(self, stream: str, group: str, cursor: Cursor) -> None:
        """Acknowledge a processed entry (drops it from the group's pending set)."""
        ...

    async def pending(self, stream: str, group: str) -> int:
        """Delivered-but-unacked count for the group — the lag signal."""
        ...

    async def trim(self, stream: str, maxlen: int) -> None:
        """Bound the stream length (where supported)."""
        ...

    async def close(self) -> None:
        """Release transport resources."""
        ...
