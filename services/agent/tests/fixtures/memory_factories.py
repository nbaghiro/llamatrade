"""Factory functions for creating test data for memory system tests.

These factories create mock objects and data structures that match the
production models, enabling isolated unit testing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from src.services.memory_service import ExtractedFact, MemorySearchResult, UserProfile

# =============================================================================
# Memory Fact Factories
# =============================================================================


def make_memory_fact(
    fact_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    category: str = "user_preference",
    content: str = "test content",
    confidence: float = 0.7,
    is_active: bool = True,
    source_session_id: UUID | None = None,
    source_message_id: UUID | None = None,
    extraction_method: str = "heuristic",
    supersedes_id: UUID | None = None,
    created_at: datetime | None = None,
    last_accessed_at: datetime | None = None,
    access_count: int = 0,
) -> MagicMock:
    """Create a mock AgentMemoryFact object.

    Args:
        fact_id: Fact UUID (auto-generated if not provided)
        tenant_id: Tenant UUID
        user_id: User UUID
        category: Fact category (from MemoryFactCategory)
        content: Fact content text
        confidence: Confidence score (0.0-1.0)
        is_active: Whether fact is active
        source_session_id: Source session UUID
        source_message_id: Source message UUID
        extraction_method: "heuristic" or "llm"
        supersedes_id: ID of fact this supersedes
        created_at: Creation timestamp
        last_accessed_at: Last access timestamp
        access_count: Number of times accessed

    Returns:
        MagicMock configured as AgentMemoryFact
    """
    mock = MagicMock()
    mock.id = fact_id or uuid4()
    mock.tenant_id = tenant_id or uuid4()
    mock.user_id = user_id or uuid4()
    mock.category = category
    mock.content = content
    mock.confidence = confidence
    mock.is_active = is_active
    mock.source_session_id = source_session_id
    mock.source_message_id = source_message_id
    mock.extraction_method = extraction_method
    mock.supersedes_id = supersedes_id
    mock.created_at = created_at or datetime.now(UTC)
    mock.last_accessed_at = last_accessed_at
    mock.access_count = access_count
    return mock


def make_extracted_fact(
    category: str = "user_preference",
    content: str = "test content",
    confidence: float = 0.7,
    extraction_method: str = "heuristic",
) -> ExtractedFact:
    """Create an ExtractedFact dataclass.

    Args:
        category: Fact category
        content: Fact content
        confidence: Confidence score
        extraction_method: "heuristic" or "llm"

    Returns:
        ExtractedFact instance
    """
    return ExtractedFact(
        category=category,
        content=content,
        confidence=confidence,
        extraction_method=extraction_method,
    )


def make_memory_search_result(
    fact_id: UUID | None = None,
    category: str = "user_preference",
    content: str = "test content",
    confidence: float = 0.7,
    created_at: datetime | None = None,
    source_session_id: UUID | None = None,
    relevance_score: float = 1.0,
) -> MemorySearchResult:
    """Create a MemorySearchResult dataclass.

    Args:
        fact_id: Fact UUID
        category: Fact category
        content: Fact content
        confidence: Confidence score
        created_at: Creation timestamp
        source_session_id: Source session UUID
        relevance_score: Relevance/similarity score

    Returns:
        MemorySearchResult instance
    """
    return MemorySearchResult(
        fact_id=fact_id or uuid4(),
        category=category,
        content=content,
        confidence=confidence,
        created_at=created_at or datetime.now(UTC),
        source_session_id=source_session_id,
        relevance_score=relevance_score,
    )


# =============================================================================
# Embedding Factories
# =============================================================================


def make_memory_embedding(
    embedding_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    embedding_type: str = "fact",
    embedding: list[float] | None = None,
    content_text: str = "test content",
    source_id: UUID | None = None,
    embedding_model: str = "text-embedding-3-small",
    created_at: datetime | None = None,
) -> MagicMock:
    """Create a mock AgentMemoryEmbedding object.

    Args:
        embedding_id: Embedding UUID
        tenant_id: Tenant UUID
        user_id: User UUID
        embedding_type: "fact", "summary", or "strategy"
        embedding: Vector embedding (defaults to 1536-dim zeros)
        content_text: Original text
        source_id: Source object UUID
        embedding_model: Model used for embedding
        created_at: Creation timestamp

    Returns:
        MagicMock configured as AgentMemoryEmbedding
    """
    mock = MagicMock()
    mock.id = embedding_id or uuid4()
    mock.tenant_id = tenant_id or uuid4()
    mock.user_id = user_id or uuid4()
    mock.embedding_type = embedding_type
    mock.embedding = embedding or [0.0] * 1536
    mock.content_text = content_text
    mock.source_id = source_id or uuid4()
    mock.embedding_model = embedding_model
    mock.created_at = created_at or datetime.now(UTC)
    return mock


def make_embedding_vector(dimension: int = 1536, value: float = 0.1) -> list[float]:
    """Create a test embedding vector.

    Args:
        dimension: Vector dimension
        value: Value for all elements

    Returns:
        List of floats
    """
    return [value] * dimension


# =============================================================================
# Session Summary Factories
# =============================================================================


def make_session_summary(
    summary_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    session_id: UUID | None = None,
    summary_short: str = "Short summary",
    summary_detailed: str = "Detailed summary of the conversation",
    topics: list[str] | None = None,
    strategies_discussed: list[str] | None = None,
    decisions: list[str] | None = None,
    message_count_at_summary: int = 10,
    created_at: datetime | None = None,
) -> MagicMock:
    """Create a mock AgentSessionSummary object.

    Args:
        summary_id: Summary UUID
        tenant_id: Tenant UUID
        user_id: User UUID
        session_id: Session UUID
        summary_short: Short summary text
        summary_detailed: Detailed summary text
        topics: List of topics
        strategies_discussed: List of strategy names
        decisions: List of decisions
        message_count_at_summary: Message count when summarized
        created_at: Creation timestamp

    Returns:
        MagicMock configured as AgentSessionSummary
    """
    mock = MagicMock()
    mock.id = summary_id or uuid4()
    mock.tenant_id = tenant_id or uuid4()
    mock.user_id = user_id or uuid4()
    mock.session_id = session_id or uuid4()
    mock.summary_short = summary_short
    mock.summary_detailed = summary_detailed
    mock.topics = topics if topics is not None else ["investing", "strategies"]
    mock.strategies_discussed = strategies_discussed if strategies_discussed is not None else []
    mock.decisions = decisions if decisions is not None else []
    mock.message_count_at_summary = message_count_at_summary
    mock.created_at = created_at or datetime.now(UTC)
    return mock


# =============================================================================
# User Profile Factory
# =============================================================================


def make_user_profile(
    risk_tolerance: str | None = "moderate risk tolerance",
    investment_goals: list[str] | None = None,
    asset_preferences: list[str] | None = None,
    asset_dislikes: list[str] | None = None,
    trading_behaviors: list[str] | None = None,
    recent_decisions: list[str] | None = None,
    general_preferences: list[str] | None = None,
) -> UserProfile:
    """Create a UserProfile dataclass.

    Args:
        risk_tolerance: Risk tolerance description
        investment_goals: List of goals
        asset_preferences: List of liked assets
        asset_dislikes: List of disliked assets
        trading_behaviors: List of behaviors
        recent_decisions: List of decisions
        general_preferences: List of general preferences

    Returns:
        UserProfile instance
    """
    return UserProfile(
        risk_tolerance=risk_tolerance,
        investment_goals=investment_goals or ["retirement savings"],
        asset_preferences=asset_preferences or ["tech stocks"],
        asset_dislikes=asset_dislikes or [],
        trading_behaviors=trading_behaviors or [],
        recent_decisions=recent_decisions or [],
        general_preferences=general_preferences or [],
    )


# =============================================================================
# Strategy Factories
# =============================================================================


def make_strategy(
    strategy_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    name: str = "Test Strategy",
    description: str | None = "A test strategy",
    dsl: str = '(strategy "Test" :rebalance monthly (asset SPY))',
    status: int = 1,  # DRAFT
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> MagicMock:
    """Create a mock Strategy object.

    Args:
        strategy_id: Strategy UUID
        tenant_id: Tenant UUID
        user_id: User UUID
        name: Strategy name
        description: Strategy description
        dsl: Strategy DSL code
        status: Strategy status (1=DRAFT, 2=ACTIVE, etc.)
        created_at: Creation timestamp
        updated_at: Update timestamp

    Returns:
        MagicMock configured as Strategy
    """
    now = datetime.now(UTC)
    mock = MagicMock()
    mock.id = strategy_id or uuid4()
    mock.tenant_id = tenant_id or uuid4()
    mock.user_id = user_id or uuid4()
    mock.name = name
    mock.description = description
    mock.dsl = dsl
    mock.status = status
    mock.created_at = created_at or now
    mock.updated_at = updated_at or now
    return mock


# =============================================================================
# Session & Message Factories
# =============================================================================


def make_agent_session(
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    title: str | None = None,
    status: int = 1,  # ACTIVE
    message_count: int = 0,
    created_at: datetime | None = None,
    last_activity_at: datetime | None = None,
) -> MagicMock:
    """Create a mock AgentSession object.

    Args:
        session_id: Session UUID
        tenant_id: Tenant UUID
        user_id: User UUID
        title: Session title
        status: Session status
        message_count: Number of messages
        created_at: Creation timestamp
        last_activity_at: Last activity timestamp

    Returns:
        MagicMock configured as AgentSession
    """
    now = datetime.now(UTC)
    mock = MagicMock()
    mock.id = session_id or uuid4()
    mock.tenant_id = tenant_id or uuid4()
    mock.user_id = user_id or uuid4()
    mock.title = title
    mock.status = status
    mock.message_count = message_count
    mock.created_at = created_at or now
    mock.last_activity_at = last_activity_at or now
    return mock


def make_agent_message(
    message_id: UUID | None = None,
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    role: int = 1,  # USER
    content: str = "Test message",
    tool_calls_json: list[dict[str, Any]] | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    """Create a mock AgentMessage object.

    Args:
        message_id: Message UUID
        session_id: Session UUID
        tenant_id: Tenant UUID
        role: Message role (1=USER, 2=ASSISTANT)
        content: Message content
        tool_calls_json: Tool calls JSON
        created_at: Creation timestamp

    Returns:
        MagicMock configured as AgentMessage
    """
    mock = MagicMock()
    mock.id = message_id or uuid4()
    mock.session_id = session_id or uuid4()
    mock.tenant_id = tenant_id or uuid4()
    mock.role = role
    mock.content = content
    mock.tool_calls_json = tool_calls_json
    mock.created_at = created_at or datetime.now(UTC)
    return mock


# =============================================================================
# Database Result Helpers
# =============================================================================


def mock_scalar_one_or_none(value: Any) -> MagicMock:
    """Create a mock result for scalar_one_or_none() queries.

    Args:
        value: Value to return from scalar_one_or_none()

    Returns:
        MagicMock configured as query result
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def mock_scalars_all(values: list[Any]) -> MagicMock:
    """Create a mock result for scalars().all() queries.

    Args:
        values: List of values to return

    Returns:
        MagicMock configured as query result
    """
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


def mock_scalar_one(value: Any) -> MagicMock:
    """Create a mock result for scalar_one() queries.

    Args:
        value: Value to return from scalar_one()

    Returns:
        MagicMock configured as query result
    """
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def mock_fetchall(rows: list[Any]) -> MagicMock:
    """Create a mock result for fetchall() queries.

    Args:
        rows: List of row objects to return

    Returns:
        MagicMock configured as query result
    """
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def mock_fetchone(row: Any) -> MagicMock:
    """Create a mock result for fetchone() queries.

    Args:
        row: Row object to return

    Returns:
        MagicMock configured as query result
    """
    result = MagicMock()
    result.fetchone.return_value = row
    return result
