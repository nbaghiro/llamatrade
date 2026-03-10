"""Tests for llamatrade_proto.clients.base module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llamatrade_proto.clients.base import BaseGRPCClient


class TestBaseGRPCClientInit:
    """Tests for BaseGRPCClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Test client initialization with default values."""
        client = BaseGRPCClient("localhost:8810")

        assert client._target == "localhost:8810"
        assert client._secure is False
        assert client._credentials is None
        assert client._interceptors == []
        assert client._channel is None

    def test_init_with_secure(self) -> None:
        """Test client initialization with secure=True."""
        client = BaseGRPCClient("localhost:8810", secure=True)

        assert client._secure is True

    def test_init_with_credentials(self) -> None:
        """Test client initialization with credentials."""
        creds = MagicMock()
        client = BaseGRPCClient("localhost:8810", credentials=creds)

        assert client._credentials is creds

    def test_init_with_interceptors(self) -> None:
        """Test client initialization with interceptors."""
        interceptor = MagicMock()
        client = BaseGRPCClient("localhost:8810", interceptors=[interceptor])

        assert client._interceptors == [interceptor]

    def test_init_with_custom_options(self) -> None:
        """Test client initialization with custom options."""
        options = [("grpc.max_send_message_length", 100)]
        client = BaseGRPCClient("localhost:8810", options=options)

        assert client._options == options

    def test_init_default_options(self) -> None:
        """Test client has sensible default options."""
        client = BaseGRPCClient("localhost:8810")

        # Should have keepalive and message size options
        option_names = [opt[0] for opt in client._options]
        assert "grpc.keepalive_time_ms" in option_names
        assert "grpc.max_receive_message_length" in option_names


class TestBaseGRPCClientChannel:
    """Tests for BaseGRPCClient channel management."""

    def test_channel_property_creates_channel(self) -> None:
        """Test channel property creates channel on first access."""
        client = BaseGRPCClient("localhost:8810")

        with patch("grpc.aio.insecure_channel") as mock_insecure:
            mock_channel = MagicMock()
            mock_insecure.return_value = mock_channel

            channel = client.channel

            assert channel is mock_channel
            mock_insecure.assert_called_once()

    def test_channel_property_returns_same_instance(self) -> None:
        """Test channel property returns same instance on subsequent calls."""
        client = BaseGRPCClient("localhost:8810")

        with patch("grpc.aio.insecure_channel") as mock_insecure:
            mock_channel = MagicMock()
            mock_insecure.return_value = mock_channel

            channel1 = client.channel
            channel2 = client.channel

            assert channel1 is channel2
            # Should only create once
            assert mock_insecure.call_count == 1

    def test_create_channel_insecure(self) -> None:
        """Test _create_channel creates insecure channel."""
        client = BaseGRPCClient("localhost:8810", secure=False)

        with patch("grpc.aio.insecure_channel") as mock_insecure:
            mock_channel = MagicMock()
            mock_insecure.return_value = mock_channel

            client._create_channel()

            mock_insecure.assert_called_once_with(
                "localhost:8810",
                options=client._options,
                interceptors=client._interceptors,
            )

    def test_create_channel_secure_default_credentials(self) -> None:
        """Test _create_channel creates secure channel with default credentials."""
        client = BaseGRPCClient("localhost:8810", secure=True)

        with patch("grpc.aio.secure_channel") as mock_secure:
            with patch("grpc.ssl_channel_credentials") as mock_ssl_creds:
                mock_creds = MagicMock()
                mock_ssl_creds.return_value = mock_creds
                mock_channel = MagicMock()
                mock_secure.return_value = mock_channel

                client._create_channel()

                mock_ssl_creds.assert_called_once()
                mock_secure.assert_called_once_with(
                    "localhost:8810",
                    mock_creds,
                    options=client._options,
                    interceptors=client._interceptors,
                )

    def test_create_channel_secure_custom_credentials(self) -> None:
        """Test _create_channel uses custom credentials when provided."""
        custom_creds = MagicMock()
        client = BaseGRPCClient("localhost:8810", secure=True, credentials=custom_creds)

        with patch("grpc.aio.secure_channel") as mock_secure:
            mock_channel = MagicMock()
            mock_secure.return_value = mock_channel

            client._create_channel()

            mock_secure.assert_called_once_with(
                "localhost:8810",
                custom_creds,
                options=client._options,
                interceptors=client._interceptors,
            )


class TestBaseGRPCClientClose:
    """Tests for BaseGRPCClient close method."""

    @pytest.mark.asyncio
    async def test_close_closes_channel(self) -> None:
        """Test close() closes the channel."""
        client = BaseGRPCClient("localhost:8810")

        mock_channel = MagicMock()
        mock_channel.close = AsyncMock()
        client._channel = mock_channel

        await client.close()

        mock_channel.close.assert_called_once()
        assert client._channel is None

    @pytest.mark.asyncio
    async def test_close_safe_when_no_channel(self) -> None:
        """Test close() is safe when no channel exists."""
        client = BaseGRPCClient("localhost:8810")
        client._channel = None

        # Should not raise
        await client.close()


class TestBaseGRPCClientContextManager:
    """Tests for BaseGRPCClient async context manager."""

    @pytest.mark.asyncio
    async def test_aenter_returns_self(self) -> None:
        """Test __aenter__ returns the client."""
        client = BaseGRPCClient("localhost:8810")

        result = await client.__aenter__()

        assert result is client

    @pytest.mark.asyncio
    async def test_aexit_calls_close(self) -> None:
        """Test __aexit__ calls close."""
        client = BaseGRPCClient("localhost:8810")
        client.close = AsyncMock()

        await client.__aexit__(None, None, None)

        client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_usage(self) -> None:
        """Test using client as async context manager."""
        with patch("grpc.aio.insecure_channel") as mock_insecure:
            mock_channel = MagicMock()
            mock_channel.close = AsyncMock()
            mock_insecure.return_value = mock_channel

            async with BaseGRPCClient("localhost:8810") as client:
                # Access channel to create it
                _ = client.channel

            # Channel should be closed after context
            mock_channel.close.assert_called_once()


class TestBaseGRPCClientWaitForReady:
    """Tests for BaseGRPCClient wait_for_ready method."""

    @pytest.mark.asyncio
    async def test_wait_for_ready_success(self) -> None:
        """Test wait_for_ready returns True when channel is ready."""
        client = BaseGRPCClient("localhost:8810")

        with patch("grpc.aio.insecure_channel") as mock_insecure:
            mock_channel = MagicMock()
            mock_channel.channel_ready = AsyncMock()
            mock_insecure.return_value = mock_channel

            result = await client.wait_for_ready(timeout=5.0)

            assert result is True
            mock_channel.channel_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_ready_failure(self) -> None:
        """Test wait_for_ready returns False on error."""
        import grpc.aio

        client = BaseGRPCClient("localhost:8810")

        with patch("grpc.aio.insecure_channel") as mock_insecure:
            mock_channel = MagicMock()
            mock_channel.channel_ready = AsyncMock(
                side_effect=grpc.aio.AioRpcError(
                    code=MagicMock(),
                    initial_metadata=MagicMock(),
                    trailing_metadata=MagicMock(),
                    details="Connection failed",
                    debug_error_string="debug",
                )
            )
            mock_insecure.return_value = mock_channel

            result = await client.wait_for_ready(timeout=1.0)

            assert result is False
