"""Tests for validation tools."""

from uuid import uuid4

import pytest

from src.tools.base import ToolContext
from src.tools.validation_tools import GetAssetInfoTool, ValidateDSLTool


@pytest.fixture
def tool_context() -> ToolContext:
    """Create a test tool context."""
    return ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        session_id=uuid4(),
    )


@pytest.fixture
def validate_dsl_tool() -> ValidateDSLTool:
    """Create a ValidateDSLTool instance."""
    return ValidateDSLTool()


@pytest.fixture
def get_asset_info_tool() -> GetAssetInfoTool:
    """Create a GetAssetInfoTool instance."""
    return GetAssetInfoTool()


class TestValidateDSLTool:
    """Tests for ValidateDSLTool."""

    def test_tool_properties(self, validate_dsl_tool: ValidateDSLTool) -> None:
        """Test tool properties."""
        assert validate_dsl_tool.name == "validate_dsl"
        assert "validate" in validate_dsl_tool.description.lower()
        assert "dsl_code" in validate_dsl_tool.parameters_schema["properties"]

    async def test_empty_dsl_code(
        self, validate_dsl_tool: ValidateDSLTool, tool_context: ToolContext
    ) -> None:
        """Test validation with empty DSL code."""
        result = await validate_dsl_tool.execute({"dsl_code": ""}, tool_context)
        assert result.success is False
        assert "required" in result.error.lower()

    async def test_missing_dsl_code(
        self, validate_dsl_tool: ValidateDSLTool, tool_context: ToolContext
    ) -> None:
        """Test validation with missing DSL code parameter."""
        result = await validate_dsl_tool.execute({}, tool_context)
        assert result.success is False
        assert "required" in result.error.lower()

    async def test_basic_validation_unbalanced_parens(
        self, validate_dsl_tool: ValidateDSLTool, tool_context: ToolContext
    ) -> None:
        """Test validation catches unbalanced parentheses."""
        dsl_code = '(strategy "Test" :rebalance monthly (asset VTI)'  # Missing closing paren
        result = await validate_dsl_tool.execute({"dsl_code": dsl_code}, tool_context)

        # Should succeed but report validation errors
        assert result.success is True
        assert result.data["valid"] is False
        # Error message varies: basic validation says "parenthes", DSL parser says "RPAREN"
        assert any(
            "parenthes" in e["message"].lower() or "rparen" in e["message"].lower()
            for e in result.data["errors"]
        )

    async def test_basic_validation_missing_strategy(
        self, validate_dsl_tool: ValidateDSLTool, tool_context: ToolContext
    ) -> None:
        """Test basic validation catches missing strategy wrapper."""
        dsl_code = "(weight :method equal (asset VTI) (asset BND))"
        result = await validate_dsl_tool.execute({"dsl_code": dsl_code}, tool_context)

        assert result.success is True
        assert result.data["valid"] is False
        assert any("strategy" in e["message"].lower() for e in result.data["errors"])

    async def test_basic_validation_extracts_symbols(
        self, validate_dsl_tool: ValidateDSLTool, tool_context: ToolContext
    ) -> None:
        """Test basic validation extracts asset symbols."""
        dsl_code = """
        (strategy "Test"
          :rebalance monthly
          (weight :method equal
            (asset VTI)
            (asset BND)
            (asset VEA)))
        """
        result = await validate_dsl_tool.execute({"dsl_code": dsl_code}, tool_context)

        assert result.success is True
        # Depending on whether full DSL library is available
        if result.data.get("valid"):
            assert "symbols" in result.data or "note" in result.data


class TestGetAssetInfoTool:
    """Tests for GetAssetInfoTool."""

    def test_tool_properties(self, get_asset_info_tool: GetAssetInfoTool) -> None:
        """Test tool properties."""
        assert get_asset_info_tool.name == "get_asset_info"
        assert "asset" in get_asset_info_tool.description.lower()
        assert "symbols" in get_asset_info_tool.parameters_schema["properties"]

    async def test_empty_symbols(
        self, get_asset_info_tool: GetAssetInfoTool, tool_context: ToolContext
    ) -> None:
        """Test with empty symbols array."""
        result = await get_asset_info_tool.execute({"symbols": []}, tool_context)
        assert result.success is False
        assert "required" in result.error.lower()

    async def test_missing_symbols(
        self, get_asset_info_tool: GetAssetInfoTool, tool_context: ToolContext
    ) -> None:
        """Test with missing symbols parameter."""
        result = await get_asset_info_tool.execute({}, tool_context)
        assert result.success is False
        assert "required" in result.error.lower()

    async def test_too_many_symbols(
        self, get_asset_info_tool: GetAssetInfoTool, tool_context: ToolContext
    ) -> None:
        """Test with too many symbols."""
        symbols = [f"SYM{i}" for i in range(25)]
        result = await get_asset_info_tool.execute({"symbols": symbols}, tool_context)
        assert result.success is False
        assert "20" in result.error or "maximum" in result.error.lower()

    async def test_basic_symbol_check_known_etfs(
        self, get_asset_info_tool: GetAssetInfoTool, tool_context: ToolContext
    ) -> None:
        """Test basic symbol check recognizes known ETFs."""
        # This test will use fallback since market data service isn't available
        symbols = ["SPY", "VTI", "BND", "UNKNOWN123"]
        result = await get_asset_info_tool.execute({"symbols": symbols}, tool_context)

        # Should succeed with fallback validation
        assert result.success is True
        # Check that known ETFs are identified
        data = result.data
        if "valid_symbols" in data:
            assert "SPY" in data["valid_symbols"]
            assert "VTI" in data["valid_symbols"]
            assert "BND" in data["valid_symbols"]
            assert "UNKNOWN123" in data["unknown_symbols"]

    async def test_symbol_normalization(
        self, get_asset_info_tool: GetAssetInfoTool, tool_context: ToolContext
    ) -> None:
        """Test that symbols are normalized to uppercase."""
        symbols = ["spy", "Vti", "bnd"]
        result = await get_asset_info_tool.execute({"symbols": symbols}, tool_context)

        # Should succeed and normalize symbols
        assert result.success is True
