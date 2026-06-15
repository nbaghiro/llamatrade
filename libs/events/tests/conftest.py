"""Test harness: an in-memory ``EventTransport`` so the whole lib runs without Redis.

``FakeTransport`` satisfies the same Protocol as ``RedisStreamsTransport`` over plain
dicts. ``tail``/``consume`` drain what's available and stop (instead of blocking),
so ``async for`` terminates in tests; ``consume`` redelivers unacked ("pending")
entries on each call to mimic ``XAUTOCLAIM``, which is what exercises the retry/DLQ
path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

from llamatrade_events.bus import EventBus
from llamatrade_events.transport.base import CURSOR_BEGIN, CURSOR_NEW, Cursor


@dataclass
class _GroupState:
    """A consumer group's read position + its delivered-but-unacked entries."""

    cursor: int = 0
    pending: dict[str, bytes] = field(default_factory=dict)


class FakeTransport:
    """In-memory ``EventTransport`` for unit tests (no Redis)."""

    def __init__(self) -> None:
        self._streams: dict[str, list[tuple[str, bytes]]] = {}
        self._seq = 0
        self._groups: dict[tuple[str, str], _GroupState] = {}
        self.published: list[tuple[str, bytes]] = []
        self.closed = False

    # -- helpers for assertions --

    def entries(self, stream: str) -> list[tuple[str, bytes]]:
        return list(self._streams.get(stream, []))

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
        self.published.append((stream, value))
        return cursor

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
        self._groups.setdefault((stream, group), _GroupState())

    async def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        block_ms: int = 5000,
        count: int = 10,
        claim_min_idle_ms: int = 60_000,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        await self.ensure_group(stream, group)
        state = self._groups[(stream, group)]
        # Redeliver unacked entries first (mimics XAUTOCLAIM of dead-consumer work).
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

    async def pending(self, stream: str, group: str) -> int:
        state = self._groups.get((stream, group))
        return len(state.pending) if state is not None else 0

    async def trim(self, stream: str, maxlen: int) -> None:
        if stream in self._streams:
            del self._streams[stream][:-maxlen]

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def bus(transport: FakeTransport) -> EventBus:
    return EventBus(transport=transport)
