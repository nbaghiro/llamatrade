"""Strategy service - CRUD operations with S-expression DSL support."""

from uuid import UUID

from fastapi import Depends
from llamatrade_db import get_db
from llamatrade_db.models.strategy import (
    DeploymentEnvironment as DBDeploymentEnvironment,
)
from llamatrade_db.models.strategy import (
    DeploymentStatus as DBDeploymentStatus,
)
from llamatrade_db.models.strategy import (
    Strategy,
    StrategyDeployment,
    StrategyVersion,
)
from llamatrade_db.models.strategy import (
    StrategyStatus as DBStrategyStatus,
)
from llamatrade_db.models.strategy import (
    StrategyType as DBStrategyType,
)
from llamatrade_dsl import parse_strategy, to_json, validate_strategy
from llamatrade_dsl.parser import ParseError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    DeploymentCreate,
    DeploymentResponse,
    DeploymentStatus,
    StrategyCreate,
    StrategyDetailResponse,
    StrategyResponse,
    StrategyStatus,
    StrategyType,
    StrategyUpdate,
    StrategyVersionResponse,
    ValidationResult,
)


class StrategyService:
    """Service for strategy management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_strategy(
        self,
        tenant_id: UUID,
        user_id: UUID,
        data: StrategyCreate,
    ) -> StrategyDetailResponse:
        """
        Create a new strategy with S-expression configuration.

        Parses and validates the S-expression, creates the strategy record,
        and creates the initial version (v1).
        """
        # Parse and validate S-expression
        try:
            ast = parse_strategy(data.config_sexpr)
        except ParseError as e:
            raise ValueError(f"Invalid strategy: {e}")

        validation = validate_strategy(ast)
        if not validation.valid:
            error_messages = [str(e) for e in validation.errors]
            raise ValueError(f"Invalid strategy: {'; '.join(error_messages)}")

        # Map strategy type
        db_type = DBStrategyType(ast.strategy_type)

        # Create strategy record
        strategy = Strategy(
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            strategy_type=db_type,
            status=DBStrategyStatus.DRAFT,
            current_version=1,
            created_by=user_id,
        )
        self.db.add(strategy)
        await self.db.flush()  # Get ID before creating version

        # Create version 1
        config_json = to_json(ast)
        version = StrategyVersion(
            strategy_id=strategy.id,
            version=1,
            config_sexpr=data.config_sexpr,
            config_json=config_json,
            symbols=ast.symbols,
            timeframe=ast.timeframe,
            created_by=user_id,
        )
        self.db.add(version)
        await self.db.commit()
        await self.db.refresh(strategy)

        return self._to_detail_response(strategy, version)

    async def get_strategy(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> StrategyDetailResponse | None:
        """Get a strategy with its current version configuration."""
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id)
        if not strategy:
            return None

        version = await self._get_version(strategy.id, strategy.current_version)
        if not version:
            return None

        return self._to_detail_response(strategy, version)

    async def list_strategies(
        self,
        tenant_id: UUID,
        status: StrategyStatus | None = None,
        strategy_type: StrategyType | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StrategyResponse], int]:
        """List strategies for a tenant with optional filtering."""
        # Build query
        stmt = select(Strategy).where(Strategy.tenant_id == tenant_id)

        if status:
            stmt = stmt.where(Strategy.status == DBStrategyStatus(status.value))
        if strategy_type:
            stmt = stmt.where(Strategy.strategy_type == DBStrategyType(strategy_type.value))

        # Exclude archived by default
        if not status:
            stmt = stmt.where(Strategy.status != DBStrategyStatus.ARCHIVED)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # Paginate and order
        stmt = stmt.order_by(Strategy.updated_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        strategies = result.scalars().all()

        return [self._to_response(s) for s in strategies], total

    async def update_strategy(
        self,
        tenant_id: UUID,
        user_id: UUID,
        strategy_id: UUID,
        data: StrategyUpdate,
    ) -> StrategyDetailResponse | None:
        """
        Update a strategy.

        If config_sexpr is provided, creates a new version.
        Otherwise, only updates metadata fields.
        """
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id)
        if not strategy:
            return None

        # Update metadata
        if data.name is not None:
            strategy.name = data.name
        if data.description is not None:
            strategy.description = data.description
        if data.status is not None:
            strategy.status = DBStrategyStatus(data.status.value)

        # If config changed, create new version
        if data.config_sexpr is not None:
            try:
                ast = parse_strategy(data.config_sexpr)
            except ParseError as e:
                raise ValueError(f"Invalid strategy: {e}")
            validation = validate_strategy(ast)
            if not validation.valid:
                error_messages = [str(e) for e in validation.errors]
                raise ValueError(f"Invalid strategy: {'; '.join(error_messages)}")

            new_version_num = strategy.current_version + 1
            config_json = to_json(ast)

            version = StrategyVersion(
                strategy_id=strategy.id,
                version=new_version_num,
                config_sexpr=data.config_sexpr,
                config_json=config_json,
                symbols=ast.symbols,
                timeframe=ast.timeframe,
                created_by=user_id,
            )
            self.db.add(version)
            strategy.current_version = new_version_num

        await self.db.commit()
        await self.db.refresh(strategy)

        current_version = await self._get_version(strategy.id, strategy.current_version)
        return self._to_detail_response(strategy, current_version)

    async def delete_strategy(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> bool:
        """Soft delete (archive) a strategy."""
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id)
        if not strategy:
            return False

        strategy.status = DBStrategyStatus.ARCHIVED
        await self.db.commit()
        return True

    async def activate_strategy(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> StrategyResponse | None:
        """Set strategy status to ACTIVE."""
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id)
        if not strategy:
            return None

        strategy.status = DBStrategyStatus.ACTIVE
        await self.db.commit()
        await self.db.refresh(strategy)
        return self._to_response(strategy)

    async def pause_strategy(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> StrategyResponse | None:
        """Set strategy status to PAUSED."""
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id)
        if not strategy:
            return None

        strategy.status = DBStrategyStatus.PAUSED
        await self.db.commit()
        await self.db.refresh(strategy)
        return self._to_response(strategy)

    async def list_versions(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> list[StrategyVersionResponse]:
        """List all versions of a strategy."""
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id)
        if not strategy:
            return []

        stmt = (
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .order_by(StrategyVersion.version.desc())
        )
        result = await self.db.execute(stmt)
        versions = result.scalars().all()

        return [self._to_version_response(v) for v in versions]

    async def get_version(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
        version: int,
    ) -> StrategyVersionResponse | None:
        """Get a specific version of a strategy."""
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id)
        if not strategy:
            return None

        v = await self._get_version(strategy_id, version)
        return self._to_version_response(v) if v else None

    async def clone_strategy(
        self,
        tenant_id: UUID,
        user_id: UUID,
        strategy_id: UUID,
        new_name: str,
    ) -> StrategyDetailResponse | None:
        """Clone a strategy with a new name."""
        original = await self.get_strategy(tenant_id, strategy_id)
        if not original:
            return None

        return await self.create_strategy(
            tenant_id=tenant_id,
            user_id=user_id,
            data=StrategyCreate(
                name=new_name,
                description=f"Cloned from: {original.name}",
                config_sexpr=original.config_sexpr,
            ),
        )

    async def validate_config(
        self,
        config_sexpr: str,
    ) -> ValidationResult:
        """Validate a strategy configuration without saving."""
        try:
            ast = parse_strategy(config_sexpr)
            validation = validate_strategy(ast)

            errors = [str(e) for e in validation.errors]
            warnings: list[str] = []

            # Add additional warnings
            if ast.risk.get("stop_loss_pct") and ast.risk["stop_loss_pct"] > 10:
                warnings.append("Stop loss exceeds 10% - consider reducing for risk management")

            if len(ast.symbols) > 20:
                warnings.append("Trading more than 20 symbols may impact execution speed")

            return ValidationResult(
                valid=validation.valid,
                errors=errors,
                warnings=warnings,
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors=[str(e)],
                warnings=[],
            )

    # ===================
    # Deployment methods
    # ===================

    async def create_deployment(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
        data: DeploymentCreate,
    ) -> DeploymentResponse | None:
        """Create a new deployment for a strategy."""
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id)
        if not strategy:
            return None

        version = data.version or strategy.current_version

        # Verify version exists
        v = await self._get_version(strategy_id, version)
        if not v:
            raise ValueError(f"Version {version} not found")

        deployment = StrategyDeployment(
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            version=version,
            environment=DBDeploymentEnvironment(data.environment.value),
            status=DBDeploymentStatus.PENDING,
            config_override=data.config_override,
        )
        self.db.add(deployment)
        await self.db.commit()
        await self.db.refresh(deployment)

        return self._to_deployment_response(deployment)

    async def list_deployments(
        self,
        tenant_id: UUID,
        strategy_id: UUID | None = None,
        status: DeploymentStatus | None = None,
    ) -> list[DeploymentResponse]:
        """List deployments for a tenant."""
        stmt = select(StrategyDeployment).where(StrategyDeployment.tenant_id == tenant_id)

        if strategy_id:
            stmt = stmt.where(StrategyDeployment.strategy_id == strategy_id)
        if status:
            stmt = stmt.where(StrategyDeployment.status == DBDeploymentStatus(status.value))

        stmt = stmt.order_by(StrategyDeployment.created_at.desc())
        result = await self.db.execute(stmt)
        deployments = result.scalars().all()

        return [self._to_deployment_response(d) for d in deployments]

    # ===================
    # Private helpers
    # ===================

    async def _get_strategy_by_id(self, tenant_id: UUID, strategy_id: UUID) -> Strategy | None:
        """Get strategy ensuring tenant isolation."""
        stmt = (
            select(Strategy)
            .where(Strategy.id == strategy_id)
            .where(Strategy.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_version(self, strategy_id: UUID, version: int) -> StrategyVersion | None:
        """Get a specific version."""
        stmt = (
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy_id)
            .where(StrategyVersion.version == version)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _to_response(self, s: Strategy) -> StrategyResponse:
        """Convert DB model to response schema."""
        return StrategyResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            strategy_type=StrategyType(s.strategy_type.value),
            status=StrategyStatus(s.status.value),
            current_version=s.current_version,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )

    def _to_detail_response(self, s: Strategy, v: StrategyVersion) -> StrategyDetailResponse:
        """Convert DB models to detailed response schema."""
        return StrategyDetailResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            strategy_type=StrategyType(s.strategy_type.value),
            status=StrategyStatus(s.status.value),
            current_version=s.current_version,
            created_at=s.created_at,
            updated_at=s.updated_at,
            config_sexpr=v.config_sexpr,
            config_json=v.config_json,
            symbols=v.symbols,
            timeframe=v.timeframe,
        )

    def _to_version_response(self, v: StrategyVersion) -> StrategyVersionResponse:
        """Convert version model to response schema."""
        return StrategyVersionResponse(
            version=v.version,
            config_sexpr=v.config_sexpr,
            config_json=v.config_json,
            symbols=v.symbols,
            timeframe=v.timeframe,
            changelog=v.changelog,
            created_at=v.created_at,
        )

    def _to_deployment_response(self, d: StrategyDeployment) -> DeploymentResponse:
        """Convert deployment model to response schema."""
        return DeploymentResponse(
            id=d.id,
            strategy_id=d.strategy_id,
            version=d.version,
            environment=d.environment.value,
            status=DeploymentStatus(d.status.value),
            started_at=d.started_at,
            stopped_at=d.stopped_at,
            config_override=d.config_override,
            error_message=d.error_message,
            created_at=d.created_at,
        )


async def get_strategy_service(
    db: AsyncSession = Depends(get_db),
) -> StrategyService:
    """Dependency to get strategy service."""
    return StrategyService(db)
