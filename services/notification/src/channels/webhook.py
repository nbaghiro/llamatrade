"""Webhook notification channel — the platform's one webhook delivery contract.

The signature is HMAC-SHA256 over the exact transmitted bytes (posted with
``content=``, never ``json=``), header ``X-Webhook-Signature: sha256=<hex>``,
so receivers verify byte-for-byte. Retries cover only transient classes
(5xx, connect, timeout); a 4xx is a permanent verdict and is returned as-is.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

import httpx

from llamatrade_telemetry import metrics

_CHANNEL = "webhook"
_TIMEOUT = 10.0
_ATTEMPTS = 3
_BACKOFF_BASE = 0.5

SIGNATURE_HEADER = "X-Webhook-Signature"


def sign_payload(secret: str, payload_bytes: bytes) -> str:
    """HMAC-SHA256 hexdigest of the exact bytes posted (webhook signature contract)."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def encode_payload(payload: dict[str, object]) -> bytes:
    """The canonical wire encoding; whatever these bytes are is what gets signed."""
    return json.dumps(payload, sort_keys=True, default=str).encode("utf-8")


@dataclass(frozen=True)
class WebhookResult:
    ok: bool
    status_code: int | None
    error: str | None


class WebhookChannel:
    """Webhook sender: sign-what-you-send, transient-only retry."""

    def __init__(
        self,
        *,
        timeout: float = _TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = timeout
        self._transport = transport

    async def send(
        self,
        url: str,
        payload: dict[str, object],
        secret: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> WebhookResult:
        body = encode_payload(payload)
        request_headers = {"Content-Type": "application/json"}
        if secret:
            request_headers[SIGNATURE_HEADER] = f"sha256={sign_payload(secret, body)}"
        if headers:
            request_headers.update(headers)

        start = time.perf_counter()
        try:
            result = await self._post_with_retry(url, body, request_headers)
        finally:
            metrics.notification.delivery_latency.labels(channel=_CHANNEL).observe(
                time.perf_counter() - start
            )
        if result.ok:
            metrics.notification.delivered(channel=_CHANNEL)
        else:
            reason = f"http_{result.status_code}" if result.status_code else result.error or "error"
            metrics.notification.delivery_failed(channel=_CHANNEL, reason=reason)
        return result

    async def _post_with_retry(
        self, url: str, body: bytes, headers: dict[str, str]
    ) -> WebhookResult:
        last: WebhookResult = WebhookResult(ok=False, status_code=None, error="unsent")
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for attempt in range(_ATTEMPTS):
                try:
                    response = await client.post(url, content=body, headers=headers)
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    last = WebhookResult(ok=False, status_code=None, error=type(e).__name__)
                except httpx.HTTPError as e:
                    return WebhookResult(ok=False, status_code=None, error=type(e).__name__)
                else:
                    if response.status_code < 400:
                        return WebhookResult(ok=True, status_code=response.status_code, error=None)
                    last = WebhookResult(ok=False, status_code=response.status_code, error=None)
                    if response.status_code < 500:
                        return last
                if attempt < _ATTEMPTS - 1:
                    await asyncio.sleep(_BACKOFF_BASE * (2**attempt))
        return last
