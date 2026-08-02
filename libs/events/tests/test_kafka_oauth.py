"""SASL/OAUTHBEARER token-refresh tests for ``KafkaTransport``.

Against GCP Managed Kafka the transport authenticates with short-lived Workload
Identity tokens, so a token fetched at connect time expires while a consumer is
still running: every new connection must fetch again, and an expired credential
must be refreshed instead of reused.

Three seams are covered here without a broker: the transport's SASL kwargs (which
provider aiokafka is handed), aiokafka's own ``OAuthAuthenticator`` (which token
reaches the wire on each authentication), and ``GcpTokenProvider``'s caching and
failure behaviour. Rotation across a real expiry boundary is proven against a
broker in ``test_integration_kafka_oauth.py``.

The client fakes model ``AIOKafkaClient.bootstrap``: it catches ``OSError`` and
``KafkaError`` per host and ends with ``KafkaConnectionError``, so a token failure
of those types becomes a reconnect while any other type propagates unchanged.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import google.auth
import pytest
from aiokafka.abc import AbstractTokenProvider
from aiokafka.conn import OAuthAuthenticator
from aiokafka.errors import KafkaConnectionError, KafkaError
from conftest import metric_value

from llamatrade_events.transport.base import CURSOR_BEGIN, Cursor
from llamatrade_events.transport.kafka import GcpTokenProvider, KafkaTransport

STREAM = "ledger:fills"
GROUP = "portfolio-ledger"
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


@pytest.fixture(autouse=True)
def no_ambient_kafka_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep a PLAINTEXT broker in the environment off the SASL paths under test."""
    monkeypatch.delenv("KAFKA_SECURITY_PROTOCOL", raising=False)
    monkeypatch.delenv("KAFKA_AUTO_CREATE_TOPICS", raising=False)
    yield


class TokenUnavailableError(RuntimeError):
    """What a credential source raises when it cannot mint a token.

    ``google.auth`` errors derive from ``Exception``, not from ``KafkaError`` or
    ``OSError`` — the distinction decides whether aiokafka converts the failure
    into a reconnect or lets it propagate.
    """


class _FakeTokenProvider(AbstractTokenProvider):
    """Mints a distinct token per fetch and records the call log."""

    def __init__(self, *, fail_times: int = 0, error: Exception | None = None) -> None:
        self.calls = 0
        self.issued: list[str] = []
        self._fail_times = fail_times
        self._error = error or TokenUnavailableError("no credentials")

    async def token(self) -> str:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise self._error
        issued = f"token-{self.calls}"
        self.issued.append(issued)
        return issued


# --- transport SASL kwargs ---


def test_plaintext_transport_needs_no_token_provider() -> None:
    assert KafkaTransport(security_protocol="PLAINTEXT")._security_kwargs() == {}


def test_sasl_defaults_to_workload_identity_tokens() -> None:
    kwargs = KafkaTransport(security_protocol="SASL_SSL")._security_kwargs()
    assert kwargs.get("security_protocol") == "SASL_SSL"
    assert kwargs.get("sasl_mechanism") == "OAUTHBEARER"
    assert isinstance(kwargs.get("sasl_oauth_token_provider"), GcpTokenProvider)


def test_one_default_provider_serves_every_client_of_a_transport() -> None:
    """A per-client provider would repeat ADC discovery on every reconnect."""
    transport = KafkaTransport(security_protocol="SASL_SSL")
    first = transport._security_kwargs().get("sasl_oauth_token_provider")
    second = transport._security_kwargs().get("sasl_oauth_token_provider")
    assert first is second


# --- aiokafka's authenticator: which token reaches the wire ---


async def _sasl_client_request(provider: AbstractTokenProvider) -> str:
    """The OAUTHBEARER client request aiokafka builds for one connection."""
    step = await OAuthAuthenticator(sasl_oauth_token_provider=provider).step(None)
    assert step is not None
    payload, _expect_response = step
    return payload.decode()


async def test_every_connection_authenticates_with_a_freshly_fetched_token() -> None:
    """aiokafka builds one authenticator per connection, so a reconnect after
    expiry carries the refreshed token rather than the stale one."""
    provider = _FakeTokenProvider()
    first = await _sasl_client_request(provider)
    second = await _sasl_client_request(provider)

    assert provider.calls == 2
    assert provider.issued[0] != provider.issued[1]
    assert f"auth=Bearer {provider.issued[0]}" in first
    assert f"auth=Bearer {provider.issued[1]}" in second
    assert provider.issued[0] not in second  # no stale token on the new attempt


async def test_authentication_does_not_swallow_a_token_failure() -> None:
    provider = _FakeTokenProvider(fail_times=1)
    with pytest.raises(TokenUnavailableError):
        await _sasl_client_request(provider)
    assert provider.calls == 1


# --- GcpTokenProvider: caching, refresh, failure ---


class _FakeCredentials:
    """Application Default Credentials stand-in with controllable validity."""

    def __init__(self) -> None:
        self.token: str | None = None
        self.valid = False
        self.refreshes: list[object] = []
        self._error: Exception | None = None

    def expire(self) -> None:
        self.valid = False

    def fail_next_refresh(self, error: Exception) -> None:
        self._error = error

    def refresh(self, request: object) -> None:
        if self._error is not None:
            error, self._error = self._error, None
            raise error
        self.refreshes.append(request)
        self.token = f"adc-token-{len(self.refreshes)}"
        self.valid = True


class _FakeAdc:
    """Records how ``google.auth.default`` was called and what it handed back."""

    def __init__(self) -> None:
        self.credentials = _FakeCredentials()
        self.scopes: list[list[str]] = []
        self.request = object()

    def default(self, *, scopes: list[str]) -> tuple[_FakeCredentials, str]:
        self.scopes.append(scopes)
        return self.credentials, "test-project"


@pytest.fixture
def adc(monkeypatch: pytest.MonkeyPatch) -> _FakeAdc:
    fake = _FakeAdc()
    monkeypatch.setattr(google.auth, "default", fake.default)
    monkeypatch.setattr("google.auth.transport.requests.Request", lambda: fake.request)
    return fake


async def test_workload_identity_token_is_minted_for_the_cloud_platform_scope(
    adc: _FakeAdc,
) -> None:
    assert await GcpTokenProvider().token() == "adc-token-1"
    assert adc.scopes == [[CLOUD_PLATFORM_SCOPE]]
    assert adc.credentials.refreshes == [adc.request]


async def test_valid_credentials_are_reused_by_later_connections(adc: _FakeAdc) -> None:
    provider = GcpTokenProvider()
    assert await provider.token() == "adc-token-1"
    assert await provider.token() == "adc-token-1"
    assert len(adc.scopes) == 1  # credentials discovered once
    assert len(adc.credentials.refreshes) == 1  # and minted once


async def test_expired_credentials_are_refreshed_on_the_next_fetch(adc: _FakeAdc) -> None:
    provider = GcpTokenProvider()
    first = await provider.token()
    adc.credentials.expire()
    second = await provider.token()

    assert (first, second) == ("adc-token-1", "adc-token-2")
    assert len(adc.scopes) == 1  # refreshed in place, not rediscovered
    assert len(adc.credentials.refreshes) == 2


async def test_concurrent_fetches_discover_and_refresh_the_credential_once(
    adc: _FakeAdc,
) -> None:
    """One provider serves every client, so a reconnect storm fetches at once.

    ``google.auth`` mutates the credential in place, so the fetch is
    single-flighted rather than run once per waiting connection.
    """
    provider = GcpTokenProvider()

    tokens = await asyncio.gather(*(provider.token() for _ in range(5)))

    assert set(tokens) == {"adc-token-1"}
    assert len(adc.scopes) == 1  # discovered once, not once per connection
    assert len(adc.credentials.refreshes) == 1


async def test_a_failed_refresh_surfaces_to_the_caller(adc: _FakeAdc) -> None:
    provider = GcpTokenProvider()
    await provider.token()
    adc.credentials.expire()
    adc.credentials.fail_next_refresh(TokenUnavailableError("metadata server unreachable"))

    with pytest.raises(TokenUnavailableError):
        await provider.token()

    adc.credentials.expire()
    assert await provider.token() == "adc-token-2"  # recovers on the next attempt


async def test_missing_default_credentials_surface_to_the_caller(
    adc: _FakeAdc, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _no_credentials(*, scopes: list[str]) -> tuple[_FakeCredentials, str]:
        raise TokenUnavailableError(f"no ADC for {scopes}")

    monkeypatch.setattr(google.auth, "default", _no_credentials)
    with pytest.raises(TokenUnavailableError):
        await GcpTokenProvider().token()


# --- transport behaviour when the token fetch fails ---


class _RecordMetadata:
    def __init__(self, partition: int, offset: int) -> None:
        self.partition = partition
        self.offset = offset


class _FakeSaslMetadata:
    """The metadata handle a producer's liveness probe goes through."""

    async def fetch_all_metadata(self) -> set[str]:
        return set()


class _FakeSaslClient:
    """aiokafka client stand-in that authenticates with the injected provider."""

    def __init__(self, *topics: str, **kwargs: object) -> None:
        self.subscribed = list(topics)
        self.kwargs = kwargs
        self.client = _FakeSaslMetadata()

    async def start(self) -> None:
        provider = self.kwargs.get("sasl_oauth_token_provider")
        if not isinstance(provider, AbstractTokenProvider):
            return
        try:
            await provider.token()
        except (KafkaError, OSError) as exc:
            raise KafkaConnectionError(f"Unable to bootstrap: {exc}") from exc

    async def stop(self) -> None: ...

    async def close(self) -> None: ...

    # liveness probes: consumers fetch topics, the admin lists them
    async def topics(self) -> set[str]:
        return set(self.subscribed)

    async def list_topics(self) -> list[str]:
        return list(self.subscribed)

    def subscribe(self, topics: list[str]) -> None:
        self.subscribed = list(topics)


class _FakeSaslProducer(_FakeSaslClient):
    def __init__(self, *topics: str, **kwargs: object) -> None:
        super().__init__(*topics, **kwargs)
        self.sent: list[bytes] = []

    async def send(
        self, topic: str, value: bytes, key: bytes | None = None
    ) -> asyncio.Future[_RecordMetadata]:
        self.sent.append(value)
        fut: asyncio.Future[_RecordMetadata] = asyncio.get_running_loop().create_future()
        fut.set_result(_RecordMetadata(0, len(self.sent) - 1))
        return fut

    async def flush(self) -> None: ...


class _FakeRecord:
    def __init__(self, offset: int, value: bytes) -> None:
        self.partition = 0
        self.offset = offset
        self.key = None
        self.value = value


class _FakeSaslConsumer(_FakeSaslClient):
    """Delivers the registry's scripted records once, then drains."""

    def __init__(self, *topics: str, records: list[bytes], **kwargs: object) -> None:
        super().__init__(*topics, **kwargs)
        self._records = records
        self._position = 0

    def __aiter__(self) -> _FakeSaslConsumer:
        return self

    async def __anext__(self) -> _FakeRecord:
        if self._position >= len(self._records):
            raise StopAsyncIteration
        record = _FakeRecord(self._position, self._records[self._position])
        self._position += 1
        return record


class _SaslClients:
    """Registry of the fake clients built during a test."""

    def __init__(self) -> None:
        self.records: list[bytes] = [b"f1"]
        self.built: list[_FakeSaslClient] = []

    def track[T: _FakeSaslClient](self, client: T) -> T:
        self.built.append(client)
        return client

    def provider_of(self, client: _FakeSaslClient) -> object:
        return client.kwargs.get("sasl_oauth_token_provider")


@pytest.fixture
def sasl_clients(monkeypatch: pytest.MonkeyPatch) -> _SaslClients:
    registry = _SaslClients()

    def producer(**kwargs: object) -> _FakeSaslProducer:
        return registry.track(_FakeSaslProducer(**kwargs))

    def consumer(*topics: str, **kwargs: object) -> _FakeSaslConsumer:
        return registry.track(_FakeSaslConsumer(*topics, records=registry.records, **kwargs))

    def admin(**kwargs: object) -> _FakeSaslClient:
        return registry.track(_FakeSaslClient(**kwargs))

    monkeypatch.setattr("llamatrade_events.transport.kafka.AIOKafkaProducer", producer)
    monkeypatch.setattr("llamatrade_events.transport.kafka.AIOKafkaConsumer", consumer)
    monkeypatch.setattr("llamatrade_events.transport.kafka.AIOKafkaAdminClient", admin)
    return registry


def _sasl_transport(provider: AbstractTokenProvider) -> KafkaTransport:
    """A SASL transport whose reconnect backoff never sleeps."""
    return KafkaTransport(
        "kafka:9092",
        security_protocol="SASL_SSL",
        token_provider=provider,
        reconnect_base_delay_seconds=0.0,
        reconnect_max_delay_seconds=0.0,
    )


async def _drain(agen: AsyncIterator[tuple[Cursor, bytes]]) -> list[bytes]:
    values = [value async for _cursor, value in agen]
    await agen.aclose()
    return values


async def test_injected_provider_authenticates_every_client(sasl_clients: _SaslClients) -> None:
    provider = _FakeTokenProvider()
    transport = _sasl_transport(provider)

    await transport.publish(STREAM, b"f1", key="acctA")
    await _drain(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN))

    assert len(sasl_clients.built) >= 2
    assert {id(sasl_clients.provider_of(c)) for c in sasl_clients.built} == {id(provider)}
    assert provider.calls == len(sasl_clients.built)  # one token per connection


async def test_the_default_provider_is_built_once_for_the_whole_transport(
    sasl_clients: _SaslClients, adc: _FakeAdc
) -> None:
    """Without an injected provider every client must still share one instance."""
    transport = KafkaTransport("kafka:9092", security_protocol="SASL_SSL")

    await transport.publish(STREAM, b"f1", key="acctA")
    await _drain(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN))

    providers = {id(sasl_clients.provider_of(c)) for c in sasl_clients.built}
    assert len(sasl_clients.built) >= 2
    assert len(providers) == 1
    assert all(
        isinstance(sasl_clients.provider_of(c), GcpTokenProvider) for c in sasl_clients.built
    )


async def test_publish_surfaces_a_token_failure_and_the_next_publish_recovers(
    sasl_clients: _SaslClients,
) -> None:
    """A failed authentication must not leave a half-started producer cached."""
    provider = _FakeTokenProvider(fail_times=1)
    transport = _sasl_transport(provider)

    with pytest.raises(TokenUnavailableError):
        await transport.publish(STREAM, b"f1", key="acctA")

    assert await transport.publish(STREAM, b"f1", key="acctA") == "0:0"
    assert provider.calls == 2


async def test_consume_reconnects_when_a_token_fetch_fails_transiently(
    sasl_clients: _SaslClients,
) -> None:
    """A ``KafkaError``-typed token failure reaches the transport as a bootstrap
    error, so the reader retries instead of dying."""
    provider = _FakeTokenProvider(fail_times=1, error=KafkaError("token endpoint down"))
    transport = _sasl_transport(provider)
    before = metric_value("llamatrade_events_reconnects_total", stream=STREAM, mode="consume")

    values = await _drain(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN))

    assert values == [b"f1"]
    assert provider.calls == 2  # the retry fetched a token again
    after = metric_value("llamatrade_events_reconnects_total", stream=STREAM, mode="consume")
    assert after == before + 1


async def test_consume_fails_fast_on_a_non_kafka_token_failure(
    sasl_clients: _SaslClients,
) -> None:
    provider = _FakeTokenProvider(fail_times=1)
    transport = _sasl_transport(provider)

    with pytest.raises(TokenUnavailableError):
        await _drain(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN))
    assert provider.calls == 1  # not retried behind the reconnect loop


async def test_tail_reconnects_when_a_token_fetch_fails_transiently(
    sasl_clients: _SaslClients,
) -> None:
    provider = _FakeTokenProvider(fail_times=1, error=OSError("metadata server unreachable"))
    transport = _sasl_transport(provider)

    values = await _drain(transport.tail(STREAM, from_cursor=CURSOR_BEGIN))

    assert values == [b"f1"]
    assert provider.calls == 2
