"""Canonical DB-row → proto mappers for strategy reads.

Proto is the single source of truth for the read/wire shape (decision 1A): these
functions map the persisted ``Strategy``/``StrategyVersion``/``StrategyExecution``
rows straight to the generated proto messages in one pass, with no intermediate
Pydantic layer, and money kept as ``Decimal`` end-to-end (5A).

Proto field names are authoritative (7A): the DB's ``config_sexpr`` maps to proto
``dsl_code`` and ``changelog`` to ``change_summary`` — read from the DB column, write to the
proto field. The DSL string is the single source of truth; the JSON IR and visual tree are
derived on demand (client-side ``fromDSLString``, or the ``CompileStrategy`` RPC), never stored
or returned on the strategy. Enum columns are stored as proto ints via TypeDecorators, so
``status``/``mode`` carry straight through.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from llamatrade_db.models.strategy import Strategy, StrategyExecution, StrategyVersion
from llamatrade_proto.generated import common_pb2, strategy_pb2

if TYPE_CHECKING:
    from src.services.template_service import TemplateData


def _ts(value: datetime) -> common_pb2.Timestamp:
    return common_pb2.Timestamp(seconds=int(value.timestamp()))


def _dec(value: Decimal) -> common_pb2.Decimal:
    return common_pb2.Decimal(value=str(value))


def _config_override_map(config_override: dict[str, Any] | None) -> dict[str, str]:
    """Flatten a persisted ConfigOverride blob to the proto ``map<string, string>``.

    List values (e.g. ``symbols``) are JSON-encoded; scalars are stringified.
    ``None`` values are dropped rather than written as the string ``"None"``.
    """
    if not config_override:
        return {}
    result: dict[str, str] = {}
    for key, value in config_override.items():
        if value is None:
            continue
        result[key] = json.dumps(value) if isinstance(value, list) else str(value)
    return result


def strategy_to_proto(strategy: Strategy, version: StrategyVersion) -> strategy_pb2.Strategy:
    """Map a Strategy row + its current StrategyVersion to a flattened proto Strategy.

    The proto ``Strategy`` message flattens the strategy metadata with the current
    version's config: ``dsl_code`` (from ``config_sexpr``), ``symbols``, and ``timeframe``.
    ``template_id``/``template_params`` and the backtest-derived ``best_sharpe``/``best_return``
    have no DB column and are left unset.
    """
    return strategy_pb2.Strategy(
        id=str(strategy.id),
        tenant_id=str(strategy.tenant_id),
        name=strategy.name,
        description=strategy.description or "",
        status=strategy.status,
        version=strategy.current_version,
        dsl_code=version.config_sexpr,
        symbols=list(version.symbols),
        timeframe=version.timeframe,
        created_by=str(strategy.created_by),
        created_at=_ts(strategy.created_at),
        updated_at=_ts(strategy.updated_at),
    )


def strategy_summary_to_proto(
    strategy: Strategy, symbols: list[str], timeframe: str
) -> strategy_pb2.Strategy:
    """Map a Strategy row to a proto Strategy summary for the list view.

    Carries the current version's ``symbols`` + ``timeframe`` (from the list join)
    so the list renders them; the DSL config is omitted (fetch via GetStrategy).
    """
    return strategy_pb2.Strategy(
        id=str(strategy.id),
        tenant_id=str(strategy.tenant_id),
        name=strategy.name,
        description=strategy.description or "",
        status=strategy.status,
        version=strategy.current_version,
        symbols=list(symbols),
        timeframe=timeframe,
        created_by=str(strategy.created_by),
        created_at=_ts(strategy.created_at),
        updated_at=_ts(strategy.updated_at),
    )


def strategy_version_to_proto(version: StrategyVersion) -> strategy_pb2.StrategyVersion:
    """Map a StrategyVersion row to a proto StrategyVersion.

    Applies the naming drift: ``config_sexpr`` → ``dsl_code``, ``changelog`` → ``change_summary``.
    """
    return strategy_pb2.StrategyVersion(
        strategy_id=str(version.strategy_id),
        version=version.version,
        dsl_code=version.config_sexpr,
        change_summary=version.changelog or "",
        created_by=str(version.created_by),
        created_at=_ts(version.created_at),
    )


def execution_to_proto(execution: StrategyExecution) -> strategy_pb2.StrategyExecution:
    """Map a StrategyExecution row to a fully-populated proto StrategyExecution.

    ``symbols``/``timeframe`` have no execution column (they live on the version)
    and are left unset. Nullable timestamps and ``allocated_capital`` are only set
    when present (5A: Decimal via string, no float hop).
    """
    proto = strategy_pb2.StrategyExecution(
        id=str(execution.id),
        strategy_id=str(execution.strategy_id),
        tenant_id=str(execution.tenant_id),
        version=execution.version,
        mode=execution.mode,
        status=execution.status,
        config_override=_config_override_map(execution.config_override),
        error_message=execution.error_message or "",
        created_at=_ts(execution.created_at),
        updated_at=_ts(execution.updated_at),
        credentials_id=str(execution.credentials_id) if execution.credentials_id else "",
        sleeve_id=str(execution.sleeve_id) if execution.sleeve_id else "",
        account_id=str(execution.account_id) if execution.account_id else "",
    )
    if execution.started_at is not None:
        proto.started_at.CopyFrom(_ts(execution.started_at))
    if execution.stopped_at is not None:
        proto.stopped_at.CopyFrom(_ts(execution.stopped_at))
    if execution.allocated_capital is not None:
        proto.allocated_capital.CopyFrom(_dec(execution.allocated_capital))
    return proto


def template_to_proto(template: TemplateData) -> strategy_pb2.StrategyTemplate:
    """Map a curated TemplateData entry to a proto StrategyTemplate.

    ``config_json`` is not part of the proto template shape (parsed on demand by
    the client), so it is intentionally dropped here.
    """
    return strategy_pb2.StrategyTemplate(
        id=template["id"],
        name=template["name"],
        description=template["description"] or "",
        category=template["category"],
        asset_class=template["asset_class"],
        config_sexpr=template["config_sexpr"],
        tags=list(template["tags"]),
        difficulty=template["difficulty"],
    )


def validation_to_proto(
    *,
    valid: bool,
    errors: list[str],
    warnings: list[str],
    detected_symbols: list[str],
    detected_indicators: list[str],
) -> strategy_pb2.ValidationResult:
    """Map raw DSL validation output to a proto ValidationResult.

    The service pre-stringifies DSL errors (location embedded in the message text),
    so ``line``/``column`` stay 0 here — behavior identical to the prior servicer
    mapping (7A).
    """
    return strategy_pb2.ValidationResult(
        valid=valid,
        errors=[
            strategy_pb2.CompilationError(line=0, column=0, message=e, code="VALIDATION_ERROR")
            for e in errors
        ],
        warnings=[
            strategy_pb2.CompilationWarning(line=0, column=0, message=w, code="WARNING")
            for w in warnings
        ],
        detected_symbols=detected_symbols,
        detected_indicators=detected_indicators,
    )
