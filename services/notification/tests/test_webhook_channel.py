"""Tests for WebhookChannel to improve coverage."""

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.channels.webhook import WebhookChannel

# === Test Fixtures ===


@pytest.fixture
def webhook_channel() -> WebhookChannel:
    """Create a WebhookChannel instance."""
    return WebhookChannel()


# === WebhookChannel.send Tests ===


class TestWebhookChannelSend:
    """Tests for WebhookChannel.send method."""

    async def test_send_success(self, webhook_channel: WebhookChannel) -> None:
        """Test successful webhook send."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload={"event": "test", "data": "value"},
            )

            assert result is True
            mock_client.post.assert_called_once()

    async def test_send_with_custom_headers(self, webhook_channel: WebhookChannel) -> None:
        """Test send with custom headers."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload={"event": "test"},
                headers={"Authorization": "Bearer token123"},
            )

            assert result is True
            # Verify headers were passed
            call_kwargs = mock_client.post.call_args.kwargs
            assert "Authorization" in call_kwargs["headers"]

    async def test_send_with_signature(self, webhook_channel: WebhookChannel) -> None:
        """Test send with HMAC signature."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            payload: dict[str, Any] = {"event": "signed_event", "value": 123}
            secret = "my_webhook_secret"

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload=payload,
                secret=secret,
            )

            assert result is True
            # Verify signature header was added
            call_kwargs = mock_client.post.call_args.kwargs
            assert "X-Signature" in call_kwargs["headers"]
            assert call_kwargs["headers"]["X-Signature"].startswith("sha256=")

    async def test_send_signature_correct(self, webhook_channel: WebhookChannel) -> None:
        """Test that HMAC signature is correctly calculated."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            payload: dict[str, str | int | float | bool | list[str] | None] = {"test": "data"}
            secret = "secret123"

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload=payload,
                secret=secret,
            )

            assert result is True
            # Verify post was called with headers containing signature
            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args.kwargs
            assert "X-Signature" in call_kwargs["headers"]
            assert call_kwargs["headers"]["X-Signature"].startswith("sha256=")

    async def test_send_failure_status_code(self, webhook_channel: WebhookChannel) -> None:
        """Test send returns False on error status code."""
        mock_response = AsyncMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload={"event": "test"},
            )

            assert result is False

    async def test_send_4xx_status_code(self, webhook_channel: WebhookChannel) -> None:
        """Test send returns False on 4xx status code."""
        mock_response = AsyncMock()
        mock_response.status_code = 400

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload={"event": "test"},
            )

            assert result is False

    async def test_send_exception_returns_false(self, webhook_channel: WebhookChannel) -> None:
        """Test send returns False on exception."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload={"event": "test"},
            )

            assert result is False

    async def test_send_timeout_returns_false(self, webhook_channel: WebhookChannel) -> None:
        """Test send returns False on timeout."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload={"event": "test"},
            )

            assert result is False

    async def test_send_content_type_header(self, webhook_channel: WebhookChannel) -> None:
        """Test that Content-Type header is set correctly."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await webhook_channel.send(
                url="https://example.com/webhook",
                payload={"test": "data"},
            )

            # Verify post was called with Content-Type header
            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args.kwargs
            assert call_kwargs["headers"]["Content-Type"] == "application/json"

    async def test_send_status_codes_boundary(self, webhook_channel: WebhookChannel) -> None:
        """Test boundary status codes (399 vs 400)."""
        # 399 should return True (< 400)
        mock_response_399 = AsyncMock()
        mock_response_399.status_code = 399

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response_399)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload={"test": "data"},
            )

            assert result is True

    async def test_send_various_payload_types(self, webhook_channel: WebhookChannel) -> None:
        """Test send with various payload value types."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            payload: dict[str, Any] = {
                "string_val": "test",
                "int_val": 42,
                "float_val": 3.14,
                "bool_val": True,
                "list_val": ["a", "b", "c"],
                "null_val": None,
            }

            result = await webhook_channel.send(
                url="https://example.com/webhook",
                payload=payload,
            )

            assert result is True
