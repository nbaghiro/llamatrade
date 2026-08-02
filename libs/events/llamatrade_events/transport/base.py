"""The transport seam — the narrow port the event backend implements.

An ``EventTransport`` moves **opaque bytes** between services with an **opaque
cursor** and an optional partition **key**. It knows nothing about proto or the
event envelope (the codec owns that), and nothing about domains (the catalog
owns that). That narrowness keeps every layer above — bus, codec, catalog,
consumer, fan-out — backend-neutral.

Two delivery shapes:
- :meth:`tail` — independent fan-out: every caller sees the full stream, and a
  reconnecting caller replays the gap from its stored cursor (Kafka own-group
  reader).
- :meth:`consume` — durable competing consumption: each named group gets every
  entry once, survives restart, and a dead member's partitions are reassigned
  automatically (Kafka shared group).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import NamedTuple, Protocol, runtime_checkable

# A transport cursor (Kafka "partition:offset"). Opaque: callers persist it for
# replay but never parse it.
Cursor = str

# Special cursors understood by every adapter.
CURSOR_NEW = "$"  # tail: only entries after now
CURSOR_BEGIN = "0"  # tail: replay from the start


class OutgoingRecord(NamedTuple):
    """One record in a batch publish: an opaque value and its partition key.

    ``key`` carries the same meaning as in :meth:`EventTransport.publish` —
    records sharing a key land in one partition and keep publish order there.
    """

    value: bytes
    key: str | None = None


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

        ``key`` is the partition/ordering key: entries sharing a key are
        delivered in publish order. ``maxlen`` is advisory — Kafka bounds a
        topic by retention config (Terraform); only backends that trim per
        publish (the in-memory fake) honor it.
        """
        ...

    async def publish_many(
        self,
        stream: str,
        records: Sequence[OutgoingRecord],
        *,
        maxlen: int | None = None,
    ) -> list[Cursor]:
        """Append every record in ``records`` to ``stream`` in one round trip;
        return their cursors in input order.

        Per-key ordering matches :meth:`publish` — records that share a key keep
        publish order within their partition. Additive for callers that already
        hold a batch (a bar flush, a DLQ replay); the single-record
        :meth:`publish`, whose returned cursor the money path threads, is
        unchanged. ``maxlen`` is advisory, exactly as in :meth:`publish`.
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
        """Idempotently prepare the stream/group for consumption (no-op if ready)."""
        ...

    def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        block_ms: int = 5000,
        count: int = 10,
        group_start_id: str = CURSOR_NEW,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        """Durable competing consumption. Yields ``(cursor, value)``; caller MUST
        :meth:`ack`. ``group_start_id`` is where a *brand-new* group begins
        (``CURSOR_BEGIN`` = never miss pre-existing entries; ``CURSOR_NEW`` =
        only-new); ignored once the group exists."""
        ...

    async def ack(self, stream: str, group: str, cursor: Cursor) -> None:
        """Acknowledge a processed entry (commits the group's offset past it)."""
        ...

    async def pause_partition(self, stream: str, group: str, cursor: Cursor) -> None:
        """Stop fetching the partition addressed by ``cursor`` on the group's
        live consumer (a long in-place retry parks just that partition's fetch)."""
        ...

    async def resume_partition(self, stream: str, group: str, cursor: Cursor) -> None:
        """Undo :meth:`pause_partition` for the cursor's partition."""
        ...

    async def pending(self, stream: str, group: str) -> int:
        """Delivered-but-unacked count for the group — the lag signal."""
        ...

    async def trim(self, stream: str, maxlen: int) -> None:
        """Bound the stream length where the backend trims explicitly (no-op on Kafka)."""
        ...

    async def length(self, stream: str) -> int:
        """Number of entries currently retained in ``stream``."""
        ...

    async def purge(self, stream: str, *, up_to_cursor: Cursor | None = None) -> None:
        """Remove entries from ``stream`` (test/operator helper).

        Without ``up_to_cursor`` this deletes to the current end. With it, only
        records at or below that cursor are removed: on Kafka the cursor's
        partition up to and including its offset (other partitions untouched); in
        the fake every entry whose sequence is at or below the cursor. That lets a
        bounded drain (a DLQ replay) clear exactly what it read and leave records
        re-parked at later cursors during the run.
        """
        ...

    async def close(self) -> None:
        """Release transport resources."""
        ...
