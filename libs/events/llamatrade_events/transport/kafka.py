"""Kafka implementation of :class:`EventTransport` (GCP Managed Service for Apache Kafka).

One adapter satisfies the whole port; every layer above (bus, codec, catalog,
consumer, fan-out) is unchanged:

- ``publish``  → producer ``send`` (idempotent, ``acks=all``), partitioned by ``key``.
- ``publish_many`` → ``send`` every record, then await the futures together, so a
  caller that already holds a batch gets one produce round trip, not one per record.
- ``tail``     → an *own-group* consumer (``group_id=None``) over all partitions;
  per-entity streams filter to their routing key.
- ``consume``  → a *shared-group* consumer; the group coordinator reassigns a dead
  member's partitions automatically.
- ``ack``      → commit ``offset+1`` on the group consumer (held in a registry).
- ``pending``  → consumer-group lag (end − committed).

``tail`` and ``consume`` reconnect on broker errors with capped, jittered
exponential backoff (counted by ``EVENTS_RECONNECTS_TOTAL``), so one transient
fault never ends a reader.

Auth: PLAINTEXT locally; SASL_SSL/OAUTHBEARER against GCP, with tokens minted from
Application Default Credentials (Workload Identity in GKE) — no static secrets.
Every client start is bounded and then proven live (see :meth:`KafkaTransport._start_client`),
because a rejected token authenticates without an error on the wire.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, TypedDict

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, OffsetAndMetadata, TopicPartition
from aiokafka.abc import AbstractTokenProvider
from aiokafka.admin import AIOKafkaAdminClient, NewTopic, RecordsToDelete
from aiokafka.errors import KafkaError
from aiokafka.structs import RecordMetadata

from llamatrade_events.channels import resolve_topic
from llamatrade_events.observability import (
    EVENTS_BROKEN_CREDENTIALS_TOTAL,
    EVENTS_CLIENT_START_FAILURES_TOTAL,
    EVENTS_PUBLISH_FAILURES_TOTAL,
    EVENTS_PUBLISHED_TOTAL,
    EVENTS_RECONNECTS_TOTAL,
    stream_label,
)
from llamatrade_events.transport.base import CURSOR_BEGIN, CURSOR_NEW, Cursor, OutgoingRecord

if TYPE_CHECKING:
    from google.auth.credentials import Credentials

logger = logging.getLogger(__name__)

DEFAULT_NAMESPACE = "lt"
DEFAULT_BOOTSTRAP = "localhost:9092"
# GCP Managed Kafka authenticates OAUTHBEARER with a cloud-platform-scoped token.
_GCP_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# Long in-place retries (ledger fills during a DB outage) must not get the member
# evicted for not polling; 30 minutes bounds a rebalance-free recovery window.
DEFAULT_MAX_POLL_INTERVAL_MS = 1_800_000
RECONNECT_BASE_DELAY_SECONDS = 0.5
RECONNECT_MAX_DELAY_SECONDS = 30.0
# A connect + SASL handshake + metadata round-trip; anything slower is a stall.
DEFAULT_CLIENT_START_TIMEOUT_SECONDS = 30.0
# Consecutive failures to start a reader before the run is called out as broken
# credentials rather than a transient fault.
DEFAULT_AUTH_FAILURE_ALERT_THRESHOLD = 5

# Producer batching: linger briefly so records enqueued together through
# publish_many (a bar flush) coalesce into one produce request instead of one
# round trip each, lifting throughput off the 1/RTT ceiling. A solo publish
# flushes immediately (see publish), so the money path never waits out the linger;
# the batch size caps a request's payload.
DEFAULT_PRODUCER_LINGER_MS = 10
DEFAULT_PRODUCER_BATCH_SIZE = 65_536
# lz4 (cramjam-backed) costs far less CPU than gzip at a comparable ratio, so it
# does not become the bottleneck once records are actually batched.
PRODUCER_COMPRESSION_TYPE = "lz4"

_TRUTHY = {"1", "true", "yes", "on"}

# Errors worth a reconnect: aiokafka's KafkaError tree plus raw socket failures.
_RECONNECT_ERRORS = (KafkaError, ConnectionError, OSError)

# The failure types a transport call surfaces to its caller: aiokafka's error
# tree, raw socket failures, and a partition that disappeared between two admin
# reads (``KeyError`` out of an offsets map). Callers that must not fail on a
# broker blip — the lag gauge — catch exactly these and let anything else through.
TRANSPORT_ERRORS: tuple[type[Exception], ...] = (KafkaError, OSError, KeyError)


class MissingTopicError(RuntimeError):
    """A required topic does not exist and auto-creation is disabled."""


class TransportAuthError(KafkaError):
    """A client did not become usable within its start budget.

    Raised by the bounded start and the post-start liveness probe. It derives
    from ``KafkaError`` so readers treat it as any other reconnectable transport
    fault (the money path never stops consuming) while ``publish`` and
    ``ensure_group`` surface it to their caller.
    """


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; using %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; using %s", name, raw, default)
        return default


def _caller_cancelled() -> bool:
    """Whether the running task is itself under cancellation."""
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


class _SecurityConfig(TypedDict, total=False):
    """The SASL kwargs shared by every aiokafka client (empty for PLAINTEXT).

    A TypedDict (not ``dict[str, object]``) so ``**``-spreading it into the typed
    aiokafka constructors stays type-checked.
    """

    security_protocol: str
    sasl_mechanism: str
    sasl_oauth_token_provider: AbstractTokenProvider


class _DescribedPartition(TypedDict):
    partition: int


class _DescribedTopic(TypedDict):
    """One entry of ``AIOKafkaAdminClient.describe_topics`` (typed as ``list[Any]``)."""

    topic: str
    error_code: int
    partitions: list[_DescribedPartition]


class GcpTokenProvider(AbstractTokenProvider):
    """SASL/OAUTHBEARER token provider backed by GCP Application Default Credentials.

    ``google.auth`` is imported lazily so PLAINTEXT (local/CI) never needs it. The
    credential is refreshed only when missing or expired; aiokafka calls
    :meth:`token` when it needs a fresh one.

    One provider serves every client on a transport, so concurrent connections
    (a reconnect storm) call :meth:`token` at once. ``google.auth`` discovers and
    refreshes the credential *in place*, so the fetch is single-flighted: the
    first caller does the work and the rest reuse the refreshed credential.
    """

    def __init__(self) -> None:
        self._credentials: Credentials | None = None
        self._lock = asyncio.Lock()

    async def token(self) -> str:
        import google.auth
        from google.auth.transport.requests import Request

        def _fetch() -> str:
            creds = self._credentials
            if creds is None:
                creds, _ = google.auth.default(scopes=[_GCP_SCOPE])
                self._credentials = creds
            if not creds.valid:
                creds.refresh(Request())
            return str(creds.token)

        async with self._lock:
            return await asyncio.to_thread(_fetch)


def _cursor(partition: int, offset: int) -> Cursor:
    return f"{partition}:{offset}"


def _parse_cursor(cursor: Cursor) -> tuple[int, int]:
    partition, offset = cursor.split(":", 1)
    return int(partition), int(offset)


class KafkaTransport:
    """`EventTransport` over Kafka via aiokafka."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        *,
        namespace: str = DEFAULT_NAMESPACE,
        security_protocol: str | None = None,
        token_provider: AbstractTokenProvider | None = None,
        max_poll_interval_ms: int = DEFAULT_MAX_POLL_INTERVAL_MS,
        reconnect_base_delay_seconds: float = RECONNECT_BASE_DELAY_SECONDS,
        reconnect_max_delay_seconds: float = RECONNECT_MAX_DELAY_SECONDS,
        client_start_timeout_seconds: float | None = None,
        auth_failure_alert_threshold: int | None = None,
    ) -> None:
        self._bootstrap = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", DEFAULT_BOOTSTRAP
        )
        self._namespace = namespace
        self._security_protocol = (
            security_protocol or os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
        ).upper()
        # Auto-creating a topic caps it at 1 partition forever, so it is a
        # dev/test convenience only: default on for PLAINTEXT (local brokers),
        # off everywhere else (production topics come from Terraform).
        auto_create = os.getenv("KAFKA_AUTO_CREATE_TOPICS")
        self._auto_create_topics = (
            self._security_protocol == "PLAINTEXT"
            if auto_create is None
            else auto_create.strip().lower() in _TRUTHY
        )
        # SASL/OAUTHBEARER token source; Workload Identity unless injected. One
        # provider per transport, shared by producer/consumers/admin, so a
        # reconnect storm does not repeat Application Default Credentials discovery.
        self._token_provider = token_provider or GcpTokenProvider()
        self._max_poll_interval_ms = max_poll_interval_ms
        self._reconnect_base = reconnect_base_delay_seconds
        self._reconnect_max = reconnect_max_delay_seconds
        self._start_timeout = (
            client_start_timeout_seconds
            if client_start_timeout_seconds is not None
            else _env_float(
                "KAFKA_CLIENT_START_TIMEOUT_SECONDS", DEFAULT_CLIENT_START_TIMEOUT_SECONDS
            )
        )
        self._auth_failure_threshold = (
            auth_failure_alert_threshold
            if auth_failure_alert_threshold is not None
            else _env_int(
                "KAFKA_AUTH_FAILURE_ALERT_THRESHOLD", DEFAULT_AUTH_FAILURE_ALERT_THRESHOLD
            )
        )
        self._producer_linger_ms = _env_int("KAFKA_PRODUCER_LINGER_MS", DEFAULT_PRODUCER_LINGER_MS)
        self._producer_batch_size = _env_int(
            "KAFKA_PRODUCER_BATCH_SIZE", DEFAULT_PRODUCER_BATCH_SIZE
        )
        self._producer: AIOKafkaProducer | None = None
        self._admin: AIOKafkaAdminClient | None = None
        # Live group consumers, keyed by (topic, group), so ``ack`` can commit on the
        # same consumer that yielded the entry (Kafka commits are consumer-scoped).
        self._consumers: dict[tuple[str, str], AIOKafkaConsumer] = {}
        self._lock = asyncio.Lock()

    # ---- topic naming ----

    def topic(self, stream: str) -> str:
        """Namespaced Kafka topic for a logical stream (``ledger:fills`` → ``lt.ledger.fills``)."""
        base, _ = resolve_topic(stream)
        return f"{self._namespace}.{base}"

    # ---- shared client config ----

    def _security_kwargs(self) -> _SecurityConfig:
        if self._security_protocol == "PLAINTEXT":
            return {}
        return {
            "security_protocol": self._security_protocol,
            "sasl_mechanism": "OAUTHBEARER",
            "sasl_oauth_token_provider": self._token_provider,
        }

    def _reconnect_delay(self, attempt: int) -> float:
        """Capped exponential backoff with jitter for reader reconnects."""
        delay = min(self._reconnect_base * (2 ** (attempt - 1)), self._reconnect_max)
        return random.uniform(delay / 2, delay)

    # ---- bounded start + liveness ----

    async def _start_client(
        self,
        *,
        kind: str,
        start: Callable[[], Awaitable[None]],
        probe: Callable[[], Awaitable[object]],
        stop: Callable[[], Awaitable[None]],
    ) -> None:
        """Start a client under a bounded wait, then prove its session is live.

        A broker answers a rejected OAUTHBEARER token in band (KIP-255:
        ``error_code=0`` with ``status=invalid_token``), which aiokafka reads as a
        successful handshake: the client logs "Authenticated" and then retries
        metadata forever with no exception, no reconnect and no metric — publish
        and consume hang. Both phases are therefore bounded, so that becomes a
        :class:`TransportAuthError` plus ``EVENTS_CLIENT_START_FAILURES_TOTAL``.

        The budget covers connect + auth + one metadata round-trip only; a group
        consumer subscribes after this, so a slow rebalance is never timed out.
        ``probe`` doubles as the metadata fetch an unsubscribed consumer needs.
        """
        started = False
        try:
            await asyncio.wait_for(start(), self._start_timeout)
            started = True
            await asyncio.wait_for(probe(), self._start_timeout)
        except TimeoutError as exc:
            await self._abandon(stop)
            reason = "liveness_timeout" if started else "start_timeout"
            EVENTS_CLIENT_START_FAILURES_TOTAL.labels(kind=kind, reason=reason).inc()
            raise TransportAuthError(
                f"Kafka {kind} did not become usable within {self._start_timeout:.1f}s "
                f"({reason}); a rejected OAUTHBEARER token authenticates without an error"
            ) from exc
        except Exception:
            await self._abandon(stop)
            raise

    async def _abandon(self, stop: Callable[[], Awaitable[None]]) -> None:
        """Release a client whose start did not complete (best effort, bounded)."""
        try:
            await asyncio.wait_for(self._stop_contained(stop), self._start_timeout)
        except Exception as exc:
            logger.debug("stop after a failed start: %s", exc)

    async def _stop_contained(self, stop: Callable[[], Awaitable[None]]) -> None:
        """Stop a client, containing aiokafka's spurious cancellation.

        ``NoGroupCoordinator.close()`` awaits a task it cancelled before that task
        ever ran, so the ``CancelledError`` surfaces in the caller even though
        nothing cancelled it — a probe consumer stopped promptly after start hits
        this every time. A genuine cancellation of the calling task is re-raised.
        """
        try:
            await stop()
        except asyncio.CancelledError:
            if _caller_cancelled():
                raise
            logger.debug("contained a spurious CancelledError from a Kafka client stop")

    async def _producer_ready(self) -> AIOKafkaProducer:
        if self._producer is None:
            async with self._lock:
                if self._producer is None:
                    producer = AIOKafkaProducer(
                        bootstrap_servers=self._bootstrap,
                        enable_idempotence=True,
                        acks="all",
                        compression_type=PRODUCER_COMPRESSION_TYPE,
                        linger_ms=self._producer_linger_ms,
                        max_batch_size=self._producer_batch_size,
                        **self._security_kwargs(),
                    )
                    await self._start_client(
                        kind="producer",
                        start=producer.start,
                        probe=producer.client.fetch_all_metadata,
                        stop=producer.stop,
                    )
                    self._producer = producer
        return self._producer

    async def _admin_ready(self) -> AIOKafkaAdminClient:
        if self._admin is None:
            async with self._lock:
                if self._admin is None:
                    admin = AIOKafkaAdminClient(
                        bootstrap_servers=self._bootstrap, **self._security_kwargs()
                    )
                    await self._start_client(
                        kind="admin",
                        start=admin.start,
                        probe=admin.list_topics,
                        stop=admin.close,
                    )
                    self._admin = admin
        return self._admin

    async def _partitions_for(self, topic: str) -> list[TopicPartition]:
        """The topic's partitions, or empty when it does not exist.

        Read through the Admin API rather than a probe consumer's
        ``partitions_for_topic``: that answers from the consumer's cached cluster,
        which an unsubscribed consumer never fills (``fetch_all_metadata`` returns
        a fresh snapshot instead of updating the cache), so it always answers None.
        """
        admin = await self._admin_ready()
        described: list[_DescribedTopic] = await admin.describe_topics([topic])
        return [
            TopicPartition(topic, partition["partition"])
            for entry in described
            if entry["topic"] == topic and entry["error_code"] == 0
            for partition in entry["partitions"]
        ]

    async def _start_consumer(self, consumer: AIOKafkaConsumer, *, kind: str) -> None:
        await self._start_client(
            kind=kind,
            start=consumer.start,
            probe=consumer.topics,
            stop=consumer.stop,
        )

    def _note_reader_failure(
        self,
        stream: str,
        group: str | None,
        mode: str,
        exc: BaseException,
        *,
        attempt: int,
        failed_starts: int,
    ) -> None:
        """Log a reader's transport error; escalate a run of start failures.

        ``failed_starts`` is 0 once the reader has started (a mid-stream fault).
        Readers retry forever, so a permanently broken credential would otherwise
        stay a warning behind the reconnect counter: past the threshold it is also
        counted and named at ERROR for operators. The retry-forever contract is
        unchanged — the signal is for humans, not for the loop.
        """
        where = f"{mode}({stream})" if group is None else f"{mode}({stream}, {group})"
        if failed_starts < self._auth_failure_threshold:
            logger.warning(
                "%s: transport error (%s: %s); reconnect #%d",
                where,
                type(exc).__name__,
                exc,
                attempt,
            )
            return
        EVENTS_BROKEN_CREDENTIALS_TOTAL.labels(stream=stream_label(stream), mode=mode).inc()
        logger.error(
            "%s: %d consecutive failures to start (%s: %s); credentials or broker "
            "access look broken; still retrying",
            where,
            failed_starts,
            type(exc).__name__,
            exc,
        )

    # ---- liveness ----

    def is_connected(self) -> bool:
        """Whether this transport holds a started producer or group consumer.

        Lets a health probe answer from the shared transport's own clients
        instead of opening a second broker connection. Reads only existing
        state: the producer (assigned after a proven-live start) and the live
        durable-group consumers. Own-group ``tail`` readers are local to their
        generator and not tracked, so a tail-only role reports ``False``.
        """
        return self._producer is not None or bool(self._consumers)

    # ---- publish ----

    async def publish(
        self,
        stream: str,
        value: bytes,
        *,
        key: str | None = None,
        maxlen: int | None = None,
    ) -> Cursor:
        # maxlen is advisory on Kafka (retention is topic config); ignored here.
        del maxlen
        try:
            producer = await self._producer_ready()
            future = await producer.send(
                self.topic(stream), value=value, key=key.encode() if key else None
            )
            # Money path (a solo ledger fill): flush so the record leaves now instead
            # of waiting out the producer's linger. The linger stays in place to batch
            # bursts through publish_many (bars); a solo publish must not pay for it.
            await producer.flush()
            metadata = await future
        except Exception:
            EVENTS_PUBLISH_FAILURES_TOTAL.labels(stream=stream_label(stream)).inc()
            raise
        EVENTS_PUBLISHED_TOTAL.labels(stream=stream_label(stream)).inc()
        return _cursor(metadata.partition, metadata.offset)

    async def publish_many(
        self,
        stream: str,
        records: Sequence[OutgoingRecord],
        *,
        maxlen: int | None = None,
    ) -> list[Cursor]:
        # maxlen is advisory on Kafka (retention is topic config); ignored here.
        del maxlen
        if not records:
            return []
        try:
            producer = await self._producer_ready()
            topic = self.topic(stream)
            # send() only appends to the per-partition accumulator, so awaiting the
            # returned futures together lets one produce request carry the whole
            # batch. Enqueuing in call order keeps per-key order within a partition.
            futures = [
                await producer.send(topic, value=r.value, key=r.key.encode() if r.key else None)
                for r in records
            ]
            metadata: list[RecordMetadata] = await asyncio.gather(*futures)
        except Exception:
            # No record in the batch was confirmed; count them all as failed.
            EVENTS_PUBLISH_FAILURES_TOTAL.labels(stream=stream_label(stream)).inc(len(records))
            raise
        EVENTS_PUBLISHED_TOTAL.labels(stream=stream_label(stream)).inc(len(records))
        return [_cursor(m.partition, m.offset) for m in metadata]

    # ---- tail (independent fan-out) ----

    def _tail_consumer(self, full_topic: str, from_cursor: Cursor) -> AIOKafkaConsumer:
        if from_cursor in (CURSOR_NEW, CURSOR_BEGIN):
            # group_id=None → an independent (own-group) reader: every caller sees
            # the whole topic, positioned by auto_offset_reset.
            return AIOKafkaConsumer(
                full_topic,
                bootstrap_servers=self._bootstrap,
                group_id=None,
                enable_auto_commit=False,
                auto_offset_reset="earliest" if from_cursor == CURSOR_BEGIN else "latest",
                **self._security_kwargs(),
            )
        # Concrete cursor → manual partition assignment; positioned in _seek_to_cursor.
        return AIOKafkaConsumer(
            bootstrap_servers=self._bootstrap,
            group_id=None,
            enable_auto_commit=False,
            **self._security_kwargs(),
        )

    async def _seek_to_cursor(
        self, consumer: AIOKafkaConsumer, full_topic: str, cursor: Cursor
    ) -> None:
        """Assign every partition; resume the cursor's partition after its offset,
        every other partition from its end (a cursor addresses one partition).

        The partition list comes from :meth:`_partitions_for` (Admin API). The
        consumer's own ``partitions_for_topic`` cannot answer here: it reads a
        cached cluster that an unsubscribed consumer never fills, so it returns
        None and the resume would silently assign the cursor's partition alone —
        a multi-partition topic would deliver nothing from the rest.
        """
        partition, offset = _parse_cursor(cursor)
        cursor_tp = TopicPartition(full_topic, partition)
        tps = sorted(set(await self._partitions_for(full_topic)) | {cursor_tp})
        consumer.assign(tps)
        others = [tp for tp in tps if tp.partition != partition]
        if others:
            await consumer.seek_to_end(*others)
        consumer.seek(cursor_tp, offset + 1)

    async def tail(
        self,
        stream: str,
        *,
        from_cursor: Cursor = CURSOR_NEW,
        block_ms: int = 5000,
        count: int = 100,
    ) -> AsyncIterator[tuple[Cursor, bytes]]:
        """Independent fan-out reader over the stream's topic.

        ``from_cursor``: ``CURSOR_NEW`` starts at the log end, ``CURSOR_BEGIN`` at
        the log start, and a concrete ``"partition:offset"`` cursor resumes AFTER
        that record. A cursor addresses a **single partition**: that partition is
        replayed from ``offset + 1`` and every other partition starts at its end.
        That replays the full gap for single-partition topics and for per-entity
        streams (one entity's key confines its records to the cursor's partition);
        on multi-partition global topics, other partitions' history is not replayed.

        Broker errors reconnect with capped, jittered exponential backoff, resuming
        from the last yielded cursor; ``EVENTS_RECONNECTS_TOTAL`` counts each retry.
        """
        del block_ms, count
        topic, routing_key = resolve_topic(stream)
        full_topic = f"{self._namespace}.{topic}"
        resume = from_cursor
        attempt = 0
        failed_starts = 0
        while True:
            consumer = self._tail_consumer(full_topic, resume)
            started = False
            try:
                await self._start_consumer(consumer, kind="consumer")
                started = True
                failed_starts = 0
                if resume not in (CURSOR_NEW, CURSOR_BEGIN):
                    await self._seek_to_cursor(consumer, full_topic, resume)
                async for record in consumer:
                    attempt = 0
                    if record.value is None:
                        continue  # no null-valued records on our topics
                    cursor = _cursor(record.partition, record.offset)
                    resume = cursor
                    # Per-entity streams share one topic; filter to this entity's key.
                    if routing_key is not None:
                        record_key = record.key.decode() if record.key else None
                        if record_key != routing_key:
                            continue
                    yield cursor, record.value
                return
            except _RECONNECT_ERRORS as exc:
                attempt += 1
                if not started:
                    failed_starts += 1
                EVENTS_RECONNECTS_TOTAL.labels(stream=stream_label(stream), mode="tail").inc()
                self._note_reader_failure(
                    stream, None, "tail", exc, attempt=attempt, failed_starts=failed_starts
                )
            finally:
                await self._stop_contained(consumer.stop)
            await asyncio.sleep(self._reconnect_delay(attempt))

    # ---- consume (durable consumer group) ----

    async def ensure_group(self, stream: str, group: str, *, start_id: str = CURSOR_NEW) -> None:
        # Kafka groups are implicit (formed on subscribe); this only ensures the
        # topic exists (see _ensure_topic for the auto-create gate).
        del group, start_id
        await self._ensure_topic(self.topic(stream))

    async def _ensure_topic(self, topic: str, *, partitions: int = 1) -> None:
        """Dev/test convenience: create a missing topic with 1 partition.

        Gated because a 1-partition auto-created topic would permanently cap a
        keyed production topic: when auto-creation is off, a missing topic is a
        provisioning error, not something to paper over.
        """
        admin = await self._admin_ready()
        if not self._auto_create_topics:
            existing = await admin.list_topics()
            if topic not in existing:
                raise MissingTopicError(
                    f"Kafka topic {topic!r} does not exist and auto-creation is disabled "
                    "(KAFKA_AUTO_CREATE_TOPICS is off outside PLAINTEXT); provision the "
                    "topic via Terraform (infrastructure/terraform)"
                )
            return
        try:
            await admin.create_topics(
                [NewTopic(topic, num_partitions=partitions, replication_factor=1)]
            )
        except Exception as e:  # TopicAlreadyExists (and friends) are benign
            if "already exists" not in str(e).lower():
                logger.debug("ensure_topic(%s): %s", topic, e)

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
        """Shared-group consumption with manual commit (see :meth:`ack`).

        Broker errors re-join the group with capped, jittered backoff; committed
        offsets make the resume lossless (uncommitted entries redeliver).

        The topic is subscribed *after* the bounded start so the start budget
        covers only connect + auth + metadata: a member that joins while another
        member sits in a long in-place retry waits out that rebalance inside the
        iteration, where waiting is correct, instead of timing out and re-joining.
        """
        del consumer, block_ms, count
        topic = self.topic(stream)
        attempt = 0
        failed_starts = 0
        while True:
            kafka_consumer = AIOKafkaConsumer(
                bootstrap_servers=self._bootstrap,
                group_id=group,
                enable_auto_commit=False,
                auto_offset_reset="earliest" if group_start_id == CURSOR_BEGIN else "latest",
                max_poll_interval_ms=self._max_poll_interval_ms,
                **self._security_kwargs(),
            )
            started = False
            try:
                await self._start_consumer(kafka_consumer, kind="consumer")
                started = True
                failed_starts = 0
                kafka_consumer.subscribe([topic])
                self._consumers[(topic, group)] = kafka_consumer
                async for record in kafka_consumer:
                    attempt = 0
                    if record.value is None:
                        continue  # no null-valued records on our topics
                    yield _cursor(record.partition, record.offset), record.value
                return
            except _RECONNECT_ERRORS as exc:
                attempt += 1
                if not started:
                    failed_starts += 1
                EVENTS_RECONNECTS_TOTAL.labels(stream=stream_label(stream), mode="consume").inc()
                self._note_reader_failure(
                    stream, group, "consume", exc, attempt=attempt, failed_starts=failed_starts
                )
            finally:
                if self._consumers.get((topic, group)) is kafka_consumer:
                    self._consumers.pop((topic, group), None)
                await self._stop_contained(kafka_consumer.stop)
            await asyncio.sleep(self._reconnect_delay(attempt))

    async def ack(self, stream: str, group: str, cursor: Cursor) -> None:
        topic = self.topic(stream)
        kafka_consumer = self._consumers.get((topic, group))
        if kafka_consumer is None:
            logger.warning("ack(%s, %s): no live consumer to commit on", stream, group)
            return
        partition, offset = _parse_cursor(cursor)
        tp = TopicPartition(topic, partition)
        # Committed offset is the NEXT record to read → last-processed + 1.
        await kafka_consumer.commit({tp: OffsetAndMetadata(offset + 1, "")})

    async def pause_partition(self, stream: str, group: str, cursor: Cursor) -> None:
        """Stop fetching the cursor's partition on the group's live consumer.

        Used around a long in-place retry so the fetcher stops prefetching the
        stalled partition while the member keeps polling and heartbeating.
        No-op (logged) when the group has no live consumer in this process.
        """
        topic = self.topic(stream)
        kafka_consumer = self._consumers.get((topic, group))
        if kafka_consumer is None:
            logger.warning("pause_partition(%s, %s): no live consumer", stream, group)
            return
        partition, _ = _parse_cursor(cursor)
        kafka_consumer.pause(TopicPartition(topic, partition))

    async def resume_partition(self, stream: str, group: str, cursor: Cursor) -> None:
        """Undo :meth:`pause_partition` for the cursor's partition."""
        topic = self.topic(stream)
        kafka_consumer = self._consumers.get((topic, group))
        if kafka_consumer is None:
            logger.warning("resume_partition(%s, %s): no live consumer", stream, group)
            return
        partition, _ = _parse_cursor(cursor)
        kafka_consumer.resume(TopicPartition(topic, partition))

    async def pending(self, stream: str, group: str) -> int:
        """Consumer-group lag (end − committed), sampled WITHOUT joining the group.

        Committed offsets come from the Admin API and end offsets from a
        **non-member** probe consumer (``group_id=None``), so lag sampling — which
        the ledger runs every ~30s on a separate loop — never rebalances the live
        group nor shares the consuming member across tasks. A partition with no
        committed offset yet counts its full end as lag.
        """
        topic = self.topic(stream)
        admin = await self._admin_ready()
        committed = await admin.list_consumer_group_offsets(group)
        tps = await self._partitions_for(topic)
        if not tps:
            return 0
        probe = AIOKafkaConsumer(bootstrap_servers=self._bootstrap, **self._security_kwargs())
        await self._start_consumer(probe, kind="probe")
        try:
            end = await probe.end_offsets(tps)
        finally:
            await self._stop_contained(probe.stop)
        lag = 0
        for tp in tps:
            meta = committed.get(tp)
            offset = meta.offset if meta is not None and meta.offset >= 0 else 0
            lag += max(0, end[tp] - offset)
        return lag

    async def trim(self, stream: str, maxlen: int) -> None:
        # No-op: Kafka bounds a topic by retention config, not per-publish trimming.
        del stream, maxlen

    async def length(self, stream: str) -> int:
        topic = self.topic(stream)
        tps = await self._partitions_for(topic)
        if not tps:
            return 0
        probe = AIOKafkaConsumer(bootstrap_servers=self._bootstrap, **self._security_kwargs())
        await self._start_consumer(probe, kind="probe")
        try:
            begin = await probe.beginning_offsets(tps)
            end = await probe.end_offsets(tps)
            return sum(end[tp] - begin[tp] for tp in tps)
        finally:
            await self._stop_contained(probe.stop)

    async def purge(self, stream: str, *, up_to_cursor: Cursor | None = None) -> None:
        topic = self.topic(stream)
        tps = await self._partitions_for(topic)
        if not tps:
            return
        admin = await self._admin_ready()
        if up_to_cursor is not None:
            # Cursor-bounded: delete only the cursor's partition, up to and
            # including its offset (before_offset is exclusive → offset + 1).
            partition, offset = _parse_cursor(up_to_cursor)
            tp = TopicPartition(topic, partition)
            await admin.delete_records({tp: RecordsToDelete(offset + 1)})
            return
        probe = AIOKafkaConsumer(bootstrap_servers=self._bootstrap, **self._security_kwargs())
        await self._start_consumer(probe, kind="probe")
        try:
            end = await probe.end_offsets(tps)
        finally:
            await self._stop_contained(probe.stop)
        # Delete every record up to the current end (log-start moves forward).
        await admin.delete_records({tp: RecordsToDelete(end[tp]) for tp in tps})

    async def close(self) -> None:
        for kafka_consumer in list(self._consumers.values()):
            await self._stop_contained(kafka_consumer.stop)
        self._consumers.clear()
        if self._producer is not None:
            await self._stop_contained(self._producer.stop)
            self._producer = None
        if self._admin is not None:
            await self._stop_contained(self._admin.close)
            self._admin = None
