"""Strategy Connect servicer implementation."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from typing import Any

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade.v1 import common_pb2, strategy_pb2

from src.models import (
    StrategyDetailResponse,
    StrategyResponse,
    StrategyStatus,
    StrategyType,
    StrategyVersionResponse,
)
from src.services.database import get_session_maker

logger = logging.getLogger(__name__)


class StrategyServicer:
    """Connect servicer for the Strategy service.

    Implements the StrategyService Protocol defined in strategy_connect.py.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: Any = None

    async def _get_db(self) -> AsyncSession:
        """Get a database session."""
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        session: AsyncSession = self._session_maker()
        return session

    async def get_strategy(
        self,
        request: strategy_pb2.GetStrategyRequest,
        ctx: Any,
    ) -> strategy_pb2.GetStrategyResponse:
        """Get a strategy by ID."""
        from src.services.strategy_service import StrategyService

        tenant_id = UUID(request.context.tenant_id)
        strategy_id = UUID(request.strategy_id)

        async with await self._get_db() as db:
            service = StrategyService(db)

            # Get specific version if requested, otherwise current
            if request.version > 0:
                version = await service.get_version(tenant_id, strategy_id, request.version)
                if not version:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Strategy version {request.version} not found",
                    )
                strategy = await service.get_strategy(tenant_id, strategy_id)
            else:
                strategy = await service.get_strategy(tenant_id, strategy_id)

            if not strategy:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy not found: {request.strategy_id}",
                )

            return strategy_pb2.GetStrategyResponse(
                strategy=self._to_proto_strategy(strategy),
            )

    async def list_strategies(
        self,
        request: strategy_pb2.ListStrategiesRequest,
        ctx: Any,
    ) -> strategy_pb2.ListStrategiesResponse:
        """List strategies for a tenant."""
        from src.services.strategy_service import StrategyService

        tenant_id = UUID(request.context.tenant_id)

        # Map status filters
        status = None
        if request.statuses:
            status = self._from_proto_status(request.statuses[0])

        # Map type filters
        strategy_type = None
        if request.types:
            strategy_type = self._from_proto_type(request.types[0])

        page = request.pagination.page if request.HasField("pagination") else 1
        page_size = request.pagination.page_size if request.HasField("pagination") else 20

        async with await self._get_db() as db:
            service = StrategyService(db)
            strategies, total = await service.list_strategies(
                tenant_id=tenant_id,
                status=status,
                strategy_type=strategy_type,
                page=page,
                page_size=page_size,
            )

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return strategy_pb2.ListStrategiesResponse(
                strategies=[self._to_proto_strategy_summary(s) for s in strategies],
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=page,
                    page_size=page_size,
                    has_next=page < total_pages,
                    has_previous=page > 1,
                ),
            )

    async def create_strategy(
        self,
        request: strategy_pb2.CreateStrategyRequest,
        ctx: Any,
    ) -> strategy_pb2.CreateStrategyResponse:
        """Create a new strategy."""
        from src.models import StrategyCreate
        from src.services.strategy_service import StrategyService

        tenant_id = UUID(request.context.tenant_id)
        user_id = UUID(request.context.user_id)

        # Map proto to internal create model
        create_data = StrategyCreate(
            name=request.name,
            description=request.description or None,
            config_sexpr=request.dsl_code,  # Map dsl_code to config_sexpr
        )

        try:
            async with await self._get_db() as db:
                service = StrategyService(db)
                strategy = await service.create_strategy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    data=create_data,
                )

                return strategy_pb2.CreateStrategyResponse(
                    strategy=self._to_proto_strategy(strategy),
                )
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def update_strategy(
        self,
        request: strategy_pb2.UpdateStrategyRequest,
        ctx: Any,
    ) -> strategy_pb2.UpdateStrategyResponse:
        """Update an existing strategy."""
        from src.models import StrategyUpdate
        from src.services.strategy_service import StrategyService

        tenant_id = UUID(request.context.tenant_id)
        user_id = UUID(request.context.user_id)
        strategy_id = UUID(request.strategy_id)

        # Build update data
        update_data = StrategyUpdate(
            name=request.name if request.name else None,
            description=request.description if request.description else None,
            config_sexpr=request.dsl_code if request.dsl_code else None,
        )

        try:
            async with await self._get_db() as db:
                service = StrategyService(db)
                strategy = await service.update_strategy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    data=update_data,
                )

                if not strategy:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Strategy not found: {request.strategy_id}",
                    )

                return strategy_pb2.UpdateStrategyResponse(
                    strategy=self._to_proto_strategy(strategy),
                )
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def delete_strategy(
        self,
        request: strategy_pb2.DeleteStrategyRequest,
        ctx: Any,
    ) -> strategy_pb2.DeleteStrategyResponse:
        """Delete (archive) a strategy."""
        from src.services.strategy_service import StrategyService

        tenant_id = UUID(request.context.tenant_id)
        strategy_id = UUID(request.strategy_id)

        async with await self._get_db() as db:
            service = StrategyService(db)
            success = await service.delete_strategy(tenant_id, strategy_id)

            if not success:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy not found: {request.strategy_id}",
                )

            return strategy_pb2.DeleteStrategyResponse(success=True)

    async def compile_strategy(
        self,
        request: strategy_pb2.CompileStrategyRequest,
        ctx: Any,
    ) -> strategy_pb2.CompileStrategyResponse:
        """Compile/validate DSL code."""
        from src.services.strategy_service import StrategyService

        async with await self._get_db() as db:
            service = StrategyService(db)
            validation = await service.validate_config(request.dsl_code)

            # If valid, try to compile to JSON
            compiled_json_str = ""
            if validation.valid:
                from llamatrade_dsl import parse_strategy, to_json

                try:
                    ast = parse_strategy(request.dsl_code)
                    compiled_json_str = json.dumps(to_json(ast))
                except Exception:
                    pass

            # Build the result
            result = strategy_pb2.CompilationResult(
                success=bool(validation.valid),
                compiled_json=compiled_json_str,
            )

            # Add errors one by one
            for e in validation.errors:
                result.errors.append(
                    strategy_pb2.CompilationError(
                        line=0,
                        column=0,
                        message=str(e),
                        code="VALIDATION_ERROR",
                    )
                )

            # Add warnings one by one
            for w in validation.warnings:
                result.warnings.append(
                    strategy_pb2.CompilationWarning(
                        line=0,
                        column=0,
                        message=str(w),
                        code="WARNING",
                    )
                )

            return strategy_pb2.CompileStrategyResponse(result=result)

    async def validate_strategy(
        self,
        request: strategy_pb2.ValidateStrategyRequest,
        ctx: Any,
    ) -> strategy_pb2.ValidateStrategyResponse:
        """Validate an existing strategy."""
        from src.services.strategy_service import StrategyService

        tenant_id = UUID(request.context.tenant_id)
        strategy_id = UUID(request.strategy_id)

        async with await self._get_db() as db:
            service = StrategyService(db)
            strategy = await service.get_strategy(tenant_id, strategy_id)

            if not strategy:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy not found: {request.strategy_id}",
                )

            # Validate the strategy's config
            validation = await service.validate_config(strategy.config_sexpr)

            errors = [
                strategy_pb2.CompilationError(
                    line=0,
                    column=0,
                    message=e,
                    code="VALIDATION_ERROR",
                )
                for e in validation.errors
            ]

            warnings = [
                strategy_pb2.CompilationWarning(
                    line=0,
                    column=0,
                    message=w,
                    code="WARNING",
                )
                for w in validation.warnings
            ]

            return strategy_pb2.ValidateStrategyResponse(
                result=strategy_pb2.ValidationResult(
                    valid=validation.valid,
                    errors=errors,
                    warnings=warnings,
                    detected_symbols=strategy.symbols,
                    detected_indicators=[],
                ),
            )

    async def list_strategy_versions(
        self,
        request: strategy_pb2.ListStrategyVersionsRequest,
        ctx: Any,
    ) -> strategy_pb2.ListStrategyVersionsResponse:
        """List versions of a strategy."""
        from src.services.strategy_service import StrategyService

        tenant_id = UUID(request.context.tenant_id)
        strategy_id = UUID(request.strategy_id)

        page = request.pagination.page if request.HasField("pagination") else 1
        page_size = request.pagination.page_size if request.HasField("pagination") else 20

        async with await self._get_db() as db:
            service = StrategyService(db)
            versions = await service.list_versions(tenant_id, strategy_id)

            # Manual pagination since service returns all
            total = len(versions)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = versions[start:end]

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return strategy_pb2.ListStrategyVersionsResponse(
                versions=[self._to_proto_version(v, strategy_id) for v in paginated],
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=page,
                    page_size=page_size,
                    has_next=page < total_pages,
                    has_previous=page > 1,
                ),
            )

    async def update_strategy_status(
        self,
        request: strategy_pb2.UpdateStrategyStatusRequest,
        ctx: Any,
    ) -> strategy_pb2.UpdateStrategyStatusResponse:
        """Update strategy status."""
        from src.models import StrategyUpdate
        from src.services.strategy_service import StrategyService

        tenant_id = UUID(request.context.tenant_id)
        strategy_id = UUID(request.strategy_id)

        status = self._from_proto_status(request.status)

        async with await self._get_db() as db:
            service = StrategyService(db)

            # Use appropriate method based on status
            if status == StrategyStatus.ACTIVE:
                strategy = await service.activate_strategy(tenant_id, strategy_id)
            elif status == StrategyStatus.PAUSED:
                strategy = await service.pause_strategy(tenant_id, strategy_id)
            elif status == StrategyStatus.ARCHIVED:
                await service.delete_strategy(tenant_id, strategy_id)
                strategy = await service.get_strategy(tenant_id, strategy_id)
            else:
                # For other statuses, use update
                strategy = await service.update_strategy(
                    tenant_id=tenant_id,
                    user_id=UUID(request.context.user_id),
                    strategy_id=strategy_id,
                    data=StrategyUpdate(status=status),
                )

            if not strategy:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy not found: {request.strategy_id}",
                )

            # Get full strategy for response
            full_strategy = await service.get_strategy(tenant_id, strategy_id)

            return strategy_pb2.UpdateStrategyStatusResponse(
                strategy=self._to_proto_strategy(full_strategy) if full_strategy else None,
            )

    # ===================
    # Helper methods
    # ===================

    def _to_proto_strategy(self, strategy: StrategyDetailResponse) -> strategy_pb2.Strategy:
        """Convert internal strategy to proto Strategy."""
        config_json_str = ""
        if strategy.config_json:
            config_json_str = json.dumps(strategy.config_json)

        return strategy_pb2.Strategy(
            id=str(strategy.id),
            tenant_id="",  # Not included in response
            name=strategy.name,
            description=strategy.description or "",
            type=self._to_proto_type(strategy.strategy_type),
            status=self._to_proto_status(strategy.status),
            version=strategy.current_version,
            dsl_code=strategy.config_sexpr,
            compiled_json=config_json_str,
            symbols=strategy.symbols,
            timeframe=strategy.timeframe,
            created_at=common_pb2.Timestamp(seconds=int(strategy.created_at.timestamp())),
            updated_at=common_pb2.Timestamp(seconds=int(strategy.updated_at.timestamp())),
        )

    def _to_proto_strategy_summary(self, strategy: StrategyResponse) -> strategy_pb2.Strategy:
        """Convert internal strategy summary to proto Strategy."""
        return strategy_pb2.Strategy(
            id=str(strategy.id),
            tenant_id="",
            name=strategy.name,
            description=strategy.description or "",
            type=self._to_proto_type(strategy.strategy_type),
            status=self._to_proto_status(strategy.status),
            version=strategy.current_version,
            created_at=common_pb2.Timestamp(seconds=int(strategy.created_at.timestamp())),
            updated_at=common_pb2.Timestamp(seconds=int(strategy.updated_at.timestamp())),
        )

    def _to_proto_version(
        self, version: StrategyVersionResponse, strategy_id: UUID
    ) -> strategy_pb2.StrategyVersion:
        """Convert internal version to proto StrategyVersion."""
        config_json_str = ""
        if version.config_json:
            config_json_str = json.dumps(version.config_json)

        return strategy_pb2.StrategyVersion(
            strategy_id=str(strategy_id),
            version=version.version,
            dsl_code=version.config_sexpr,
            compiled_json=config_json_str,
            change_summary=version.changelog or "",
            created_at=common_pb2.Timestamp(seconds=int(version.created_at.timestamp())),
        )

    def _to_proto_status(self, status: StrategyStatus) -> int:
        """Convert internal status to proto enum value."""
        status_map: dict[StrategyStatus, int] = {
            StrategyStatus.DRAFT: int(strategy_pb2.STRATEGY_STATUS_DRAFT),
            StrategyStatus.ACTIVE: int(strategy_pb2.STRATEGY_STATUS_ACTIVE),
            StrategyStatus.PAUSED: int(strategy_pb2.STRATEGY_STATUS_PAUSED),
            StrategyStatus.ARCHIVED: int(strategy_pb2.STRATEGY_STATUS_ARCHIVED),
        }
        return status_map.get(status, int(strategy_pb2.STRATEGY_STATUS_UNSPECIFIED))

    def _from_proto_status(self, status: int) -> StrategyStatus | None:
        """Convert proto status enum to internal status."""
        status_map = {
            strategy_pb2.STRATEGY_STATUS_DRAFT: StrategyStatus.DRAFT,
            strategy_pb2.STRATEGY_STATUS_ACTIVE: StrategyStatus.ACTIVE,
            strategy_pb2.STRATEGY_STATUS_PAUSED: StrategyStatus.PAUSED,
            strategy_pb2.STRATEGY_STATUS_ARCHIVED: StrategyStatus.ARCHIVED,
        }
        return status_map.get(status)

    def _to_proto_type(self, stype: StrategyType) -> int:
        """Convert internal strategy type to proto enum value."""
        # Default to DSL since all strategies are S-expression based
        return int(strategy_pb2.STRATEGY_TYPE_DSL)

    def _from_proto_type(self, stype: int) -> StrategyType | None:
        """Convert proto type enum to internal type."""
        # Since proto types don't map directly, return None to not filter
        return None
