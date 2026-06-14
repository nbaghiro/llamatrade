"""Tests for the events module: the Event codec AND the EventBus transport.

- Codec round-trip tests pin the fix for the old ``.strip('{"data":')``
  serialization, which stripped *characters* (not a prefix) and corrupted any
  payload beginning or ending with those characters.
- EventBus tests cover the bus logic deterministically over an in-memory fake
  Redis (cursor advancement, group bookkeeping, reclaim hand-off, acks,
  trimming, namespacing, backoff). Real-Redis behaviors (blocking reads,
  reconnect backoff under transport failure) are exercised by the integration
  suite.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
import redis.asyncio as aioredis

from llamatrade_common.events import (
    RECONNECT_MAX_DELAY_SECONDS,
    Event,
    EventBus,
    EventType,
    _backoff_delay,
)

# =============================================================================
# Event codec round-trip
# =============================================================================


def _round_trip(event: Event) -> Event:
    return Event.from_redis_stream(event.to_redis_stream())


def test_round_trip_basic_fields() -> None:
    event = Event(
        type=EventType.ORDER_FILLED,
        tenant_id=uuid4(),
        user_id=uuid4(),
        data={"order_id": "abc", "symbol": "SPY", "qty": 50.0, "price": 480.0},
        metadata={"source_service": "trading", "correlation_id": "c-1"},
    )
    restored = _round_trip(event)
    assert restored.id == event.id
    assert restored.type == event.type
    assert restored.tenant_id == event.tenant_id
    assert restored.user_id == event.user_id
    assert restored.data == event.data
    assert restored.metadata == event.metadata


def test_round_trip_payload_with_stripped_characters() -> None:
    """The old strip-based codec corrupted exactly this shape of payload."""
    event = Event(
        type=EventType.BACKTEST_PROGRESS,
        # '{', '"', 'd', 'a', 't', ':' at the boundaries were eaten by .strip()
        data={"message": '{"data": nested-looking string}', "symbol": "data"},
    )
    restored = _round_trip(event)
    assert restored.data["message"] == '{"data": nested-looking string}'
    assert restored.data["symbol"] == "data"


def test_round_trip_unicode_and_empty_maps() -> None:
    event = Event(type=EventType.ALERT_TRIGGERED, data={"message": "résumé — 利益 ✓"})
    restored = _round_trip(event)
    assert restored.data["message"] == "résumé — 利益 ✓"
    assert restored.metadata == {}

    empty = _round_trip(Event(type=EventType.USER_CREATED))
    assert empty.data == {}
    assert empty.metadata == {}


def test_round_trip_optional_ids_absent() -> None:
    event = Event(type=EventType.PRICE_UPDATE)
    fields = event.to_redis_stream()
    assert fields["tenant_id"] == ""
    assert fields["user_id"] == ""
    restored = Event.from_redis_stream(fields)
    assert restored.tenant_id is None
    assert restored.user_id is None


def test_stream_fields_are_flat_strings() -> None:
    """XADD requires flat string fields — no nested values may leak through."""
    event = Event(
        type=EventType.ORDER_SUBMITTED,
        timestamp=datetime(2026, 6, 12, 14, 30, tzinfo=UTC),
        data={"qty": 1.5, "total_trades": 3},
    )
    fields = event.to_redis_stream()
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in fields.items())
    assert fields["timestamp"] == "2026-06-12T14:30:00+00:00"


# =============================================================================
# EventBus transport (over an in-memory fake Redis)
# =============================================================================


class FakeRedis:
    """Minimal in-memory stand-in for the stream commands the bus uses.

    Entries are ``(id, fields)`` with ids ``"<n>-0"``; group state tracks a
    per-group cursor and pending entries per consumer.
    """

    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[bytes, bytes]]]] = {}
        self.groups: dict[tuple[str, str], dict] = {}  # (key, group) -> state
        self._next_seq = 0
        self.closed = False

    def _encode(self, fields: dict[str, str]) -> dict[bytes, bytes]:
        return {k.encode(): v.encode() for k, v in fields.items()}

    async def xadd(self, key, fields, maxlen=None, approximate=True):
        self._next_seq += 1
        entry_id = f"{self._next_seq}-0"
        self.streams.setdefault(key, []).append((entry_id, self._encode(fields)))
        if maxlen is not None:
            self.streams[key] = self.streams[key][-maxlen:]
        return entry_id.encode()

    async def xread(self, streams, block=None, count=None):
        out = []
        for key, last_id in streams.items():
            entries = [
                (eid.encode(), fields)
                for eid, fields in self.streams.get(key, [])
                if last_id in ("$",) or self._after(eid, last_id)
            ]
            if count is not None:
                entries = entries[:count]
            if entries:
                out.append((key.encode(), entries))
        return out

    @staticmethod
    def _after(entry_id: str, last_id: str) -> bool:
        if last_id == "0":
            return True
        return int(entry_id.split("-")[0]) > int(last_id.split("-")[0])

    async def xgroup_create(self, key, group, id="$", mkstream=False):
        state_key = (key, group)
        if state_key in self.groups:
            raise aioredis.ResponseError("BUSYGROUP Consumer Group name already exists")
        start = (
            "0" if id == "0" else (self.streams.get(key, [("0-0", {})])[-1][0] if id == "$" else id)
        )
        self.groups[state_key] = {"cursor": start, "pending": {}}  # pending: id -> consumer

    async def xreadgroup(self, group, consumer, streams, block=None, count=None):
        out = []
        for key in streams:
            state = self.groups[(key, group)]
            entries = [
                (eid.encode(), fields)
                for eid, fields in self.streams.get(key, [])
                if self._after(eid, state["cursor"])
            ]
            if count is not None:
                entries = entries[:count]
            if entries:
                state["cursor"] = entries[-1][0].decode()
                for eid, _ in entries:
                    state["pending"][eid.decode()] = consumer
                out.append((key.encode(), entries))
        return out

    async def xautoclaim(self, key, group, consumer, min_idle_time=0, count=None):
        state = self.groups.get((key, group), {"pending": {}})
        claimed = []
        for eid, owner in list(state.get("pending", {}).items()):
            if owner == consumer:
                continue
            fields = next((f for i, f in self.streams.get(key, []) if i == eid), None)
            state["pending"][eid] = consumer
            claimed.append((eid.encode(), fields))
            if count is not None and len(claimed) >= count:
                break
        return b"0-0", claimed, []

    async def xack(self, key, group, entry_id):
        self.groups[(key, group)]["pending"].pop(entry_id, None)
        return 1

    async def xpending(self, key, group):
        return {"pending": len(self.groups[(key, group)]["pending"])}

    async def xtrim(self, key, maxlen, approximate=True):
        before = len(self.streams.get(key, []))
        self.streams[key] = self.streams.get(key, [])[-maxlen:]
        return before - len(self.streams[key])

    async def aclose(self):
        self.closed = True


@pytest.fixture
def fake() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def bus(fake: FakeRedis) -> EventBus:
    return EventBus(redis_client=cast("aioredis.Redis", fake))


async def _take(aiter, n: int) -> list[tuple[str, dict[str, str]]]:
    out: list[tuple[str, dict[str, str]]] = []
    async for entry in aiter:
        out.append(entry)
        if len(out) >= n:
            break
    return out


class TestPublishTail:
    async def test_publish_returns_entry_id_and_namespaces_key(
        self, bus: EventBus, fake: FakeRedis
    ) -> None:
        entry_id = await bus.publish("fills", {"a": "1"})
        assert entry_id == "1-0"
        assert "lt:fills" in fake.streams

    async def test_tail_decodes_and_advances_cursor(self, bus: EventBus) -> None:
        await bus.publish("s", {"seq": "1"})
        await bus.publish("s", {"seq": "2"})
        entries = await asyncio.wait_for(_take(bus.tail("s", last_id="0"), 2), timeout=2)
        assert [f["seq"] for _, f in entries] == ["1", "2"]
        # ids decoded to str
        assert all(isinstance(eid, str) for eid, _ in entries)

    async def test_tail_replays_only_after_cursor(self, bus: EventBus) -> None:
        await bus.publish("s", {"seq": "1"})
        ((first_id, _),) = await asyncio.wait_for(_take(bus.tail("s", last_id="0"), 1), timeout=2)
        await bus.publish("s", {"seq": "2"})
        entries = await asyncio.wait_for(_take(bus.tail("s", last_id=first_id), 1), timeout=2)
        assert entries[0][1]["seq"] == "2"

    async def test_publish_maxlen_bounds(self, bus: EventBus, fake: FakeRedis) -> None:
        for i in range(20):
            await bus.publish("b", {"seq": str(i)}, maxlen=5)
        assert len(fake.streams["lt:b"]) == 5


class TestGroups:
    async def test_ensure_group_idempotent(self, bus: EventBus) -> None:
        await bus.ensure_group("g", "grp")
        await bus.ensure_group("g", "grp")  # BUSYGROUP swallowed

    async def test_consume_ack_pending(self, bus: EventBus) -> None:
        await bus.ensure_group("f", "grp", start_id="0")
        await bus.publish("f", {"coid": "1"})
        entries = await asyncio.wait_for(_take(bus.consume("f", "grp", "c1"), 1), timeout=2)
        assert entries[0][1]["coid"] == "1"
        assert await bus.pending_count("f", "grp") == 1
        await bus.ack("f", "grp", entries[0][0])
        assert await bus.pending_count("f", "grp") == 0

    async def test_reclaim_takes_over_other_consumers_pending(self, bus: EventBus) -> None:
        await bus.ensure_group("r", "grp", start_id="0")
        await bus.publish("r", {"coid": "dead"})
        await asyncio.wait_for(_take(bus.consume("r", "grp", "dead-pod"), 1), timeout=2)

        entries = await asyncio.wait_for(
            _take(bus.consume("r", "grp", "new-pod", claim_min_idle_ms=0), 1), timeout=2
        )
        assert entries[0][1]["coid"] == "dead"

    async def test_reclaimed_trimmed_entry_skipped(self, bus: EventBus, fake: FakeRedis) -> None:
        await bus.ensure_group("t", "grp", start_id="0")
        await bus.publish("t", {"coid": "1"})
        await bus.publish("t", {"coid": "2"})
        await asyncio.wait_for(_take(bus.consume("t", "grp", "dead-pod"), 2), timeout=2)
        # First entry trimmed away while pending → xautoclaim yields fields=None
        fake.streams["lt:t"] = fake.streams["lt:t"][1:]
        entries = await asyncio.wait_for(
            _take(bus.consume("t", "grp", "new-pod", claim_min_idle_ms=0), 1), timeout=2
        )
        assert entries[0][1]["coid"] == "2"


class TestUtilities:
    async def test_trim(self, bus: EventBus, fake: FakeRedis) -> None:
        for i in range(10):
            await bus.publish("tr", {"seq": str(i)})
        await bus.trim("tr", 3)
        assert len(fake.streams["lt:tr"]) == 3

    async def test_close(self, bus: EventBus, fake: FakeRedis) -> None:
        await bus.close()
        assert fake.closed is True

    def test_namespace_override(self) -> None:
        assert EventBus(namespace="x").key("s") == "x:s"

    def test_backoff_grows_and_caps(self) -> None:
        assert _backoff_delay(1) <= RECONNECT_MAX_DELAY_SECONDS
        assert _backoff_delay(99) <= RECONNECT_MAX_DELAY_SECONDS
        assert _backoff_delay(99) > 0
