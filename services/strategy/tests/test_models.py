"""Tests for Pydantic request-schema validation bounds (Issue 8A) and the
proto enum <-> string conversion helpers."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from llamatrade_proto.generated.common_pb2 import ExecutionMode, ExecutionStatus
from llamatrade_proto.generated.strategy_pb2 import (
    AssetClass,
    IndicatorType,
    StrategyStatus,
    TemplateCategory,
    TemplateDifficulty,
)

from src.models import (
    ExecutionCreate,
    StrategyCreate,
    StrategyUpdate,
    asset_class_to_str,
    execution_mode_to_str,
    execution_status_to_str,
    indicator_type_to_str,
    str_to_asset_class,
    str_to_template_category,
    str_to_template_difficulty,
    strategy_status_to_str,
    template_category_to_str,
    template_difficulty_to_str,
)

_VALID_SEXPR = "(strategy (asset SPY))"


class TestStrategyCreateValidation:
    """Bounds on StrategyCreate fields."""

    def test_minimal_valid(self) -> None:
        s = StrategyCreate(name="S", config_sexpr=_VALID_SEXPR)
        assert s.name == "S"

    def test_empty_config_sexpr_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategyCreate(name="S", config_sexpr="")

    def test_oversized_config_sexpr_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategyCreate(name="S", config_sexpr="x" * 100_001)

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategyCreate(name="", config_sexpr=_VALID_SEXPR)

    def test_oversized_description_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategyCreate(name="S", config_sexpr=_VALID_SEXPR, description="d" * 2_001)


class TestStrategyUpdateValidation:
    """Bounds on StrategyUpdate fields (all optional)."""

    def test_empty_config_sexpr_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategyUpdate(config_sexpr="")

    def test_none_config_sexpr_allowed(self) -> None:
        u = StrategyUpdate(name="New")
        assert u.config_sexpr is None

    def test_oversized_changelog_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StrategyUpdate(changelog="c" * 2_001)


class TestExecutionCreateValidation:
    """Bounds on the funded-execution money field."""

    def test_positive_capital_ok(self) -> None:
        e = ExecutionCreate(allocated_capital=Decimal("1000"))
        assert e.allocated_capital == Decimal("1000")

    def test_zero_capital_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionCreate(allocated_capital=Decimal("0"))

    def test_negative_capital_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionCreate(allocated_capital=Decimal("-1"))

    def test_excessive_capital_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionCreate(allocated_capital=Decimal("1000000001"))

    def test_capital_optional(self) -> None:
        assert ExecutionCreate().allocated_capital is None


class TestEnumConversionHelpers:
    """Proto enum <-> string conversion helpers used by API responses/filters."""

    def test_to_str_helpers_cover_all_values(self) -> None:
        assert all(strategy_status_to_str(v) for v in StrategyStatus.values())
        assert all(execution_status_to_str(v) for v in ExecutionStatus.values())
        assert all(execution_mode_to_str(v) for v in ExecutionMode.values())
        assert all(indicator_type_to_str(v) for v in IndicatorType.values())

    def test_template_category_round_trip(self) -> None:
        for value in TemplateCategory.values():
            if TemplateCategory.Name(value).endswith("UNSPECIFIED"):
                continue
            assert str_to_template_category(template_category_to_str(value)) == value

    def test_asset_class_round_trip(self) -> None:
        for value in AssetClass.values():
            if AssetClass.Name(value).endswith("UNSPECIFIED"):
                continue
            assert str_to_asset_class(asset_class_to_str(value)) == value

    def test_template_difficulty_round_trip(self) -> None:
        for value in TemplateDifficulty.values():
            if TemplateDifficulty.Name(value).endswith("UNSPECIFIED"):
                continue
            assert str_to_template_difficulty(template_difficulty_to_str(value)) == value

    def test_str_to_helpers_reject_unknown_and_empty(self) -> None:
        assert str_to_template_category("") is None
        assert str_to_template_category("not-a-category") is None
        assert str_to_asset_class("") is None
        assert str_to_asset_class("not-an-asset-class") is None
        assert str_to_template_difficulty("") is None
        assert str_to_template_difficulty("not-a-difficulty") is None
