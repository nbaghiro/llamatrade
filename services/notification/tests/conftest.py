"""Shared test fixtures for notification service."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_ALERT_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_NOTIFICATION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_CHANNEL_ID = UUID("55555555-5555-5555-5555-555555555555")


@pytest.fixture
def tenant_id() -> UUID:
    """Return test tenant ID."""
    return TEST_TENANT_ID


@pytest.fixture
def user_id() -> UUID:
    """Return test user ID."""
    return TEST_USER_ID


@pytest.fixture
async def client() -> AsyncClient:
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class MockServicerContext:
    """Mock gRPC servicer context for testing."""

    def __init__(self) -> None:
        self.code = None
        self.details = None
        self._cancelled = False

    async def abort(self, code, details: str) -> None:
        """Mock abort that raises an exception."""
        import grpc

        self.code = code
        self.details = details
        raise grpc.aio.AioRpcError(
            code=code,
            initial_metadata=None,
            trailing_metadata=None,
            details=details,
            debug_error_string=None,
        )

    def cancelled(self) -> bool:
        return self._cancelled


@pytest.fixture
def grpc_context() -> MockServicerContext:
    """Create a mock gRPC context."""
    return MockServicerContext()


@pytest.fixture
def notification_servicer():
    """Create a notification servicer instance."""
    from src.grpc.servicer import NotificationServicer

    return NotificationServicer()


@pytest.fixture
def sample_notification() -> dict:
    """Create a sample notification."""
    return {
        "id": str(TEST_NOTIFICATION_ID),
        "tenant_id": str(TEST_TENANT_ID),
        "user_id": str(TEST_USER_ID),
        "type": 1,  # INFO
        "title": "Test Notification",
        "message": "This is a test notification",
        "is_read": False,
        "metadata": {"key": "value"},
        "created_at": datetime.now(UTC).isoformat(),
        "read_at": None,
    }


@pytest.fixture
def sample_alert() -> dict:
    """Create a sample alert."""
    return {
        "id": str(TEST_ALERT_ID),
        "tenant_id": str(TEST_TENANT_ID),
        "user_id": str(TEST_USER_ID),
        "name": "Price Alert",
        "description": "Alert when AAPL goes above $200",
        "is_active": True,
        "condition": {
            "type": 1,  # PRICE_ABOVE
            "symbol": "AAPL",
            "threshold": "200.0",
            "strategy_id": "",
        },
        "channels": [1],  # EMAIL
        "cooldown_minutes": 60,
        "times_triggered": 0,
        "last_triggered_at": None,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


@pytest.fixture
def sample_channel() -> dict:
    """Create a sample channel."""
    return {
        "id": str(TEST_CHANNEL_ID),
        "tenant_id": str(TEST_TENANT_ID),
        "user_id": str(TEST_USER_ID),
        "type": 1,  # EMAIL
        "is_enabled": True,
        "is_verified": True,
        "config": {"email": "test@example.com"},
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
