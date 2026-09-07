"""Behavioral tests for the outgoing service-auth interceptor and its token cache."""

from __future__ import annotations

from collections.abc import Sequence

import grpc.aio
import pytest

from llamatrade_proto.interceptors.auth import (
    ServiceAuthClientInterceptor,
    _ServiceTokenCache,
    _with_authorization,
)


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class MintRecorder:
    """Counting stand-in for ``mint_service_token``; returns a fresh token per call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def __call__(self, *, service_name: str = "internal", ttl_seconds: int = 300) -> str:
        self.calls.append((service_name, ttl_seconds))
        return f"token-{len(self.calls)}"


@pytest.fixture
def mint(monkeypatch: pytest.MonkeyPatch) -> MintRecorder:
    recorder = MintRecorder()
    monkeypatch.setattr("llamatrade_common.auth.mint_service_token", recorder)
    return recorder


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr("llamatrade_proto.interceptors.auth.time.time", fake)
    return fake


def _details(
    metadata: Sequence[tuple[str, str]] | None = None,
) -> grpc.aio.ClientCallDetails:
    return grpc.aio.ClientCallDetails(
        method="/llamatrade.Test/Method",
        timeout=5.0,
        metadata=metadata,
        credentials=None,
        wait_for_ready=None,
    )


class TestServiceTokenCache:
    def test_first_get_mints_with_service_name_and_ttl(
        self, mint: MintRecorder, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SERVICE_NAME", "billing")
        cache = _ServiceTokenCache(ttl_seconds=300, refresh_margin=60)

        assert cache.get() == "token-1"
        assert mint.calls == [("billing", 300)]

    def test_default_service_name_is_internal(
        self, mint: MintRecorder, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SERVICE_NAME", raising=False)

        _ServiceTokenCache().get()

        assert mint.calls == [("internal", 300)]

    def test_token_cached_inside_refresh_margin(self, mint: MintRecorder, clock: FakeClock) -> None:
        cache = _ServiceTokenCache(ttl_seconds=300, refresh_margin=60)

        assert cache.get() == "token-1"
        clock.advance(239)
        assert cache.get() == "token-1"
        assert len(mint.calls) == 1

    def test_refresh_margin_triggers_early_refresh(
        self, mint: MintRecorder, clock: FakeClock
    ) -> None:
        cache = _ServiceTokenCache(ttl_seconds=300, refresh_margin=60)

        assert cache.get() == "token-1"
        # 240s in: 60s of the 300s TTL remain, exactly the refresh margin.
        clock.advance(240)
        assert cache.get() == "token-2"
        assert len(mint.calls) == 2

    def test_expired_token_is_reminted(self, mint: MintRecorder, clock: FakeClock) -> None:
        cache = _ServiceTokenCache(ttl_seconds=300, refresh_margin=0)

        assert cache.get() == "token-1"
        clock.advance(299)
        assert cache.get() == "token-1"
        clock.advance(2)
        assert cache.get() == "token-2"

    def test_refreshed_token_starts_a_new_ttl_window(
        self, mint: MintRecorder, clock: FakeClock
    ) -> None:
        cache = _ServiceTokenCache(ttl_seconds=300, refresh_margin=60)

        cache.get()
        clock.advance(240)
        assert cache.get() == "token-2"
        clock.advance(239)
        assert cache.get() == "token-2"
        assert len(mint.calls) == 2


class TestWithAuthorization:
    def test_appends_bearer_header_and_preserves_call_fields(self) -> None:
        details = _details(metadata=[("x-request-id", "42")])

        out = _with_authorization(details, "tok")

        assert list(out.metadata or []) == [
            ("x-request-id", "42"),
            ("authorization", "Bearer tok"),
        ]
        assert out.method == details.method
        assert out.timeout == details.timeout
        assert out.credentials is None
        assert out.wait_for_ready is None

    def test_handles_absent_metadata(self) -> None:
        out = _with_authorization(_details(metadata=None), "tok")

        assert list(out.metadata or []) == [("authorization", "Bearer tok")]

    def test_existing_authorization_header_wins(self) -> None:
        details = _details(metadata=[("authorization", "Bearer user-token")])

        out = _with_authorization(details, "service-token")

        assert out is details

    def test_existing_header_match_is_case_insensitive(self) -> None:
        details = _details(metadata=[("Authorization", "Bearer user-token")])

        out = _with_authorization(details, "service-token")

        assert out is details


class TestServiceAuthClientInterceptor:
    @pytest.mark.parametrize(
        "method_name",
        [
            "intercept_unary_unary",
            "intercept_unary_stream",
            "intercept_stream_unary",
            "intercept_stream_stream",
        ],
    )
    async def test_each_interceptor_attaches_token_and_passes_through(
        self, method_name: str
    ) -> None:
        interceptor = ServiceAuthClientInterceptor(token_provider=lambda: "tok")
        seen: list[grpc.aio.ClientCallDetails] = []

        async def continuation(details: grpc.aio.ClientCallDetails, request: object) -> str:
            seen.append(details)
            return "response"

        result = await getattr(interceptor, method_name)(continuation, _details(), "req")

        assert result == "response"
        assert ("authorization", "Bearer tok") in list(seen[0].metadata or [])

    async def test_default_provider_is_the_token_cache(
        self, mint: MintRecorder, clock: FakeClock
    ) -> None:
        interceptor = ServiceAuthClientInterceptor()
        seen: list[grpc.aio.ClientCallDetails] = []

        async def continuation(details: grpc.aio.ClientCallDetails, request: object) -> str:
            seen.append(details)
            return "response"

        await interceptor.intercept_unary_unary(continuation, _details(), "req")
        await interceptor.intercept_unary_unary(continuation, _details(), "req")

        headers = [dict(d.metadata or [])["authorization"] for d in seen]
        assert headers == ["Bearer token-1", "Bearer token-1"]
        assert len(mint.calls) == 1

    async def test_forwarded_user_token_not_overridden(self) -> None:
        interceptor = ServiceAuthClientInterceptor(token_provider=lambda: "svc")
        seen: list[grpc.aio.ClientCallDetails] = []

        async def continuation(details: grpc.aio.ClientCallDetails, request: object) -> str:
            seen.append(details)
            return "response"

        details = _details(metadata=[("authorization", "Bearer user")])
        await interceptor.intercept_unary_unary(continuation, details, "req")

        assert list(seen[0].metadata or []) == [("authorization", "Bearer user")]
