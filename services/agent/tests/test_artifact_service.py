"""Tests for ArtifactService database operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated.agent_pb2 import ARTIFACT_TYPE_STRATEGY

from src.services.artifact_service import ArtifactService

# =============================================================================
# Helper Functions
# =============================================================================


def mock_scalar_one_or_none(value: Any) -> MagicMock:
    """Create a mock result that returns the value from scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def make_mock_artifact(
    artifact_id: UUID | None = None,
    session_id: UUID | None = None,
    tenant_id: UUID | None = None,
    artifact_type: int = ARTIFACT_TYPE_STRATEGY,
    name: str = "Test Strategy",
    description: str | None = "Test description",
    dsl_code: str = '(strategy "Test")',
    is_committed: bool = False,
    committed_resource_id: UUID | None = None,
) -> MagicMock:
    """Create a mock PendingArtifact."""
    mock = MagicMock()
    mock.id = artifact_id or uuid4()
    mock.session_id = session_id or uuid4()
    mock.tenant_id = tenant_id or uuid4()
    mock.artifact_type = artifact_type
    mock.name = name
    mock.description = description
    mock.artifact_json = {
        "name": name,
        "description": description,
        "dsl_code": dsl_code,
        "symbols": [],
        "timeframe": "1D",
    }
    mock.is_committed = is_committed
    mock.committed_resource_id = committed_resource_id
    mock.committed_at = None
    mock.created_at = datetime.now(UTC)
    return mock


# =============================================================================
# Creation Tests
# =============================================================================


class TestCreateStrategyArtifact:
    """Tests for strategy artifact creation."""

    @pytest.mark.asyncio
    async def test_create_strategy_artifact_success(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test creating a strategy artifact with all fields."""
        session_id = uuid4()
        added_artifact = None

        def capture_add(obj: Any) -> None:
            nonlocal added_artifact
            added_artifact = obj

        artifact_service.db.add = capture_add
        artifact_service.db.commit = AsyncMock()
        artifact_service.db.refresh = AsyncMock()

        await artifact_service.create_strategy_artifact(
            session_id=session_id,
            name="My Strategy",
            dsl_code='(strategy "My Strategy" :rebalance monthly)',
            description="A test strategy",
            symbols=["VTI", "BND"],
            timeframe="1D",
        )

        assert added_artifact is not None
        assert added_artifact.session_id == session_id
        assert added_artifact.name == "My Strategy"
        assert added_artifact.description == "A test strategy"
        assert added_artifact.artifact_type == ARTIFACT_TYPE_STRATEGY
        assert added_artifact.is_committed is False

    @pytest.mark.asyncio
    async def test_create_strategy_artifact_minimal(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test creating a strategy artifact with minimal required fields."""
        session_id = uuid4()
        added_artifact = None

        def capture_add(obj: Any) -> None:
            nonlocal added_artifact
            added_artifact = obj

        artifact_service.db.add = capture_add
        artifact_service.db.commit = AsyncMock()
        artifact_service.db.refresh = AsyncMock()

        await artifact_service.create_strategy_artifact(
            session_id=session_id,
            name="Minimal Strategy",
            dsl_code='(strategy "Minimal")',
        )

        assert added_artifact is not None
        assert added_artifact.name == "Minimal Strategy"
        assert added_artifact.artifact_json["symbols"] == []
        assert added_artifact.artifact_json["timeframe"] == "1D"

    @pytest.mark.asyncio
    async def test_create_strategy_artifact_json_structure(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test that artifact_json has correct structure."""
        session_id = uuid4()
        added_artifact = None

        def capture_add(obj: Any) -> None:
            nonlocal added_artifact
            added_artifact = obj

        artifact_service.db.add = capture_add
        artifact_service.db.commit = AsyncMock()
        artifact_service.db.refresh = AsyncMock()

        await artifact_service.create_strategy_artifact(
            session_id=session_id,
            name="Structured Strategy",
            dsl_code='(strategy "Test")',
            description="Test description",
            config_json={"risk_level": "moderate"},
            symbols=["SPY", "QQQ"],
            timeframe="4H",
        )

        assert added_artifact is not None
        json_data = added_artifact.artifact_json
        assert json_data["name"] == "Structured Strategy"
        assert json_data["description"] == "Test description"
        assert json_data["dsl_code"] == '(strategy "Test")'
        assert json_data["config_json"] == {"risk_level": "moderate"}
        assert json_data["symbols"] == ["SPY", "QQQ"]
        assert json_data["timeframe"] == "4H"


# =============================================================================
# Retrieval Tests
# =============================================================================


class TestGetArtifact:
    """Tests for artifact retrieval."""

    @pytest.mark.asyncio
    async def test_get_artifact_exists(
        self,
        artifact_service: ArtifactService,
        tenant_id: UUID,
    ) -> None:
        """Test retrieving an existing artifact."""
        artifact_id = uuid4()
        mock_artifact = make_mock_artifact(artifact_id=artifact_id, tenant_id=tenant_id)

        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(mock_artifact))

        found = await artifact_service.get_artifact(artifact_id)

        assert found is not None
        assert found.id == artifact_id

    @pytest.mark.asyncio
    async def test_get_artifact_not_found(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test retrieving a non-existent artifact."""
        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(None))

        result = await artifact_service.get_artifact(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_artifact_tenant_isolation(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test that artifacts are isolated by tenant."""
        artifact_id = uuid4()
        # Artifact exists but for different tenant
        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(None))

        result = await artifact_service.get_artifact(artifact_id)

        assert result is None


# =============================================================================
# Commit Tests
# =============================================================================


class TestCommitArtifact:
    """Tests for artifact commit operations."""

    @pytest.mark.asyncio
    async def test_commit_artifact_success(
        self,
        artifact_service: ArtifactService,
        tenant_id: UUID,
    ) -> None:
        """Test successfully committing an artifact."""
        artifact_id = uuid4()
        mock_artifact = make_mock_artifact(
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            is_committed=False,
        )

        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(mock_artifact))
        artifact_service.db.commit = AsyncMock()

        resource_id = uuid4()
        with patch.object(artifact_service, "_commit_strategy", return_value=resource_id):
            result = await artifact_service.commit_artifact(artifact_id)

        assert result is not None
        assert result["resource_type"] == "strategy"
        assert result["resource_id"] == resource_id
        assert mock_artifact.is_committed is True
        assert mock_artifact.committed_resource_id == resource_id

    @pytest.mark.asyncio
    async def test_commit_artifact_with_overrides(
        self,
        artifact_service: ArtifactService,
        tenant_id: UUID,
    ) -> None:
        """Test committing with name/description overrides."""
        artifact_id = uuid4()
        mock_artifact = make_mock_artifact(
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            name="Original Name",
        )

        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(mock_artifact))
        artifact_service.db.commit = AsyncMock()

        resource_id = uuid4()
        with patch.object(
            artifact_service, "_commit_strategy", return_value=resource_id
        ) as mock_commit:
            await artifact_service.commit_artifact(
                artifact_id,
                overrides={"name": "New Name", "description": "New description"},
            )

        # Verify the commit was called with overridden data
        call_args = mock_commit.call_args[0][0]
        assert call_args["name"] == "New Name"
        assert call_args["description"] == "New description"

    @pytest.mark.asyncio
    async def test_commit_artifact_not_found(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test committing a non-existent artifact."""
        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(None))

        result = await artifact_service.commit_artifact(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_commit_artifact_already_committed(
        self,
        artifact_service: ArtifactService,
        tenant_id: UUID,
    ) -> None:
        """Test that already committed artifacts cannot be committed again."""
        artifact_id = uuid4()
        mock_artifact = make_mock_artifact(
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            is_committed=True,  # Already committed
            committed_resource_id=uuid4(),
        )

        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(mock_artifact))

        result = await artifact_service.commit_artifact(artifact_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_commit_artifact_strategy_creation_fails(
        self,
        artifact_service: ArtifactService,
        tenant_id: UUID,
    ) -> None:
        """Test handling when strategy creation fails."""
        artifact_id = uuid4()
        mock_artifact = make_mock_artifact(
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            is_committed=False,
        )

        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(mock_artifact))

        # Mock strategy client to return None (failure)
        with patch.object(artifact_service, "_commit_strategy", return_value=None):
            result = await artifact_service.commit_artifact(artifact_id)

        assert result is None
        assert mock_artifact.is_committed is False


class TestCommitStrategy:
    """Tests for the internal _commit_strategy method."""

    @pytest.mark.asyncio
    async def test_commit_strategy_calls_client(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test that _commit_strategy calls the strategy client correctly."""
        artifact_data = {
            "name": "Test Strategy",
            "dsl_code": '(strategy "Test")',
            "description": "Test description",
            "symbols": ["VTI", "BND"],
            "timeframe": "1D",
        }

        expected_id = uuid4()
        mock_client = MagicMock()
        mock_client.create_strategy = AsyncMock(return_value={"id": str(expected_id)})

        with patch(
            "src.tools.strategy_client.get_strategy_client",
            return_value=mock_client,
        ):
            result = await artifact_service._commit_strategy(artifact_data)

        assert result == expected_id
        mock_client.create_strategy.assert_called_once_with(
            tenant_id=artifact_service.tenant_id,
            user_id=artifact_service.user_id,
            name="Test Strategy",
            dsl_code='(strategy "Test")',
            description="Test description",
            symbols=["VTI", "BND"],
            timeframe="1D",
        )

    @pytest.mark.asyncio
    async def test_commit_strategy_handles_exception(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test that _commit_strategy handles exceptions gracefully."""
        artifact_data = {
            "name": "Test",
            "dsl_code": "(strategy)",
        }

        mock_client = MagicMock()
        mock_client.create_strategy = AsyncMock(side_effect=Exception("Network error"))

        with patch(
            "src.tools.strategy_client.get_strategy_client",
            return_value=mock_client,
        ):
            result = await artifact_service._commit_strategy(artifact_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_commit_strategy_handles_no_id(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test that _commit_strategy handles response with no ID."""
        artifact_data = {
            "name": "Test",
            "dsl_code": "(strategy)",
        }

        mock_client = MagicMock()
        mock_client.create_strategy = AsyncMock(return_value={})  # No id in response

        with patch(
            "src.tools.strategy_client.get_strategy_client",
            return_value=mock_client,
        ):
            result = await artifact_service._commit_strategy(artifact_data)

        assert result is None


# =============================================================================
# Deletion Tests
# =============================================================================


class TestDeleteArtifact:
    """Tests for artifact deletion."""

    @pytest.mark.asyncio
    async def test_delete_artifact_success(
        self,
        artifact_service: ArtifactService,
        tenant_id: UUID,
    ) -> None:
        """Test deleting an existing artifact."""
        artifact_id = uuid4()
        mock_artifact = make_mock_artifact(artifact_id=artifact_id, tenant_id=tenant_id)

        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(mock_artifact))
        artifact_service.db.delete = AsyncMock()
        artifact_service.db.commit = AsyncMock()

        result = await artifact_service.delete_artifact(artifact_id)

        assert result is True
        artifact_service.db.delete.assert_called_once_with(mock_artifact)

    @pytest.mark.asyncio
    async def test_delete_artifact_not_found(
        self,
        artifact_service: ArtifactService,
    ) -> None:
        """Test deleting a non-existent artifact."""
        artifact_service.db.execute = AsyncMock(return_value=mock_scalar_one_or_none(None))

        result = await artifact_service.delete_artifact(uuid4())

        assert result is False
