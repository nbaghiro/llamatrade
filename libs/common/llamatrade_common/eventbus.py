"""EventBus — Redis Streams transport for inter-service events.

Replaces fire-and-forget pub/sub on the channels where durability and
multiple consumers matter (see .docs/planning/redis-streams-migration.md).
Two delivery modes, matching the two shapes of "multiple consumers":

- :meth:`tail` — independent fan-out via ``XREAD`` (no group). Every caller
  sees the full stream; a reconnecting client passes its last-seen entry id
  back and replays the gap. For live UI streams.
- :meth:`consume` — durable competing consumption via ``XREADGROUP`` +
  :meth:`ack`, with periodic ``XAUTOCLAIM`` so entries pending on a dead
  consumer are reclaimed. Each *group* gets every entry at least once; the
  consumer dedupes (the ledger already does, by ``event_id``). For backends.

The bus is payload-agnostic: entries are flat ``dict[str, str]`` fields —
Redis Streams' native model — so locked wire contracts (e.g. the ledger fill
payload, CONTRACTS.md §1) cross without translation. The shared
``llamatrade_common.events.Event`` model plugs in via its
``to_redis_stream()`` / ``from_redis_stream()`` codec.

Streams are transport, not the book of record: producers and consumers are
Postgres-durable on both ends, so ``MAXLEN ~ N`` trimming is safe.

This lib is service-agnostic (same rule as ``llamatrade_alpaca``): it must
not import from any service.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from collections.abc import AsyncIterator
from typing import cast

import redis.asyncio as aioredis
from prometheus_client import Counter
from redis.typing import EncodableT, FieldT

logger = logging.getLogger(__name__)

# Labeled by the stream's logical prefix (e.g. "trading:orders"), never the
# full per-session key — bounded metric cardinality.
EVENTBUS_PUBLISHED_TOTAL = Counter(
    "eventbus_published_total",
    "Entries published to Redis Streams via the EventBus",
    ["stream"],
)
EVENTBUS_RECONNECTS_TOTAL = Counter(
    "eventbus_reconnects_total",
    "Transport-error reconnects in EventBus readers",
    ["stream", "mode"],  # mode: tail / consume
)


def _stream_label(stream: str) -> str:
    return ":".join(stream.split(":")[:2])


DEFAULT_NAMESPACE = "lt"
RECONNECT_BASE_DELAY_SECONDS = 1.0
RECONNECT_MAX_DELAY_SECONDS = 30.0


def _decode_fields(raw: dict[bytes | str, bytes | str]) -> dict[str, str]:
    """Stream entries arrive as bytes unless decode_responses is set."""
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in raw.items()
    }


def _decode_id(entry_id: bytes | str) -> str:
    return entry_id.decode() if isinstance(entry_id, bytes) else entry_id


class EventBus:
    """Redis Streams transport: publish, tail (fan-out), consume (durable)."""

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        namespace: str = DEFAULT_NAMESPACE,
        redis_client: aioredis.Redis | None = None,
    ) -> None:
        self._redis: aioredis.Redis | None = redis_client
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._namespace = namespace

    def key(self, stream: str) -> str:
        """The namespaced Redis key for a logical stream name."""
        return f"{self._namespace}:{stream}"

    async def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url)
        return self._redis

    async def publish(
        self,
        stream: str,
        fields: dict[str, str],
        *,
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str:
        """XADD the fields; returns the assigned stream entry id.

        ``maxlen`` bounds the stream (approximate trim by default) — safe
        because the durable record lives in Postgres on both ends.
        """
        redis = await self._client()
        entry_id = await redis.xadd(
            self.key(stream),
            cast("dict[FieldT, EncodableT]", fields),
            maxlen=maxlen,
            approximate=approximate,
        )
        EVENTBUS_PUBLISHED_TOTAL.labels(stream=_stream_label(stream)).inc()
        return _decode_id(entry_id)

    async def tail(
        self,
        stream: str,
        *,
        last_id: str = "$",
        block_ms: int = 5000,
        count: int = 100,
    ) -> AsyncIterator[tuple[str, dict[str, str]]]:
        """Independent fan-out via XREAD (no group). Yields (entry_id, fields).

        Every tailer sees the full stream. Persist the yielded ``entry_id``
        and pass it back as ``last_id`` on reconnect to replay the gap —
        ``"$"`` starts from new entries only, ``"0"`` replays from the start.
        Transport errors retry with exponential backoff + jitter; the cursor
        is preserved across reconnects.
        """
        cursor = last_id
        attempt = 0
        while True:
            try:
                redis = await self._client()
                response = await redis.xread(
                    {self.key(stream): cursor}, block=block_ms, count=count
                )
                attempt = 0
                if not response:
                    continue
                for _, entries in response:
                    for entry_id, raw in entries:
                        decoded_id = _decode_id(entry_id)
                        cursor = decoded_id
                        yield decoded_id, _decode_fields(raw)
            except asyncio.CancelledError:
                raise
            except Exception:
                attempt += 1
                EVENTBUS_RECONNECTS_TOTAL.labels(stream=_stream_label(stream), mode="tail").inc()
                delay = _backoff_delay(attempt)
                logger.warning(
                    "tail(%s) transport error; retrying in %.1fs", stream, delay, exc_info=True
                )
                await asyncio.sleep(delay)

    async def ensure_group(self, stream: str, group: str, *, start_id: str = "$") -> None:
        """Idempotent ``XGROUP CREATE … MKSTREAM`` (BUSYGROUP is success)."""
        redis = await self._client()
        try:
            await redis.xgroup_create(self.key(stream), group, id=start_id, mkstream=True)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        block_ms: int = 5000,
        count: int = 10,
        claim_min_idle_ms: int = 60_000,
    ) -> AsyncIterator[tuple[str, dict[str, str]]]:
        """Durable consumption via XREADGROUP. Yields (entry_id, fields).

        The caller MUST :meth:`ack` each processed entry — unacked entries
        stay pending and are redelivered. Before each read, entries pending
        longer than ``claim_min_idle_ms`` on *other* (dead) consumers are
        reclaimed via XAUTOCLAIM, so a crashed pod's work is taken over.
        Delivery is at-least-once: consumers dedupe by their own idempotency
        key. Run a single active consumer per group when per-key ordering
        matters (e.g. the ledger's per-account FIFO).
        """
        await self.ensure_group(stream, group)
        key = self.key(stream)
        attempt = 0
        while True:
            try:
                redis = await self._client()

                # Take over stale pending entries from dead consumers first.
                _, claimed, _ = await redis.xautoclaim(
                    key, group, consumer, min_idle_time=claim_min_idle_ms, count=count
                )
                for entry_id, raw in claimed:
                    if raw is None:
                        continue  # entry trimmed while pending; nothing to process
                    yield _decode_id(entry_id), _decode_fields(raw)

                response = await redis.xreadgroup(
                    group, consumer, {key: ">"}, block=block_ms, count=count
                )
                attempt = 0
                if not response:
                    continue
                for _, entries in response:
                    for entry_id, raw in entries:
                        yield _decode_id(entry_id), _decode_fields(raw)
            except asyncio.CancelledError:
                raise
            except Exception:
                attempt += 1
                EVENTBUS_RECONNECTS_TOTAL.labels(stream=_stream_label(stream), mode="consume").inc()
                delay = _backoff_delay(attempt)
                logger.warning(
                    "consume(%s, group=%s) transport error; retrying in %.1fs",
                    stream,
                    group,
                    delay,
                    exc_info=True,
                )
                await asyncio.sleep(delay)

    async def ack(self, stream: str, group: str, entry_id: str) -> None:
        """XACK a processed entry (removes it from the group's pending list)."""
        redis = await self._client()
        await redis.xack(self.key(stream), group, entry_id)

    async def pending_count(self, stream: str, group: str) -> int:
        """Number of delivered-but-unacked entries (the group's lag signal)."""
        redis = await self._client()
        info = await redis.xpending(self.key(stream), group)
        pending = info.get("pending", 0) if isinstance(info, dict) else 0
        return int(pending)

    async def trim(self, stream: str, maxlen: int, *, approximate: bool = True) -> None:
        """Bound the stream length (XTRIM MAXLEN)."""
        redis = await self._client()
        await redis.xtrim(self.key(stream), maxlen=maxlen, approximate=approximate)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter (mirrors llamatrade_alpaca.streaming)."""
    base = min(RECONNECT_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), RECONNECT_MAX_DELAY_SECONDS)
    return base * (0.5 + random.random() / 2)
