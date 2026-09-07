"""``validate_dsl`` driven through the real DSL library.

The existing suite only reaches ``_basic_validation``, the parenthesis-counting
fallback used when ``llamatrade_dsl`` cannot be imported. That leaves the branch
that actually runs in production untested: parse, validate, then extract the
symbols and indicators the assistant quotes back before offering to save. The
library is a first-party dependency and is always installed here, so these drive
it for real rather than mocking the result.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.tools.base import ToolContext
from src.tools.validation_tools import ValidateDSLTool

VALID = '(strategy "Balanced" :rebalance monthly (weight :method equal (asset SPY) (asset AGG)))'


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(tenant_id=uuid4(), user_id=uuid4(), session_id=uuid4())


class TestValidStrategy:
    async def test_reports_the_parsed_shape(self, ctx: ToolContext) -> None:
        result = await ValidateDSLTool().execute({"dsl_code": VALID}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["valid"] is True
        assert result.data["errors"] == []
        assert result.data["strategy_name"] == "Balanced"
        assert result.data["rebalance_frequency"] == "monthly"
        assert set(result.data["symbols"]) == {"SPY", "AGG"}

    async def test_defaults_the_benchmark_when_unset(self, ctx: ToolContext) -> None:
        result = await ValidateDSLTool().execute({"dsl_code": VALID}, ctx)

        assert result.data is not None
        assert result.data["benchmark"] == "SPY"

    async def test_reports_an_explicit_benchmark(self, ctx: ToolContext) -> None:
        dsl = '(strategy "B" :benchmark QQQ :rebalance daily (asset SPY :weight 100))'

        result = await ValidateDSLTool().execute({"dsl_code": dsl}, ctx)

        assert result.data is not None
        assert result.data["benchmark"] == "QQQ"

    async def test_collects_indicators_used_in_conditions(self, ctx: ToolContext) -> None:
        dsl = (
            '(strategy "Cross" :rebalance daily '
            "(if (> (rsi SPY 14) 70) (asset AGG :weight 100) (else (asset SPY :weight 100))))"
        )

        result = await ValidateDSLTool().execute({"dsl_code": dsl}, ctx)

        assert result.data is not None
        assert result.data["valid"] is True
        assert "rsi" in result.data["indicators"]
        # Both branches contribute symbols, not only the taken one.
        assert set(result.data["symbols"]) == {"SPY", "AGG"}


class TestRejections:
    async def test_a_parse_error_is_reported_as_invalid_not_as_a_tool_failure(
        self, ctx: ToolContext
    ) -> None:
        """The model must be able to read the reason and correct the DSL."""
        result = await ValidateDSLTool().execute({"dsl_code": '(strategy "Broken" (asset'}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["valid"] is False
        assert result.data["errors"][0]["type"] == "parse_error"
        assert result.data["errors"][0]["message"]

    async def test_a_semantic_error_carries_a_message(self, ctx: ToolContext) -> None:
        # Parses cleanly, but the weights do not form a valid allocation.
        dsl = '(strategy "Overweight" :rebalance daily (asset SPY :weight 150))'

        result = await ValidateDSLTool().execute({"dsl_code": dsl}, ctx)

        assert result.success is True
        assert result.data is not None
        if not result.data["valid"]:
            error = result.data["errors"][0]
            assert error["type"] == "validation_error"
            assert error["message"]
            # Symbols are still reported so the assistant can talk about the draft.
            assert "symbols" in result.data

    @pytest.mark.parametrize("dsl_code", ["", "   ", "\n\t "])
    async def test_blank_input_is_refused(self, ctx: ToolContext, dsl_code: str) -> None:
        result = await ValidateDSLTool().execute({"dsl_code": dsl_code}, ctx)

        assert result.success is False
        assert result.error is not None and "dsl_code" in result.error

    async def test_missing_argument_is_refused(self, ctx: ToolContext) -> None:
        result = await ValidateDSLTool().execute({}, ctx)

        assert result.success is False
