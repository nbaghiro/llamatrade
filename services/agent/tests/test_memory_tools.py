"""Tests for memory tools.

Tests memory-related agent tools for recall, profile, strategy search, and summaries.
Target coverage: 85%
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from tests.fixtures.memory_factories import (
    make_memory_search_result,
    make_user_profile,
)

from src.tools.base import ToolContext
from src.tools.memory_tools import (
    GetSessionSummaryTool,
    GetUserProfileTool,
    RecallMemoryTool,
    SearchPastStrategiesTool,
)

# =============================================================================
# RecallMemoryTool Tests
# =============================================================================


class TestRecallMemoryTool:
    """Tests for RecallMemoryTool."""

    @pytest.fixture
    def tool(self) -> RecallMemoryTool:
        """Create tool instance."""
        return RecallMemoryTool()

    @pytest.fixture
    def context(self, tenant_id: UUID, user_id: UUID, session_id: UUID) -> ToolContext:
        """Create tool context."""
        return ToolContext(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )

    # =========================================================================
    # Properties Tests
    # =========================================================================

    def test_tool_name(self, tool: RecallMemoryTool) -> None:
        """Test tool name property."""
        assert tool.name == "recall_memory"

    def test_tool_description(self, tool: RecallMemoryTool) -> None:
        """Test tool description property."""
        assert "recall" in tool.description.lower()
        assert "past conversations" in tool.description.lower()

    def test_parameters_schema(self, tool: RecallMemoryTool) -> None:
        """Test parameters schema."""
        schema = tool.parameters_schema
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "categories" in schema["properties"]
        assert "time_range_days" in schema["properties"]
        assert "limit" in schema["properties"]
        assert "query" in schema["required"]

    def test_parameters_schema_categories_enum(self, tool: RecallMemoryTool) -> None:
        """Test that categories parameter has correct enum values."""
        schema = tool.parameters_schema
        categories_enum = schema["properties"]["categories"]["items"]["enum"]
        assert "user_preference" in categories_enum
        assert "risk_tolerance" in categories_enum
        assert "investment_goal" in categories_enum
        assert "asset_preference" in categories_enum
        assert "strategy_decision" in categories_enum

    # =========================================================================
    # Execution Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_execute_with_query(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test execution with query parameter."""
        mock_results = [
            make_memory_search_result(
                content="User prefers tech stocks",
                category="asset_preference",
                confidence=0.85,
            ),
        ]

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search = AsyncMock(return_value=mock_results)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute(
                    {"query": "tech stocks"},
                    context,
                )

        assert result.success is True
        assert result.data["count"] == 1
        assert len(result.data["facts"]) == 1

    @pytest.mark.asyncio
    async def test_execute_with_categories(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test execution with category filter."""
        mock_results = [make_memory_search_result(category="risk_tolerance")]

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search = AsyncMock(return_value=mock_results)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute(
                    {
                        "query": "risk",
                        "categories": ["risk_tolerance"],
                    },
                    context,
                )

        assert result.success is True
        mock_service.search.assert_called_once()
        call_kwargs = mock_service.search.call_args[1]
        assert call_kwargs["categories"] == ["risk_tolerance"]

    @pytest.mark.asyncio
    async def test_execute_with_time_range(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test execution with time range filter."""
        mock_results = []

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search = AsyncMock(return_value=mock_results)
                mock_memory_service_cls.return_value = mock_service

                await tool.execute(
                    {
                        "query": "recent",
                        "time_range_days": 7,
                    },
                    context,
                )

        mock_service.search.assert_called_once()
        call_kwargs = mock_service.search.call_args[1]
        assert call_kwargs["time_range_days"] == 7

    @pytest.mark.asyncio
    async def test_execute_with_limit(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test execution with result limit."""
        mock_results = []

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search = AsyncMock(return_value=mock_results)
                mock_memory_service_cls.return_value = mock_service

                await tool.execute(
                    {
                        "query": "test",
                        "limit": 5,
                    },
                    context,
                )

        mock_service.search.assert_called_once()
        call_kwargs = mock_service.search.call_args[1]
        assert call_kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_formats_results_correctly(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test that results are formatted correctly."""
        created_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_results = [
            make_memory_search_result(
                category="user_preference",
                content="Prefers low fees",
                confidence=0.756,
                created_at=created_at,
                relevance_score=0.923,
            ),
        ]

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search = AsyncMock(return_value=mock_results)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({"query": "fees"}, context)

        fact = result.data["facts"][0]
        assert fact["category"] == "user_preference"
        assert fact["content"] == "Prefers low fees"

    @pytest.mark.asyncio
    async def test_rounds_confidence_to_2_decimals(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test that confidence is rounded to 2 decimal places."""
        mock_results = [
            make_memory_search_result(confidence=0.756789),
        ]

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search = AsyncMock(return_value=mock_results)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({"query": "test"}, context)

        fact = result.data["facts"][0]
        assert fact["confidence"] == 0.76

    @pytest.mark.asyncio
    async def test_formats_date_as_yyyy_mm_dd(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test that dates are formatted as YYYY-MM-DD."""
        created_at = datetime(2024, 3, 15, 14, 30, 0, tzinfo=UTC)
        mock_results = [make_memory_search_result(created_at=created_at)]

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search = AsyncMock(return_value=mock_results)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({"query": "test"}, context)

        fact = result.data["facts"][0]
        assert fact["date"] == "2024-03-15"

    # =========================================================================
    # Validation Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_missing_query_fails(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test that missing query parameter returns error."""
        result = await tool.execute({}, context)

        assert result.success is False
        assert "query" in result.error.lower()

    # =========================================================================
    # Edge Case Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_no_results_returns_empty_array(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test that no results returns empty array."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search = AsyncMock(return_value=[])
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({"query": "nonexistent"}, context)

        assert result.success is True
        assert result.data["facts"] == []
        assert result.data["count"] == 0
        assert "No relevant memories" in result.data["message"]

    @pytest.mark.asyncio
    async def test_handles_service_exception(
        self,
        tool: RecallMemoryTool,
        context: ToolContext,
    ) -> None:
        """Test handling of service exception."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search = AsyncMock(side_effect=Exception("DB Error"))
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({"query": "test"}, context)

        assert result.success is False
        assert "Failed to recall memories" in result.error


# =============================================================================
# GetUserProfileTool Tests
# =============================================================================


class TestGetUserProfileTool:
    """Tests for GetUserProfileTool."""

    @pytest.fixture
    def tool(self) -> GetUserProfileTool:
        """Create tool instance."""
        return GetUserProfileTool()

    @pytest.fixture
    def context(self, tenant_id: UUID, user_id: UUID, session_id: UUID) -> ToolContext:
        """Create tool context."""
        return ToolContext(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )

    def test_tool_properties(self, tool: GetUserProfileTool) -> None:
        """Test tool properties."""
        assert tool.name == "get_user_profile"
        assert "profile" in tool.description.lower()
        assert tool.parameters_schema["required"] == []

    @pytest.mark.asyncio
    async def test_execute_all_sections(
        self,
        tool: GetUserProfileTool,
        context: ToolContext,
    ) -> None:
        """Test execution returns all profile sections."""
        mock_profile = make_user_profile(
            risk_tolerance="moderate",
            investment_goals=["retirement"],
            asset_preferences=["tech"],
            trading_behaviors=["monthly rebalance"],
        )

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_user_profile = AsyncMock(return_value=mock_profile)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({}, context)

        assert result.success is True
        assert result.data["is_new_user"] is False
        assert "risk_tolerance" in result.data["profile"]
        assert "investment_goals" in result.data["profile"]

    @pytest.mark.asyncio
    async def test_execute_specific_sections(
        self,
        tool: GetUserProfileTool,
        context: ToolContext,
    ) -> None:
        """Test execution with specific sections requested."""
        mock_profile = make_user_profile(risk_tolerance="aggressive")

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_user_profile = AsyncMock(return_value=mock_profile)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute(
                    {"include_sections": ["risk_profile"]},
                    context,
                )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_new_user_returns_empty_profile(
        self,
        tool: GetUserProfileTool,
        context: ToolContext,
    ) -> None:
        """Test that new user returns empty profile."""
        empty_profile = make_user_profile(
            risk_tolerance=None,
            investment_goals=[],
            asset_preferences=[],
            asset_dislikes=[],
            trading_behaviors=[],
            recent_decisions=[],
            general_preferences=[],
        )
        # Override to make truly empty
        empty_profile.risk_tolerance = None
        empty_profile.investment_goals = []
        empty_profile.asset_preferences = []
        empty_profile.asset_dislikes = []
        empty_profile.trading_behaviors = []
        empty_profile.recent_decisions = []
        empty_profile.general_preferences = []

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_user_profile = AsyncMock(return_value=empty_profile)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({}, context)

        assert result.success is True
        assert result.data["is_new_user"] is True
        assert result.data["profile"] == {}

    @pytest.mark.asyncio
    async def test_formats_asset_preferences(
        self,
        tool: GetUserProfileTool,
        context: ToolContext,
    ) -> None:
        """Test that asset preferences are formatted correctly."""
        mock_profile = make_user_profile(
            risk_tolerance=None,
            investment_goals=[],
            asset_preferences=["tech stocks"],
            asset_dislikes=["energy sector"],
        )
        mock_profile.trading_behaviors = []
        mock_profile.recent_decisions = []
        mock_profile.general_preferences = []

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_user_profile = AsyncMock(return_value=mock_profile)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({}, context)

        assert result.success is True
        assert "asset_preferences" in result.data["profile"]
        prefs = result.data["profile"]["asset_preferences"]
        assert "likes" in prefs
        assert "dislikes" in prefs

    @pytest.mark.asyncio
    async def test_handles_service_exception(
        self,
        tool: GetUserProfileTool,
        context: ToolContext,
    ) -> None:
        """Test handling of service exception."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_user_profile = AsyncMock(side_effect=Exception("Error"))
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({}, context)

        assert result.success is False


# =============================================================================
# SearchPastStrategiesTool Tests
# =============================================================================


class TestSearchPastStrategiesTool:
    """Tests for SearchPastStrategiesTool."""

    @pytest.fixture
    def tool(self) -> SearchPastStrategiesTool:
        """Create tool instance."""
        return SearchPastStrategiesTool()

    @pytest.fixture
    def context(self, tenant_id: UUID, user_id: UUID, session_id: UUID) -> ToolContext:
        """Create tool context."""
        return ToolContext(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )

    def test_tool_properties(self, tool: SearchPastStrategiesTool) -> None:
        """Test tool properties."""
        assert tool.name == "search_past_strategies"
        assert "strategies" in tool.description.lower()
        assert tool.parameters_schema["required"] == []

    @pytest.mark.asyncio
    async def test_execute_with_query(
        self,
        tool: SearchPastStrategiesTool,
        context: ToolContext,
    ) -> None:
        """Test execution with query parameter."""
        mock_strategy = MagicMock()
        mock_strategy.strategy_id = uuid4()
        mock_strategy.strategy_name = "Momentum Strategy"
        mock_strategy.dsl_snippet = "(strategy...)"
        mock_strategy.symbols = ["SPY", "QQQ"]
        mock_strategy.discussed_at = datetime.now(UTC)
        mock_strategy.context = "Test description"
        mock_strategy.performance_summary = None

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search_past_strategies = AsyncMock(return_value=[mock_strategy])
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({"query": "momentum"}, context)

        assert result.success is True
        assert result.data["count"] == 1
        assert result.data["strategies"][0]["name"] == "Momentum Strategy"

    @pytest.mark.asyncio
    async def test_execute_with_symbols(
        self,
        tool: SearchPastStrategiesTool,
        context: ToolContext,
    ) -> None:
        """Test execution with symbols filter."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search_past_strategies = AsyncMock(return_value=[])
                mock_memory_service_cls.return_value = mock_service

                await tool.execute(
                    {"symbols": ["SPY", "QQQ"]},
                    context,
                )

        mock_service.search_past_strategies.assert_called_once()
        call_kwargs = mock_service.search_past_strategies.call_args[1]
        assert call_kwargs["symbols"] == ["SPY", "QQQ"]

    @pytest.mark.asyncio
    async def test_execute_with_strategy_types(
        self,
        tool: SearchPastStrategiesTool,
        context: ToolContext,
    ) -> None:
        """Test execution with strategy types filter."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search_past_strategies = AsyncMock(return_value=[])
                mock_memory_service_cls.return_value = mock_service

                await tool.execute(
                    {"strategy_types": ["momentum", "defensive"]},
                    context,
                )

        call_kwargs = mock_service.search_past_strategies.call_args[1]
        assert call_kwargs["strategy_types"] == ["momentum", "defensive"]

    @pytest.mark.asyncio
    async def test_include_drafts_parameter(
        self,
        tool: SearchPastStrategiesTool,
        context: ToolContext,
    ) -> None:
        """Test include_drafts parameter."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search_past_strategies = AsyncMock(return_value=[])
                mock_memory_service_cls.return_value = mock_service

                await tool.execute(
                    {"include_drafts": False},
                    context,
                )

        call_kwargs = mock_service.search_past_strategies.call_args[1]
        assert call_kwargs["include_drafts"] is False

    @pytest.mark.asyncio
    async def test_no_results_returns_empty(
        self,
        tool: SearchPastStrategiesTool,
        context: ToolContext,
    ) -> None:
        """Test that no results returns empty."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search_past_strategies = AsyncMock(return_value=[])
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({}, context)

        assert result.success is True
        assert result.data["strategies"] == []
        assert "No matching strategies" in result.data["message"]

    @pytest.mark.asyncio
    async def test_handles_service_exception(
        self,
        tool: SearchPastStrategiesTool,
        context: ToolContext,
    ) -> None:
        """Test handling of service exception."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.search_past_strategies = AsyncMock(side_effect=Exception("Error"))
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({}, context)

        assert result.success is False


# =============================================================================
# GetSessionSummaryTool Tests
# =============================================================================


class TestGetSessionSummaryTool:
    """Tests for GetSessionSummaryTool."""

    @pytest.fixture
    def tool(self) -> GetSessionSummaryTool:
        """Create tool instance."""
        return GetSessionSummaryTool()

    @pytest.fixture
    def context(self, tenant_id: UUID, user_id: UUID, session_id: UUID) -> ToolContext:
        """Create tool context."""
        return ToolContext(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )

    def test_tool_properties(self, tool: GetSessionSummaryTool) -> None:
        """Test tool properties."""
        assert tool.name == "get_session_summary"
        assert "summary" in tool.description.lower()
        assert tool.parameters_schema["required"] == []

    @pytest.mark.asyncio
    async def test_execute_by_session_id(
        self,
        tool: GetSessionSummaryTool,
        context: ToolContext,
    ) -> None:
        """Test execution with session_id."""
        session_id = uuid4()
        mock_summary = MagicMock()
        mock_summary.session_id = session_id
        mock_summary.summary_short = "Short summary"
        mock_summary.summary_detailed = "Detailed summary"
        mock_summary.topics = ["investing"]
        mock_summary.strategies_discussed = ["60/40"]
        mock_summary.decisions = ["chose conservative"]
        mock_summary.created_at = datetime.now(UTC)
        mock_summary.message_count = 15

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_session_summary = AsyncMock(return_value=mock_summary)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute(
                    {"session_id": str(session_id)},
                    context,
                )

        assert result.success is True
        assert result.data["summary"]["session_id"] == str(session_id)
        assert result.data["summary"]["summary_short"] == "Short summary"

    @pytest.mark.asyncio
    async def test_execute_by_date(
        self,
        tool: GetSessionSummaryTool,
        context: ToolContext,
    ) -> None:
        """Test execution with session_date."""
        mock_summary = MagicMock()
        mock_summary.session_id = uuid4()
        mock_summary.summary_short = "Summary"
        mock_summary.summary_detailed = "Detailed"
        mock_summary.topics = []
        mock_summary.strategies_discussed = []
        mock_summary.decisions = []
        mock_summary.created_at = datetime.now(UTC)
        mock_summary.message_count = 10

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_session_summary = AsyncMock(return_value=mock_summary)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute(
                    {"session_date": "2024-01-15"},
                    context,
                )

        assert result.success is True
        mock_service.get_session_summary.assert_called_once()
        call_kwargs = mock_service.get_session_summary.call_args[1]
        assert call_kwargs["session_date"] == "2024-01-15"

    @pytest.mark.asyncio
    async def test_invalid_uuid_fails(
        self,
        tool: GetSessionSummaryTool,
        context: ToolContext,
    ) -> None:
        """Test that invalid UUID returns error."""
        result = await tool.execute(
            {"session_id": "not-a-valid-uuid"},
            context,
        )

        assert result.success is False
        assert "Invalid session_id" in result.error

    @pytest.mark.asyncio
    async def test_not_found_returns_null_summary(
        self,
        tool: GetSessionSummaryTool,
        context: ToolContext,
    ) -> None:
        """Test that not found returns null summary."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_session_summary = AsyncMock(return_value=None)
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute(
                    {"session_id": str(uuid4())},
                    context,
                )

        assert result.success is True
        assert result.data["summary"] is None
        assert "No session summary found" in result.data["message"]

    @pytest.mark.asyncio
    async def test_include_messages_parameter(
        self,
        tool: GetSessionSummaryTool,
        context: ToolContext,
    ) -> None:
        """Test include_messages parameter is passed."""
        mock_summary = MagicMock()
        mock_summary.session_id = uuid4()
        mock_summary.summary_short = "Summary"
        mock_summary.summary_detailed = "Detailed"
        mock_summary.topics = []
        mock_summary.strategies_discussed = []
        mock_summary.decisions = []
        mock_summary.created_at = datetime.now(UTC)
        mock_summary.message_count = 10

        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_session_summary = AsyncMock(return_value=mock_summary)
                mock_memory_service_cls.return_value = mock_service

                await tool.execute(
                    {"include_messages": True},
                    context,
                )

        call_kwargs = mock_service.get_session_summary.call_args[1]
        assert call_kwargs["include_messages"] is True

    @pytest.mark.asyncio
    async def test_handles_service_exception(
        self,
        tool: GetSessionSummaryTool,
        context: ToolContext,
    ) -> None:
        """Test handling of service exception."""
        with patch("src.tools.memory_tools.get_db") as mock_get_db:
            mock_db = AsyncMock()
            mock_get_db.return_value = mock_db_context(mock_db)

            with patch("src.tools.memory_tools.MemoryService") as mock_memory_service_cls:
                mock_service = MagicMock()
                mock_service.get_session_summary = AsyncMock(side_effect=Exception("Error"))
                mock_memory_service_cls.return_value = mock_service

                result = await tool.execute({}, context)

        assert result.success is False


# =============================================================================
# Tool Registration Tests
# =============================================================================


class TestToolRegistration:
    """Tests for tool registration in executor."""

    def test_all_memory_tools_instantiate(self) -> None:
        """Test that all memory tools can be instantiated."""
        tools = [
            RecallMemoryTool(),
            GetUserProfileTool(),
            SearchPastStrategiesTool(),
            GetSessionSummaryTool(),
        ]

        for tool in tools:
            assert tool.name is not None
            assert tool.description is not None
            assert tool.parameters_schema is not None

    def test_tool_definitions_valid(self) -> None:
        """Test that tool definitions are valid for Claude."""
        tools = [
            RecallMemoryTool(),
            GetUserProfileTool(),
            SearchPastStrategiesTool(),
            GetSessionSummaryTool(),
        ]

        for tool in tools:
            definition = tool.to_claude_tool_definition()
            assert "name" in definition
            assert "description" in definition
            assert "input_schema" in definition
            assert definition["input_schema"]["type"] == "object"


# =============================================================================
# Helper Functions
# =============================================================================


async def mock_db_context(mock_db: AsyncMock) -> Any:
    """Create an async generator that yields the mock db."""
    yield mock_db
