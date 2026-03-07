"""Tests for client_base module."""

import httpx
import pytest
import respx

from llamatrade_alpaca import (
    AlpacaClientBase,
    AlpacaCredentials,
    AuthenticationError,
    InvalidRequestError,
)
from llamatrade_alpaca.resilience import CircuitBreaker, RateLimiter


class MockAlpacaClient(AlpacaClientBase):
    """Mock client implementation for tests."""

    BASE_URL_LIVE = "https://api.example.com/v2"
    BASE_URL_PAPER = "https://paper-api.example.com/v2"


class TestAlpacaClientBase:
    """Tests for AlpacaClientBase."""

    def test_init_with_paper(self, api_key: str, api_secret: str) -> None:
        """Test client initialization for paper trading."""
        client = MockAlpacaClient(api_key=api_key, api_secret=api_secret, paper=True)
        assert client.paper is True
        assert client.base_url == "https://paper-api.example.com/v2"

    def test_init_with_live(self, api_key: str, api_secret: str) -> None:
        """Test client initialization for live trading."""
        client = MockAlpacaClient(api_key=api_key, api_secret=api_secret, paper=False)
        assert client.paper is False
        assert client.base_url == "https://api.example.com/v2"

    def test_init_with_credentials(self) -> None:
        """Test client initialization with AlpacaCredentials."""
        creds = AlpacaCredentials(api_key="cred_key", api_secret="cred_secret")
        client = MockAlpacaClient(credentials=creds)
        assert client.credentials.api_key == "cred_key"

    def test_init_with_resilience(self) -> None:
        """Test client initialization with resilience components."""
        rate_limiter = RateLimiter(capacity=100)
        circuit_breaker = CircuitBreaker(failure_threshold=3)

        client = MockAlpacaClient(
            api_key="key",
            api_secret="secret",
            rate_limiter=rate_limiter,
            circuit_breaker=circuit_breaker,
        )

        assert client._rate_limiter is rate_limiter
        assert client._circuit_breaker is circuit_breaker

    @respx.mock
    async def test_request_success(self) -> None:
        """Test successful request."""
        respx.get("https://paper-api.example.com/v2/test").mock(
            return_value=httpx.Response(200, json={"result": "ok"})
        )

        async with MockAlpacaClient(api_key="key", api_secret="secret") as client:
            response = await client._request("GET", "/test")
            assert response.status_code == 200
            assert response.json() == {"result": "ok"}

    @respx.mock
    async def test_request_401_raises_auth_error(self) -> None:
        """Test 401 raises AuthenticationError."""
        respx.get("https://paper-api.example.com/v2/test").mock(
            return_value=httpx.Response(401, json={"message": "unauthorized"})
        )

        async with MockAlpacaClient(api_key="key", api_secret="secret") as client:
            with pytest.raises(AuthenticationError) as exc_info:
                await client._request("GET", "/test")
            assert "Invalid API credentials" in str(exc_info.value)

    @respx.mock
    async def test_request_403_raises_auth_error(self) -> None:
        """Test 403 raises AuthenticationError."""
        respx.get("https://paper-api.example.com/v2/test").mock(
            return_value=httpx.Response(403, json={"message": "forbidden"})
        )

        async with MockAlpacaClient(api_key="key", api_secret="secret") as client:
            with pytest.raises(AuthenticationError) as exc_info:
                await client._request("GET", "/test")
            assert "Forbidden" in str(exc_info.value)

    @respx.mock
    async def test_request_400_raises_invalid_request(self) -> None:
        """Test 400 raises InvalidRequestError."""
        respx.get("https://paper-api.example.com/v2/test").mock(
            return_value=httpx.Response(400, json={"message": "bad request"})
        )

        async with MockAlpacaClient(api_key="key", api_secret="secret") as client:
            with pytest.raises(InvalidRequestError):
                await client._request("GET", "/test")

    @respx.mock
    async def test_get_convenience_method(self) -> None:
        """Test _get convenience method."""
        respx.get("https://paper-api.example.com/v2/test").mock(
            return_value=httpx.Response(200, json={"result": "ok"})
        )

        async with MockAlpacaClient(api_key="key", api_secret="secret") as client:
            response = await client._get("/test")
            assert response.status_code == 200

    @respx.mock
    async def test_post_convenience_method(self) -> None:
        """Test _post convenience method."""
        respx.post("https://paper-api.example.com/v2/test").mock(
            return_value=httpx.Response(201, json={"id": "123"})
        )

        async with MockAlpacaClient(api_key="key", api_secret="secret") as client:
            response = await client._post("/test", json={"data": "value"})
            assert response.status_code == 201

    @respx.mock
    async def test_delete_convenience_method(self) -> None:
        """Test _delete convenience method."""
        respx.delete("https://paper-api.example.com/v2/test/123").mock(
            return_value=httpx.Response(204)
        )

        async with MockAlpacaClient(api_key="key", api_secret="secret") as client:
            response = await client._delete("/test/123")
            assert response.status_code == 204

    async def test_context_manager(self) -> None:
        """Test async context manager."""
        async with MockAlpacaClient(api_key="key", api_secret="secret") as client:
            assert client._client is not None
        # Client should be closed after context

    @respx.mock
    async def test_request_with_rate_limiter(self) -> None:
        """Test request uses rate limiter when configured."""
        respx.get("https://paper-api.example.com/v2/test").mock(
            return_value=httpx.Response(200, json={"result": "ok"})
        )

        rate_limiter = RateLimiter(capacity=10)
        initial_tokens = rate_limiter.available_tokens

        async with MockAlpacaClient(
            api_key="key", api_secret="secret", rate_limiter=rate_limiter
        ) as client:
            await client._request("GET", "/test")

        # Token should have been consumed
        assert rate_limiter.available_tokens < initial_tokens
