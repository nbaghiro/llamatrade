"""Real-Kafka SASL/OAUTHBEARER tests: the token path across an expiry boundary.

Kafka's built-in unsecured-JWT validator accepts self-issued tokens carrying a
real ``exp`` claim, so a broker with SASL_PLAINTEXT/OAUTHBEARER needs no OIDC
server. The broker then enforces the token's lifetime: the SASL response carries
a session lifetime derived from ``exp`` and capped by ``connections.max.reauth.ms``,
and the broker closes the connection once it elapses.

aiokafka never re-authenticates in place — it reconnects, and every new connection
calls the token provider again — so this is exactly the refresh path that runs in
GCP, where Workload Identity tokens are short-lived and a consumer outlives them.

Gated behind ``@pytest.mark.integration``; self-skips when Docker/testcontainers
is unavailable. Set ``KAFKA_OAUTH_BOOTSTRAP_SERVERS`` to run against an
externally provided SASL_PLAINTEXT/OAUTHBEARER broker instead of the container.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from collections.abc import AsyncIterator, Iterator, Mapping

import pytest
from aiokafka.abc import AbstractTokenProvider
from conftest import metric_value

from llamatrade_events.transport.base import CURSOR_BEGIN
from llamatrade_events.transport.kafka import KafkaTransport, TransportAuthError

pytestmark = pytest.mark.integration

STREAM = "ledger:fills"
GROUP = "portfolio-ledger"
# Short enough to keep the rejected-token tests quick; far longer than a healthy
# connect + SASL handshake + metadata round-trip against a local broker.
REJECTED_TOKEN_START_TIMEOUT = 5.0

# Short enough that a test spans several token lifetimes without being slow.
TOKEN_TTL_SECONDS = 4
# Cap above the token lifetime so ``exp`` is what ends the session.
REAUTH_WINDOW_MS = 10_000

_UNSECURED_VALIDATOR = (
    "org.apache.kafka.common.security.oauthbearer.internals.unsecured"
    ".OAuthBearerUnsecuredValidatorCallbackHandler"
)
_BROKER_JAAS = (
    "org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required "
    'unsecuredLoginStringClaim_sub="broker";'
)
# The container's client listener is named PLAINTEXT; these remap it to
# SASL_PLAINTEXT/OAUTHBEARER. Inter-broker and controller traffic stays plaintext.
_BROKER_ENV = {
    "KAFKA_SASL_ENABLED_MECHANISMS": "OAUTHBEARER",
    "KAFKA_LISTENER_NAME_PLAINTEXT_SASL_ENABLED_MECHANISMS": "OAUTHBEARER",
    "KAFKA_LISTENER_NAME_PLAINTEXT_OAUTHBEARER_SASL_SERVER_CALLBACK_HANDLER_CLASS": (
        _UNSECURED_VALIDATOR
    ),
    "KAFKA_LISTENER_NAME_PLAINTEXT_OAUTHBEARER_SASL_JAAS_CONFIG": _BROKER_JAAS,
    "KAFKA_LISTENER_NAME_PLAINTEXT_OAUTHBEARER_CONNECTIONS_MAX_REAUTH_MS": str(REAUTH_WINDOW_MS),
}


def _b64url(claims: Mapping[str, object]) -> str:
    raw = json.dumps(claims, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class ShortLivedTokenProvider(AbstractTokenProvider):
    """Mints unsecured JWTs with a controllable lifetime and logs every fetch.

    A negative TTL yields tokens the broker must reject as expired.
    """

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self.issued: list[tuple[float, str]] = []

    def minted_after(self, mark: float) -> list[str]:
        return [token for at, token in self.issued if at > mark]

    async def token(self) -> str:
        now = int(time.time())
        claims = {
            "sub": "llamatrade-events",
            "iat": now,
            "exp": now + self._ttl,
            "jti": str(len(self.issued)),  # keeps every token distinct
        }
        token = f"{_b64url({'alg': 'none'})}.{_b64url(claims)}."
        self.issued.append((time.monotonic(), token))
        return token


@pytest.fixture(scope="module")
def sasl_bootstrap() -> Iterator[str]:
    """A Kafka broker whose client listener speaks SASL_PLAINTEXT/OAUTHBEARER.

    The plaintext broker the rest of the suite uses cannot serve these tests, so
    this always builds its own container unless one is provided explicitly.
    """
    provided = os.getenv("KAFKA_OAUTH_BOOTSTRAP_SERVERS")
    if provided:
        yield provided
        return
    kafka_mod = pytest.importorskip("testcontainers.kafka")
    docker_errors = pytest.importorskip("docker.errors")
    try:
        container = kafka_mod.KafkaContainer().with_kraft()
        container.security_protocol_map = "BROKER:PLAINTEXT,PLAINTEXT:SASL_PLAINTEXT"
        for name, value in _BROKER_ENV.items():
            container.with_env(name, value)
        container.start()
    except docker_errors.DockerException as exc:  # daemon down / image unavailable
        pytest.skip(f"Docker/Kafka unavailable: {exc}")
    # A broker that boots but never reports readiness is a broken SASL config,
    # not a missing prerequisite: let that fail loudly.
    try:
        yield container.get_bootstrap_server()
    finally:
        container.stop()


def _oauth_transport(
    bootstrap: str,
    provider: AbstractTokenProvider,
    request: pytest.FixtureRequest,
    **overrides: float | int,
) -> KafkaTransport:
    """A SASL transport on a per-test namespace so topics never collide."""
    return KafkaTransport(
        bootstrap,
        namespace=f"oauth{abs(hash(request.node.nodeid)) % 1_000_000}",
        security_protocol="SASL_PLAINTEXT",
        token_provider=provider,
        **overrides,
    )


async def _wait_for_metric(name: str, above: float, *, timeout: float, **labels: str) -> float:
    """Poll a counter until it rises above ``above``; fail the test on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = metric_value(name, **labels)
        if current > above:
            return current
        await asyncio.sleep(0.25)
    pytest.fail(f"{name}{labels} stayed at {above} for {timeout}s")


@pytest.fixture
def rotating_provider() -> ShortLivedTokenProvider:
    return ShortLivedTokenProvider(TOKEN_TTL_SECONDS)


@pytest.fixture
async def oauth_transport(
    sasl_bootstrap: str,
    rotating_provider: ShortLivedTokenProvider,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[KafkaTransport]:
    # Topics come from Terraform outside PLAINTEXT; these tests own their own.
    monkeypatch.setenv("KAFKA_AUTO_CREATE_TOPICS", "1")
    transport = _oauth_transport(sasl_bootstrap, rotating_provider, request)
    try:
        yield transport
    finally:
        await transport.close()


async def test_consumption_survives_token_expiry_mid_stream(
    oauth_transport: KafkaTransport, rotating_provider: ShortLivedTokenProvider
) -> None:
    """A group consumer outlives its token: the broker ends the authenticated
    session, the transport reconnects with a freshly minted token, and records
    published after the boundary still arrive exactly once."""
    total = 6
    half = total // 2
    expected = {f"m{i}".encode() for i in range(total)}

    await oauth_transport.ensure_group(STREAM, GROUP)
    for i in range(half):
        await oauth_transport.publish(STREAM, f"m{i}".encode(), key="acctA")

    seen: list[bytes] = []
    first_batch = asyncio.Event()
    stream = oauth_transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN)

    async def drain() -> None:
        try:
            async for cursor, value in stream:
                seen.append(value)
                await oauth_transport.ack(STREAM, GROUP, cursor)
                if len(seen) >= half:
                    first_batch.set()
                if len(seen) >= total:
                    break
        finally:
            await stream.aclose()

    task = asyncio.create_task(drain())
    try:
        await asyncio.wait_for(first_batch.wait(), timeout=60.0)
        tokens_before_expiry = len(rotating_provider.issued)
        mark = time.monotonic()

        # Outlive the authenticated session, then publish and consume across it.
        await asyncio.sleep(TOKEN_TTL_SECONDS + 3)
        for i in range(half, total):
            await oauth_transport.publish(STREAM, f"m{i}".encode(), key="acctA")

        await asyncio.wait_for(task, timeout=90.0)
    finally:
        task.cancel()

    assert set(seen) == expected  # nothing lost across the re-authentication
    assert len(seen) == total  # and nothing redelivered
    # Tokens were fetched again after the boundary, and each one was distinct.
    assert rotating_provider.minted_after(mark)
    assert len(rotating_provider.issued) > tokens_before_expiry
    tokens = [token for _at, token in rotating_provider.issued]
    assert len(set(tokens)) == len(tokens)


async def test_a_rejected_token_fails_the_publisher_loudly(
    sasl_bootstrap: str, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The broker answers an expired token with an in-band ``invalid_token``
    status, which aiokafka reads as a successful handshake: the client then
    retries metadata forever, so ``publish`` used to never return and never
    raise. The bounded start turns that stall into a typed error and a metric.
    """
    monkeypatch.setenv("KAFKA_AUTO_CREATE_TOPICS", "1")
    provider = ShortLivedTokenProvider(-30)
    transport = _oauth_transport(
        sasl_bootstrap,
        provider,
        request,
        client_start_timeout_seconds=REJECTED_TOKEN_START_TIMEOUT,
    )
    counter = "llamatrade_events_client_start_failures_total"
    labels = {"kind": "producer", "reason": "start_timeout"}
    before = metric_value(counter, **labels)
    try:
        # The outer wait_for is the regression guard: a hang fails the test.
        with pytest.raises(TransportAuthError, match="start_timeout"):
            await asyncio.wait_for(
                transport.publish(STREAM, b"rejected", key="acctA"),
                timeout=REJECTED_TOKEN_START_TIMEOUT * 4,
            )
        assert provider.issued  # the token was fetched and sent
        assert metric_value(counter, **labels) == before + 1
    finally:
        await transport.close()


async def test_a_rejected_token_keeps_the_reader_retrying_and_flags_broken_credentials(
    sasl_bootstrap: str, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reader must never give up on the money path, so a permanently rejected
    token keeps it reconnecting; the operator signal is the broken-credentials
    counter (and its ERROR log) once the start failures run consecutively."""
    monkeypatch.setenv("KAFKA_AUTO_CREATE_TOPICS", "1")
    provider = ShortLivedTokenProvider(-30)
    transport = _oauth_transport(
        sasl_bootstrap,
        provider,
        request,
        client_start_timeout_seconds=REJECTED_TOKEN_START_TIMEOUT,
        auth_failure_alert_threshold=2,
        reconnect_base_delay_seconds=0.0,
        reconnect_max_delay_seconds=0.0,
    )
    counter = "llamatrade_events_broken_credentials_total"
    labels = {"stream": STREAM, "mode": "consume"}
    before = metric_value(counter, **labels)
    stream = transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN)

    async def drain() -> None:
        try:
            async for _cursor, _value in stream:
                return
        finally:
            await stream.aclose()

    task = asyncio.create_task(drain())
    try:
        await _wait_for_metric(counter, before, timeout=REJECTED_TOKEN_START_TIMEOUT * 8, **labels)
        assert not task.done()  # still retrying rather than dead or hung
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await transport.close()
