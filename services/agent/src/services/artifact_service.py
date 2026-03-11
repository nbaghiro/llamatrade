"""Artifact service for managing pending artifacts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import PendingArtifact
from llamatrade_proto.generated.agent_pb2 import ARTIFACT_TYPE_STRATEGY

logger = logging.getLogger(__name__)


class ArtifactService:
    """Service for managing pending artifacts.

    Artifacts are generated resources (like strategies) that are created
    by the agent but not yet committed to the actual resource tables.
    This allows users to review, modify, and approve before final creation.
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
    ) -> None:
        """Initialize the artifact service.

        Args:
            db: Async database session
            tenant_id: Current tenant UUID
            user_id: Current user UUID
        """
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    async def create_strategy_artifact(
        self,
        session_id: UUID,
        name: str,
        dsl_code: str,
        description: str | None = None,
        config_json: dict[str, Any] | None = None,
        symbols: list[str] | None = None,
        timeframe: str = "1D",
    ) -> PendingArtifact:
        """Create a pending strategy artifact.

        Args:
            session_id: Agent session UUID
            name: Strategy name
            dsl_code: Strategy DSL code
            description: Optional description
            config_json: Parsed JSON representation
            symbols: Extracted symbols
            timeframe: Strategy timeframe

        Returns:
            Created PendingArtifact
        """
        artifact_json = {
            "name": name,
            "description": description,
            "dsl_code": dsl_code,
            "config_json": config_json,
            "symbols": symbols or [],
            "timeframe": timeframe,
        }

        artifact = PendingArtifact(
            session_id=session_id,
            tenant_id=self.tenant_id,
            artifact_type=ARTIFACT_TYPE_STRATEGY,
            name=name,
            description=description,
            artifact_json=artifact_json,
            is_committed=False,
        )

        self.db.add(artifact)

        try:
            # Flush to get the ID assigned
            await self.db.flush()

            # Commit immediately to ensure artifact is persisted
            await self.db.commit()

            logger.info(
                "Created and committed pending strategy artifact: %s (session=%s, tenant=%s)",
                artifact.id,
                session_id,
                self.tenant_id,
            )
        except Exception as e:
            logger.exception("Failed to commit artifact: %s", e)
            await self.db.rollback()
            raise

        return artifact

    async def get_artifact(
        self,
        artifact_id: UUID,
    ) -> PendingArtifact | None:
        """Get an artifact by ID.

        Args:
            artifact_id: Artifact UUID

        Returns:
            PendingArtifact if found, None otherwise
        """
        logger.debug(
            "Looking up artifact: id=%s, tenant=%s",
            artifact_id,
            self.tenant_id,
        )
        stmt = select(PendingArtifact).where(
            (PendingArtifact.id == artifact_id) & (PendingArtifact.tenant_id == self.tenant_id)
        )
        result = await self.db.execute(stmt)
        artifact = result.scalar_one_or_none()
        if artifact is None:
            logger.warning(
                "Artifact not found: id=%s, tenant=%s",
                artifact_id,
                self.tenant_id,
            )
        return artifact

    async def commit_artifact(
        self,
        artifact_id: UUID,
        overrides: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Commit an artifact to create the actual resource.

        Args:
            artifact_id: Artifact UUID
            overrides: Optional overrides (e.g., name change)

        Returns:
            Dictionary with resource_id and resource_type, or None if not found
        """
        artifact = await self.get_artifact(artifact_id)
        if not artifact or artifact.is_committed:
            return None

        # Apply overrides to artifact data
        artifact_data = dict(artifact.artifact_json)
        if overrides:
            if "name" in overrides:
                artifact_data["name"] = overrides["name"]
            if "description" in overrides:
                artifact_data["description"] = overrides["description"]

        # Commit based on artifact type
        resource_id: UUID | None = None
        resource_type: str = ""

        if artifact.artifact_type == ARTIFACT_TYPE_STRATEGY:
            resource_id = await self._commit_strategy(artifact_data)
            resource_type = "strategy"
        else:
            logger.warning("Unknown artifact type: %s", artifact.artifact_type)
            return None

        if resource_id:
            # Mark artifact as committed
            artifact.is_committed = True
            artifact.committed_resource_id = resource_id
            artifact.committed_at = datetime.now(UTC)
            await self.db.commit()

            logger.info(
                "Committed artifact %s -> %s %s",
                artifact_id,
                resource_type,
                resource_id,
            )

            return {
                "resource_id": resource_id,
                "resource_type": resource_type,
            }

        return None

    async def _commit_strategy(
        self,
        artifact_data: dict[str, Any],
    ) -> UUID | None:
        """Commit a strategy artifact by creating the actual strategy.

        Args:
            artifact_data: Strategy artifact data

        Returns:
            Created strategy UUID, or None on failure
        """
        from src.tools.strategy_client import get_strategy_client

        try:
            client = get_strategy_client()

            result = await client.create_strategy(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                name=artifact_data.get("name", "Untitled Strategy"),
                dsl_code=artifact_data.get("dsl_code", ""),
                description=artifact_data.get("description"),
                symbols=artifact_data.get("symbols", []),
                timeframe=artifact_data.get("timeframe", "1D"),
            )

            if result and "id" in result:
                return UUID(result["id"])

            logger.warning("Strategy creation returned no ID")
            return None

        except Exception as e:
            logger.exception("Failed to commit strategy: %s", e)
            return None

    async def delete_artifact(
        self,
        artifact_id: UUID,
    ) -> bool:
        """Delete a pending artifact.

        Args:
            artifact_id: Artifact UUID

        Returns:
            True if deleted, False if not found
        """
        artifact = await self.get_artifact(artifact_id)
        if not artifact:
            return False

        await self.db.delete(artifact)
        await self.db.commit()
        return True
