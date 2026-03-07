"""Strategy Connect servicer implementation."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Type alias for generic request context (accepts any request/response types)
type AnyContext = RequestContext[object, object]

from llamatrade_proto.generated import common_pb2, strategy_pb2
from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_PAPER
from llamatrade_proto.generated.strategy_pb2 import (
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_ARCHIVED,
    STRATEGY_STATUS_PAUSED,
)

from src.models import (
    ExecutionResponse,
    StrategyDetailResponse,
    StrategyResponse,
    StrategyVersionResponse,
)
from src.services.database import get_session_maker

logger = logging.getLogger(__name__)

# Nil UUID used to detect missing/invalid context
_NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")


def _validate_tenant_context(context: common_pb2.TenantContext) -> tuple[UUID, UUID]:
    """Validate and extract tenant_id and user_id from context.

    Raises:
        ConnectError: If context is invalid (empty or nil UUIDs)
    """
    if not context.tenant_id or not context.user_id:
        raise ConnectError(
            Code.UNAUTHENTICATED,
            "Valid tenant context is required",
        )

    try:
        tenant_id = UUID(context.tenant_id)
        user_id = UUID(context.user_id)
    except ValueError as e:
        raise ConnectError(
            Code.INVALID_ARGUMENT,
            f"Invalid UUID in context: {e}",
        )

    if tenant_id == _NIL_UUID or user_id == _NIL_UUID:
        raise ConnectError(
            Code.UNAUTHENTICATED,
            "Valid tenant context is required (nil UUID not allowed)",
        )

    return tenant_id, user_id


class StrategyServicer:
    """Connect servicer for the Strategy service.

    Implements the StrategyService Protocol defined in strategy_connect.py.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    async def _get_db(self) -> AsyncSession:
        """Get a database session."""
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        assert self._session_maker is not None
        session: AsyncSession = self._session_maker()
        return session

    async def get_strategy(
        self,
        request: strategy_pb2.GetStrategyRequest,
        ctx: AnyContext,
    ) -> strategy_pb2.GetStrategyResponse:
        """Get a strategy by ID."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
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
        ctx: AnyContext,
    ) -> strategy_pb2.ListStrategiesResponse:
        """List strategies for a tenant with filtering, search, and sort."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)

        # Map status filters - pass proto int value directly
        status = request.statuses[0] if request.statuses else None

        # Extract search term
        search = request.search if request.search else None

        # Extract sort parameters
        sort_field = None
        sort_direction = None
        if request.HasField("sort"):
            sort_field = request.sort.field if request.sort.field else None
            # Map proto enum to string
            if request.sort.direction == common_pb2.SORT_DIRECTION_ASC:
                sort_direction = "asc"
            elif request.sort.direction == common_pb2.SORT_DIRECTION_DESC:
                sort_direction = "desc"

        page = request.pagination.page if request.HasField("pagination") else 1
        page_size = request.pagination.page_size if request.HasField("pagination") else 20

        async with await self._get_db() as db:
            service = StrategyService(db)
            strategies, total = await service.list_strategies(
                tenant_id=tenant_id,
                status=status,
                search=search,
                sort_field=sort_field,
                sort_direction=sort_direction,
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
        ctx: AnyContext,
    ) -> strategy_pb2.CreateStrategyResponse:
        """Create a new strategy.

        Supports two creation modes:
        1. From DSL code: provide dsl_code field
        2. From template: provide template_id field (optionally with template_params)
        """
        from src.models import StrategyCreate
        from src.services.strategy_service import StrategyService

        tenant_id, user_id = _validate_tenant_context(request.context)

        try:
            async with await self._get_db() as db:
                service = StrategyService(db)

                # Check if creating from template
                if request.template_id:
                    template_params = (
                        dict(request.template_params) if request.template_params else None
                    )
                    strategy = await service.create_from_template(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        template_id=request.template_id,
                        name=request.name if request.name else None,
                        description=request.description if request.description else None,
                        template_params=template_params,
                    )
                else:
                    # Create from DSL code
                    parameters = dict(request.parameters) if request.parameters else None
                    create_data = StrategyCreate(
                        name=request.name,
                        description=request.description or None,
                        config_sexpr=request.dsl_code,
                        parameters=parameters,
                    )
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
        ctx: AnyContext,
    ) -> strategy_pb2.UpdateStrategyResponse:
        """Update an existing strategy."""
        from src.models import StrategyUpdate
        from src.services.strategy_service import StrategyService

        tenant_id, user_id = _validate_tenant_context(request.context)
        strategy_id = UUID(request.strategy_id)

        # Build update data
        # Convert proto map to dict
        parameters = dict(request.parameters) if request.parameters else None
        update_data = StrategyUpdate(
            name=request.name if request.name else None,
            description=request.description if request.description else None,
            config_sexpr=request.dsl_code if request.dsl_code else None,
            parameters=parameters,
            changelog=request.change_summary if request.change_summary else None,
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
        ctx: AnyContext,
    ) -> strategy_pb2.DeleteStrategyResponse:
        """Delete (archive) a strategy."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
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
        ctx: AnyContext,
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
        ctx: AnyContext,
    ) -> strategy_pb2.ValidateStrategyResponse:
        """Validate an existing strategy."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
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
                    detected_symbols=validation.detected_symbols,
                    detected_indicators=validation.detected_indicators,
                ),
            )

    async def list_strategy_versions(
        self,
        request: strategy_pb2.ListStrategyVersionsRequest,
        ctx: AnyContext,
    ) -> strategy_pb2.ListStrategyVersionsResponse:
        """List versions of a strategy."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
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
        ctx: AnyContext,
    ) -> strategy_pb2.UpdateStrategyStatusResponse:
        """Update strategy status.

        Status transitions are validated:
        - DRAFT → ACTIVE (allowed)
        - ACTIVE ↔ PAUSED (allowed)
        - Any → ARCHIVED (allowed)
        - All other transitions are rejected
        """
        from src.models import StrategyUpdate
        from src.services.strategy_service import StrategyService

        tenant_id, user_id = _validate_tenant_context(request.context)
        strategy_id = UUID(request.strategy_id)

        # Use proto int value directly
        status = request.status

        try:
            async with await self._get_db() as db:
                service = StrategyService(db)

                # Use appropriate method based on status
                if status == STRATEGY_STATUS_ACTIVE:
                    strategy = await service.activate_strategy(tenant_id, strategy_id)
                elif status == STRATEGY_STATUS_PAUSED:
                    strategy = await service.pause_strategy(tenant_id, strategy_id)
                elif status == STRATEGY_STATUS_ARCHIVED:
                    await service.delete_strategy(tenant_id, strategy_id)
                    strategy = await service.get_strategy(tenant_id, strategy_id)
                else:
                    # For other statuses, use update
                    strategy = await service.update_strategy(
                        tenant_id=tenant_id,
                        user_id=user_id,
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
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def clone_strategy(
        self,
        request: strategy_pb2.CloneStrategyRequest,
        ctx: AnyContext,
    ) -> strategy_pb2.CloneStrategyResponse:
        """Clone a strategy with a new name."""
        from src.services.strategy_service import StrategyService

        tenant_id, user_id = _validate_tenant_context(request.context)
        strategy_id = UUID(request.strategy_id)

        if not request.new_name:
            raise ConnectError(Code.INVALID_ARGUMENT, "new_name is required")

        async with await self._get_db() as db:
            service = StrategyService(db)

            # If specific version requested, get that version first
            if request.version > 0:
                version = await service.get_version(tenant_id, strategy_id, request.version)
                if not version:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Strategy version {request.version} not found",
                    )
                # Create from the specific version's config
                from src.models import StrategyCreate

                strategy = await service.create_strategy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    data=StrategyCreate(
                        name=request.new_name,
                        description=f"Cloned from version {request.version}",
                        config_sexpr=version.config_sexpr,
                        parameters=version.parameters,
                    ),
                )
            else:
                # Clone current version
                strategy = await service.clone_strategy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    new_name=request.new_name,
                )

            if not strategy:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy not found: {request.strategy_id}",
                )

            return strategy_pb2.CloneStrategyResponse(
                strategy=self._to_proto_strategy(strategy),
            )

    async def create_execution(
        self,
        request: strategy_pb2.CreateExecutionRequest,
        ctx: AnyContext,
    ) -> strategy_pb2.CreateExecutionResponse:
        """Create a new execution for a strategy."""
        from src.models import ExecutionCreate
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        strategy_id = UUID(request.strategy_id)

        # Use proto mode directly (int), default to PAPER
        mode = request.mode if request.mode > 0 else EXECUTION_MODE_PAPER

        # Build config override from proto map
        config_override = dict(request.config_override) if request.config_override else None

        create_data = ExecutionCreate(
            version=request.version if request.version > 0 else None,
            mode=mode,
            config_override=config_override,  # type: ignore[arg-type]
        )

        try:
            async with await self._get_db() as db:
                service = StrategyService(db)
                execution = await service.create_execution(
                    tenant_id=tenant_id,
                    strategy_id=strategy_id,
                    data=create_data,
                )

                if not execution:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Strategy not found: {request.strategy_id}",
                    )

                return strategy_pb2.CreateExecutionResponse(
                    execution=self._to_proto_execution(execution),
                )
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def get_execution(
        self,
        request: strategy_pb2.GetExecutionRequest,
        ctx: AnyContext,
    ) -> strategy_pb2.GetExecutionResponse:
        """Get an execution by ID."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        execution_id = UUID(request.execution_id)

        async with await self._get_db() as db:
            service = StrategyService(db)
            execution = await service.get_execution(tenant_id, execution_id)

            if not execution:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Execution not found: {request.execution_id}",
                )

            return strategy_pb2.GetExecutionResponse(
                execution=self._to_proto_execution(execution),
            )

    async def list_executions(
        self,
        request: strategy_pb2.ListExecutionsRequest,
        ctx: AnyContext,
    ) -> strategy_pb2.ListExecutionsResponse:
        """List executions with optional filters."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)

        # Map filters - pass proto int values directly
        strategy_id = UUID(request.strategy_id) if request.strategy_id else None
        status = request.statuses[0] if request.statuses else None
        mode = request.modes[0] if request.modes else None

        page = request.pagination.page if request.HasField("pagination") else 1
        page_size = request.pagination.page_size if request.HasField("pagination") else 20

        async with await self._get_db() as db:
            service = StrategyService(db)
            executions, total = await service.list_executions(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                status=status,
                mode=mode,
                page=page,
                page_size=page_size,
            )

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return strategy_pb2.ListExecutionsResponse(
                executions=[self._to_proto_execution(e) for e in executions],
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=page,
                    page_size=page_size,
                    has_next=page < total_pages,
                    has_previous=page > 1,
                ),
            )

    async def start_execution(
        self,
        request: strategy_pb2.StartExecutionRequest,
        ctx: AnyContext,
    ) -> strategy_pb2.StartExecutionResponse:
        """Start a pending execution."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        execution_id = UUID(request.execution_id)

        try:
            async with await self._get_db() as db:
                service = StrategyService(db)
                execution = await service.start_execution(tenant_id, execution_id)

                if not execution:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Execution not found: {request.execution_id}",
                    )

                return strategy_pb2.StartExecutionResponse(
                    execution=self._to_proto_execution(execution),
                )
        except ValueError as e:
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))

    async def pause_execution(
        self,
        request: strategy_pb2.PauseExecutionRequest,
        ctx: AnyContext,
    ) -> strategy_pb2.PauseExecutionResponse:
        """Pause a running execution."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        execution_id = UUID(request.execution_id)

        try:
            async with await self._get_db() as db:
                service = StrategyService(db)
                execution = await service.pause_execution(tenant_id, execution_id)

                if not execution:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Execution not found: {request.execution_id}",
                    )

                return strategy_pb2.PauseExecutionResponse(
                    execution=self._to_proto_execution(execution),
                )
        except ValueError as e:
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))

    async def stop_execution(
        self,
        request: strategy_pb2.StopExecutionRequest,
        ctx: AnyContext,
    ) -> strategy_pb2.StopExecutionResponse:
        """Stop an execution."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        execution_id = UUID(request.execution_id)

        reason = request.reason if request.reason else None

        try:
            async with await self._get_db() as db:
                service = StrategyService(db)
                execution = await service.stop_execution(
                    tenant_id=tenant_id,
                    execution_id=execution_id,
                    reason=reason,
                )

                if not execution:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Execution not found: {request.execution_id}",
                    )

                return strategy_pb2.StopExecutionResponse(
                    execution=self._to_proto_execution(execution),
                )
        except ValueError as e:
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))

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
            status=strategy.status,  # Already proto int
            version=strategy.current_version,
            dsl_code=strategy.config_sexpr,
            compiled_json=config_json_str,
            symbols=strategy.symbols,
            timeframe=strategy.timeframe,
            parameters=strategy.parameters,
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
            status=strategy.status,  # Already proto int
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
            parameters=version.parameters,
            change_summary=version.changelog or "",
            created_at=common_pb2.Timestamp(seconds=int(version.created_at.timestamp())),
        )

    def _to_proto_execution(self, execution: ExecutionResponse) -> strategy_pb2.StrategyExecution:
        """Convert internal execution response to proto StrategyExecution."""
        config_override_map: dict[str, str] = {}
        if execution.config_override:
            # Convert ConfigOverride to string map
            for key, value in execution.config_override.items():
                if value is not None:
                    if isinstance(value, list):
                        config_override_map[key] = json.dumps(value)
                    else:
                        config_override_map[key] = str(value)

        return strategy_pb2.StrategyExecution(
            id=str(execution.id),
            strategy_id=str(execution.strategy_id),
            tenant_id="",  # Not included in response
            version=execution.version,
            mode=execution.mode,  # Already proto int
            status=execution.status,  # Already proto int
            config_override=config_override_map,
            started_at=common_pb2.Timestamp(seconds=int(execution.started_at.timestamp()))
            if execution.started_at
            else common_pb2.Timestamp(),
            stopped_at=common_pb2.Timestamp(seconds=int(execution.stopped_at.timestamp()))
            if execution.stopped_at
            else common_pb2.Timestamp(),
            error_message=execution.error_message or "",
            created_at=common_pb2.Timestamp(seconds=int(execution.created_at.timestamp())),
        )
