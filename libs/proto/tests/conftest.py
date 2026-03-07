"""Shared fixtures for proto library tests."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_channel():
    """Create a mock gRPC channel."""
    channel = MagicMock()
    channel.close = AsyncMock()
    channel.channel_ready = AsyncMock()
    return channel


@pytest.fixture
def mock_grpc_aio(monkeypatch):
    """Mock grpc.aio module."""
    mock_aio = MagicMock()
    mock_aio.insecure_channel = MagicMock()
    mock_aio.secure_channel = MagicMock()
    return mock_aio


@pytest.fixture
def tenant_context():
    """Create a sample tenant context."""
    from llamatrade_proto.clients.auth import TenantContext

    return TenantContext(
        tenant_id="tenant-123",
        user_id="user-456",
        roles=["admin", "trader"],
    )


@pytest.fixture
def sample_datetime():
    """Return a fixed datetime for testing."""
    return datetime(2024, 1, 15, 10, 30, 0)


@pytest.fixture
def sample_decimal():
    """Return a sample decimal value."""
    return Decimal("100.50")
