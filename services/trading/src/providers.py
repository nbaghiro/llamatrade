"""Execution primitives: turning a resolved account credential into clients.

One place that maps a decrypted credential to the trading REST client and the
market-data / trade-update streams, so credential-to-client construction is not
scattered across the service. Today only bring-your-own-keys exists; when an
Alpaca Broker API path is added these gain a provider-selection branch. See
`.docs/planning/broker-provider-seam.md`.
"""

from __future__ import annotations

from collections.abc import Callable

from llamatrade_alpaca import (
    AlpacaCredentials,
    BarStreamClient,
    TradingClient,
    TradingStreamClient,
)

from src.credentials import DecryptedCredentials


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
) -> BarStreamClient:
    """Market-data (bar) stream from the account's own Alpaca credentials."""
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
