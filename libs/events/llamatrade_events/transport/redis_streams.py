"""Redis Streams implementation of :class:`EventTransport`.

The byte value rides in a single stream field (``v``); everything else is the
Redis Streams primitives the previous ``EventBus`` already used (XADD, XREAD,
XREADGROUP, XACK, XAUTOCLAIM, XTRIM), with exponential-backoff reconnects.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
from collections.abc import AsyncIterator
from typing import cast

import redis.asyncio as aioredis
from redis.typing import EncodableT, FieldT

from llamatrade_events.observability import (
    EVENTS_PUBLISHED_TOTAL,
    EVENTS_RECONNECTS_TOTAL,
    stream_label,
)
from llamatrade_events.transport.base import CURSOR_NEW, Cursor

logger = logging.getLogger(__name__)

_VALUE_FIELD = b"v"
DEFAULT_NAMESPACE = "lt"
RECONNECT_BASE_DELAY_SECONDS = 1.0
RECONNECT_MAX_DELAY_SECONDS = 30.0
# Bound the pool so a fleet of concurrent blocking readers (per-session UI tails
# each hold a connection for ``block_ms``) can't open unbounded sockets to Redis.
DEFAULT_MAX_CONNECTIONS = 64
# Ping idle pooled connections so a Redis restart/failover surfaces as a clean
# reconnect rather than a stale-socket error on the next command.
HEALTH_CHECK_INTERVAL_SECONDS = 30


def _decode_id(entry_id: bytes | str) -> str:
    return entry_id.decode() if isinstance(entry_id, bytes) else entry_id


def _backoff_delay(attempt: int) -> float:
    base = min(RECONNECT_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), RECONNECT_MAX_DELAY_SECONDS)
    return base * (0.5 + random.random() / 2)


def _value(raw: dict[bytes | str, bytes | str]) -> bytes:
    v = raw.get(_VALUE_FIELD) if _VALUE_FIELD in raw else raw.get("v", b"")
    return v if isinstance(v, bytes) else str(v).encode()


class RedisStreamsTransport:
    """`EventTransport` over Redis Streams (the default backend)."""

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        namespace: str = DEFAULT_NAMESPACE,
        redis_client: aioredis.Redis | None = None,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
    ) -> None:
        self._redis: aioredis.Redis | None = redis_client
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._namespace = namespace
        self._max_connections = max_connections

    def key(self, stream: str) -> str:
        """The namespaced Redis key for a logical stream name."""
        return f"{self._namespace}:{stream}"

    async def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url,
                max_connections=self._max_connections,
                health_check_interval=HEALTH_CHECK_INTERVAL_SECONDS,
            )
        return self._redis

    async def publish(
        self,
        stream: str,
        value: bytes,
        *,
        key: str | None = None,
        maxlen: int | None = None,
    ) -> Cursor:
        # `key` (partition/ordering key) is unused on single-stream Redis; Kafka
        # would route on it. Part of the EventTransport signature, kept for parity.
        del key
        redis = await self._client()
        fields = cast("dict[FieldT, EncodableT]", {_VALUE_FIELD: value})
        entry_id = await redis.xadd(self.key(stream), fields, maxlen=maxlen, approximate=True)
        EVENTS_PUBLISHED_TOTAL.labels(stream=stream_label(stream)).inc()
        return _decode_id(entry_id)

    async def tail(
        self,
        stream: str,
        *,
        from_cursor: Cursor = CURSOR_NEW,
        block_ms: int = 5000,
        count: int = 100,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        cursor = from_cursor
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
                        cursor = _decode_id(entry_id)
                        yield cursor, _value(raw)
            except asyncio.CancelledError:
                raise
            except Exception:
                attempt += 1
                EVENTS_RECONNECTS_TOTAL.labels(stream=stream_label(stream), mode="tail").inc()
                delay = _backoff_delay(attempt)
                logger.warning("tail(%s) transport error; retrying in %.1fs", stream, delay)
                await asyncio.sleep(delay)

    async def ensure_group(self, stream: str, group: str, *, start_id: str = CURSOR_NEW) -> None:
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
        group_start_id: str = CURSOR_NEW,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        await self.ensure_group(stream, group, start_id=group_start_id)
        key = self.key(stream)
        attempt = 0
        # XAUTOCLAIM scan position; "0-0" restarts the PEL scan. Threading it
        # lets a large pending list drain across iterations rather than
        # re-scanning from the start every pass.
        claim_cursor = "0-0"
        while True:
            try:
                redis = await self._client()
                # Reclaim entries left pending by a dead consumer (idle past the
                # threshold) — this is also how THIS consumer's own un-acked
                # (failed) entries get redelivered.
                next_cursor, claimed, _ = await redis.xautoclaim(
                    key,
                    group,
                    consumer,
                    min_idle_time=claim_min_idle_ms,
                    count=count,
                    start_id=claim_cursor,
                )
                claim_cursor = _decode_id(next_cursor)
                for entry_id, raw in claimed:
                    if raw is None:
                        continue  # entry trimmed while pending
                    yield _decode_id(entry_id), _value(raw)

                response = await redis.xreadgroup(
                    group, consumer, {key: ">"}, block=block_ms, count=count
                )
                attempt = 0
                if not response:
                    continue
                for _, entries in response:
                    for entry_id, raw in entries:
                        yield _decode_id(entry_id), _value(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempt += 1
                # Redis lost the group (restart without AOF / failover to an
                # empty replica): recreate it so we resume instead of looping on
                # NOGROUP forever.
                if isinstance(exc, aioredis.ResponseError) and "NOGROUP" in str(exc):
                    claim_cursor = "0-0"
                    with contextlib.suppress(Exception):
                        await self.ensure_group(stream, group, start_id=group_start_id)
                    logger.warning(
                        "consume(%s, group=%s): group recreated after NOGROUP", stream, group
                    )
                EVENTS_RECONNECTS_TOTAL.labels(stream=stream_label(stream), mode="consume").inc()
                delay = _backoff_delay(attempt)
                logger.warning(
                    "consume(%s, group=%s) transport error; retrying in %.1fs", stream, group, delay
                )
                await asyncio.sleep(delay)

    async def ack(self, stream: str, group: str, cursor: Cursor) -> None:
        redis = await self._client()
        await redis.xack(self.key(stream), group, cursor)

    async def pending(self, stream: str, group: str) -> int:
        redis = await self._client()
        info = await redis.xpending(self.key(stream), group)
        return int(info.get("pending", 0)) if isinstance(info, dict) else 0

    async def trim(self, stream: str, maxlen: int) -> None:
        redis = await self._client()
        await redis.xtrim(self.key(stream), maxlen=maxlen, approximate=True)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
