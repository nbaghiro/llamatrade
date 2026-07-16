"""Tests for the agent's Strategy service HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from llamatrade_common.auth import verify_credential

from src.tools.strategy_client import StrategyClient


def _mock_response(status_code: int, json_body: dict[str, object] | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = ""
    return resp


@pytest.mark.asyncio
async def test_create_strategy_attaches_verifiable_service_token() -> None:
    """create_strategy authenticates the fail-closed Strategy service with a
    service bearer token; tenant/user identity travels in the body context."""
    client = StrategyClient()
    mock_http = MagicMock()
    strategy_id = str(uuid4())
    mock_http.post = AsyncMock(return_value=_mock_response(200, {"strategy": {"id": strategy_id}}))
    client._client = mock_http

    result = await client.create_strategy(
        tenant_id=uuid4(),
        user_id=uuid4(),
        name="My Strategy",
        dsl_code='(strategy "S" :rebalance daily)',
    )

    assert result == {"id": strategy_id}

    _, kwargs = mock_http.post.call_args
    auth = kwargs["headers"]["Authorization"]
    assert auth.startswith("Bearer ")

    # The minted token must actually verify as a service credential — that's what
    # gets it past the Strategy service's fail-closed AuthMiddleware.
    ctx = verify_credential(auth.split(" ", 1)[1])
    assert ctx is not None
    assert ctx.is_service

    assert "context" in kwargs["json"]
    assert kwargs["json"]["name"] == "My Strategy"


@pytest.mark.asyncio
async def test_create_strategy_returns_none_on_error() -> None:
    """A non-200 response yields None so Save surfaces the failure."""
    client = StrategyClient()
    mock_http = MagicMock()
    mock_http.post = AsyncMock(return_value=_mock_response(401))
    client._client = mock_http

    result = await client.create_strategy(
        tenant_id=uuid4(),
        user_id=uuid4(),
        name="S",
        dsl_code="(strategy)",
    )

    assert result is None
