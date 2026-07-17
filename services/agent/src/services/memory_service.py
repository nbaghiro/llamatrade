"""Memory service for cross-session user memory management.

This service handles:
- Storing and retrieving memory facts (extracted user preferences)
- User profile consolidation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import (
    AgentMemoryFact,
    AgentSession,
    MemoryFactCategory,
    Strategy,
)

logger = logging.getLogger(__name__)


# Data Classes


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
class MemoryHint:
    """Lightweight memory hint for system prompt injection."""

    is_new_user: bool = True
    session_count: int = 0
    risk_tolerance: str | None = None
    goal_summary: str | None = None
    recent_strategies: list[str] = field(default_factory=list)


# Memory Service


class MemoryService:
    """Service for managing user memory across sessions.

    Provides CRUD operations for memory facts and user profile consolidation
    from historical data.
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

    # Fact Storage

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
            # Skip an exact re-mention already on file (any category) so repeated
            # phrasing across turns doesn't accumulate duplicate facts.
            if await self._active_fact_exists(fact.category, fact.content):
                continue

            # Replace-categories (e.g. risk tolerance) supersede the prior value.
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

        if not created_facts:
            return []

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

    async def _active_fact_exists(self, category: str, content: str) -> bool:
        """Whether an active fact with the same category and (case-insensitive)
        content already exists for this user."""
        stmt = (
            select(AgentMemoryFact.id)
            .where(
                and_(
                    AgentMemoryFact.tenant_id == self.tenant_id,
                    AgentMemoryFact.user_id == self.user_id,
                    AgentMemoryFact.category == category,
                    AgentMemoryFact.is_active.is_(True),
                    func.lower(AgentMemoryFact.content) == content.strip().lower(),
                )
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.first() is not None

    # Fact Retrieval

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
        stmt = select(AgentMemoryFact).where(
            and_(
                AgentMemoryFact.tenant_id == self.tenant_id,
                AgentMemoryFact.user_id == self.user_id,
                AgentMemoryFact.is_active.is_(True),
            )
        )

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

    # User Profile

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

    # Strategy Memory

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
        # Only the acting user's own strategies — Strategy is tenant-scoped, so
        # created_by is what keeps one user's history out of another's memory.
        stmt = select(Strategy).where(
            Strategy.tenant_id == self.tenant_id,
            Strategy.created_by == self.user_id,
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

    # Memory Hint

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

        # Recent strategies this user authored (names only, for the prompt hint).
        strategy_stmt = (
            select(Strategy.name)
            .where(
                Strategy.tenant_id == self.tenant_id,
                Strategy.created_by == self.user_id,
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
