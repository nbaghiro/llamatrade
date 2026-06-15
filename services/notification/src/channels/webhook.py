"""Webhook notification channel."""

import hashlib
import hmac
import time

import httpx

from llamatrade_telemetry import metrics

_CHANNEL = "webhook"


class WebhookChannel:
    """Webhook notification sender."""

    async def send(
        self,
        url: str,
        payload: dict[str, str | int | float | bool | list[str] | None],
        secret: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> bool:
        """Send a webhook notification."""
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)

        # Sign payload if secret provided
        if secret:
            import json

            body = json.dumps(payload).encode()
            signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            request_headers["X-Signature"] = f"sha256={signature}"

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=request_headers,
                    timeout=30.0,
                )
                ok = bool(response.status_code < 400)
                if ok:
                    metrics.notification.delivered(channel=_CHANNEL)
                else:
                    metrics.notification.delivery_failed(
                        channel=_CHANNEL, reason=f"http_{response.status_code}"
                    )
                return ok
        except Exception as e:
            metrics.notification.delivery_failed(channel=_CHANNEL, reason=type(e).__name__)
            return False
        finally:
            metrics.notification.delivery_latency.labels(channel=_CHANNEL).observe(
                time.perf_counter() - start
            )
