"""Tests for the client-side gRPC logging interceptor."""

import logging
from unittest.mock import AsyncMock

import grpc
import grpc.aio
import pytest

from llamatrade_proto.interceptors.logging import ClientLoggingInterceptor

LOGGER_NAME = "llamatrade_proto.interceptors.logging"
METHOD = "/llamatrade.AuthService/Login"


def _call_details(method: str = METHOD) -> grpc.aio.ClientCallDetails:
    return grpc.aio.ClientCallDetails(
        method=method, timeout=None, metadata=None, credentials=None, wait_for_ready=None
    )


class TestClientLoggingInterceptor:
    """Behavioral tests driven through intercept_unary_unary with caplog."""

    async def test_success_logs_call_and_response_at_configured_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        interceptor = ClientLoggingInterceptor(log_level=logging.INFO)
        continuation = AsyncMock(return_value="response")

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            result = await interceptor.intercept_unary_unary(
                continuation, _call_details(), object()
            )

        assert result == "response"
        messages = [record.getMessage() for record in caplog.records]
        assert f"gRPC client call: {METHOD}" in messages
        assert any(
            message.startswith(f"gRPC client response: {METHOD} status=OK") for message in messages
        )
        assert all(record.levelno == logging.INFO for record in caplog.records)

    async def test_default_level_is_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        interceptor = ClientLoggingInterceptor()
        continuation = AsyncMock(return_value="response")

        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            await interceptor.intercept_unary_unary(continuation, _call_details(), object())

        assert caplog.records
        assert all(record.levelno == logging.DEBUG for record in caplog.records)

    async def test_rpc_error_logs_warning_and_reraises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        interceptor = ClientLoggingInterceptor()
        error = grpc.aio.AioRpcError(
            code=grpc.StatusCode.UNAVAILABLE,
            initial_metadata=grpc.aio.Metadata(),
            trailing_metadata=grpc.aio.Metadata(),
            details="connection refused",
            debug_error_string="debug",
        )
        continuation = AsyncMock(side_effect=error)

        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            with pytest.raises(grpc.aio.AioRpcError) as excinfo:
                await interceptor.intercept_unary_unary(continuation, _call_details(), object())

        assert excinfo.value is error
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        message = warnings[0].getMessage()
        assert METHOD in message
        assert "status=UNAVAILABLE" in message
        assert "details=connection refused" in message
