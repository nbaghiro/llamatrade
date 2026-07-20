"""Execution-primitive construction from resolved credentials."""

from uuid import uuid4

from llamatrade_alpaca import BarStreamClient, TradingClient, TradingStreamClient

from src.credentials import DecryptedCredentials
from src.providers import build_bar_stream, build_trade_stream, build_trading_client


def _creds(is_paper: bool = True) -> DecryptedCredentials:
    return DecryptedCredentials(
        id=uuid4(),
        name="Test Keys",
        api_key="PKTEST12345678901234",
        api_secret="SKTEST12345678901234567890123456789012345",
        is_paper=is_paper,
    )


async def test_build_trading_client_carries_creds_and_mode() -> None:
    """Trading client is built from the account's own keys and paper flag."""
    creds = _creds(is_paper=True)
    client = build_trading_client(creds)
    assert isinstance(client, TradingClient)
    try:
        assert client.paper is True
        assert client.credentials.api_key == creds.api_key
        assert client.credentials.api_secret == creds.api_secret
    finally:
        await client.close()


async def test_build_trading_client_uses_oauth_token() -> None:
    """OAuth credentials build a bearer-authenticated client."""
    creds = DecryptedCredentials(
        id=uuid4(), name="Alpaca (OAuth)", access_token="tok123", is_paper=True
    )
    client = build_trading_client(creds)
    assert isinstance(client, TradingClient)
    try:
        assert client.paper is True
        assert client.credentials.to_headers() == {"Authorization": "Bearer tok123"}
    finally:
        await client.close()


def test_build_bar_stream_carries_creds_and_mode() -> None:
    """Bar stream is built from the account's own keys and paper flag."""
    creds = _creds(is_paper=False)
    stream = build_bar_stream(
        creds,
        on_reconnect=lambda: None,
        on_connection_change=lambda _connected: None,
    )
    assert isinstance(stream, BarStreamClient)
    assert stream.paper is False
    assert stream.credentials.api_key == creds.api_key


def test_build_trade_stream_carries_creds_and_mode() -> None:
    """Trade-update stream is built from the account's own keys and paper flag."""
    creds = _creds(is_paper=True)
    stream = build_trade_stream(creds)
    assert isinstance(stream, TradingStreamClient)
    assert stream.paper is True
    assert stream.credentials.api_secret == creds.api_secret
