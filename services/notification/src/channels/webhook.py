"""Webhook notification channel."""

import hashlib
import hmac

import httpx


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

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=request_headers,
                    timeout=30.0,
                )
                return bool(response.status_code < 400)
        except Exception:
            return False
