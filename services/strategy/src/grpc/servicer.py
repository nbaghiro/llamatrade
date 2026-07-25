"""Strategy Connect servicer implementation."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, cast
from uuid import UUID

if TYPE_CHECKING:
    from llamatrade_proto.clients.ledger import LedgerClient

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_common.connect import resolve_identity_connect
from llamatrade_db import get_session_maker, system_session, tenant_session
from llamatrade_db.models import StrategyExecution
from llamatrade_db.plan_limits import PlanLimitExceededError, enforce_plan_limit
from llamatrade_proto.generated import common_pb2, strategy_pb2
from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_PAPER
from llamatrade_proto.generated.strategy_pb2 import (
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_ARCHIVED,
    STRATEGY_STATUS_PAUSED,
)

from src.grpc.error_handler import handle_service_errors, parse_uuid
from src.models import ConfigOverride
from src.proto_mappers import (
    execution_to_proto,
    strategy_summary_to_proto,
    strategy_to_proto,
    strategy_version_to_proto,
    template_to_proto,
)

logger = logging.getLogger(__name__)


def _validate_tenant_context(context: common_pb2.TenantContext) -> tuple[UUID, UUID]:
    """Verified ``(tenant_id, user_id)`` for the call.

    Derives identity from the authenticated principal (JWT via ``AuthMiddleware``),
    rejecting a request whose wire ``context`` tenant doesn't match the token.
    """
    return resolve_identity_connect(context)


class StrategyServicer:
    """Connect servicer for the Strategy service.

    Implements the StrategyService Protocol defined in strategy_connect.py.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: async_sessionmaker[AsyncSession] | None = None
        self._ledger_client: LedgerClient | None = None

    def _maker(self) -> async_sessionmaker[AsyncSession]:
        """The session factory (lazily created; tests inject a test-DB factory)."""
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        return self._session_maker

    def _get_ledger(self) -> LedgerClient:
        """Lazy LedgerClient to the portfolio service (sleeve funding)."""
        if self._ledger_client is None:
            import os

            from llamatrade_proto.clients.ledger import LedgerClient

            self._ledger_client = LedgerClient(
                os.getenv("PORTFOLIO_GRPC_TARGET", "portfolio:8860"), service_name="strategy"
            )
        return self._ledger_client

    @handle_service_errors
    async def get_strategy(
        self,
        request: strategy_pb2.GetStrategyRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.GetStrategyResponse:
        """Get a strategy by ID."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        strategy_id = parse_uuid(request.strategy_id, "strategy_id")

        async with tenant_session(tenant_id, self._maker()) as db:
            service = StrategyService(db)

            # Get specific version if requested, otherwise current
            if request.version > 0:
                version = await service.get_version(tenant_id, strategy_id, request.version)
                if not version:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Strategy version {request.version} not found",
                    )

            result = await service.get_strategy(tenant_id, strategy_id)
            if not result:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy not found: {request.strategy_id}",
                )

            return strategy_pb2.GetStrategyResponse(
                strategy=strategy_to_proto(*result),
            )

    @handle_service_errors
    async def list_strategies(
        self,
        request: strategy_pb2.ListStrategiesRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.ListStrategiesResponse:
        """List strategies for a tenant with filtering, search, and sort."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)

        # Map status filters - pass proto int value directly
        status = request.statuses[0] if request.statuses else None

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

        async with tenant_session(tenant_id, self._maker()) as db:
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
                strategies=[
                    strategy_summary_to_proto(s, symbols, timeframe)
                    for s, symbols, timeframe in strategies
                ],
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=page,
                    page_size=page_size,
                    has_next=page < total_pages,
                    has_previous=page > 1,
                ),
            )

    @handle_service_errors
    async def create_strategy(
        self,
        request: strategy_pb2.CreateStrategyRequest,
        ctx: RequestContext[object, object],
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
            async with tenant_session(tenant_id, self._maker()) as db:
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
                    create_data = StrategyCreate(
                        name=request.name,
                        description=request.description or None,
                        config_sexpr=request.dsl_code,
                    )
                    strategy = await service.create_strategy(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        data=create_data,
                    )

                return strategy_pb2.CreateStrategyResponse(
                    strategy=strategy_to_proto(*strategy),
                )
        except ValueError as e:
            # Validation errors are invalid arguments
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    @handle_service_errors
    async def update_strategy(
        self,
        request: strategy_pb2.UpdateStrategyRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.UpdateStrategyResponse:
        """Update an existing strategy."""
        from src.models import StrategyUpdate
        from src.services.strategy_service import StrategyService

        tenant_id, user_id = _validate_tenant_context(request.context)
        strategy_id = parse_uuid(request.strategy_id, "strategy_id")

        update_data = StrategyUpdate(
            name=request.name if request.name else None,
            description=request.description if request.description else None,
            config_sexpr=request.dsl_code if request.dsl_code else None,
            changelog=request.change_summary if request.change_summary else None,
        )

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
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
                    strategy=strategy_to_proto(*strategy),
                )
        except ValueError as e:
            # Validation errors are invalid arguments
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    @handle_service_errors
    async def delete_strategy(
        self,
        request: strategy_pb2.DeleteStrategyRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.DeleteStrategyResponse:
        """Delete (archive) a strategy.

        Refused (FAILED_PRECONDITION) while an active execution is still running;
        the operator must stop it first.
        """
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        strategy_id = parse_uuid(request.strategy_id, "strategy_id")

        async with tenant_session(tenant_id, self._maker()) as db:
            service = StrategyService(db)
            try:
                success = await service.delete_strategy(tenant_id, strategy_id)
            except ValueError as e:
                # Active execution still running — archiving is a precondition failure.
                raise ConnectError(Code.FAILED_PRECONDITION, str(e)) from e

            if not success:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy not found: {request.strategy_id}",
                )

            return strategy_pb2.DeleteStrategyResponse(success=True)

    @handle_service_errors
    async def compile_strategy(
        self,
        request: strategy_pb2.CompileStrategyRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.CompileStrategyResponse:
        """Compile/validate DSL code (stateless — touches no tenant data)."""
        from src.services.strategy_service import StrategyService

        # Compilation reads no tenant rows, so it runs outside a tenant scope.
        async with system_session(self._maker()) as db:
            service = StrategyService(db)
            validation = await service.validate_config(request.dsl_code)

            # Compile validated DSL to JSON; a compile failure on otherwise-valid
            # DSL is surfaced to the caller, not swallowed.
            compiled_json_str = ""
            compile_error: str | None = None
            if validation.valid:
                from llamatrade_dsl import parse_strategy, to_json

                try:
                    ast = parse_strategy(request.dsl_code)
                    compiled_json_str = json.dumps(to_json(ast))
                except Exception as e:
                    compile_error = f"compilation failed: {e}"

            result = strategy_pb2.CompilationResult(
                success=validation.valid and compile_error is None,
                compiled_json=compiled_json_str,
            )

            if compile_error is not None:
                result.errors.append(
                    strategy_pb2.CompilationError(
                        line=0,
                        column=0,
                        message=compile_error,
                        code="COMPILE_ERROR",
                    )
                )

            # validation already carries structured errors/warnings (proto).
            result.errors.extend(validation.errors)
            result.warnings.extend(validation.warnings)

            return strategy_pb2.CompileStrategyResponse(result=result)

    @handle_service_errors
    async def validate_strategy(
        self,
        request: strategy_pb2.ValidateStrategyRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.ValidateStrategyResponse:
        """Validate an existing strategy."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        strategy_id = parse_uuid(request.strategy_id, "strategy_id")

        async with tenant_session(tenant_id, self._maker()) as db:
            service = StrategyService(db)
            result = await service.get_strategy(tenant_id, strategy_id)

            if not result:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy not found: {request.strategy_id}",
                )

            _, version = result
            # Validate the current version's config; the service returns the
            # structured proto ValidationResult directly.
            validation = await service.validate_config(version.config_sexpr)

            return strategy_pb2.ValidateStrategyResponse(result=validation)

    @handle_service_errors
    async def list_strategy_versions(
        self,
        request: strategy_pb2.ListStrategyVersionsRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.ListStrategyVersionsResponse:
        """List versions of a strategy."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        strategy_id = parse_uuid(request.strategy_id, "strategy_id")

        page = request.pagination.page if request.HasField("pagination") else 1
        page_size = request.pagination.page_size if request.HasField("pagination") else 20

        async with tenant_session(tenant_id, self._maker()) as db:
            service = StrategyService(db)
            versions = await service.list_versions(tenant_id, strategy_id)

            # Manual pagination since service returns all
            total = len(versions)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = versions[start:end]

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return strategy_pb2.ListStrategyVersionsResponse(
                versions=[strategy_version_to_proto(v) for v in paginated],
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=page,
                    page_size=page_size,
                    has_next=page < total_pages,
                    has_previous=page > 1,
                ),
            )

    @handle_service_errors
    async def update_strategy_status(
        self,
        request: strategy_pb2.UpdateStrategyStatusRequest,
        ctx: RequestContext[object, object],
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
        strategy_id = parse_uuid(request.strategy_id, "strategy_id")

        # Use proto int value directly
        status = request.status

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
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
                    strategy=strategy_to_proto(*full_strategy) if full_strategy else None,
                )
        except ValueError as e:
            # Status transition validation errors
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    @handle_service_errors
    async def clone_strategy(
        self,
        request: strategy_pb2.CloneStrategyRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.CloneStrategyResponse:
        """Clone a strategy with a new name."""
        from src.services.strategy_service import StrategyService

        tenant_id, user_id = _validate_tenant_context(request.context)
        strategy_id = parse_uuid(request.strategy_id, "strategy_id")

        if not request.new_name:
            raise ConnectError(Code.INVALID_ARGUMENT, "new_name is required")

        async with tenant_session(tenant_id, self._maker()) as db:
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

                result = await service.create_strategy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    data=StrategyCreate(
                        name=request.new_name,
                        description=f"Cloned from version {request.version}",
                        config_sexpr=version.config_sexpr,
                    ),
                )
            else:
                # Clone current version
                result = await service.clone_strategy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    new_name=request.new_name,
                )

            if not result:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy not found: {request.strategy_id}",
                )

            return strategy_pb2.CloneStrategyResponse(
                strategy=strategy_to_proto(*result),
            )

    @handle_service_errors
    async def create_execution(
        self,
        request: strategy_pb2.CreateExecutionRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.CreateExecutionResponse:
        """Create a new execution for a strategy."""
        from src.models import ExecutionCreate
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        strategy_id = parse_uuid(request.strategy_id, "strategy_id")

        # Use proto mode directly (int), default to PAPER
        mode = request.mode if request.mode > 0 else EXECUTION_MODE_PAPER

        # Build config override from proto map
        # Cast to ConfigOverride since TypedDict is total=False (all keys optional)
        config_override: ConfigOverride | None = (
            cast(ConfigOverride, dict(request.config_override)) if request.config_override else None
        )

        create_data = ExecutionCreate(
            version=request.version if request.version > 0 else None,
            mode=mode,
            config_override=config_override,
            allocated_capital=(
                Decimal(request.allocated_capital.value)
                if request.allocated_capital.value
                else None
            ),
            credentials_id=(
                parse_uuid(request.credentials_id, "credentials_id")
                if request.credentials_id
                else None
            ),
        )

        async with tenant_session(tenant_id, self._maker()) as db:
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
                execution=execution_to_proto(execution),
            )

    @handle_service_errors
    async def get_execution(
        self,
        request: strategy_pb2.GetExecutionRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.GetExecutionResponse:
        """Get an execution by ID."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        execution_id = parse_uuid(request.execution_id, "execution_id")

        async with tenant_session(tenant_id, self._maker()) as db:
            service = StrategyService(db)
            execution = await service.get_execution(tenant_id, execution_id)

            if not execution:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Execution not found: {request.execution_id}",
                )

            return strategy_pb2.GetExecutionResponse(
                execution=execution_to_proto(execution),
            )

    @handle_service_errors
    async def list_executions(
        self,
        request: strategy_pb2.ListExecutionsRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.ListExecutionsResponse:
        """List executions with optional filters."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)

        # Map filters - pass proto int values directly
        strategy_id = (
            parse_uuid(request.strategy_id, "strategy_id") if request.strategy_id else None
        )
        status = request.statuses[0] if request.statuses else None
        mode = request.modes[0] if request.modes else None

        page = request.pagination.page if request.HasField("pagination") else 1
        page_size = request.pagination.page_size if request.HasField("pagination") else 20

        async with tenant_session(tenant_id, self._maker()) as db:
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
                executions=[execution_to_proto(e) for e in executions],
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=page,
                    page_size=page_size,
                    has_next=page < total_pages,
                    has_previous=page > 1,
                ),
            )

    @handle_service_errors
    async def _enforce_live_strategy_quota(self, db: AsyncSession, tenant_id: UUID) -> None:
        """Reject when the tenant is at its plan's live-strategy limit."""
        running = (
            await db.scalar(
                select(func.count())
                .select_from(StrategyExecution)
                .where(
                    StrategyExecution.tenant_id == tenant_id,
                    StrategyExecution.status == common_pb2.EXECUTION_STATUS_RUNNING,
                )
            )
            or 0
        )
        try:
            await enforce_plan_limit(db, tenant_id, "live_strategies", running)
        except PlanLimitExceededError as e:
            raise ConnectError(
                Code.RESOURCE_EXHAUSTED,
                f"Plan limit reached: {e.limit} live strateg(ies); upgrade to run more.",
            ) from e

    async def start_execution(
        self,
        request: strategy_pb2.StartExecutionRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.StartExecutionResponse:
        """Start a pending execution."""
        from src.services.strategy_service import StrategyService

        tenant_id, user_id = _validate_tenant_context(request.context)
        execution_id = parse_uuid(request.execution_id, "execution_id")

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
                await self._enforce_live_strategy_quota(db, tenant_id)
                service = StrategyService(db)
                execution = await service.start_execution(
                    tenant_id,
                    execution_id,
                    ledger=self._get_ledger(),
                    user_id=user_id,
                )

                if not execution:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Execution not found: {request.execution_id}",
                    )

                return strategy_pb2.StartExecutionResponse(
                    execution=execution_to_proto(execution),
                )
        except ValueError as e:
            # State transition / funding errors are precondition failures
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))

    @handle_service_errors
    async def pause_execution(
        self,
        request: strategy_pb2.PauseExecutionRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.PauseExecutionResponse:
        """Pause a running execution."""
        from src.services.strategy_service import StrategyService

        tenant_id, _ = _validate_tenant_context(request.context)
        execution_id = parse_uuid(request.execution_id, "execution_id")

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
                service = StrategyService(db)
                execution = await service.pause_execution(tenant_id, execution_id)

                if not execution:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Execution not found: {request.execution_id}",
                    )

                return strategy_pb2.PauseExecutionResponse(
                    execution=execution_to_proto(execution),
                )
        except ValueError as e:
            # State transition errors are precondition failures
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))

    @handle_service_errors
    async def stop_execution(
        self,
        request: strategy_pb2.StopExecutionRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.StopExecutionResponse:
        """Stop an execution and release its ledger sleeve."""
        from src.services.strategy_service import StrategyService

        tenant_id, user_id = _validate_tenant_context(request.context)
        execution_id = parse_uuid(request.execution_id, "execution_id")

        reason = request.reason if request.reason else None

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
                service = StrategyService(db)
                execution = await service.stop_execution(
                    tenant_id=tenant_id,
                    execution_id=execution_id,
                    reason=reason,
                    ledger=self._get_ledger(),
                    user_id=user_id,
                )

                if not execution:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Execution not found: {request.execution_id}",
                    )

                return strategy_pb2.StopExecutionResponse(
                    execution=execution_to_proto(execution),
                )
        except ValueError as e:
            # State transition errors are precondition failures
            raise ConnectError(Code.FAILED_PRECONDITION, str(e))

    @handle_service_errors
    async def list_templates(
        self,
        request: strategy_pb2.ListTemplatesRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.ListTemplatesResponse:
        """List available strategy templates.

        Templates are pre-built strategy definitions that users can use as starting points.
        No authentication required - templates are public.
        """
        from src.services.template_service import get_template_service

        template_service = get_template_service()

        # proto enum values; 0 (unspecified) means no filter
        category = request.category if request.category else None
        asset_class = request.asset_class if request.asset_class else None
        difficulty = request.difficulty if request.difficulty else None

        templates = await template_service.list_templates(
            category=category,
            asset_class=asset_class,
            difficulty=difficulty,
        )

        return strategy_pb2.ListTemplatesResponse(
            templates=[template_to_proto(t) for t in templates],
        )

    @handle_service_errors
    async def get_template(
        self,
        request: strategy_pb2.GetTemplateRequest,
        ctx: RequestContext[object, object],
    ) -> strategy_pb2.GetTemplateResponse:
        """Get a specific template by ID.

        No authentication required - templates are public.
        """
        from src.services.template_service import get_template_service

        template_service = get_template_service()
        template = await template_service.get_template(request.template_id)

        if not template:
            raise ConnectError(
                Code.NOT_FOUND,
                f"Template not found: {request.template_id}",
            )

        return strategy_pb2.GetTemplateResponse(
            template=template_to_proto(template),
        )
