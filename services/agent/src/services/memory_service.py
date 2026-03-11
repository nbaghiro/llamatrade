"""Memory service for cross-session user memory management.

This service handles:
- Storing and retrieving memory facts (extracted user preferences)
- Semantic search via pgvector embeddings
- User profile consolidation
- Session summary management
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import (
    AgentMemoryEmbedding,
    AgentMemoryFact,
    AgentSession,
    AgentSessionSummary,
    MemoryFactCategory,
    Strategy,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ExtractedFact:
    """A fact extracted from user messages."""

    category: str
    content: str
    confidence: float
    extraction_method: str = "heuristic"


@dataclass
class MemorySearchResult:
    """Result from memory search."""

    fact_id: UUID
    category: str
    content: str
    confidence: float
    created_at: datetime
    source_session_id: UUID | None = None
    relevance_score: float = 1.0


@dataclass
class UserProfile:
    """Consolidated user profile from memory facts."""

    risk_tolerance: str | None = None
    investment_goals: list[str] = field(default_factory=list)
    asset_preferences: list[str] = field(default_factory=list)
    asset_dislikes: list[str] = field(default_factory=list)
    trading_behaviors: list[str] = field(default_factory=list)
    recent_decisions: list[str] = field(default_factory=list)
    general_preferences: list[str] = field(default_factory=list)


@dataclass
class StrategyMemory:
    """Memory of a past strategy discussion."""

    strategy_id: UUID | None
    strategy_name: str
    dsl_snippet: str | None
    symbols: list[str]
    discussed_at: datetime
    context: str | None = None
    performance_summary: str | None = None


@dataclass
class SessionSummaryResult:
    """Summary of a past session."""

    session_id: UUID
    summary_short: str
    summary_detailed: str
    topics: list[str]
    strategies_discussed: list[str]
    decisions: list[str]
    created_at: datetime
    message_count: int


@dataclass
class MemoryHint:
    """Lightweight memory hint for system prompt injection."""

    is_new_user: bool = True
    session_count: int = 0
    risk_tolerance: str | None = None
    goal_summary: str | None = None
    recent_strategies: list[str] = field(default_factory=list)


# =============================================================================
# Memory Service
# =============================================================================


class MemoryService:
    """Service for managing user memory across sessions.

    Provides CRUD operations for memory facts, semantic search via embeddings,
    and user profile consolidation from historical data.
    """

    def __init__(self, db: AsyncSession, tenant_id: UUID, user_id: UUID) -> None:
        """Initialize the memory service.

        Args:
            db: Async database session
            tenant_id: Tenant UUID for isolation
            user_id: User UUID
        """
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    # =========================================================================
    # Fact Storage
    # =========================================================================

    async def store_facts(
        self,
        facts: list[ExtractedFact],
        session_id: UUID | None = None,
        message_id: UUID | None = None,
    ) -> list[AgentMemoryFact]:
        """Store extracted facts to the database.

        Args:
            facts: List of extracted facts
            session_id: Optional source session ID
            message_id: Optional source message ID

        Returns:
            List of created AgentMemoryFact objects
        """
        if not facts:
            return []

        created_facts: list[AgentMemoryFact] = []

        for fact in facts:
            # Check for existing similar fact to potentially supersede
            existing = await self._find_similar_fact(fact.category, fact.content)

            db_fact = AgentMemoryFact(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                category=fact.category,
                content=fact.content,
                confidence=fact.confidence,
                extraction_method=fact.extraction_method,
                source_session_id=session_id,
                source_message_id=message_id,
                is_active=True,
                supersedes_id=existing.id if existing else None,
            )

            if existing:
                # Mark old fact as inactive
                existing.is_active = False

            self.db.add(db_fact)
            created_facts.append(db_fact)

        await self.db.commit()

        for fact in created_facts:
            await self.db.refresh(fact)

        logger.info(
            "Stored %d memory facts for user %s",
            len(created_facts),
            self.user_id,
        )

        return created_facts

    async def _find_similar_fact(
        self,
        category: str,
        content: str,
    ) -> AgentMemoryFact | None:
        """Find an existing fact that might be superseded by new content.

        For certain categories (risk_tolerance), we want to supersede
        rather than accumulate facts.

        Args:
            category: Fact category
            content: New fact content

        Returns:
            Existing fact to supersede, or None
        """
        # Categories where we replace rather than accumulate
        replace_categories = {
            MemoryFactCategory.RISK_TOLERANCE,
        }

        if category not in replace_categories:
            return None

        stmt = (
            select(AgentMemoryFact)
            .where(
                and_(
                    AgentMemoryFact.tenant_id == self.tenant_id,
                    AgentMemoryFact.user_id == self.user_id,
                    AgentMemoryFact.category == category,
                    AgentMemoryFact.is_active.is_(True),
                )
            )
            .order_by(AgentMemoryFact.created_at.desc())
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # =========================================================================
    # Fact Retrieval
    # =========================================================================

    async def search(
        self,
        query: str | None = None,
        categories: list[str] | None = None,
        limit: int = 10,
        time_range_days: int | None = None,
    ) -> list[MemorySearchResult]:
        """Search memory facts with optional filters.

        Args:
            query: Optional text query for full-text search
            categories: Optional list of categories to filter
            limit: Maximum results to return
            time_range_days: Optional limit to facts from recent N days

        Returns:
            List of MemorySearchResult objects
        """
        # Build base query
        stmt = select(AgentMemoryFact).where(
            and_(
                AgentMemoryFact.tenant_id == self.tenant_id,
                AgentMemoryFact.user_id == self.user_id,
                AgentMemoryFact.is_active.is_(True),
            )
        )

        # Apply category filter
        if categories:
            stmt = stmt.where(AgentMemoryFact.category.in_(categories))

        # Apply time range filter
        if time_range_days:
            cutoff = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            from datetime import timedelta

            cutoff = cutoff - timedelta(days=time_range_days)
            stmt = stmt.where(AgentMemoryFact.created_at >= cutoff)

        # Apply text search if query provided
        if query:
            # Simple ILIKE search; for better results use embedding search
            search_pattern = f"%{query}%"
            stmt = stmt.where(AgentMemoryFact.content.ilike(search_pattern))

        # Order by recency and confidence
        stmt = stmt.order_by(
            AgentMemoryFact.confidence.desc(),
            AgentMemoryFact.created_at.desc(),
        ).limit(limit)

        result = await self.db.execute(stmt)
        facts = result.scalars().all()

        # Update access tracking
        now = datetime.now(UTC)
        for fact in facts:
            fact.last_accessed_at = now
            fact.access_count += 1

        await self.db.commit()

        return [
            MemorySearchResult(
                fact_id=fact.id,
                category=fact.category,
                content=fact.content,
                confidence=fact.confidence,
                created_at=fact.created_at,
                source_session_id=fact.source_session_id,
            )
            for fact in facts
        ]

    async def semantic_search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        min_similarity: float = 0.7,
    ) -> list[MemorySearchResult]:
        """Search memory using semantic similarity via pgvector.

        If pgvector is not available, falls back to returning recent facts
        (semantic search is not possible without vector operations).

        Args:
            query_embedding: Query embedding vector (1536 dimensions)
            limit: Maximum results to return
            min_similarity: Minimum cosine similarity threshold

        Returns:
            List of MemorySearchResult objects with relevance scores
        """
        try:
            # Check if pgvector is available by checking the column type
            check_sql = text(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'agent_memory_embeddings' AND column_name = 'embedding'
                """
            )
            type_result = await self.db.execute(check_sql)
            column_type = type_result.scalar_one_or_none()

            # If column is not vector type (e.g., jsonb), fall back to text search
            if column_type != "USER-DEFINED":  # pgvector creates a USER-DEFINED type
                logger.warning("pgvector not available, falling back to text-based fact retrieval")
                return await self._fallback_recent_facts(limit)

            # Use raw SQL for pgvector operations
            sql = text(
                """
                SELECT
                    e.source_id as fact_id,
                    e.content_text,
                    f.category,
                    f.confidence,
                    f.created_at,
                    f.source_session_id,
                    1 - (e.embedding <=> :query_embedding::vector) as similarity
                FROM agent_memory_embeddings e
                JOIN agent_memory_facts f ON f.id = e.source_id
                WHERE e.tenant_id = :tenant_id
                  AND e.user_id = :user_id
                  AND e.embedding_type = 'fact'
                  AND f.is_active = true
                  AND 1 - (e.embedding <=> :query_embedding::vector) >= :min_similarity
                ORDER BY e.embedding <=> :query_embedding::vector
                LIMIT :limit
                """
            )

            # Convert embedding to PostgreSQL array format
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

            result = await self.db.execute(
                sql,
                {
                    "tenant_id": str(self.tenant_id),
                    "user_id": str(self.user_id),
                    "query_embedding": embedding_str,
                    "min_similarity": min_similarity,
                    "limit": limit,
                },
            )

            rows = result.fetchall()

            return [
                MemorySearchResult(
                    fact_id=row.fact_id,
                    category=row.category,
                    content=row.content_text,
                    confidence=row.confidence,
                    created_at=row.created_at,
                    source_session_id=row.source_session_id,
                    relevance_score=row.similarity,
                )
                for row in rows
            ]

        except Exception as e:
            logger.warning("Semantic search failed, falling back to recent facts: %s", e)
            return await self._fallback_recent_facts(limit)

    async def _fallback_recent_facts(self, limit: int = 10) -> list[MemorySearchResult]:
        """Fallback to returning recent facts when semantic search unavailable.

        Args:
            limit: Maximum results to return

        Returns:
            List of recent facts as MemorySearchResult
        """
        stmt = (
            select(AgentMemoryFact)
            .where(
                and_(
                    AgentMemoryFact.tenant_id == self.tenant_id,
                    AgentMemoryFact.user_id == self.user_id,
                    AgentMemoryFact.is_active.is_(True),
                )
            )
            .order_by(AgentMemoryFact.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        facts = result.scalars().all()

        return [
            MemorySearchResult(
                fact_id=fact.id,
                category=fact.category,
                content=fact.content,
                confidence=fact.confidence,
                created_at=fact.created_at,
                source_session_id=fact.source_session_id,
                relevance_score=0.5,  # Unknown relevance without semantic search
            )
            for fact in facts
        ]

    # =========================================================================
    # User Profile
    # =========================================================================

    async def get_user_profile(
        self,
        sections: list[str] | None = None,
    ) -> UserProfile:
        """Get consolidated user profile from memory facts.

        Args:
            sections: Optional list of profile sections to include
                      (e.g., ["risk_profile", "goals", "preferences"])

        Returns:
            Consolidated UserProfile object
        """
        profile = UserProfile()

        # Fetch all active facts for the user
        stmt = (
            select(AgentMemoryFact)
            .where(
                and_(
                    AgentMemoryFact.tenant_id == self.tenant_id,
                    AgentMemoryFact.user_id == self.user_id,
                    AgentMemoryFact.is_active.is_(True),
                )
            )
            .order_by(AgentMemoryFact.created_at.desc())
        )

        result = await self.db.execute(stmt)
        facts = result.scalars().all()

        # Organize facts by category
        for fact in facts:
            if fact.category == MemoryFactCategory.RISK_TOLERANCE:
                if not profile.risk_tolerance:
                    profile.risk_tolerance = fact.content
            elif fact.category == MemoryFactCategory.INVESTMENT_GOAL:
                profile.investment_goals.append(fact.content)
            elif fact.category == MemoryFactCategory.ASSET_PREFERENCE:
                if "avoid" in fact.content.lower() or "don't" in fact.content.lower():
                    profile.asset_dislikes.append(fact.content)
                else:
                    profile.asset_preferences.append(fact.content)
            elif fact.category == MemoryFactCategory.TRADING_BEHAVIOR:
                profile.trading_behaviors.append(fact.content)
            elif fact.category == MemoryFactCategory.STRATEGY_DECISION:
                profile.recent_decisions.append(fact.content)
            elif fact.category == MemoryFactCategory.USER_PREFERENCE:
                profile.general_preferences.append(fact.content)

        # Deduplicate lists (keep first occurrence which is most recent)
        profile.investment_goals = list(dict.fromkeys(profile.investment_goals))[:5]
        profile.asset_preferences = list(dict.fromkeys(profile.asset_preferences))[:5]
        profile.asset_dislikes = list(dict.fromkeys(profile.asset_dislikes))[:3]
        profile.trading_behaviors = list(dict.fromkeys(profile.trading_behaviors))[:3]
        profile.recent_decisions = list(dict.fromkeys(profile.recent_decisions))[:3]
        profile.general_preferences = list(dict.fromkeys(profile.general_preferences))[:5]

        return profile

    # =========================================================================
    # Strategy Memory
    # =========================================================================

    async def search_past_strategies(
        self,
        query: str | None = None,
        symbols: list[str] | None = None,
        strategy_types: list[str] | None = None,
        include_drafts: bool = True,
        limit: int = 10,
    ) -> list[StrategyMemory]:
        """Search strategies from user's history.

        Args:
            query: Optional text query
            symbols: Optional symbols to filter
            strategy_types: Optional strategy types to filter
            include_drafts: Include draft strategies
            limit: Maximum results

        Returns:
            List of StrategyMemory objects
        """
        # Query tenant's strategies (Strategy is tenant-scoped, not user-scoped)
        stmt = select(Strategy).where(
            Strategy.tenant_id == self.tenant_id,
        )

        if not include_drafts:
            # Filter out draft status (assuming draft = 1)
            stmt = stmt.where(Strategy.status != 1)

        if query:
            search_pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    Strategy.name.ilike(search_pattern),
                    Strategy.description.ilike(search_pattern),
                )
            )

        stmt = stmt.order_by(Strategy.updated_at.desc()).limit(limit)

        result = await self.db.execute(stmt)
        strategies = result.scalars().all()

        # Convert to StrategyMemory objects
        memories: list[StrategyMemory] = []
        for strategy in strategies:
            # Extract symbols from DSL if available
            extracted_symbols: list[str] = []
            # Get DSL from the latest version if available
            dsl: str | None = None
            if strategy.versions:
                dsl = strategy.versions[0].config_sexpr
            if dsl:
                # Simple regex extraction
                import re

                matches = re.findall(r"\(asset\s+([A-Z]+)", dsl)
                extracted_symbols = list(set(matches))

            # Filter by symbols if provided
            if symbols:
                if not any(s in extracted_symbols for s in symbols):
                    continue

            memories.append(
                StrategyMemory(
                    strategy_id=strategy.id,
                    strategy_name=strategy.name,
                    dsl_snippet=(dsl[:200] + "..." if dsl and len(dsl) > 200 else dsl),
                    symbols=extracted_symbols[:5],
                    discussed_at=strategy.updated_at,
                    context=strategy.description,
                )
            )

        return memories[:limit]

    # =========================================================================
    # Session Summaries
    # =========================================================================

    async def get_session_summary(
        self,
        session_id: UUID | None = None,
        session_date: str | None = None,
        include_messages: bool = False,
    ) -> SessionSummaryResult | None:
        """Get summary of a past session.

        Args:
            session_id: Optional session ID to fetch
            session_date: Optional date string to find session (YYYY-MM-DD)
            include_messages: Include recent message excerpts

        Returns:
            SessionSummaryResult or None
        """
        if session_id:
            stmt = select(AgentSessionSummary).where(
                and_(
                    AgentSessionSummary.tenant_id == self.tenant_id,
                    AgentSessionSummary.user_id == self.user_id,
                    AgentSessionSummary.session_id == session_id,
                )
            )
        elif session_date:
            # Parse date and find session from that day
            from datetime import timedelta

            try:
                date = datetime.strptime(session_date, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                return None

            next_date = date + timedelta(days=1)

            # Find session summary where session was created on that date
            stmt = (
                select(AgentSessionSummary)
                .join(AgentSession, AgentSession.id == AgentSessionSummary.session_id)
                .where(
                    and_(
                        AgentSessionSummary.tenant_id == self.tenant_id,
                        AgentSessionSummary.user_id == self.user_id,
                        AgentSession.created_at >= date,
                        AgentSession.created_at < next_date,
                    )
                )
                .order_by(AgentSession.created_at.desc())
            )
        else:
            # Get most recent session summary
            stmt = (
                select(AgentSessionSummary)
                .where(
                    and_(
                        AgentSessionSummary.tenant_id == self.tenant_id,
                        AgentSessionSummary.user_id == self.user_id,
                    )
                )
                .order_by(AgentSessionSummary.created_at.desc())
            )

        result = await self.db.execute(stmt.limit(1))
        summary = result.scalar_one_or_none()

        if not summary:
            return None

        return SessionSummaryResult(
            session_id=summary.session_id,
            summary_short=summary.summary_short,
            summary_detailed=summary.summary_detailed,
            topics=summary.topics,
            strategies_discussed=summary.strategies_discussed,
            decisions=summary.decisions,
            created_at=summary.created_at,
            message_count=summary.message_count_at_summary,
        )

    async def store_session_summary(
        self,
        session_id: UUID,
        summary_short: str,
        summary_detailed: str,
        topics: list[str],
        strategies_discussed: list[str],
        decisions: list[str],
        message_count: int,
    ) -> AgentSessionSummary:
        """Store a session summary.

        Args:
            session_id: Session UUID
            summary_short: Short summary (1-2 sentences)
            summary_detailed: Full detailed summary
            topics: Key topics discussed
            strategies_discussed: Strategy names mentioned
            decisions: Key decisions made
            message_count: Number of messages at time of summary

        Returns:
            Created AgentSessionSummary
        """
        # Check for existing summary
        stmt = select(AgentSessionSummary).where(AgentSessionSummary.session_id == session_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing summary
            existing.summary_short = summary_short
            existing.summary_detailed = summary_detailed
            existing.topics = topics
            existing.strategies_discussed = strategies_discussed
            existing.decisions = decisions
            existing.message_count_at_summary = message_count
            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        # Create new summary
        summary = AgentSessionSummary(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            session_id=session_id,
            summary_short=summary_short,
            summary_detailed=summary_detailed,
            topics=topics,
            strategies_discussed=strategies_discussed,
            decisions=decisions,
            message_count_at_summary=message_count,
        )

        self.db.add(summary)
        await self.db.commit()
        await self.db.refresh(summary)

        return summary

    # =========================================================================
    # Memory Hint
    # =========================================================================

    async def get_memory_hint(self) -> MemoryHint:
        """Get lightweight memory hint for system prompt injection.

        This is designed to be fast and return minimal data for
        the system prompt (~50 tokens).

        Returns:
            MemoryHint object
        """
        # Count user's sessions
        session_count_stmt = select(func.count()).where(
            and_(
                AgentSession.tenant_id == self.tenant_id,
                AgentSession.user_id == self.user_id,
            )
        )
        session_result = await self.db.execute(session_count_stmt)
        session_count = session_result.scalar_one()

        if session_count == 0:
            return MemoryHint(is_new_user=True)

        # Get risk tolerance if available
        risk_stmt = (
            select(AgentMemoryFact.content)
            .where(
                and_(
                    AgentMemoryFact.tenant_id == self.tenant_id,
                    AgentMemoryFact.user_id == self.user_id,
                    AgentMemoryFact.category == MemoryFactCategory.RISK_TOLERANCE,
                    AgentMemoryFact.is_active.is_(True),
                )
            )
            .order_by(AgentMemoryFact.created_at.desc())
            .limit(1)
        )
        risk_result = await self.db.execute(risk_stmt)
        risk_tolerance = risk_result.scalar_one_or_none()

        # Get primary investment goal
        goal_stmt = (
            select(AgentMemoryFact.content)
            .where(
                and_(
                    AgentMemoryFact.tenant_id == self.tenant_id,
                    AgentMemoryFact.user_id == self.user_id,
                    AgentMemoryFact.category == MemoryFactCategory.INVESTMENT_GOAL,
                    AgentMemoryFact.is_active.is_(True),
                )
            )
            .order_by(AgentMemoryFact.created_at.desc())
            .limit(1)
        )
        goal_result = await self.db.execute(goal_stmt)
        goal_summary = goal_result.scalar_one_or_none()

        # Get recent strategies (just names) - Strategy is tenant-scoped
        strategy_stmt = (
            select(Strategy.name)
            .where(
                Strategy.tenant_id == self.tenant_id,
            )
            .order_by(Strategy.updated_at.desc())
            .limit(3)
        )
        strategy_result = await self.db.execute(strategy_stmt)
        recent_strategies = [row[0] for row in strategy_result.fetchall()]

        return MemoryHint(
            is_new_user=False,
            session_count=session_count,
            risk_tolerance=risk_tolerance,
            goal_summary=goal_summary,
            recent_strategies=recent_strategies,
        )

    # =========================================================================
    # Embedding Storage
    # =========================================================================

    async def store_embedding(
        self,
        embedding: list[float],
        content_text: str,
        source_id: UUID,
        embedding_type: str = "fact",
        embedding_model: str = "text-embedding-3-small",
    ) -> AgentMemoryEmbedding | None:
        """Store a vector embedding.

        Handles both pgvector (vector type) and fallback (JSONB) storage.

        Args:
            embedding: Vector embedding (1536 dimensions)
            content_text: Original text that was embedded
            source_id: ID of the source (fact, summary, or strategy)
            embedding_type: Type of embedding ("fact", "summary", "strategy")
            embedding_model: Model used to generate embedding

        Returns:
            Created AgentMemoryEmbedding or None if storage failed
        """
        try:
            # Check if pgvector is available
            check_sql = text(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'agent_memory_embeddings' AND column_name = 'embedding'
                """
            )
            type_result = await self.db.execute(check_sql)
            column_type = type_result.scalar_one_or_none()

            use_pgvector = column_type == "USER-DEFINED"

            if use_pgvector:
                # Use pgvector format
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                sql = text(
                    """
                    INSERT INTO agent_memory_embeddings
                    (id, tenant_id, user_id, embedding_type, embedding, content_text, source_id, embedding_model, created_at, updated_at)
                    VALUES
                    (gen_random_uuid(), :tenant_id, :user_id, :embedding_type, :embedding::vector, :content_text, :source_id, :embedding_model, NOW(), NOW())
                    RETURNING id
                    """
                )
                params = {
                    "tenant_id": str(self.tenant_id),
                    "user_id": str(self.user_id),
                    "embedding_type": embedding_type,
                    "embedding": embedding_str,
                    "content_text": content_text,
                    "source_id": str(source_id),
                    "embedding_model": embedding_model,
                }
            else:
                # Use JSONB format
                import json

                embedding_json = json.dumps(embedding)
                sql = text(
                    """
                    INSERT INTO agent_memory_embeddings
                    (id, tenant_id, user_id, embedding_type, embedding, content_text, source_id, embedding_model, created_at, updated_at)
                    VALUES
                    (gen_random_uuid(), :tenant_id, :user_id, :embedding_type, :embedding::jsonb, :content_text, :source_id, :embedding_model, NOW(), NOW())
                    RETURNING id
                    """
                )
                params = {
                    "tenant_id": str(self.tenant_id),
                    "user_id": str(self.user_id),
                    "embedding_type": embedding_type,
                    "embedding": embedding_json,
                    "content_text": content_text,
                    "source_id": str(source_id),
                    "embedding_model": embedding_model,
                }

            result = await self.db.execute(sql, params)
            row = result.fetchone()
            await self.db.commit()

            if row:
                # Fetch the created embedding
                stmt = select(AgentMemoryEmbedding).where(AgentMemoryEmbedding.id == row[0])
                fetch_result = await self.db.execute(stmt)
                return fetch_result.scalar_one_or_none()

            return None

        except Exception as e:
            logger.exception("Failed to store embedding: %s", e)
            return None
