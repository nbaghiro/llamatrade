"""Base HTTP client for Alpaca APIs."""

import logging
from typing import Any, Self

import httpx

from .config import AlpacaCredentials
from .errors import AuthenticationError
from .resilience import CircuitBreaker, RateLimiter, parse_alpaca_error

logger = logging.getLogger(__name__)


class AlpacaClientBase:
    """Base client with auth, resilience, and request handling.

    Subclasses should:
    1. Set BASE_URL_LIVE and BASE_URL_PAPER class attributes
    2. Implement their own API methods using _request()

    Example:
        class AlpacaDataClient(AlpacaClientBase):
            BASE_URL_LIVE = "https://data.alpaca.markets/v2"
            BASE_URL_PAPER = "https://data.sandbox.alpaca.markets/v2"

            async def get_bars(self, symbol: str) -> list[Bar]:
                response = await self._request("GET", f"/stocks/{symbol}/bars")
                return [parse_bar(b) for b in response.json().get("bars", [])]
    """

    BASE_URL_LIVE: str = ""  # Override in subclass
    BASE_URL_PAPER: str = ""  # Override in subclass

    def __init__(
        self,
        credentials: AlpacaCredentials | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        paper: bool = True,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        timeout: float = 30.0,
    ):
        """Initialize Alpaca client.

        Args:
            credentials: Pre-configured credentials (takes precedence)
            api_key: API key (alternative to credentials)
            api_secret: API secret (alternative to credentials)
            paper: Use paper trading environment (default True)
            rate_limiter: Optional rate limiter instance
            circuit_breaker: Optional circuit breaker instance
            timeout: HTTP request timeout in seconds
        """
        if credentials:
            self.credentials = credentials
        else:
            self.credentials = AlpacaCredentials.from_env(api_key, api_secret)

        self.paper = paper
        self.base_url = self.BASE_URL_PAPER if paper else self.BASE_URL_LIVE

        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.credentials.to_headers(),
            timeout=timeout,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a request with optional rate limiting and circuit breaker.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., "/stocks/AAPL/bars")
            params: Query parameters
            json: JSON body for POST/PUT requests

        Returns:
            HTTP response

        Raises:
            AlpacaError subclass on API errors
            CircuitOpenError if circuit breaker is open
            AuthenticationError if credentials are invalid
        """
        # Rate limiting (if configured)
        if self._rate_limiter:
            await self._rate_limiter.acquire()

        async def make_request() -> httpx.Response:
            response = await self._client.request(method, path, params=params, json=json)

            if response.status_code == 401:
                raise AuthenticationError("Invalid API credentials")
            if response.status_code == 403:
                raise AuthenticationError("Forbidden - check API permissions")
            if response.status_code >= 400:
                raise parse_alpaca_error(response)

            return response

        # Circuit breaker (if configured)
        if self._circuit_breaker:
            return await self._circuit_breaker.call(make_request)

        return await make_request()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """Convenience method for GET requests."""
        return await self._request("GET", path, params=params)

    async def _post(
        self, path: str, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        """Convenience method for POST requests."""
        return await self._request("POST", path, params=params, json=json)

    async def _delete(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """Convenience method for DELETE requests."""
        return await self._request("DELETE", path, params=params)
