"""Execution primitives: turning a resolved account credential into clients.

One place that maps a decrypted credential to the trading REST client and the
market-data / trade-update streams, so credential-to-client construction is not
scattered across the service. Today only bring-your-own-keys exists; when an
Alpaca Broker API path is added these gain a provider-selection branch. See
`.docs/planning/broker-provider-seam.md`.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from llamatrade_alpaca import (
    AlpacaCredentials,
    BarStreamClient,
    TradingClient,
    TradingStreamClient,
)

from src.credentials import DecryptedCredentials
from src.runner.service_bar_stream import ServiceBarStream

# Opt-in (default off): source live bars from the shared market-data StreamBars fan-out (one platform connection) instead of a per-tenant Alpaca WebSocket. See service_bar_stream.py.
_BARS_FROM_SERVICE = os.getenv("TRADING_BARS_FROM_SERVICE", "").lower() in ("1", "true", "yes")
_MARKET_DATA_TARGET = os.getenv("MARKET_DATA_GRPC_TARGET", "market-data:8840")


def build_trading_client(creds: DecryptedCredentials) -> TradingClient:
    """Trading REST client from the account's own Alpaca credentials.

    Uses an OAuth bearer token when present, else the API key/secret pair.
    """
    if creds.access_token:
        return TradingClient(
            credentials=AlpacaCredentials(access_token=creds.access_token),
            paper=creds.is_paper,
        )
    return TradingClient(
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        paper=creds.is_paper,
    )


def build_bar_stream(
    creds: DecryptedCredentials,
    *,
    on_reconnect: Callable[[], None] | None = None,
    on_connection_change: Callable[[bool], None] | None = None,
) -> BarStreamClient | ServiceBarStream:
    """Market-data (bar) stream for a session.

    Default: the account's own Alpaca WebSocket. With ``TRADING_BARS_FROM_SERVICE``:
    the shared market-data ``StreamBars`` fan-out (one platform connection), which lets
    a tenant run multiple concurrent live strategies without exhausting their single
    Alpaca market-data stream. Credentials are unused in the shared-stream path (bars
    are public); per-tenant creds remain for execution / trade-updates.
    """
    if _BARS_FROM_SERVICE:
        return ServiceBarStream(
            _MARKET_DATA_TARGET,
            on_reconnect=on_reconnect,
            on_connection_change=on_connection_change,
        )
    return BarStreamClient(
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        paper=creds.is_paper,
        on_reconnect=on_reconnect,
        on_connection_change=on_connection_change,
    )


def build_trade_stream(
    creds: DecryptedCredentials,
    *,
    on_reconnect: Callable[[], None] | None = None,
    on_connection_change: Callable[[bool], None] | None = None,
) -> TradingStreamClient:
    """Trade-update stream from the account's own Alpaca credentials."""
    return TradingStreamClient(
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        paper=creds.is_paper,
        on_reconnect=on_reconnect,
        on_connection_change=on_connection_change,
    )
