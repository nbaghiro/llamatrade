"""Alpaca API configuration and URL constants."""

import os
from dataclasses import dataclass
from enum import StrEnum


class AlpacaEnvironment(StrEnum):
    """Alpaca trading environment."""

    PAPER = "paper"
    LIVE = "live"


class AlpacaUrls:
    """URL configuration for Alpaca APIs."""

    # Market Data API
    DATA_LIVE = "https://data.alpaca.markets/v2"
    DATA_PAPER = "https://data.sandbox.alpaca.markets/v2"

    # Trading API
    TRADING_LIVE = "https://api.alpaca.markets/v2"
    TRADING_PAPER = "https://paper-api.alpaca.markets/v2"

    # Streaming WebSocket
    STREAM_LIVE = "wss://stream.data.alpaca.markets/v2/iex"
    STREAM_PAPER = "wss://stream.data.sandbox.alpaca.markets/v2/iex"

    @classmethod
    def data_url(cls, paper: bool = True) -> str:
        """Get market data API URL."""
        return cls.DATA_PAPER if paper else cls.DATA_LIVE

    @classmethod
    def trading_url(cls, paper: bool = True) -> str:
        """Get trading API URL."""
        return cls.TRADING_PAPER if paper else cls.TRADING_LIVE

    @classmethod
    def stream_url(cls, paper: bool = True) -> str:
        """Get WebSocket streaming URL."""
        return cls.STREAM_PAPER if paper else cls.STREAM_LIVE


@dataclass
class AlpacaCredentials:
    """Alpaca API credentials."""

    api_key: str
    api_secret: str

    @classmethod
    def from_env(
        cls,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> AlpacaCredentials:
        """Load credentials from params or environment variables.

        Args:
            api_key: API key (falls back to ALPACA_API_KEY env var)
            api_secret: API secret (falls back to ALPACA_API_SECRET env var)

        Returns:
            AlpacaCredentials instance
        """
        return cls(
            api_key=api_key or os.getenv("ALPACA_API_KEY", ""),
            api_secret=api_secret or os.getenv("ALPACA_API_SECRET", ""),
        )

    def to_headers(self) -> dict[str, str]:
        """Convert credentials to Alpaca auth headers.

        Returns:
            Dict with APCA-API-KEY-ID and APCA-API-SECRET-KEY headers
        """
        headers: dict[str, str] = {}
        if self.api_key:
            headers["APCA-API-KEY-ID"] = self.api_key
        if self.api_secret:
            headers["APCA-API-SECRET-KEY"] = self.api_secret
        return headers

    def is_valid(self) -> bool:
        """Check if credentials are present (non-empty)."""
        return bool(self.api_key and self.api_secret)
