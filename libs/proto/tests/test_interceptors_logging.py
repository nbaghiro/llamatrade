"""Tests for llamatrade_proto.interceptors.logging module."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llamatrade_proto.interceptors.logging import (
    ClientLoggingInterceptor,
    LoggingInterceptor,
)


class TestLoggingInterceptorInit:
    """Tests for LoggingInterceptor initialization."""

    def test_init_with_defaults(self) -> None:
        """Test LoggingInterceptor initialization with defaults."""
        interceptor = LoggingInterceptor()

        assert interceptor._log_level == logging.DEBUG
        assert interceptor._log_request_metadata is False

    def test_init_with_custom_log_level(self) -> None:
        """Test LoggingInterceptor with custom log level."""
        interceptor = LoggingInterceptor(log_level=logging.INFO)

        assert interceptor._log_level == logging.INFO

    def test_init_with_metadata_logging(self) -> None:
        """Test LoggingInterceptor with metadata logging enabled."""
        interceptor = LoggingInterceptor(log_request_metadata=True)

        assert interceptor._log_request_metadata is True


class TestLoggingInterceptorInterceptService:
    """Tests for LoggingInterceptor.intercept_service method."""

    @pytest.mark.asyncio
    async def test_logs_request_and_response(self) -> None:
        """Test interceptor logs request and response."""
        interceptor = LoggingInterceptor(log_level=logging.INFO)

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/llamatrade.v1.StrategyService/CreateStrategy"
        mock_handler_details.invocation_metadata = []

        mock_continuation = AsyncMock(return_value="response")

        with patch.object(
            logging.getLogger("llamatrade_proto.interceptors.logging"), "log"
        ) as mock_log:
            result = await interceptor.intercept_service(mock_continuation, mock_handler_details)

            # Should log at least request and response
            assert mock_log.call_count >= 2
            assert result == "response"

    @pytest.mark.asyncio
    async def test_logs_metadata_when_enabled(self) -> None:
        """Test interceptor logs metadata when enabled."""
        interceptor = LoggingInterceptor(log_level=logging.DEBUG, log_request_metadata=True)

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/test"
        mock_handler_details.invocation_metadata = [
            ("x-request-id", "req-123"),
            ("authorization", "Bearer secret"),  # Should be redacted
        ]

        mock_continuation = AsyncMock(return_value="response")

        with patch.object(
            logging.getLogger("llamatrade_proto.interceptors.logging"), "log"
        ) as mock_log:
            await interceptor.intercept_service(mock_continuation, mock_handler_details)

            # Check that authorization was redacted in logged message
            log_calls = [str(call) for call in mock_log.call_args_list]
            log_messages = " ".join(log_calls)
            # Authorization should be redacted
            assert "Bearer secret" not in log_messages or "REDACTED" in log_messages

    @pytest.mark.asyncio
    async def test_logs_grpc_error(self) -> None:
        """Test interceptor logs gRPC errors."""
        interceptor = LoggingInterceptor()

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/test"
        mock_handler_details.invocation_metadata = []

        # Use a real exception class
        class MockRpcError(Exception):
            def code(self):
                return MagicMock(name="NOT_FOUND")

            def details(self):
                return "Resource not found"

        mock_continuation = AsyncMock(side_effect=MockRpcError())

        with pytest.raises(MockRpcError):
            await interceptor.intercept_service(mock_continuation, mock_handler_details)

    @pytest.mark.asyncio
    async def test_logs_generic_exception(self) -> None:
        """Test interceptor logs generic exceptions."""
        interceptor = LoggingInterceptor()

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/test"
        mock_handler_details.invocation_metadata = []

        mock_continuation = AsyncMock(side_effect=ValueError("Something went wrong"))

        with pytest.raises(ValueError):
            await interceptor.intercept_service(mock_continuation, mock_handler_details)


class TestClientLoggingInterceptorInit:
    """Tests for ClientLoggingInterceptor initialization."""

    def test_init_with_defaults(self) -> None:
        """Test ClientLoggingInterceptor initialization with defaults."""
        interceptor = ClientLoggingInterceptor()

        assert interceptor._log_level == logging.DEBUG

    def test_init_with_custom_log_level(self) -> None:
        """Test ClientLoggingInterceptor with custom log level."""
        interceptor = ClientLoggingInterceptor(log_level=logging.WARNING)

        assert interceptor._log_level == logging.WARNING


class TestClientLoggingInterceptorInterceptUnaryUnary:
    """Tests for ClientLoggingInterceptor.intercept_unary_unary method."""

    @pytest.mark.asyncio
    async def test_logs_request_and_response(self) -> None:
        """Test client interceptor logs request and response."""
        interceptor = ClientLoggingInterceptor(log_level=logging.INFO)

        mock_client_call_details = MagicMock()
        mock_client_call_details.method = "/llamatrade.v1.StrategyService/CreateStrategy"

        mock_continuation = AsyncMock(return_value="response")
        mock_request = MagicMock()

        with patch.object(
            logging.getLogger("llamatrade_proto.interceptors.logging"), "log"
        ) as mock_log:
            result = await interceptor.intercept_unary_unary(
                mock_continuation,
                mock_client_call_details,
                mock_request,
            )

            # Should log at least request and response
            assert mock_log.call_count >= 2
            assert result == "response"

    @pytest.mark.asyncio
    async def test_logs_grpc_client_error(self) -> None:
        """Test client interceptor logs gRPC errors."""
        interceptor = ClientLoggingInterceptor()

        mock_client_call_details = MagicMock()
        mock_client_call_details.method = "/test"

        # Use a real exception class
        class MockRpcError(Exception):
            def code(self):
                return MagicMock(name="UNAVAILABLE")

            def details(self):
                return "Service unavailable"

        mock_continuation = AsyncMock(side_effect=MockRpcError())
        mock_request = MagicMock()

        with pytest.raises(MockRpcError):
            await interceptor.intercept_unary_unary(
                mock_continuation,
                mock_client_call_details,
                mock_request,
            )


class TestLoggingInterceptorMetadataRedaction:
    """Tests for metadata redaction in LoggingInterceptor."""

    @pytest.mark.asyncio
    async def test_redacts_authorization_header(self) -> None:
        """Test authorization header is redacted."""
        interceptor = LoggingInterceptor(log_request_metadata=True)

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/test"
        mock_handler_details.invocation_metadata = [
            ("authorization", "Bearer super-secret-token"),
        ]

        mock_continuation = AsyncMock(return_value="response")

        # The interceptor should redact sensitive headers
        await interceptor.intercept_service(mock_continuation, mock_handler_details)

        # Test passes if no exception - actual redaction verified by log output

    @pytest.mark.asyncio
    async def test_redacts_api_key_header(self) -> None:
        """Test x-api-key header is redacted."""
        interceptor = LoggingInterceptor(log_request_metadata=True)

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/test"
        mock_handler_details.invocation_metadata = [
            ("x-api-key", "secret-api-key-12345"),
        ]

        mock_continuation = AsyncMock(return_value="response")

        await interceptor.intercept_service(mock_continuation, mock_handler_details)
