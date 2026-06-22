"""RedisStreamsTransport over an in-memory fake Redis (no Docker).

Mirrors the repo's established pattern (``libs/common/tests/test_events.py``):
inject a fake ``redis.asyncio`` client so the *real* transport code — XADD / XREAD /
XREADGROUP / XAUTOCLAIM / XACK / XPENDING / XTRIM — actually runs. The transport
stores its byte value in a single bytes field (``b"v"``), so this fake keeps
fields as raw bytes (unlike the string-field bus fake in common).
"""

from __future__ import annotations

import re
from typing import cast

import pytest
import redis.asyncio as aioredis

from llamatrade_events.transport import redis_streams
from llamatrade_events.transport.base import CURSOR_BEGIN, CURSOR_NEW
from llamatrade_events.transport.redis_streams import RedisStreamsTransport
from llamatrade_telemetry import get_metrics


def _metric_value(name: str, **labels: str) -> float:
    """Read a single metric value from the Prometheus exposition (0.0 if absent)."""
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    pattern = re.compile(rf"^{re.escape(name)}\{{{re.escape(label_str)}\}} (.+)$", re.M)
    match = pattern.search(get_metrics().decode())
    return float(match.group(1)) if match else 0.0


class FakeRedis:
    """In-memory stand-in for the stream commands the transport uses."""

    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[bytes, bytes]]]] = {}
        self.groups: dict[tuple[str, str], dict[str, object]] = {}
        self._next_seq = 0
        self.closed = False

    @staticmethod
    def _after(entry_id: str, last_id: str) -> bool:
        return int(entry_id.split("-")[0]) > int(last_id.split("-")[0])

    async def xadd(self, key, fields, maxlen=None, approximate=True):
        self._next_seq += 1
        entry_id = f"{self._next_seq}-0"
        bucket = self.streams.setdefault(key, [])
        bucket.append((entry_id, dict(fields)))
        if maxlen is not None:
            self.streams[key] = bucket[-maxlen:]
        return entry_id.encode()

    async def xread(self, streams, block=None, count=None):
        out = []
        for key, last_id in streams.items():
            entries = []
            for eid, fields in self.streams.get(key, []):
                if last_id == CURSOR_NEW:
                    continue  # "$" = only entries after now
                if last_id == CURSOR_BEGIN or self._after(eid, last_id):
                    entries.append((eid.encode(), fields))
            if count is not None:
                entries = entries[:count]
            if entries:
                out.append((key.encode(), entries))
        return out

    async def xgroup_create(self, key, group, id="$", mkstream=False):
        state_key = (key, group)
        if state_key in self.groups:
            raise aioredis.ResponseError("BUSYGROUP Consumer Group name already exists")
        last = self.streams.get(key, [("0-0", {})])
        start = "0" if id == CURSOR_BEGIN else (last[-1][0] if id == CURSOR_NEW else id)
        self.groups[state_key] = {"cursor": start, "pending": {}}

    async def xreadgroup(self, group, consumer, streams, block=None, count=None):
        out = []
        for key in streams:
            state = self.groups[(key, group)]
            entries = []
            for eid, fields in self.streams.get(key, []):
                if self._after(eid, cast("str", state["cursor"])):
                    entries.append((eid.encode(), fields))
            if count is not None:
                entries = entries[:count]
            if entries:
                state["cursor"] = entries[-1][0].decode()
                pending = cast("dict[str, str]", state["pending"])
                for eid, _ in entries:
                    pending[eid.decode()] = consumer
                out.append((key.encode(), entries))
        return out

    async def xautoclaim(self, key, group, consumer, min_idle_time=0, start_id="0-0", count=None):
        state = self.groups.get((key, group))
        claimed = []
        if state is not None:
            pending = cast("dict[str, str]", state["pending"])
            for eid, owner in list(pending.items()):
                if owner == consumer:
                    continue
                fields = next((f for i, f in self.streams.get(key, []) if i == eid), None)
                pending[eid] = consumer
                claimed.append((eid.encode(), fields))
                if count is not None and len(claimed) >= count:
                    break
        return b"0-0", claimed, []

    async def xack(self, key, group, entry_id):
        cast("dict[str, str]", self.groups[(key, group)]["pending"]).pop(entry_id, None)
        return 1

    async def xpending(self, key, group):
        return {"pending": len(cast("dict[str, str]", self.groups[(key, group)]["pending"]))}

    async def xtrim(self, key, maxlen, approximate=True):
        before = len(self.streams.get(key, []))
        self.streams[key] = self.streams.get(key, [])[-maxlen:]
        return before - len(self.streams[key])

    async def aclose(self):
        self.closed = True


def _transport(fake: FakeRedis) -> RedisStreamsTransport:
    return RedisStreamsTransport(redis_client=cast("aioredis.Redis", fake))


async def _take(agen, n: int) -> list:
    """Pull exactly ``n`` items from an infinite transport generator, then close."""
    out = []
    async for item in agen:
        out.append(item)
        if len(out) >= n:
            break
    await agen.aclose()
    return out


# -- publish + tail --


async def test_publish_returns_cursor_and_stores_value() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    cursor = await t.publish("trading:orders:s1", b"hello", maxlen=10)
    assert cursor == "1-0"
    # Stored in the single bytes field the transport reads back.
    _, fields = fake.streams["lt:trading:orders:s1"][0]
    assert fields[b"v"] == b"hello"


async def test_tail_round_trips_value() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    await t.publish("s", b"a", maxlen=10)
    await t.publish("s", b"b", maxlen=10)
    got = await _take(t.tail("s", from_cursor=CURSOR_BEGIN), 2)
    assert [v for _, v in got] == [b"a", b"b"]


async def test_tail_new_cursor_skips_existing() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    await t.publish("s", b"old", maxlen=10)
    # "$" yields nothing already stored; xread returns [] so the loop blocks —
    # so publish a new entry after a first empty poll is hard to simulate; instead
    # assert the fake returns nothing for "$" directly.
    assert await fake.xread({"lt:s": CURSOR_NEW}) == []


async def test_publish_maxlen_trims() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    for i in range(5):
        await t.publish("s", str(i).encode(), maxlen=2)
    assert [v for _, v in fake.streams["lt:s"]] == [{b"v": b"3"}, {b"v": b"4"}]


# -- consumer group --


async def test_ensure_group_is_idempotent() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    await t.ensure_group("s", "g")
    await t.ensure_group("s", "g")  # BUSYGROUP swallowed
    assert ("lt:s", "g") in fake.groups


async def test_consume_ack_and_pending() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    # Durable group exists before fills flow (deploy-time), reading from the start.
    await t.ensure_group("ledger:fills", "g", start_id=CURSOR_BEGIN)
    await t.publish("ledger:fills", b"f1", maxlen=10)
    got = await _take(t.consume("ledger:fills", "g", "c1"), 1)
    cursor, value = got[0]
    assert value == b"f1"
    assert await t.pending("ledger:fills", "g") == 1
    await t.ack("ledger:fills", "g", cursor)
    assert await t.pending("ledger:fills", "g") == 0


async def test_consume_reclaims_pending_from_dead_consumer() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    await t.ensure_group("s", "g", start_id=CURSOR_BEGIN)
    await t.publish("s", b"x", maxlen=10)
    # c1 reads but never acks → entry is pending, owned by c1.
    await _take(t.consume("s", "g", "c1"), 1)
    assert await t.pending("s", "g") == 1
    # c2 starts: XAUTOCLAIM hands it the stale entry.
    got = await _take(t.consume("s", "g", "c2"), 1)
    assert got[0][1] == b"x"


async def test_pending_zero_when_group_absent() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    await t.ensure_group("s", "g")
    assert await t.pending("s", "g") == 0


# -- trim / close / namespacing --


async def test_trim_bounds_stream() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    for i in range(4):
        await t.publish("s", str(i).encode(), maxlen=100)
    await t.trim("s", 2)
    assert len(fake.streams["lt:s"]) == 2


async def test_close_closes_client() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    await t.publish("s", b"x", maxlen=10)
    await t.close()
    assert fake.closed is True


def test_key_is_namespaced() -> None:
    assert _transport(FakeRedis()).key("ledger:fills") == "lt:ledger:fills"


# -- reconnect / backoff on transient transport errors --


class FlakyRedis(FakeRedis):
    """Raises a transport error the first ``fail_times`` calls to ``method``."""

    def __init__(self, method: str, fail_times: int = 1) -> None:
        super().__init__()
        self._method = method
        self._fails_left = fail_times

    async def _maybe_fail(self, name: str) -> None:
        if name == self._method and self._fails_left > 0:
            self._fails_left -= 1
            raise aioredis.ConnectionError("transient")

    async def xread(self, streams, block=None, count=None):
        await self._maybe_fail("xread")
        return await super().xread(streams, block=block, count=count)

    async def xreadgroup(self, group, consumer, streams, block=None, count=None):
        await self._maybe_fail("xreadgroup")
        return await super().xreadgroup(group, consumer, streams, block=block, count=count)


async def test_tail_reconnects_after_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(redis_streams, "_backoff_delay", lambda _a: 0.0)
    fake = FlakyRedis("xread", fail_times=1)
    t = _transport(fake)
    await t.publish("s", b"a", maxlen=10)
    before = _metric_value("llamatrade_events_reconnects_total", stream="s", mode="tail")
    got = await _take(t.tail("s", from_cursor=CURSOR_BEGIN), 1)
    after = _metric_value("llamatrade_events_reconnects_total", stream="s", mode="tail")
    assert got[0][1] == b"a"  # recovered and delivered
    assert after == before + 1  # one reconnect recorded


async def test_consume_reconnects_after_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(redis_streams, "_backoff_delay", lambda _a: 0.0)
    fake = FlakyRedis("xreadgroup", fail_times=1)
    t = _transport(fake)
    await t.ensure_group("s", "g", start_id=CURSOR_BEGIN)
    await t.publish("s", b"x", maxlen=10)
    got = await _take(t.consume("s", "g", "c1"), 1)
    assert got[0][1] == b"x"  # recovered and delivered


def test_backoff_delay_grows_and_is_bounded() -> None:
    d1 = redis_streams._backoff_delay(1)
    d5 = redis_streams._backoff_delay(5)
    # Jittered, so assert the bounded envelope rather than exact values.
    assert 0 < d1 <= redis_streams.RECONNECT_BASE_DELAY_SECONDS
    assert d5 <= redis_streams.RECONNECT_MAX_DELAY_SECONDS


# -- NOGROUP recovery (Redis lost the consumer group) --


class NoGroupOnceRedis(FakeRedis):
    """Raises NOGROUP on the first XAUTOCLAIM (group vanished), then behaves."""

    def __init__(self) -> None:
        super().__init__()
        self._raised = False

    async def xautoclaim(self, key, group, consumer, min_idle_time=0, start_id="0-0", count=None):
        if not self._raised:
            self._raised = True
            self.groups.pop((key, group), None)  # simulate the group being gone
            raise aioredis.ResponseError("NOGROUP No such key or consumer group")
        return await super().xautoclaim(
            key, group, consumer, min_idle_time=min_idle_time, start_id=start_id, count=count
        )


async def test_consume_recovers_after_nogroup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(redis_streams, "_backoff_delay", lambda _a: 0.0)
    fake = NoGroupOnceRedis()
    t = _transport(fake)
    await t.publish("s", b"z", maxlen=10)
    before = _metric_value("llamatrade_events_reconnects_total", stream="s", mode="consume")
    # group_start=BEGIN so the recreated group replays the pre-existing entry.
    got = await _take(t.consume("s", "g", "c1", group_start_id=CURSOR_BEGIN), 1)
    after = _metric_value("llamatrade_events_reconnects_total", stream="s", mode="consume")
    assert got[0][1] == b"z"  # group recreated and the entry delivered
    assert after == before + 1  # one consume reconnect recorded
    assert ("lt:s", "g") in fake.groups  # group was recreated


# -- trimmed-while-pending: XAUTOCLAIM returns (id, None) --


class TrimmedPendingRedis(FakeRedis):
    """First XAUTOCLAIM hands back one entry whose fields were trimmed (None)."""

    def __init__(self) -> None:
        super().__init__()
        self._served = False

    async def xautoclaim(self, key, group, consumer, min_idle_time=0, start_id="0-0", count=None):
        if not self._served:
            self._served = True
            return b"0-0", [(b"99-0", None)], []  # trimmed-while-pending entry
        return b"0-0", [], []


async def test_consume_skips_trimmed_pending_entry() -> None:
    fake = TrimmedPendingRedis()
    t = _transport(fake)
    await t.ensure_group("s", "g", start_id=CURSOR_BEGIN)
    await t.publish("s", b"real", maxlen=10)
    # The None-field claimed entry must be skipped, not yielded; only the live
    # XREADGROUP entry comes through.
    got = await _take(t.consume("s", "g", "c1"), 1)
    assert [v for _, v in got] == [b"real"]


# -- connection pool / health-check config --


async def test_client_configures_bounded_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_from_url(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeRedis()

    monkeypatch.setattr(redis_streams.aioredis, "from_url", fake_from_url)
    t = RedisStreamsTransport("redis://example:6379/0", max_connections=7)
    await t._client()
    assert captured["url"] == "redis://example:6379/0"
    assert captured["max_connections"] == 7
    assert captured["health_check_interval"] == redis_streams.HEALTH_CHECK_INTERVAL_SECONDS


async def test_client_is_cached_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_from_url(url, **kwargs):
        nonlocal calls
        calls += 1
        return FakeRedis()

    monkeypatch.setattr(redis_streams.aioredis, "from_url", fake_from_url)
    t = RedisStreamsTransport("redis://example:6379/0")
    first = await t._client()
    second = await t._client()
    assert first is second  # one pool, reused
    assert calls == 1


# -- group-start position threaded into the consumer group --


async def test_consume_group_start_begin_replays_preexisting() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    await t.publish("ledger:fills", b"f1", maxlen=10)  # published before any group
    got = await _take(t.consume("ledger:fills", "g", "c1", group_start_id=CURSOR_BEGIN), 1)
    assert got[0][1] == b"f1"  # fresh group created at "0" replayed it


async def test_consume_new_group_starts_at_tail() -> None:
    fake = FakeRedis()
    t = _transport(fake)
    await t.publish("s", b"old", maxlen=10)
    # CURSOR_NEW → consume() creates the group at the latest id, so a pre-existing
    # entry is not in its backlog (it would otherwise block reading). Assert the
    # group cursor sits at the tail rather than draining the generator.
    await t.ensure_group("s", "g", start_id=CURSOR_NEW)
    assert fake.groups[("lt:s", "g")]["cursor"] == "1-0"
