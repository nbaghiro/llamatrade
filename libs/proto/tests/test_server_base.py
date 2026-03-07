"""Tests for llamatrade_proto.server.base module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llamatrade_proto.server.base import GRPCServer


class TestGRPCServerInit:
    """Tests for GRPCServer initialization."""

    def test_init_with_port(self) -> None:
        """Test GRPCServer initialization with port."""
        server = GRPCServer(port=8810)

        assert server._port == 8810
        assert server._host == "0.0.0.0"
        assert server._interceptors == []
        assert server._server is None
        assert server._servicer_registrations == []

    def test_init_with_custom_host(self) -> None:
        """Test GRPCServer initialization with custom host."""
        server = GRPCServer(port=8810, host="127.0.0.1")

        assert server._host == "127.0.0.1"

    def test_init_with_interceptors(self) -> None:
        """Test GRPCServer initialization with interceptors."""
        interceptor1 = MagicMock()
        interceptor2 = MagicMock()

        server = GRPCServer(port=8810, interceptors=[interceptor1, interceptor2])

        assert server._interceptors == [interceptor1, interceptor2]

    def test_init_with_custom_options(self) -> None:
        """Test GRPCServer initialization with custom options."""
        options = [("grpc.max_send_message_length", 100)]
        server = GRPCServer(port=8810, options=options)

        assert server._options == options

    def test_init_default_options(self) -> None:
        """Test GRPCServer has sensible default options."""
        server = GRPCServer(port=8810)

        option_names = [opt[0] for opt in server._options]
        assert "grpc.max_receive_message_length" in option_names
        assert "grpc.keepalive_time_ms" in option_names


class TestGRPCServerProperties:
    """Tests for GRPCServer properties."""

    def test_port_property(self) -> None:
        """Test port property returns the port."""
        server = GRPCServer(port=8820)

        assert server.port == 8820

    def test_is_running_false_initially(self) -> None:
        """Test is_running is False initially."""
        server = GRPCServer(port=8810)

        assert server.is_running is False

    def test_is_running_true_when_server_exists(self) -> None:
        """Test is_running is True when server exists."""
        server = GRPCServer(port=8810)
        server._server = MagicMock()

        assert server.is_running is True


class TestGRPCServerAddServicer:
    """Tests for GRPCServer.add_servicer method."""

    def test_add_servicer_stores_registration(self) -> None:
        """Test add_servicer stores the registration function."""
        server = GRPCServer(port=8810)

        def register_fn(s):
            pass

        server.add_servicer(register_fn)

        assert len(server._servicer_registrations) == 1
        assert server._servicer_registrations[0] is register_fn

    def test_add_multiple_servicers(self) -> None:
        """Test adding multiple servicers."""
        server = GRPCServer(port=8810)

        def register_fn1(s):
            pass

        def register_fn2(s):
            pass

        server.add_servicer(register_fn1)
        server.add_servicer(register_fn2)

        assert len(server._servicer_registrations) == 2


class TestGRPCServerStart:
    """Tests for GRPCServer.start method."""

    @pytest.mark.asyncio
    async def test_start_creates_server(self) -> None:
        """Test start creates and starts the server."""
        server = GRPCServer(port=8810)

        with patch("grpc.aio.server") as mock_server_factory:
            mock_grpc_server = MagicMock()
            mock_grpc_server.add_insecure_port = MagicMock()
            mock_grpc_server.start = AsyncMock()
            mock_server_factory.return_value = mock_grpc_server

            await server.start()

            mock_server_factory.assert_called_once()
            mock_grpc_server.add_insecure_port.assert_called_once_with("0.0.0.0:8810")
            mock_grpc_server.start.assert_called_once()
            assert server._server is mock_grpc_server

    @pytest.mark.asyncio
    async def test_start_registers_servicers(self) -> None:
        """Test start calls all servicer registration functions."""
        server = GRPCServer(port=8810)

        mock_register1 = MagicMock()
        mock_register2 = MagicMock()
        server.add_servicer(mock_register1)
        server.add_servicer(mock_register2)

        with patch("grpc.aio.server") as mock_server_factory:
            mock_grpc_server = MagicMock()
            mock_grpc_server.add_insecure_port = MagicMock()
            mock_grpc_server.start = AsyncMock()
            mock_server_factory.return_value = mock_grpc_server

            await server.start()

            mock_register1.assert_called_once_with(mock_grpc_server)
            mock_register2.assert_called_once_with(mock_grpc_server)

    @pytest.mark.asyncio
    async def test_start_does_nothing_if_already_running(self) -> None:
        """Test start does nothing if server is already running."""
        server = GRPCServer(port=8810)
        server._server = MagicMock()  # Pretend already running

        with patch("grpc.aio.server") as mock_server_factory:
            await server.start()

            mock_server_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_uses_custom_host(self) -> None:
        """Test start uses custom host in listen address."""
        server = GRPCServer(port=8810, host="127.0.0.1")

        with patch("grpc.aio.server") as mock_server_factory:
            mock_grpc_server = MagicMock()
            mock_grpc_server.add_insecure_port = MagicMock()
            mock_grpc_server.start = AsyncMock()
            mock_server_factory.return_value = mock_grpc_server

            await server.start()

            mock_grpc_server.add_insecure_port.assert_called_once_with("127.0.0.1:8810")


class TestGRPCServerStartSecure:
    """Tests for GRPCServer.start_secure method."""

    @pytest.mark.asyncio
    async def test_start_secure_creates_server(self) -> None:
        """Test start_secure creates server with TLS."""
        server = GRPCServer(port=8810)
        mock_credentials = MagicMock()

        with patch("grpc.aio.server") as mock_server_factory:
            mock_grpc_server = MagicMock()
            mock_grpc_server.add_secure_port = MagicMock()
            mock_grpc_server.start = AsyncMock()
            mock_server_factory.return_value = mock_grpc_server

            await server.start_secure(mock_credentials)

            mock_grpc_server.add_secure_port.assert_called_once_with(
                "0.0.0.0:8810", mock_credentials
            )
            mock_grpc_server.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_secure_does_nothing_if_already_running(self) -> None:
        """Test start_secure does nothing if already running."""
        server = GRPCServer(port=8810)
        server._server = MagicMock()
        mock_credentials = MagicMock()

        with patch("grpc.aio.server") as mock_server_factory:
            await server.start_secure(mock_credentials)

            mock_server_factory.assert_not_called()


class TestGRPCServerStop:
    """Tests for GRPCServer.stop method."""

    @pytest.mark.asyncio
    async def test_stop_stops_server(self) -> None:
        """Test stop stops the server gracefully."""
        server = GRPCServer(port=8810)

        mock_grpc_server = MagicMock()
        mock_grpc_server.stop = AsyncMock()
        server._server = mock_grpc_server

        await server.stop(grace=5.0)

        mock_grpc_server.stop.assert_called_once_with(5.0)
        assert server._server is None

    @pytest.mark.asyncio
    async def test_stop_default_grace_period(self) -> None:
        """Test stop uses default grace period."""
        server = GRPCServer(port=8810)

        mock_grpc_server = MagicMock()
        mock_grpc_server.stop = AsyncMock()
        server._server = mock_grpc_server

        await server.stop()

        mock_grpc_server.stop.assert_called_once_with(5.0)

    @pytest.mark.asyncio
    async def test_stop_does_nothing_if_not_running(self) -> None:
        """Test stop does nothing if server is not running."""
        server = GRPCServer(port=8810)
        server._server = None

        # Should not raise
        await server.stop()


class TestGRPCServerWaitForTermination:
    """Tests for GRPCServer.wait_for_termination method."""

    @pytest.mark.asyncio
    async def test_wait_for_termination_no_timeout(self) -> None:
        """Test wait_for_termination with no timeout."""
        server = GRPCServer(port=8810)

        mock_grpc_server = MagicMock()
        mock_grpc_server.wait_for_termination = AsyncMock()
        server._server = mock_grpc_server

        await server.wait_for_termination()

        mock_grpc_server.wait_for_termination.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_termination_with_timeout(self) -> None:
        """Test wait_for_termination with timeout."""

        server = GRPCServer(port=8810)

        mock_grpc_server = MagicMock()
        mock_grpc_server.wait_for_termination = AsyncMock()
        server._server = mock_grpc_server

        await server.wait_for_termination(timeout=10.0)

        # Wait was called (may have been wrapped in wait_for)
        mock_grpc_server.wait_for_termination.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_for_termination_does_nothing_if_not_running(self) -> None:
        """Test wait_for_termination does nothing if not running."""
        server = GRPCServer(port=8810)
        server._server = None

        # Should not raise
        await server.wait_for_termination()

    @pytest.mark.asyncio
    async def test_wait_for_termination_timeout_expired(self) -> None:
        """Test wait_for_termination handles timeout."""
        import asyncio

        server = GRPCServer(port=8810)

        mock_grpc_server = MagicMock()

        # Simulate wait that never completes
        async def never_terminate():
            await asyncio.sleep(100)

        mock_grpc_server.wait_for_termination = never_terminate
        server._server = mock_grpc_server

        # Should timeout and not raise
        await server.wait_for_termination(timeout=0.01)
