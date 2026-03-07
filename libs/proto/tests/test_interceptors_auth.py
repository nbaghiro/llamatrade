"""Tests for llamatrade_proto.interceptors.auth module."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from llamatrade_proto.interceptors.auth import (
    AuthInterceptor,
    ClientAuthInterceptor,
)


class TestAuthInterceptorInit:
    """Tests for AuthInterceptor initialization."""

    def test_init_with_auth_client(self) -> None:
        """Test AuthInterceptor initialization with auth client."""
        mock_auth_client = MagicMock()
        interceptor = AuthInterceptor(mock_auth_client)

        assert interceptor._auth_client is mock_auth_client
        assert interceptor._skip_methods == set()

    def test_init_with_skip_methods(self) -> None:
        """Test AuthInterceptor initialization with skip methods."""
        mock_auth_client = MagicMock()
        skip_methods = ["/llamatrade.v1.AuthService/Login", "/llamatrade.v1.AuthService/Register"]

        interceptor = AuthInterceptor(mock_auth_client, skip_methods=skip_methods)

        assert interceptor._skip_methods == set(skip_methods)

    def test_init_with_empty_skip_methods(self) -> None:
        """Test AuthInterceptor initialization with empty skip methods."""
        mock_auth_client = MagicMock()
        interceptor = AuthInterceptor(mock_auth_client, skip_methods=[])

        assert interceptor._skip_methods == set()


class TestAuthInterceptorInterceptService:
    """Tests for AuthInterceptor.intercept_service method."""

    @pytest.mark.asyncio
    async def test_skip_method_passes_through(self) -> None:
        """Test skipped methods pass through without auth."""
        mock_auth_client = MagicMock()
        interceptor = AuthInterceptor(
            mock_auth_client,
            skip_methods=["/llamatrade.v1.AuthService/Login"],
        )

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/llamatrade.v1.AuthService/Login"
        mock_handler_details.invocation_metadata = []

        mock_continuation = AsyncMock(return_value="response")

        result = await interceptor.intercept_service(mock_continuation, mock_handler_details)

        mock_continuation.assert_called_once_with(mock_handler_details)
        assert result == "response"
        # Auth client should not be called
        mock_auth_client.validate_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_auth_header_returns_unauthenticated(self) -> None:
        """Test missing authorization header returns unauthenticated handler."""
        mock_auth_client = MagicMock()
        interceptor = AuthInterceptor(mock_auth_client)

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/llamatrade.v1.StrategyService/CreateStrategy"
        mock_handler_details.invocation_metadata = []

        mock_continuation = AsyncMock()

        result = await interceptor.intercept_service(mock_continuation, mock_handler_details)

        # Should return unauthenticated handler
        mock_continuation.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalid_token_returns_unauthenticated(self) -> None:
        """Test invalid token returns unauthenticated handler."""
        from llamatrade_proto.clients.auth import TokenValidationResult

        mock_auth_client = MagicMock()
        mock_auth_client.validate_token = AsyncMock(
            return_value=TokenValidationResult(
                valid=False,
                context=None,
                expires_at=None,
                token_type=None,
            )
        )

        interceptor = AuthInterceptor(mock_auth_client)

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/llamatrade.v1.StrategyService/CreateStrategy"
        mock_handler_details.invocation_metadata = [("authorization", "Bearer invalid-token")]

        mock_continuation = AsyncMock()

        _result = await interceptor.intercept_service(mock_continuation, mock_handler_details)  # noqa: F841

        mock_auth_client.validate_token.assert_called_once_with("invalid-token")
        mock_continuation.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_token_continues(self) -> None:
        """Test valid token allows request to continue."""
        from llamatrade_proto.clients.auth import TenantContext, TokenValidationResult

        mock_auth_client = MagicMock()
        mock_auth_client.validate_token = AsyncMock(
            return_value=TokenValidationResult(
                valid=True,
                context=TenantContext("tenant-123", "user-456", ["admin"]),
                expires_at=None,
                token_type="access",
            )
        )

        interceptor = AuthInterceptor(mock_auth_client)

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/llamatrade.v1.StrategyService/CreateStrategy"
        mock_handler_details.invocation_metadata = [("authorization", "Bearer valid-token")]

        mock_continuation = AsyncMock(return_value="response")

        result = await interceptor.intercept_service(mock_continuation, mock_handler_details)

        mock_auth_client.validate_token.assert_called_once_with("valid-token")
        mock_continuation.assert_called_once_with(mock_handler_details)
        assert result == "response"

    @pytest.mark.asyncio
    async def test_token_without_bearer_prefix(self) -> None:
        """Test token without Bearer prefix is still used."""
        from llamatrade_proto.clients.auth import TenantContext, TokenValidationResult

        mock_auth_client = MagicMock()
        mock_auth_client.validate_token = AsyncMock(
            return_value=TokenValidationResult(
                valid=True,
                context=TenantContext("tenant-123", "user-456", []),
                expires_at=None,
                token_type="access",
            )
        )

        interceptor = AuthInterceptor(mock_auth_client)

        mock_handler_details = MagicMock()
        mock_handler_details.method = "/test"
        mock_handler_details.invocation_metadata = [("authorization", "raw-token")]

        mock_continuation = AsyncMock(return_value="response")

        await interceptor.intercept_service(mock_continuation, mock_handler_details)

        mock_auth_client.validate_token.assert_called_once_with("raw-token")


class TestAuthInterceptorUnauthenticatedHandler:
    """Tests for AuthInterceptor._unauthenticated_handler method."""

    def test_unauthenticated_handler_returns_handler(self) -> None:
        """Test _unauthenticated_handler returns a valid handler."""
        mock_auth_client = MagicMock()
        interceptor = AuthInterceptor(mock_auth_client)

        handler = interceptor._unauthenticated_handler()

        # Handler should be an RpcMethodHandler
        assert handler is not None


class TestClientAuthInterceptorInit:
    """Tests for ClientAuthInterceptor initialization."""

    def test_init_with_token_string(self) -> None:
        """Test ClientAuthInterceptor with static token string."""
        interceptor = ClientAuthInterceptor("my-token")

        assert interceptor._token == "my-token"

    def test_init_with_token_callable(self) -> None:
        """Test ClientAuthInterceptor with token callable."""

        def token_fn() -> str:
            return "dynamic-token"

        interceptor = ClientAuthInterceptor(token_fn)

        assert callable(interceptor._token)


class TestClientAuthInterceptorInterceptUnaryUnary:
    """Tests for ClientAuthInterceptor.intercept_unary_unary method."""

    @pytest.mark.asyncio
    async def test_adds_authorization_header_static(self) -> None:
        """Test interceptor adds authorization header with static token."""
        interceptor = ClientAuthInterceptor("my-static-token")

        mock_client_call_details = MagicMock()
        mock_client_call_details.method = "/test"
        mock_client_call_details.timeout = None
        mock_client_call_details.metadata = []
        mock_client_call_details.credentials = None
        mock_client_call_details.wait_for_ready = None

        mock_continuation = AsyncMock(return_value="response")
        mock_request = MagicMock()

        result = await interceptor.intercept_unary_unary(
            mock_continuation,
            mock_client_call_details,
            mock_request,
        )

        # Check that continuation was called with updated metadata
        call_args = mock_continuation.call_args
        new_details = call_args[0][0]
        metadata = list(new_details.metadata)

        assert ("authorization", "Bearer my-static-token") in metadata
        assert result == "response"

    @pytest.mark.asyncio
    async def test_adds_authorization_header_dynamic(self) -> None:
        """Test interceptor adds authorization header with dynamic token."""

        def token_fn() -> str:
            return "dynamic-token-123"

        interceptor = ClientAuthInterceptor(token_fn)

        mock_client_call_details = MagicMock()
        mock_client_call_details.method = "/test"
        mock_client_call_details.timeout = None
        mock_client_call_details.metadata = None  # None metadata
        mock_client_call_details.credentials = None
        mock_client_call_details.wait_for_ready = None

        mock_continuation = AsyncMock(return_value="response")
        mock_request = MagicMock()

        _result = await interceptor.intercept_unary_unary(  # noqa: F841
            mock_continuation,
            mock_client_call_details,
            mock_request,
        )

        call_args = mock_continuation.call_args
        new_details = call_args[0][0]
        metadata = list(new_details.metadata)

        assert ("authorization", "Bearer dynamic-token-123") in metadata

    @pytest.mark.asyncio
    async def test_preserves_existing_metadata(self) -> None:
        """Test interceptor preserves existing metadata."""
        interceptor = ClientAuthInterceptor("token")

        mock_client_call_details = MagicMock()
        mock_client_call_details.method = "/test"
        mock_client_call_details.timeout = None
        mock_client_call_details.metadata = [("x-custom-header", "custom-value")]
        mock_client_call_details.credentials = None
        mock_client_call_details.wait_for_ready = None

        mock_continuation = AsyncMock(return_value="response")
        mock_request = MagicMock()

        await interceptor.intercept_unary_unary(
            mock_continuation,
            mock_client_call_details,
            mock_request,
        )

        call_args = mock_continuation.call_args
        new_details = call_args[0][0]
        metadata = list(new_details.metadata)

        assert ("x-custom-header", "custom-value") in metadata
        assert ("authorization", "Bearer token") in metadata
