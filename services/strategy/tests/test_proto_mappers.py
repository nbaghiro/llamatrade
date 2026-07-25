"""Golden round-trip tests for the DB-row -> proto strategy mappers (1A).

Validates the canonical mappers in isolation: DB row in, proto out, with
(1) Decimal precision preserved (no float hop, 5A), (2) the proto field-name drift
applied (7A) — DB ``config_sexpr`` -> proto ``dsl_code``, ``changelog`` ->
``change_summary`` — and (3) no proto Decimal field left unset outside an explicit allowlist.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from google.protobuf.message import Message

from llamatrade_db.models.strategy import Strategy, StrategyExecution, StrategyVersion
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_RUNNING,
)
from llamatrade_proto.generated.strategy_pb2 import (
    ASSET_CLASS_MULTI_ASSET,
    STRATEGY_STATUS_ACTIVE,
    TEMPLATE_CATEGORY_TREND,
    TEMPLATE_DIFFICULTY_BEGINNER,
)

from src.proto_mappers import (
    execution_to_proto,
    strategy_summary_to_proto,
    strategy_to_proto,
    strategy_version_to_proto,
    template_to_proto,
    validation_to_proto,
)
from src.services.template_service import TemplateData

# best_sharpe/best_return come from backtests and have no strategy/version column.
_STRATEGY_DECIMAL_UNSET_ALLOWLIST = {"best_sharpe", "best_return"}

_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
_EXEC_ID = UUID("44444444-4444-4444-4444-444444444444")
_SLEEVE_ID = UUID("55555555-5555-5555-5555-555555555555")
_ACCOUNT_ID = UUID("66666666-6666-6666-6666-666666666666")
_CREDS_ID = UUID("77777777-7777-7777-7777-777777777777")

_CREATED = datetime(2024, 1, 2, tzinfo=UTC)
_UPDATED = datetime(2024, 1, 3, tzinfo=UTC)

_DSL = '(strategy "S" (weight :method equal (asset SPY) (asset AGG)))'


def _decimal_field_names(message: Message) -> list[str]:
    """Names of message-typed Decimal fields on a proto message."""
    return [
        f.name
        for f in message.DESCRIPTOR.fields
        if f.message_type is not None and f.message_type.name == "Decimal"
    ]


def _make_strategy() -> Strategy:
    return Strategy(
        id=_STRATEGY_ID,
        tenant_id=_TENANT_ID,
        name="Momentum",
        description="A momentum strategy",
        status=STRATEGY_STATUS_ACTIVE,
        current_version=3,
        created_by=_USER_ID,
        created_at=_CREATED,
        updated_at=_UPDATED,
    )


def _make_version() -> StrategyVersion:
    return StrategyVersion(
        strategy_id=_STRATEGY_ID,
        tenant_id=_TENANT_ID,
        version=3,
        config_sexpr=_DSL,
        symbols=["SPY", "AGG"],
        timeframe="1D",
        changelog="tightened stops",
        created_by=_USER_ID,
        created_at=_CREATED,
    )


def _make_execution(**overrides: object) -> StrategyExecution:
    execution = StrategyExecution(
        id=_EXEC_ID,
        tenant_id=_TENANT_ID,
        strategy_id=_STRATEGY_ID,
        version=3,
        mode=EXECUTION_MODE_PAPER,
        status=EXECUTION_STATUS_RUNNING,
        config_override={"symbols": ["QQQ", "IWM"], "stop_loss_pct": 2.5},
        error_message=None,
        allocated_capital=Decimal("40000.00"),
        credentials_id=_CREDS_ID,
        sleeve_id=_SLEEVE_ID,
        account_id=_ACCOUNT_ID,
        started_at=_CREATED,
        stopped_at=None,
        created_at=_CREATED,
        updated_at=_UPDATED,
    )
    for key, value in overrides.items():
        setattr(execution, key, value)
    return execution


def test_strategy_flatten_and_field_renames() -> None:
    proto = strategy_to_proto(_make_strategy(), _make_version())

    # Flattened metadata carried straight from the row.
    assert proto.id == str(_STRATEGY_ID)
    assert proto.tenant_id == str(_TENANT_ID)  # populated (was blanked pre-1A)
    assert proto.created_by == str(_USER_ID)
    assert proto.name == "Momentum"
    assert proto.description == "A momentum strategy"
    # Enum carried as the proto int, not a string.
    assert proto.status == STRATEGY_STATUS_ACTIVE
    assert proto.version == 3

    # 7A: DB config_sexpr -> proto dsl_code (the single stored representation).
    assert proto.dsl_code == _DSL

    assert list(proto.symbols) == ["SPY", "AGG"]
    assert proto.timeframe == "1D"
    assert proto.created_at.seconds == int(_CREATED.timestamp())
    assert proto.updated_at.seconds == int(_UPDATED.timestamp())


def test_strategy_decimal_fields_unset_allowlist() -> None:
    proto = strategy_to_proto(_make_strategy(), _make_version())
    for name in _decimal_field_names(proto):
        assert name in _STRATEGY_DECIMAL_UNSET_ALLOWLIST, f"unexpected Decimal field {name}"
        assert not proto.HasField(name), f"{name} should be unset (no DB column)"


def test_strategy_summary_carries_symbols_omits_dsl() -> None:
    proto = strategy_summary_to_proto(_make_strategy(), ["SPY", "AGG"], "1D")
    assert proto.id == str(_STRATEGY_ID)
    assert proto.tenant_id == str(_TENANT_ID)
    assert list(proto.symbols) == ["SPY", "AGG"]
    assert proto.timeframe == "1D"
    # The DSL config is omitted from the list projection.
    assert proto.dsl_code == ""


def test_version_field_renames() -> None:
    proto = strategy_version_to_proto(_make_version())
    assert proto.strategy_id == str(_STRATEGY_ID)
    assert proto.version == 3
    # 7A: config_sexpr -> dsl_code, changelog -> change_summary.
    assert proto.dsl_code == _DSL
    assert proto.change_summary == "tightened stops"
    assert proto.created_by == str(_USER_ID)
    assert proto.created_at.seconds == int(_CREATED.timestamp())


def test_execution_full_population_and_decimal_precision() -> None:
    proto = execution_to_proto(_make_execution())

    assert proto.id == str(_EXEC_ID)
    assert proto.tenant_id == str(_TENANT_ID)  # populated (was blanked pre-1A)
    assert proto.strategy_id == str(_STRATEGY_ID)
    assert proto.mode == EXECUTION_MODE_PAPER
    assert proto.status == EXECUTION_STATUS_RUNNING
    # 5A: Decimal via string, scale preserved, no float hop.
    assert proto.allocated_capital.value == "40000.00"
    assert Decimal(proto.allocated_capital.value) == Decimal("40000")
    assert proto.credentials_id == str(_CREDS_ID)
    assert proto.sleeve_id == str(_SLEEVE_ID)
    assert proto.account_id == str(_ACCOUNT_ID)
    assert proto.created_at.seconds == int(_CREATED.timestamp())
    assert proto.updated_at.seconds == int(_UPDATED.timestamp())

    # config_override flattens to map<string,string>: lists JSON-encoded, scalars str().
    assert proto.config_override["symbols"] == '["QQQ", "IWM"]'
    assert proto.config_override["stop_loss_pct"] == "2.5"

    # started_at is set; stopped_at is None -> left unset.
    assert proto.HasField("started_at")
    assert not proto.HasField("stopped_at")


def test_execution_decimal_completeness_when_funded() -> None:
    proto = execution_to_proto(_make_execution())
    # allocated_capital is the only Decimal field; funded -> set (empty allowlist).
    for name in _decimal_field_names(proto):
        assert proto.HasField(name), f"{name} unexpectedly left at default"


def test_execution_unfunded_leaves_allocated_capital_unset() -> None:
    proto = execution_to_proto(_make_execution(allocated_capital=None))
    assert not proto.HasField("allocated_capital")


def test_execution_empty_config_override() -> None:
    proto = execution_to_proto(_make_execution(config_override=None))
    assert dict(proto.config_override) == {}


def test_template_maps_fields_and_drops_config_json() -> None:
    template: TemplateData = {
        "id": "ma-crossover",
        "name": "Moving Average Crossover",
        "description": "Trend following",
        "category": TEMPLATE_CATEGORY_TREND,
        "asset_class": ASSET_CLASS_MULTI_ASSET,
        "tags": ["trend", "ema"],
        "difficulty": TEMPLATE_DIFFICULTY_BEGINNER,
        "config_sexpr": _DSL,
    }
    proto = template_to_proto(template)
    assert proto.id == "ma-crossover"
    assert proto.name == "Moving Average Crossover"
    assert proto.category == TEMPLATE_CATEGORY_TREND
    assert proto.asset_class == ASSET_CLASS_MULTI_ASSET
    assert list(proto.tags) == ["trend", "ema"]
    assert proto.difficulty == TEMPLATE_DIFFICULTY_BEGINNER
    assert proto.config_sexpr == _DSL


def test_validation_maps_to_structured_proto() -> None:
    proto = validation_to_proto(
        valid=False,
        errors=["missing entry condition"],
        warnings=["trades many symbols"],
        detected_symbols=["SPY", "AGG"],
        detected_indicators=["rsi(14)"],
    )
    assert proto.valid is False
    assert len(proto.errors) == 1
    assert proto.errors[0].message == "missing entry condition"
    assert proto.errors[0].code == "VALIDATION_ERROR"
    assert proto.errors[0].line == 0 and proto.errors[0].column == 0
    assert proto.warnings[0].code == "WARNING"
    assert list(proto.detected_symbols) == ["SPY", "AGG"]
    assert list(proto.detected_indicators) == ["rsi(14)"]


def test_validation_valid_has_no_errors() -> None:
    proto = validation_to_proto(
        valid=True, errors=[], warnings=[], detected_symbols=[], detected_indicators=[]
    )
    assert proto.valid is True
    assert len(proto.errors) == 0
    assert len(proto.warnings) == 0
