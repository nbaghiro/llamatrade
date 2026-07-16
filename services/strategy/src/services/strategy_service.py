"""Strategy service - CRUD operations with S-expression DSL support."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from fastapi import Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from llamatrade_proto.clients.ledger import LedgerClient

from llamatrade_compiler import extract_indicators, get_required_symbols
from llamatrade_db import get_db
from llamatrade_db.models.strategy import (
    Strategy,
    StrategyExecution,
    StrategyVersion,
)
from llamatrade_dsl import ParseError, parse_strategy, to_json, validate_strategy
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PAUSED,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_STOPPED,
)
from llamatrade_proto.generated.strategy_pb2 import (
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_ARCHIVED,
    STRATEGY_STATUS_DRAFT,
    STRATEGY_STATUS_PAUSED,
)
from llamatrade_telemetry import metrics

from src.models import (
    ConfigOverride,
    ExecutionCreate,
    ExecutionResponse,
    StrategyConfigJSON,
    StrategyCreate,
    StrategyDetailResponse,
    StrategyResponse,
    StrategyUpdate,
    StrategyVersionResponse,
    ValidationResult,
    execution_status_to_str,
)

logger = logging.getLogger(__name__)


def _naive_utc_now() -> datetime:
    """UTC now, tz-stripped: ``strategy_executions.started_at``/``stopped_at`` are
    TIMESTAMP WITHOUT TIME ZONE, and asyncpg rejects aware values for those."""
    return datetime.now(UTC).replace(tzinfo=None)

# Valid status transitions: (from_status, to_status) using proto int values
# Rules: DRAFT→ACTIVE, ACTIVE↔PAUSED, any→ARCHIVED
_VALID_STATUS_TRANSITIONS: set[tuple[int, int]] = {
    (STRATEGY_STATUS_DRAFT, STRATEGY_STATUS_ACTIVE),
    (STRATEGY_STATUS_ACTIVE, STRATEGY_STATUS_PAUSED),
    (STRATEGY_STATUS_PAUSED, STRATEGY_STATUS_ACTIVE),
    (STRATEGY_STATUS_DRAFT, STRATEGY_STATUS_ARCHIVED),
    (STRATEGY_STATUS_ACTIVE, STRATEGY_STATUS_ARCHIVED),
    (STRATEGY_STATUS_PAUSED, STRATEGY_STATUS_ARCHIVED),
}


def _rebalance_to_timeframe(rebalance: str | None) -> str:
    """Convert rebalance frequency to a timeframe string.

    Allocation strategies use rebalance frequency instead of intraday timeframes.
    We map to daily-level timeframes for the DB schema.
    """
    mapping = {
        "daily": "1D",
        "weekly": "1W",
        "monthly": "1M",
        "quarterly": "3M",
        "annually": "1Y",
    }
    return mapping.get(rebalance or "daily", "1D")


def _validate_status_transition(current: int, target: int) -> tuple[bool, str]:
    """Validate a status transition.

    Args:
        current: Current status (proto int value)
        target: Target status (proto int value)

    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    if current == target:
        return True, ""

    if (current, target) in _VALID_STATUS_TRANSITIONS:
        return True, ""

    return False, f"Invalid status transition: {current} → {target}"


# Template parameter overrides. Each entry maps a public parameter name to:
#   (field_pattern, value_validator, replacement)
# field_pattern locates the S-expression field to replace, value_validator
# constrains caller input so it cannot inject arbitrary S-expression text, and
# replacement is the substitution (``{value}`` is filled with the validated input).
_TEMPLATE_PARAM_FIELDS: dict[str, tuple[str, str, str]] = {
    "symbols": (
        r":symbols\s+\[.*?\]",
        r'^\[\s*(?:"[A-Za-z0-9.\-]+"\s*)+\]$',
        ":symbols {value}",
    ),
    "timeframe": (r':timeframe\s+"[^"]*"', r"^[A-Za-z0-9]+$", ':timeframe "{value}"'),
    "stop_loss_pct": (r":stop-loss-pct\s+[\d.]+", r"^\d+(?:\.\d+)?$", ":stop-loss-pct {value}"),
    "take_profit_pct": (
        r":take-profit-pct\s+[\d.]+",
        r"^\d+(?:\.\d+)?$",
        ":take-profit-pct {value}",
    ),
}


def _apply_template_params(config_sexpr: str, template_id: str, params: dict[str, str]) -> str:
    """Apply validated parameter overrides to a template's S-expression.

    Every override must (1) be a known parameter, (2) pass value validation so
    untrusted input cannot inject S-expression text, and (3) actually match a
    field in the template. An unknown parameter, an invalid value, or an
    unmatched field raises ``ValueError`` — overrides never silently no-op,
    because a strategy that quietly trades the wrong symbols is a hazard.
    """
    import re

    for name, value in params.items():
        field = _TEMPLATE_PARAM_FIELDS.get(name)
        if field is None:
            raise ValueError(f"Unknown template parameter: {name}")
        search, validator, replacement = field
        if not re.fullmatch(validator, value):
            raise ValueError(f"Invalid value for template parameter {name!r}: {value!r}")
        config_sexpr, count = re.subn(search, replacement.format(value=value), config_sexpr)
        if count == 0:
            raise ValueError(f"Template {template_id!r} has no {name!r} field to override")
    return config_sexpr


class StrategyService:
    """Service for strategy management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _generate_unique_name(self, tenant_id: UUID, base_name: str) -> str:
        """Generate a unique strategy name by appending (1), (2), etc. if needed.

        Args:
            tenant_id: Tenant UUID for scoping the uniqueness check
            base_name: The requested strategy name

        Returns:
            A unique name, either the original or with a numeric suffix
        """
        import re

        # Strip any existing suffix like (1), (2) from the base name
        suffix_pattern = re.compile(r"\s*\(\d+\)$")
        clean_name = suffix_pattern.sub("", base_name).strip()

        # Find all strategies with names matching the pattern "name" or "name (N)"
        like_pattern = f"{clean_name}%"
        query = select(Strategy.name).where(
            Strategy.tenant_id == tenant_id,
            Strategy.name.like(like_pattern),
        )
        result = await self.db.execute(query)
        existing_names = {row[0] for row in result.fetchall()}

        # If the exact name doesn't exist, use it
        if base_name not in existing_names:
            return base_name

        # If clean_name doesn't exist and differs from base_name, try it
        if clean_name != base_name and clean_name not in existing_names:
            return clean_name

        # Find the highest existing suffix number
        max_suffix = 0
        suffix_extract = re.compile(rf"^{re.escape(clean_name)}\s*\((\d+)\)$")

        for name in existing_names:
            if name == clean_name:
                # Base name exists, we need at least (1)
                max_suffix = max(max_suffix, 0)
            else:
                match = suffix_extract.match(name)
                if match:
                    max_suffix = max(max_suffix, int(match.group(1)))

        # Return with the next suffix
        return f"{clean_name} ({max_suffix + 1})"

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

        Uses a nested transaction (savepoint) to ensure atomicity - if version
        creation fails, the strategy creation is rolled back.
        """
        # Parse and validate S-expression (do this before starting transaction)
        try:
            with metrics.strategy.compile_duration.time():
                ast = parse_strategy(data.config_sexpr)
        except ParseError as e:
            metrics.strategy.parse_error(kind="parse")
            raise ValueError(f"Invalid strategy: {e}")

        validation = validate_strategy(ast)
        if not validation.valid:
            metrics.strategy.parse_error(kind="validate")
            error_messages = [str(e) for e in validation.errors]
            raise ValueError(f"Invalid strategy: {'; '.join(error_messages)}")

        # Extract symbols from the allocation strategy
        symbols = list(get_required_symbols(ast))

        # Map rebalance frequency to a timeframe for DB storage
        timeframe = _rebalance_to_timeframe(ast.rebalance)

        # Generate unique name (adds suffix if name already exists)
        unique_name = await self._generate_unique_name(tenant_id, data.name)

        # Use nested transaction for atomicity (strategy + version created together)
        async with self.db.begin_nested():
            # Create strategy record
            strategy = Strategy(
                tenant_id=tenant_id,
                name=unique_name,
                description=data.description,
                status=STRATEGY_STATUS_DRAFT,
                current_version=1,
                created_by=user_id,
            )
            self.db.add(strategy)
            await self.db.flush()  # Get ID before creating version

            # Create version 1
            config_json = to_json(ast)
            version = StrategyVersion(
                tenant_id=tenant_id,  # Defense-in-depth tenant isolation
                strategy_id=strategy.id,
                version=1,
                config_sexpr=data.config_sexpr,
                config_json=config_json,
                symbols=symbols,
                timeframe=timeframe,
                parameters=data.parameters or {},
                created_by=user_id,
            )
            self.db.add(version)

        await self.db.commit()
        await self.db.refresh(strategy)

        metrics.strategy.version_minted()

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

        version = await self._get_version(tenant_id, strategy.id, strategy.current_version)
        if not version:
            return None

        return self._to_detail_response(strategy, version)

    async def list_strategies(
        self,
        tenant_id: UUID,
        status: int | None = None,  # StrategyStatus proto int
        search: str | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StrategyResponse], int]:
        """List strategies for a tenant with optional filtering, search, and sort.

        Args:
            tenant_id: Tenant UUID
            status: Filter by status
            search: Search term for name/description (case-insensitive)
            sort_field: Field to sort by (name, created_at, updated_at, status)
            sort_direction: Sort direction (asc, desc)
            page: Page number (1-indexed)
            page_size: Items per page
        """
        # Outer-join current version for symbols/timeframe (no DSL blob); outer so a missing version row still lists the strategy.
        stmt = (
            select(Strategy, StrategyVersion.symbols, StrategyVersion.timeframe)
            .outerjoin(
                StrategyVersion,
                and_(
                    StrategyVersion.strategy_id == Strategy.id,
                    StrategyVersion.version == Strategy.current_version,
                ),
            )
            .where(Strategy.tenant_id == tenant_id)
        )

        if status:
            stmt = stmt.where(Strategy.status == status)  # Already proto int

        # Search by name or description (case-insensitive)
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Strategy.name.ilike(search_pattern),
                    Strategy.description.ilike(search_pattern),
                )
            )

        # Exclude archived by default
        if not status:
            stmt = stmt.where(Strategy.status != STRATEGY_STATUS_ARCHIVED)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        sort_column = self._get_sort_column(sort_field)
        if sort_direction == "asc":
            stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(sort_column.desc())

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        rows = result.all()

        return [self._to_response(s, symbols, timeframe) for s, symbols, timeframe in rows], total

    def _get_sort_column(self, field: str | None) -> Any:
        """Get SQLAlchemy column for sorting."""
        sort_columns = {
            "name": Strategy.name,
            "created_at": Strategy.created_at,
            "updated_at": Strategy.updated_at,
            "status": Strategy.status,
        }
        return sort_columns.get(field or "updated_at", Strategy.updated_at)

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

        Uses a nested transaction (savepoint) to ensure atomicity - if version
        creation fails, the strategy update is rolled back.

        Raises:
            ValueError: If status transition is invalid or config is invalid.
        """
        # for_update acquires a row-level lock to prevent races from concurrent saves.
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id, for_update=True)
        if not strategy:
            return None

        # Parse and validate config before starting transaction
        ast = None
        if data.config_sexpr is not None:
            try:
                with metrics.strategy.compile_duration.time():
                    ast = parse_strategy(data.config_sexpr)
            except ParseError as e:
                metrics.strategy.parse_error(kind="parse")
                raise ValueError(f"Invalid strategy: {e}")
            validation = validate_strategy(ast)
            if not validation.valid:
                metrics.strategy.parse_error(kind="validate")
                error_messages = [str(e) for e in validation.errors]
                raise ValueError(f"Invalid strategy: {'; '.join(error_messages)}")

        # Validate status transition before starting transaction
        if data.status is not None:
            is_valid, error_msg = _validate_status_transition(strategy.status, data.status)
            if not is_valid:
                raise ValueError(error_msg)

        # Use nested transaction for atomicity (strategy update + version created together)
        async with self.db.begin_nested():
            # Update metadata
            if data.name is not None:
                strategy.name = data.name
            if data.description is not None:
                strategy.description = data.description

            # Apply validated status change
            if data.status is not None:
                strategy.status = data.status

            # If config changed, create new version
            if ast is not None:
                new_version_num = strategy.current_version + 1
                config_json = to_json(ast)

                # Extract symbols and timeframe from allocation strategy
                symbols = list(get_required_symbols(ast))
                timeframe = _rebalance_to_timeframe(ast.rebalance)

                version = StrategyVersion(
                    tenant_id=tenant_id,  # Defense-in-depth tenant isolation
                    strategy_id=strategy.id,
                    version=new_version_num,
                    config_sexpr=data.config_sexpr,
                    config_json=config_json,
                    symbols=symbols,
                    timeframe=timeframe,
                    parameters=data.parameters or {},
                    changelog=data.changelog,
                    created_by=user_id,
                )
                self.db.add(version)
                strategy.current_version = new_version_num

        await self.db.commit()
        await self.db.refresh(strategy)

        if ast is not None:
            metrics.strategy.version_minted()

        current_version = await self._get_version(tenant_id, strategy.id, strategy.current_version)
        if current_version is None:
            raise ValueError("Strategy version not found after update")
        return self._to_detail_response(strategy, current_version)

    async def delete_strategy(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> bool:
        """Soft delete (archive) a strategy.

        Refuses to archive while the strategy has an active (RUNNING or PAUSED)
        execution: those carry a funded sleeve and may back a live trading
        runner, so the operator must stop them explicitly first — which releases
        the sleeve and halts the session — rather than have archiving silently
        release capital out from under a live runner. PENDING executions were
        never funded or started, so they are simply cancelled.

        Returns False if the strategy does not exist.

        Raises:
            ValueError: If the strategy still has an active execution.
        """
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id, for_update=True)
        if not strategy:
            return False

        active = await self._count_active_executions(tenant_id, strategy_id)
        if active:
            raise ValueError(
                f"Cannot archive strategy: {active} active execution(s) still running; "
                "stop them before archiving"
            )

        await self._cancel_pending_executions(tenant_id, strategy_id)
        strategy.status = STRATEGY_STATUS_ARCHIVED
        await self.db.commit()
        return True

    async def _count_active_executions(self, tenant_id: UUID, strategy_id: UUID) -> int:
        """Count RUNNING/PAUSED executions — these must be stopped before archiving."""
        stmt = (
            select(func.count())
            .select_from(StrategyExecution)
            .where(
                StrategyExecution.tenant_id == tenant_id,
                StrategyExecution.strategy_id == strategy_id,
                StrategyExecution.status.in_([EXECUTION_STATUS_RUNNING, EXECUTION_STATUS_PAUSED]),
            )
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def _cancel_pending_executions(self, tenant_id: UUID, strategy_id: UUID) -> None:
        """Cancel never-started PENDING executions (unfunded — no sleeve, no runner).

        Does not commit — the caller commits the archive and these cancellations
        in one transaction.
        """
        stmt = select(StrategyExecution).where(
            StrategyExecution.tenant_id == tenant_id,
            StrategyExecution.strategy_id == strategy_id,
            StrategyExecution.status == EXECUTION_STATUS_PENDING,
        )
        now = _naive_utc_now()
        for execution in (await self.db.execute(stmt)).scalars().all():
            execution.status = EXECUTION_STATUS_STOPPED
            execution.stopped_at = now
            execution.error_message = "Cancelled: strategy archived"

    async def activate_strategy(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> StrategyResponse | None:
        """Set strategy status to ACTIVE.

        Raises:
            ValueError: If status transition is not allowed.
        """
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id, for_update=True)
        if not strategy:
            return None

        is_valid, error_msg = _validate_status_transition(strategy.status, STRATEGY_STATUS_ACTIVE)
        if not is_valid:
            raise ValueError(error_msg)

        strategy.status = STRATEGY_STATUS_ACTIVE
        await self.db.commit()
        await self.db.refresh(strategy)
        return self._to_response(strategy)

    async def pause_strategy(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
    ) -> StrategyResponse | None:
        """Set strategy status to PAUSED.

        Raises:
            ValueError: If status transition is not allowed.
        """
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id, for_update=True)
        if not strategy:
            return None

        is_valid, error_msg = _validate_status_transition(strategy.status, STRATEGY_STATUS_PAUSED)
        if not is_valid:
            raise ValueError(error_msg)

        strategy.status = STRATEGY_STATUS_PAUSED
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
            .where(StrategyVersion.tenant_id == tenant_id)
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

        v = await self._get_version(tenant_id, strategy_id, version)
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

    async def create_from_template(
        self,
        tenant_id: UUID,
        user_id: UUID,
        template_id: str,
        name: str | None = None,
        description: str | None = None,
        template_params: dict[str, str] | None = None,
    ) -> StrategyDetailResponse:
        """Create a strategy from a template.

        Args:
            tenant_id: Tenant UUID
            user_id: User UUID
            template_id: Template ID (e.g., "ma_crossover", "rsi_mean_reversion")
            name: Optional custom name (defaults to template name)
            description: Optional custom description
            template_params: Optional parameter overrides (e.g., symbols, timeframe)

        Raises:
            ValueError: If template_id is not found or params are invalid
        """
        from src.services.template_service import TEMPLATES

        template = TEMPLATES.get(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        metrics.strategy.template_instantiated(template=template_id)

        config_sexpr = template["config_sexpr"]

        # Overrides are validated; an unmatched one raises rather than silently
        # trading the wrong symbols (a money-safety hazard, not a no-op).
        if template_params:
            config_sexpr = _apply_template_params(config_sexpr, template_id, template_params)

        strategy_name = name or template["name"]
        strategy_description = description or template["description"]

        return await self.create_strategy(
            tenant_id=tenant_id,
            user_id=user_id,
            data=StrategyCreate(
                name=strategy_name,
                description=strategy_description,
                config_sexpr=config_sexpr,
            ),
        )

    async def validate_config(
        self,
        config_sexpr: str,
    ) -> ValidationResult:
        """Validate a strategy configuration without saving.

        Returns validation result including detected symbols and indicators.
        """
        try:
            with metrics.strategy.compile_duration.time():
                ast = parse_strategy(config_sexpr)
            validation = validate_strategy(ast)

            if not validation.valid:
                metrics.strategy.parse_error(kind="validate")

            errors = [str(e) for e in validation.errors]
            warnings: list[str] = []

            # Extract symbols from the allocation strategy
            detected_symbols: list[str] = []
            if validation.valid:
                try:
                    detected_symbols = list(get_required_symbols(ast))
                except Exception:
                    pass

            # Add warning for strategies with many symbols
            if len(detected_symbols) > 20:
                warnings.append("Trading more than 20 symbols may impact execution speed")

            # Extract detected indicators
            detected_indicators: list[str] = []
            if validation.valid:
                try:
                    indicator_specs = extract_indicators(ast)
                    # Format as "indicator_type(params)" for display
                    for spec in indicator_specs:
                        params_str = ", ".join(str(p) for p in spec.params)
                        detected_indicators.append(f"{spec.indicator_type}({params_str})")
                except Exception:
                    # Don't fail validation if indicator extraction fails
                    pass

            return ValidationResult(
                valid=validation.valid,
                errors=errors,
                warnings=warnings,
                detected_symbols=detected_symbols,
                detected_indicators=detected_indicators,
            )
        except Exception as e:
            metrics.strategy.parse_error(kind="parse")
            return ValidationResult(
                valid=False,
                errors=[str(e)],
                warnings=[],
                detected_symbols=[],
                detected_indicators=[],
            )

    # Execution methods

    async def create_execution(
        self,
        tenant_id: UUID,
        strategy_id: UUID,
        data: ExecutionCreate,
    ) -> ExecutionResponse | None:
        """Create a new execution for a strategy.

        Uses a nested transaction (savepoint) to ensure atomicity.
        """
        strategy = await self._get_strategy_by_id(tenant_id, strategy_id)
        if not strategy:
            return None

        version = data.version or strategy.current_version

        # Verify version exists (with tenant isolation)
        v = await self._get_version(tenant_id, strategy_id, version)
        if not v:
            raise ValueError(f"Version {version} not found")

        async with self.db.begin_nested():
            execution = StrategyExecution(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                version=version,
                mode=data.mode,  # Already proto int
                status=EXECUTION_STATUS_PENDING,
                config_override=data.config_override,
                allocated_capital=data.allocated_capital,
                credentials_id=data.credentials_id,
            )
            self.db.add(execution)

        await self.db.commit()
        await self.db.refresh(execution)

        return self._to_execution_response(execution)

    async def list_executions(
        self,
        tenant_id: UUID,
        strategy_id: UUID | None = None,
        status: int | None = None,
        mode: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ExecutionResponse], int]:
        """List executions for a tenant with pagination."""
        stmt = select(StrategyExecution).where(StrategyExecution.tenant_id == tenant_id)

        if strategy_id:
            stmt = stmt.where(StrategyExecution.strategy_id == strategy_id)
        if status:
            stmt = stmt.where(StrategyExecution.status == status)  # Already proto int
        if mode:
            stmt = stmt.where(StrategyExecution.mode == mode)  # Already proto int

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(StrategyExecution.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        executions = result.scalars().all()

        return [self._to_execution_response(e) for e in executions], total

    async def get_execution(
        self,
        tenant_id: UUID,
        execution_id: UUID,
    ) -> ExecutionResponse | None:
        """Get an execution by ID."""
        execution = await self._get_execution_by_id(tenant_id, execution_id)
        if not execution:
            return None
        return self._to_execution_response(execution)

    async def start_execution(
        self,
        tenant_id: UUID,
        execution_id: UUID,
        *,
        ledger: LedgerClient | None = None,
        user_id: UUID | None = None,
    ) -> ExecutionResponse | None:
        """Start a pending execution.

        Transitions status from PENDING to RUNNING and sets started_at.
        When the execution carries funding intent (allocated_capital +
        credentials_id), its ledger sleeve is opened and funded first — the
        execution does not start if funding fails.

        Raises:
            ValueError: If execution is not in PENDING status, or funding fails.
        """
        execution = await self._get_execution_by_id(tenant_id, execution_id)
        if not execution:
            return None

        if execution.status != EXECUTION_STATUS_PENDING:
            raise ValueError(
                f"Cannot start execution: status is {execution_status_to_str(execution.status)}, expected pending"
            )

        await self._fund_sleeve(tenant_id, execution, ledger=ledger, user_id=user_id)

        execution.status = EXECUTION_STATUS_RUNNING
        execution.started_at = _naive_utc_now()
        await self.db.commit()
        await self.db.refresh(execution)

        return self._to_execution_response(execution)

    async def _fund_sleeve(
        self,
        tenant_id: UUID,
        execution: StrategyExecution,
        *,
        ledger: LedgerClient | None,
        user_id: UUID | None,
    ) -> None:
        """Open + fund the execution's ledger sleeve via the portfolio service.

        No-op when no client is wired, the execution carries no funding intent,
        or it is already funded (sleeve_id set) — so restarts never double-fund
        (idempotent server-side too).
        """
        if (
            ledger is None
            or execution.sleeve_id is not None
            or execution.allocated_capital is None
            or execution.credentials_id is None
        ):
            return

        from connectrpc.errors import ConnectError

        strategy = await self._get_strategy_by_id(tenant_id, execution.strategy_id)
        sleeve_name = strategy.name if strategy else f"Strategy {execution.strategy_id}"
        try:
            bootstrap = await ledger.get_or_create_account(
                str(tenant_id), str(user_id) if user_id else "", str(execution.credentials_id)
            )
            sleeve = await ledger.allocate_capital(
                str(tenant_id),
                str(user_id) if user_id else "",
                bootstrap.account.id,
                "",
                execution.allocated_capital,
                strategy_execution_id=str(execution.id),
                sleeve_name=sleeve_name,
            )
        except ConnectError as e:
            raise ValueError(f"Cannot start execution: sleeve funding failed: {e.message}") from e

        execution.sleeve_id = UUID(sleeve.id)
        execution.account_id = UUID(bootstrap.account.id)

    async def pause_execution(
        self,
        tenant_id: UUID,
        execution_id: UUID,
    ) -> ExecutionResponse | None:
        """Pause a running execution.

        Transitions status from RUNNING to PAUSED.

        Raises:
            ValueError: If execution is not in RUNNING status.
        """
        execution = await self._get_execution_by_id(tenant_id, execution_id)
        if not execution:
            return None

        if execution.status != EXECUTION_STATUS_RUNNING:
            raise ValueError(
                f"Cannot pause execution: status is {execution_status_to_str(execution.status)}, expected running"
            )

        execution.status = EXECUTION_STATUS_PAUSED
        await self.db.commit()
        await self.db.refresh(execution)

        return self._to_execution_response(execution)

    async def resume_execution(
        self,
        tenant_id: UUID,
        execution_id: UUID,
    ) -> ExecutionResponse | None:
        """Resume a paused execution.

        Transitions status from PAUSED to RUNNING.

        Raises:
            ValueError: If execution is not in PAUSED status.
        """
        execution = await self._get_execution_by_id(tenant_id, execution_id)
        if not execution:
            return None

        if execution.status != EXECUTION_STATUS_PAUSED:
            raise ValueError(
                f"Cannot resume execution: status is {execution_status_to_str(execution.status)}, expected paused"
            )

        execution.status = EXECUTION_STATUS_RUNNING
        await self.db.commit()
        await self.db.refresh(execution)

        return self._to_execution_response(execution)

    async def stop_execution(
        self,
        tenant_id: UUID,
        execution_id: UUID,
        reason: str | None = None,
        *,
        ledger: LedgerClient | None = None,
        user_id: UUID | None = None,
    ) -> ExecutionResponse | None:
        """Stop an execution and release its ledger sleeve.

        Can stop from RUNNING or PAUSED status. Sets stopped_at, then closes the
        execution's sleeve (re-homing open positions to the Unmanaged sleeve and
        free cash to Unallocated) so a stopped strategy never traps capital. The
        close is best-effort — the stop succeeds even if the ledger is
        unreachable.

        Raises:
            ValueError: If execution is already stopped or in error state.
        """
        execution = await self._get_execution_by_id(tenant_id, execution_id)
        if not execution:
            return None

        if execution.status in (EXECUTION_STATUS_STOPPED, EXECUTION_STATUS_ERROR):
            raise ValueError(
                f"Cannot stop execution: already in terminal status {execution_status_to_str(execution.status)}"
            )

        if execution.status == EXECUTION_STATUS_PENDING:
            raise ValueError("Cannot stop execution: execution has not started yet")

        execution.status = EXECUTION_STATUS_STOPPED
        execution.stopped_at = _naive_utc_now()
        if reason:
            execution.error_message = f"Stopped: {reason}"
        await self.db.commit()
        await self.db.refresh(execution)

        await self._close_sleeve(
            tenant_id, execution, ledger=ledger, user_id=user_id, reason=reason
        )

        return self._to_execution_response(execution)

    async def _close_sleeve(
        self,
        tenant_id: UUID,
        execution: StrategyExecution,
        *,
        ledger: LedgerClient | None,
        user_id: UUID | None,
        reason: str | None,
    ) -> None:
        """Release a stopped execution's sleeve back to the account.

        The ledger owns sleeve lifecycle; closing re-homes open positions to the
        Unmanaged sleeve and free cash to Unallocated. No-op when no client is
        wired or the execution was never funded (no sleeve).

        On success the ``sleeve_id`` is cleared, which both marks the sleeve as
        released and stops a closed sleeve from anchoring a new session. A close
        failure (ledger down, or an in-flight order still holding reserved cash)
        is logged, not raised — the stop must not fail — and ``sleeve_id`` is
        left set so :meth:`reconcile_stranded_sleeves` retries it later. Capital
        is therefore never silently trapped.
        """
        if ledger is None or execution.sleeve_id is None or execution.account_id is None:
            return

        from connectrpc.errors import ConnectError

        try:
            await ledger.close_sleeve(
                str(tenant_id),
                str(user_id) if user_id else "",
                str(execution.account_id),
                str(execution.sleeve_id),
                reason=reason or "strategy execution stopped",
            )
        except ConnectError as e:
            # Leave sleeve_id set as the "needs release" marker for the sweeper.
            logger.warning(
                "sleeve close deferred for execution %s (sleeve %s): %s",
                execution.id,
                execution.sleeve_id,
                e.message,
            )
            return

        execution.sleeve_id = None
        await self.db.commit()

    async def reconcile_stranded_sleeves(
        self,
        *,
        ledger: LedgerClient,
        user_id: UUID | None = None,
        limit: int = 100,
    ) -> int:
        """Retry sleeve release for terminal executions whose close earlier failed.

        A STOPPED/ERROR execution that still carries a ``sleeve_id`` had its
        ledger close deferred (ledger unreachable, or an in-flight order holding
        reserved cash). This sweeps them and retries so capital is never
        permanently trapped. Intended to run periodically (cron/Celery), across
        all tenants. Returns the number of sleeves successfully released.
        """
        stmt = (
            select(StrategyExecution)
            .where(
                StrategyExecution.status.in_([EXECUTION_STATUS_STOPPED, EXECUTION_STATUS_ERROR]),
                StrategyExecution.sleeve_id.is_not(None),
            )
            .limit(limit)
        )
        stranded = list((await self.db.execute(stmt)).scalars().all())
        released = 0
        for execution in stranded:
            await self._close_sleeve(
                execution.tenant_id,
                execution,
                ledger=ledger,
                user_id=user_id,
                reason="reconcile stranded sleeve",
            )
            if execution.sleeve_id is None:  # close succeeded -> released
                released += 1
        return released

    async def _get_execution_by_id(
        self, tenant_id: UUID, execution_id: UUID
    ) -> StrategyExecution | None:
        """Get execution ensuring tenant isolation."""
        stmt = (
            select(StrategyExecution)
            .where(StrategyExecution.id == execution_id)
            .where(StrategyExecution.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # Private helpers

    async def _get_strategy_by_id(
        self, tenant_id: UUID, strategy_id: UUID, for_update: bool = False
    ) -> Strategy | None:
        """Get strategy ensuring tenant isolation.

        Args:
            tenant_id: Tenant UUID for isolation
            strategy_id: Strategy UUID
            for_update: If True, acquires row-level lock (SELECT FOR UPDATE)
                       to prevent concurrent modifications. Use when modifying.
        """
        stmt = (
            select(Strategy)
            .where(Strategy.id == strategy_id)
            .where(Strategy.tenant_id == tenant_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_version(
        self, tenant_id: UUID, strategy_id: UUID, version: int
    ) -> StrategyVersion | None:
        """Get a specific version with tenant isolation.

        Uses direct tenant_id filter on StrategyVersion for defense-in-depth,
        in addition to joining with Strategy table to verify ownership.
        """
        stmt = (
            select(StrategyVersion)
            .join(Strategy, StrategyVersion.strategy_id == Strategy.id)
            .where(StrategyVersion.tenant_id == tenant_id)
            .where(Strategy.tenant_id == tenant_id)
            .where(StrategyVersion.strategy_id == strategy_id)
            .where(StrategyVersion.version == version)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _to_response(
        self, s: Strategy, symbols: list[str] | None = None, timeframe: str = ""
    ) -> StrategyResponse:
        """Convert DB model to response schema.

        symbols/timeframe come from the current version (supplied by
        list_strategies); status-only callers omit them.
        """
        return StrategyResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            status=s.status,
            current_version=s.current_version,
            created_at=s.created_at,
            updated_at=s.updated_at,
            symbols=symbols or [],
            timeframe=timeframe,
        )

    def _to_detail_response(self, s: Strategy, v: StrategyVersion) -> StrategyDetailResponse:
        """Convert DB models to detailed response schema."""
        return StrategyDetailResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            status=s.status,
            current_version=s.current_version,
            created_at=s.created_at,
            updated_at=s.updated_at,
            config_sexpr=v.config_sexpr,
            config_json=cast(StrategyConfigJSON, v.config_json),
            symbols=v.symbols,
            timeframe=v.timeframe,
            parameters=v.parameters or {},
        )

    def _to_version_response(self, v: StrategyVersion) -> StrategyVersionResponse:
        """Convert version model to response schema."""
        return StrategyVersionResponse(
            version=v.version,
            config_sexpr=v.config_sexpr,
            config_json=cast(StrategyConfigJSON, v.config_json),
            symbols=v.symbols,
            timeframe=v.timeframe,
            changelog=v.changelog,
            created_at=v.created_at,
            parameters=v.parameters or {},
        )

    def _to_execution_response(self, e: StrategyExecution) -> ExecutionResponse:
        """Convert execution model to response schema."""
        return ExecutionResponse(
            id=e.id,
            strategy_id=e.strategy_id,
            version=e.version,
            mode=e.mode,
            status=e.status,
            started_at=e.started_at,
            stopped_at=e.stopped_at,
            config_override=cast(ConfigOverride, e.config_override) if e.config_override else None,
            error_message=e.error_message,
            created_at=e.created_at,
            allocated_capital=e.allocated_capital,
            credentials_id=e.credentials_id,
            sleeve_id=e.sleeve_id,
            account_id=e.account_id,
        )


async def get_strategy_service(
    db: AsyncSession = Depends(get_db),
) -> StrategyService:
    """Dependency to get strategy service."""
    return StrategyService(db)
