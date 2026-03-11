"""Test configuration and fixtures for Agent service tests."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from llamatrade_proto.generated import agent_pb2, common_pb2
from tests.fixtures.mock_embedding import MockEmbeddingService

from src.main import app

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
# Mock Service Fixtures
# =============================================================================


class MockConversationService:
    """Mock conversation service for testing."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}
        self.messages: dict[str, list[dict[str, Any]]] = {}
        self.artifacts: dict[str, list[dict[str, Any]]] = {}

    async def create_session(
        self,
        tenant_id: UUID,
        user_id: UUID,
        title: str | None = None,
    ) -> Any:
        """Create a mock session."""
        session_id = uuid4()
        data = make_session_data(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
        )
        self.sessions[str(session_id)] = data
        self.messages[str(session_id)] = []
        self.artifacts[str(session_id)] = []

        # Return a mock object with the data as attributes
        class MockSession:
            pass

        session = MockSession()
        for key, value in data.items():
            setattr(session, key, value)
        return session

    async def get_session(
        self,
        tenant_id: UUID,
        session_id: UUID,
    ) -> Any | None:
        """Get a mock session."""
        data = self.sessions.get(str(session_id))
        if not data or data.get("tenant_id") != str(tenant_id):
            return None

        class MockSession:
            pass

        session = MockSession()
        for key, value in data.items():
            setattr(session, key, value)
        return session

    async def add_message(
        self,
        session_id: UUID,
        tenant_id: UUID,
        role: int,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Add a mock message."""
        message_id = uuid4()
        data = make_message_data(
            message_id=message_id,
            session_id=session_id,
            tenant_id=tenant_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
        )

        if str(session_id) in self.messages:
            self.messages[str(session_id)].append(data)

        class MockMessage:
            pass

        message = MockMessage()
        for key, value in data.items():
            setattr(message, key, value)
        return message


@pytest.fixture
def mock_conversation_service() -> MockConversationService:
    """Create a mock conversation service."""
    return MockConversationService()


# =============================================================================
# DSL Fixtures
# =============================================================================


@pytest.fixture
def sample_dsl_60_40() -> str:
    """Return sample 60/40 portfolio DSL."""
    return """(strategy "Classic 60/40"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (group "Equities" :weight 60
      (weight :method equal
        (asset VTI)
        (asset VEA)))
    (group "Bonds" :weight 40
      (weight :method equal
        (asset BND)
        (asset BNDX)))))"""


@pytest.fixture
def sample_dsl_momentum() -> str:
    """Return sample momentum strategy DSL."""
    return """(strategy "Momentum Rotation"
  :rebalance monthly
  :benchmark SPY
  (filter :by momentum :select (top 3) :lookback 90
    (weight :method equal
      (asset XLK)
      (asset XLF)
      (asset XLV)
      (asset XLE)
      (asset XLI))))"""


@pytest.fixture
def sample_dsl_tactical() -> str:
    """Return sample tactical strategy DSL."""
    return """(strategy "Tactical 60/40"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (weight :method specified
      (asset VTI :weight 60)
      (asset BND :weight 40))
    (else
      (weight :method specified
        (asset VTI :weight 20)
        (asset BND :weight 80)))))"""


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
def mock_memory_db(mock_db_session: AsyncMock) -> AsyncMock:
    """Create a database session mock with memory-specific query helpers.

    This fixture extends mock_db_session with common memory query patterns.
    """
    return mock_db_session


@pytest.fixture
def memory_service(
    mock_memory_db: AsyncMock,
    tenant_id: UUID,
    user_id: UUID,
) -> Any:
    """Create a MemoryService with mocked database."""
    from src.services.memory_service import MemoryService

    return MemoryService(mock_memory_db, tenant_id, user_id)


@pytest.fixture
def extraction_service() -> Any:
    """Create an ExtractionService for testing.

    Note: ExtractionService is a collection of functions, not a class.
    This fixture is mainly for documentation/organization.
    """
    from src.services import extraction_service

    return extraction_service


@pytest.fixture
def mock_embedding_service() -> MockEmbeddingService:
    """Create a mock embedding service."""
    return MockEmbeddingService()


@pytest.fixture
def session_summary_service(
    mock_memory_db: AsyncMock,
    tenant_id: UUID,
    user_id: UUID,
) -> Any:
    """Create a SessionSummaryService with mocked database."""
    from src.services.session_summary_service import SessionSummaryService

    return SessionSummaryService(mock_memory_db, tenant_id, user_id)


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


# =============================================================================
# Memory Test Data Fixtures
# =============================================================================


@pytest.fixture
def sample_user_messages() -> list[str]:
    """Sample user messages containing extractable facts."""
    return [
        "My risk tolerance is moderate, I can handle up to 15% drawdown.",
        "I'm a long-term investor saving for retirement in 20 years.",
        "I like tech stocks but want to avoid energy sector.",
        "I prefer to rebalance quarterly.",
        "I'll go with the 60/40 allocation you suggested.",
    ]


@pytest.fixture
def sample_conversation_history() -> list[dict[str, str]]:
    """Sample conversation history for LLM extraction tests."""
    return [
        {"role": "user", "content": "Hi, I want to create an investment strategy."},
        {"role": "assistant", "content": "I'd be happy to help! What are your investment goals?"},
        {
            "role": "user",
            "content": "I'm saving for retirement, about 20 years away. I'm moderately aggressive with risk.",
        },
        {
            "role": "assistant",
            "content": "Great! For a 20-year horizon with moderate-aggressive risk, I'd suggest a growth-oriented approach. Any sectors you prefer?",
        },
        {
            "role": "user",
            "content": "I like tech and healthcare. I want to avoid oil and gas companies.",
        },
    ]
