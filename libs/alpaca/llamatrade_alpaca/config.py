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

    # Market Data API — host is environment-agnostic (paper and live share it;
    # only the trading API is paper/live split). IEX feed is free for paper.
    DATA_LIVE = "https://data.alpaca.markets/v2"
    DATA_PAPER = "https://data.alpaca.markets/v2"

    # Trading API
    TRADING_LIVE = "https://api.alpaca.markets/v2"
    TRADING_PAPER = "https://paper-api.alpaca.markets/v2"

    # Market Data Streaming WebSocket (real-time trades/quotes/bars, IEX feed) —
    # single host for paper and live (see DATA_* above).
    STREAM_LIVE = "wss://stream.data.alpaca.markets/v2/iex"
    STREAM_PAPER = "wss://stream.data.alpaca.markets/v2/iex"

    # Trading (account) Streaming WebSocket (order/trade_updates events)
    TRADE_STREAM_LIVE = "wss://api.alpaca.markets/stream"
    TRADE_STREAM_PAPER = "wss://paper-api.alpaca.markets/stream"

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
        """Get market data WebSocket streaming URL."""
        return cls.STREAM_PAPER if paper else cls.STREAM_LIVE

    @classmethod
    def trade_stream_url(cls, paper: bool = True) -> str:
        """Get trading (account) WebSocket streaming URL for trade_updates."""
        return cls.TRADE_STREAM_PAPER if paper else cls.TRADE_STREAM_LIVE


@dataclass
class AlpacaCredentials:
    """Alpaca API credentials.

    Either an API key + secret (BYO / env), or an OAuth bearer ``access_token``
    obtained via the authorization-code flow. When a token is present it takes
    precedence and drives ``Authorization: Bearer`` auth.
    """

    api_key: str = ""
    api_secret: str = ""
    access_token: str | None = None

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
            ``Authorization: Bearer`` when an OAuth token is set, else the
            ``APCA-API-KEY-ID`` / ``APCA-API-SECRET-KEY`` header pair.
        """
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        headers: dict[str, str] = {}
        if self.api_key:
            headers["APCA-API-KEY-ID"] = self.api_key
        if self.api_secret:
            headers["APCA-API-SECRET-KEY"] = self.api_secret
        return headers

    def is_valid(self) -> bool:
        """Present if an OAuth token, or both API key and secret, are set."""
        return bool(self.access_token or (self.api_key and self.api_secret))
