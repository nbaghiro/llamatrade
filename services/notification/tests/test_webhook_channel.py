"""Webhook channel contract: sign-what-you-send, transient-only retry.

These tests capture the actual wire request through ``httpx.MockTransport``
and verify the HMAC against the raw transmitted body — the receiver's
perspective, not the sender's bookkeeping.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx
import pytest

from src.channels.webhook import SIGNATURE_HEADER, WebhookChannel, encode_payload, sign_payload

PAYLOAD: dict[str, object] = {"category": 1, "title": "T", "message": "M"}


class _Capture:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._responses = responses

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self._responses) - 1)
        return self._responses[index]


def _channel(capture: _Capture) -> WebhookChannel:
    return WebhookChannel(transport=httpx.MockTransport(capture))


async def test_signature_verifies_against_transmitted_bytes() -> None:
    capture = _Capture([httpx.Response(200)])
    result = await _channel(capture).send("https://example.test/hook", PAYLOAD, secret="s3cret")

    assert result.ok
    request = capture.requests[0]
    expected = hmac.new(b"s3cret", request.content, hashlib.sha256).hexdigest()
    assert request.headers[SIGNATURE_HEADER] == f"sha256={expected}"


def test_encode_sign_round_trip() -> None:
    body = encode_payload(PAYLOAD)
    assert sign_payload("k", body) == hmac.new(b"k", body, hashlib.sha256).hexdigest()


async def test_no_secret_no_signature_header() -> None:
    capture = _Capture([httpx.Response(200)])
    await _channel(capture).send("https://example.test/hook", PAYLOAD)
    assert SIGNATURE_HEADER not in capture.requests[0].headers


async def test_custom_headers_included() -> None:
    capture = _Capture([httpx.Response(200)])
    await _channel(capture).send("https://example.test/hook", PAYLOAD, headers={"X-Custom": "yes"})
    assert capture.requests[0].headers["X-Custom"] == "yes"
    assert capture.requests[0].headers["Content-Type"] == "application/json"


async def test_4xx_is_permanent_no_retry() -> None:
    capture = _Capture([httpx.Response(404)])
    result = await _channel(capture).send("https://example.test/hook", PAYLOAD)
    assert not result.ok
    assert result.status_code == 404
    assert len(capture.requests) == 1


async def test_5xx_retries_then_succeeds() -> None:
    capture = _Capture([httpx.Response(500), httpx.Response(200)])
    result = await _channel(capture).send("https://example.test/hook", PAYLOAD)
    assert result.ok
    assert len(capture.requests) == 2


async def test_5xx_exhausts_attempts() -> None:
    capture = _Capture([httpx.Response(503)])
    result = await _channel(capture).send("https://example.test/hook", PAYLOAD)
    assert not result.ok
    assert result.status_code == 503
    assert len(capture.requests) == 3


async def test_timeout_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("boom")

    channel = WebhookChannel(transport=httpx.MockTransport(handler))
    result = await channel.send("https://example.test/hook", PAYLOAD)
    assert not result.ok
    assert result.error == "ConnectTimeout"
    assert calls == 3


async def test_connect_error_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("refused")

    channel = WebhookChannel(transport=httpx.MockTransport(handler))
    result = await channel.send("https://example.test/hook", PAYLOAD)
    assert not result.ok
    assert result.error == "ConnectError"
    assert calls == 3


async def test_identical_payload_signs_identically() -> None:
    signatures = []
    for _ in range(2):
        capture = _Capture([httpx.Response(200)])
        await _channel(capture).send("https://example.test/hook", dict(PAYLOAD), secret="k")
        signatures.append(capture.requests[0].headers[SIGNATURE_HEADER])
    assert signatures[0] == signatures[1]


@pytest.mark.parametrize("status", [200, 201, 204, 399])
async def test_success_statuses(status: int) -> None:
    capture = _Capture([httpx.Response(status)])
    result = await _channel(capture).send("https://example.test/hook", PAYLOAD)
    assert result.ok
    assert result.status_code == status
