"""Tests for config module."""

import os
from unittest.mock import patch

from llamatrade_alpaca import AlpacaCredentials, AlpacaEnvironment, AlpacaUrls


class TestAlpacaUrls:
    """Tests for AlpacaUrls."""

    def test_data_url_paper(self) -> None:
        """Test paper data URL."""
        assert AlpacaUrls.data_url(paper=True) == "https://data.sandbox.alpaca.markets/v2"

    def test_data_url_live(self) -> None:
        """Test live data URL."""
        assert AlpacaUrls.data_url(paper=False) == "https://data.alpaca.markets/v2"

    def test_trading_url_paper(self) -> None:
        """Test paper trading URL."""
        assert AlpacaUrls.trading_url(paper=True) == "https://paper-api.alpaca.markets/v2"

    def test_trading_url_live(self) -> None:
        """Test live trading URL."""
        assert AlpacaUrls.trading_url(paper=False) == "https://api.alpaca.markets/v2"

    def test_stream_url_paper(self) -> None:
        """Test paper stream URL."""
        assert (
            AlpacaUrls.stream_url(paper=True) == "wss://stream.data.sandbox.alpaca.markets/v2/iex"
        )

    def test_stream_url_live(self) -> None:
        """Test live stream URL."""
        assert AlpacaUrls.stream_url(paper=False) == "wss://stream.data.alpaca.markets/v2/iex"


class TestAlpacaCredentials:
    """Tests for AlpacaCredentials."""

    def test_direct_creation(self, api_key: str, api_secret: str) -> None:
        """Test creating credentials directly."""
        creds = AlpacaCredentials(api_key=api_key, api_secret=api_secret)
        assert creds.api_key == api_key
        assert creds.api_secret == api_secret

    def test_from_env_with_params(self, api_key: str, api_secret: str) -> None:
        """Test from_env with explicit params takes precedence."""
        env_vars = {"ALPACA_API_KEY": "env_key", "ALPACA_API_SECRET": "env_secret"}
        with patch.dict(os.environ, env_vars):
            creds = AlpacaCredentials.from_env(api_key=api_key, api_secret=api_secret)
            assert creds.api_key == api_key
            assert creds.api_secret == api_secret

    def test_from_env_without_params(self) -> None:
        """Test from_env falls back to environment variables."""
        with patch.dict(
            os.environ, {"ALPACA_API_KEY": "env_key", "ALPACA_API_SECRET": "env_secret"}
        ):
            creds = AlpacaCredentials.from_env()
            assert creds.api_key == "env_key"
            assert creds.api_secret == "env_secret"

    def test_from_env_missing_vars(self) -> None:
        """Test from_env with missing env vars returns empty strings."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env vars if they exist
            os.environ.pop("ALPACA_API_KEY", None)
            os.environ.pop("ALPACA_API_SECRET", None)
            creds = AlpacaCredentials.from_env()
            assert creds.api_key == ""
            assert creds.api_secret == ""

    def test_to_headers(self, api_key: str, api_secret: str) -> None:
        """Test converting credentials to headers."""
        creds = AlpacaCredentials(api_key=api_key, api_secret=api_secret)
        headers = creds.to_headers()
        assert headers["APCA-API-KEY-ID"] == api_key
        assert headers["APCA-API-SECRET-KEY"] == api_secret

    def test_to_headers_empty_credentials(self) -> None:
        """Test to_headers with empty credentials returns empty dict."""
        creds = AlpacaCredentials(api_key="", api_secret="")
        headers = creds.to_headers()
        assert headers == {}

    def test_is_valid_true(self, api_key: str, api_secret: str) -> None:
        """Test is_valid returns True when both credentials present."""
        creds = AlpacaCredentials(api_key=api_key, api_secret=api_secret)
        assert creds.is_valid() is True

    def test_is_valid_false_missing_key(self, api_secret: str) -> None:
        """Test is_valid returns False when key missing."""
        creds = AlpacaCredentials(api_key="", api_secret=api_secret)
        assert creds.is_valid() is False

    def test_is_valid_false_missing_secret(self, api_key: str) -> None:
        """Test is_valid returns False when secret missing."""
        creds = AlpacaCredentials(api_key=api_key, api_secret="")
        assert creds.is_valid() is False


class TestAlpacaEnvironment:
    """Tests for AlpacaEnvironment enum."""

    def test_paper_value(self) -> None:
        """Test paper environment value."""
        assert AlpacaEnvironment.PAPER == "paper"

    def test_live_value(self) -> None:
        """Test live environment value."""
        assert AlpacaEnvironment.LIVE == "live"
