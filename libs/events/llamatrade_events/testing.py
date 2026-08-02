"""In-memory :class:`EventTransport` for tests — the whole lib runs without a broker.

``FakeTransport`` satisfies the same Protocol as :class:`KafkaTransport` over plain
dicts. ``tail``/``consume`` drain what's available and stop (instead of blocking),
so ``async for`` terminates in tests; ``consume`` redelivers unacked ("pending")
entries on each call to mimic dead-consumer reclaim, which exercises the retry/DLQ
path. Shipped with the lib so consuming services reuse it instead of hand-rolling a
fake.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from llamatrade_events.transport.base import CURSOR_BEGIN, CURSOR_NEW, Cursor, OutgoingRecord


@dataclass
class _GroupState:
    """A consumer group's read position + its delivered-but-unacked entries."""

    cursor: int = 0
    pending: dict[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishRecord:
    """A captured ``publish`` call (stream, value, partition key)."""

    stream: str
    value: bytes
    key: str | None


class FakeTransport:
    """In-memory ``EventTransport`` for unit tests (no broker)."""

    def __init__(self) -> None:
        self._streams: dict[str, list[tuple[str, bytes]]] = {}
        self._seq = 0
        self._groups: dict[tuple[str, str], _GroupState] = {}
        self.records: list[PublishRecord] = []
        self.pause_calls: list[tuple[str, str, Cursor]] = []
        self.resume_calls: list[tuple[str, str, Cursor]] = []
        self.paused: set[tuple[str, str]] = set()
        # Failure injection: length() raises the mapped error for that stream.
        self.length_errors: dict[str, Exception] = {}
        self.closed = False

    # -- helpers for assertions --

    @property
    def published(self) -> list[tuple[str, bytes]]:
        return [(r.stream, r.value) for r in self.records]

    def entries(self, stream: str) -> list[tuple[str, bytes]]:
        return list(self._streams.get(stream, []))

    async def length(self, stream: str) -> int:
        error = self.length_errors.get(stream)
        if error is not None:
            raise error
        return len(self._streams.get(stream, []))

    async def purge(self, stream: str, *, up_to_cursor: Cursor | None = None) -> None:
        if up_to_cursor is None:
            self._streams.pop(stream, None)
            return
        bound = int(up_to_cursor)
        entries = self._streams.get(stream)
        if entries is not None:
            self._streams[stream] = [(c, v) for c, v in entries if int(c) > bound]

    # -- EventTransport --

    async def publish(
        self,
        stream: str,
        value: bytes,
        *,
        key: str | None = None,
        maxlen: int | None = None,
    ) -> Cursor:
        self._seq += 1
        cursor = str(self._seq)
        bucket = self._streams.setdefault(stream, [])
        bucket.append((cursor, value))
        if maxlen is not None and len(bucket) > maxlen:
            del bucket[:-maxlen]
        self.records.append(PublishRecord(stream, value, key))
        return cursor

    async def publish_many(
        self,
        stream: str,
        records: Sequence[OutgoingRecord],
        *,
        maxlen: int | None = None,
    ) -> list[Cursor]:
        return [await self.publish(stream, r.value, key=r.key, maxlen=maxlen) for r in records]

    async def tail(
        self,
        stream: str,
        *,
        from_cursor: Cursor = CURSOR_NEW,
        block_ms: int = 5000,
        count: int = 100,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        if from_cursor == CURSOR_NEW:
            start = self._seq  # only entries published after "now"
        elif from_cursor == CURSOR_BEGIN:
            start = 0
        else:
            start = int(from_cursor)
        for cursor, value in self.entries(stream):
            if int(cursor) > start:
                yield cursor, value

    async def ensure_group(self, stream: str, group: str, *, start_id: str = CURSOR_NEW) -> None:
        if (stream, group) not in self._groups:
            # CURSOR_NEW = only entries after now; CURSOR_BEGIN = replay all.
            cursor = self._seq if start_id == CURSOR_NEW else 0
            self._groups[(stream, group)] = _GroupState(cursor=cursor)

    async def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        block_ms: int = 5000,
        count: int = 10,
        group_start_id: str = CURSOR_NEW,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        await self.ensure_group(stream, group, start_id=group_start_id)
        state = self._groups[(stream, group)]
        # Redeliver unacked entries first (mimics reclaim of dead-consumer work).
        for cursor, value in list(state.pending.items()):
            yield cursor, value
        for cursor, value in self.entries(stream):
            if int(cursor) > state.cursor:
                state.cursor = int(cursor)
                state.pending[cursor] = value
                yield cursor, value

    async def ack(self, stream: str, group: str, cursor: Cursor) -> None:
        state = self._groups.get((stream, group))
        if state is not None:
            state.pending.pop(cursor, None)

    async def pause_partition(self, stream: str, group: str, cursor: Cursor) -> None:
        self.pause_calls.append((stream, group, cursor))
        self.paused.add((stream, group))

    async def resume_partition(self, stream: str, group: str, cursor: Cursor) -> None:
        self.resume_calls.append((stream, group, cursor))
        self.paused.discard((stream, group))

    async def pending(self, stream: str, group: str) -> int:
        state = self._groups.get((stream, group))
        return len(state.pending) if state is not None else 0

    async def trim(self, stream: str, maxlen: int) -> None:
        if stream in self._streams:
            del self._streams[stream][:-maxlen]

    async def close(self) -> None:
        self.closed = True
