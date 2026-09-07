"""Test configuration and fixtures for Agent service tests."""

import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from llamatrade_proto.generated import agent_pb2, common_pb2
from llamatrade_telemetry import get_metrics

from src.main import app


def metric_value(name: str, **labels: str) -> float:
    """Read a single metric value from the Prometheus exposition (0.0 if absent).

    Matches on label containment, not equality: the OTel Prometheus exporter
    appends ``otel_scope_*`` labels whose presence varies by exporter version.
    """
    for line in get_metrics().decode().splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        match = re.match(rf"{re.escape(name)}(?:\{{(?P<labels>[^}}]*)\}})?\s+(?P<value>\S+)$", line)
        if match is None:
            continue
        present = dict(re.findall(r'(\w+)="([^"]*)"', match.group("labels") or ""))
        if all(present.get(k) == v for k, v in labels.items()):
            return float(match.group("value"))
    return 0.0


# =============================================================================
# HTTP Client Fixtures
# =============================================================================


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# ID Fixtures
# =============================================================================


@pytest.fixture
def tenant_id() -> UUID:
    """Create a test tenant ID."""
    return uuid4()


@pytest.fixture
def user_id() -> UUID:
    """Create a test user ID."""
    return uuid4()


@pytest.fixture
def session_id() -> UUID:
    """Create a test session ID."""
    return uuid4()


# =============================================================================
# Mock Database Session Fixtures
# =============================================================================


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create a mock async database session.

    This provides a mock that can be used for unit testing services
    without requiring an actual database connection.
    """
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.delete = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.rollback = AsyncMock()
    return mock_session


@pytest.fixture
def conversation_service(mock_db_session: AsyncMock) -> Any:
    """Create a ConversationService with mocked database."""
    from src.services.conversation_service import ConversationService

    return ConversationService(mock_db_session)


@pytest.fixture
def artifact_service(
    mock_db_session: AsyncMock,
    tenant_id: UUID,
    user_id: UUID,
) -> Any:
    """Create an ArtifactService with mocked database."""
    from src.services.artifact_service import ArtifactService

    return ArtifactService(mock_db_session, tenant_id, user_id)


# =============================================================================
# gRPC Fixtures
# =============================================================================


@pytest.fixture
def valid_tenant_context(tenant_id: UUID, user_id: UUID) -> common_pb2.TenantContext:
    """Create a valid TenantContext proto."""
    return common_pb2.TenantContext(
        tenant_id=str(tenant_id),
        user_id=str(user_id),
    )


@pytest.fixture
def mock_request_context() -> MagicMock:
    """Create a mock RequestContext for servicer methods."""
    ctx = MagicMock()
    ctx.peer = MagicMock(return_value="test-peer")
    return ctx


@pytest.fixture
def mock_session_maker(mock_db_session: AsyncMock) -> Any:
    """Create a mock session maker that returns the test session."""
    mock_maker = MagicMock()

    # Make the maker callable and return an async context manager
    class MockAsyncContextManager:
        async def __aenter__(self) -> AsyncMock:
            return mock_db_session

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    mock_maker.return_value = MockAsyncContextManager()
    return mock_maker


@pytest.fixture
def servicer(mock_session_maker: Any) -> Any:
    """Create an AgentServicer with mocked database."""
    from src.grpc.servicer import AgentServicer

    svc = AgentServicer()
    svc._session_maker = mock_session_maker
    return svc


# =============================================================================
# Mock Data Factories
# =============================================================================


def make_tenant_context(
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
) -> dict[str, str]:
    """Create a mock tenant context."""
    return {
        "tenant_id": str(tenant_id or uuid4()),
        "user_id": str(user_id or uuid4()),
        "roles": ["user"],
    }


def make_session_data(
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    title: str | None = None,
    status: int = 1,  # ACTIVE
    message_count: int = 0,
) -> dict[str, Any]:
    """Create mock session data."""
    now = datetime.now(UTC)
    return {
        "id": str(session_id or uuid4()),
        "tenant_id": str(tenant_id or uuid4()),
        "user_id": str(user_id or uuid4()),
        "title": title,
        "status": status,
        "message_count": message_count,
        "created_at": now,
        "last_activity_at": now,
    }


def make_message_data(
    message_id: UUID | None = None,
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    role: int = 1,  # USER
    content: str = "Test message",
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create mock message data."""
    return {
        "id": str(message_id or uuid4()),
        "session_id": str(session_id or uuid4()),
        "tenant_id": str(tenant_id or uuid4()),
        "role": role,
        "content": content,
        "tool_calls_json": tool_calls,
        "created_at": datetime.now(UTC),
    }


def make_artifact_data(
    artifact_id: UUID | None = None,
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    artifact_type: int = 1,  # STRATEGY
    name: str = "Test Strategy",
    dsl_code: str = '(strategy "Test" :rebalance monthly (asset SPY))',
) -> dict[str, Any]:
    """Create mock artifact data."""
    return {
        "id": str(artifact_id or uuid4()),
        "session_id": str(session_id or uuid4()),
        "tenant_id": str(tenant_id or uuid4()),
        "artifact_type": artifact_type,
        "name": name,
        "description": "Test strategy description",
        "artifact_json": {
            "name": name,
            "dsl_code": dsl_code,
            "symbols": ["SPY"],
            "timeframe": "1D",
        },
        "is_committed": False,
        "committed_resource_id": None,
        "created_at": datetime.now(UTC),
    }


# =============================================================================
# Proto Mock Factories
# =============================================================================


def make_proto_session(
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    title: str = "",
    status: int = 1,  # ACTIVE
    message_count: int = 0,
) -> agent_pb2.AgentSession:
    """Create an AgentSession proto for testing."""
    now = int(datetime.now(UTC).timestamp())
    return agent_pb2.AgentSession(
        id=str(session_id or uuid4()),
        tenant_id=str(tenant_id or uuid4()),
        user_id=str(user_id or uuid4()),
        title=title,
        status=status,
        message_count=message_count,
        created_at=common_pb2.Timestamp(seconds=now),
        last_activity_at=common_pb2.Timestamp(seconds=now),
    )


def make_proto_message(
    message_id: UUID | None = None,
    session_id: UUID | None = None,
    role: int = 1,  # USER
    content: str = "Test message",
    tool_calls: list[agent_pb2.ToolCall] | None = None,
) -> agent_pb2.AgentMessage:
    """Create an AgentMessage proto for testing."""
    now = int(datetime.now(UTC).timestamp())
    return agent_pb2.AgentMessage(
        id=str(message_id or uuid4()),
        session_id=str(session_id or uuid4()),
        role=role,
        content=content,
        tool_calls=tool_calls or [],
        created_at=common_pb2.Timestamp(seconds=now),
    )


def make_proto_artifact(
    artifact_id: UUID | None = None,
    session_id: UUID | None = None,
    artifact_type: int = 1,  # STRATEGY
    name: str = "Test Strategy",
    description: str = "Test description",
    is_committed: bool = False,
) -> agent_pb2.PendingArtifact:
    """Create a PendingArtifact proto for testing."""
    now = int(datetime.now(UTC).timestamp())
    return agent_pb2.PendingArtifact(
        id=str(artifact_id or uuid4()),
        session_id=str(session_id or uuid4()),
        artifact_type=artifact_type,
        name=name,
        description=description,
        preview_json="{}",
        is_committed=is_committed,
        committed_resource_id="",
        created_at=common_pb2.Timestamp(seconds=now),
    )


def make_create_session_request(
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
) -> agent_pb2.CreateSessionRequest:
    """Create a CreateSessionRequest proto for testing."""
    return agent_pb2.CreateSessionRequest(
        context=common_pb2.TenantContext(
            tenant_id=str(tenant_id or uuid4()),
            user_id=str(user_id or uuid4()),
        ),
    )


def make_send_message_request(
    session_id: UUID,
    content: str,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    page: str | None = None,
    strategy_id: str | None = None,
) -> agent_pb2.SendMessageRequest:
    """Create a SendMessageRequest proto for testing."""
    request = agent_pb2.SendMessageRequest(
        context=common_pb2.TenantContext(
            tenant_id=str(tenant_id or uuid4()),
            user_id=str(user_id or uuid4()),
        ),
        session_id=str(session_id),
        content=content,
    )
    if page or strategy_id:
        request.ui_context.CopyFrom(
            agent_pb2.UIContext(
                page=page or "",
                strategy_id=strategy_id or "",
            )
        )
    return request


# =============================================================================
# Memory Service Fixtures
# =============================================================================


@pytest.fixture
def memory_service(
    mock_db_session: AsyncMock,
    tenant_id: UUID,
    user_id: UUID,
) -> Any:
    """Create a MemoryService with mocked database."""
    from src.services.memory_service import MemoryService

    return MemoryService(mock_db_session, tenant_id, user_id)


@pytest.fixture
def extraction_service() -> Any:
    """Create an ExtractionService for testing.

    Note: ExtractionService is a collection of functions, not a class.
    This fixture is mainly for documentation/organization.
    """
    from src.services import extraction_service

    return extraction_service


@pytest.fixture
def tool_context(
    tenant_id: UUID,
    user_id: UUID,
    session_id: UUID,
) -> Any:
    """Create a ToolContext for memory tool tests."""
    from src.tools.base import ToolContext

    return ToolContext(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
    )


@pytest.fixture(autouse=True)
def _fake_notification_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the shared notification publisher at an in-memory stream."""
    from llamatrade_events import EventBus
    from llamatrade_events.catalog import notifications as notifications_module
    from llamatrade_events.catalog.notifications import NotificationEvents
    from llamatrade_events.testing import FakeTransport

    monkeypatch.setattr(
        notifications_module,
        "_shared",
        NotificationEvents(bus=EventBus(FakeTransport())),
    )
