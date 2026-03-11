"""DSL validation tools for the agent.

These tools validate strategy DSL code before presenting it to users,
ensuring generated strategies are syntactically and semantically correct.
"""

from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

# Known ETF symbols for fallback validation
KNOWN_ETFS = {
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "VTI",
    "VOO",
    "VEA",
    "VWO",
    "VXUS",
    "BND",
    "BNDX",
    "TLT",
    "SHY",
    "IEF",
    "LQD",
    "HYG",
    "AGG",
    "GLD",
    "SLV",
    "USO",
    "UNG",
    "XLF",
    "XLK",
    "XLV",
    "XLE",
    "XLI",
    "XLY",
    "XLP",
    "XLU",
    "XLB",
    "XLC",
    "XLRE",
    "VNQ",
    "VNQI",
    "EEM",
    "EFA",
    "SCHZ",
}


class ValidateDSLTool(BaseTool):
    """Validate DSL code for syntax and semantic correctness."""

    @property
    def name(self) -> str:
        return "validate_dsl"

    @property
    def description(self) -> str:
        return (
            "Parse and validate DSL code. ALWAYS use this before presenting "
            "a strategy to the user to ensure it's valid. Returns validation "
            "errors if any, or extracted information about the strategy."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dsl_code": {
                    "type": "string",
                    "description": "The S-expression DSL code to validate",
                },
            },
            "required": ["dsl_code"],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the validate_dsl tool."""
        dsl_code = arguments.get("dsl_code", "").strip()

        if not dsl_code:
            return ToolResult(
                success=False,
                error="dsl_code is required",
            )

        try:
            # Import DSL library - imports from root module
            from llamatrade_dsl import ParseError, parse_strategy, validate_strategy

            # Parse the DSL
            try:
                strategy_ast = parse_strategy(dsl_code)
            except ParseError as e:
                return ToolResult(
                    success=True,
                    data={
                        "valid": False,
                        "errors": [{"type": "parse_error", "message": str(e)}],
                    },
                )

            # Validate the strategy - returns ValidationResult with .valid and .errors
            validation_result = validate_strategy(strategy_ast)

            # Extract symbols and indicators from the AST
            symbols = _extract_symbols(strategy_ast)
            indicators = _extract_indicators(strategy_ast)

            if validation_result.valid:
                return ToolResult(
                    success=True,
                    data={
                        "valid": True,
                        "errors": [],
                        "strategy_name": strategy_ast.name,
                        "rebalance_frequency": strategy_ast.rebalance or "",
                        "benchmark": strategy_ast.benchmark or "SPY",
                        "symbols": list(symbols),
                        "indicators": list(indicators),
                    },
                )
            else:
                # Convert ValidationError objects to dicts
                errors = [
                    {
                        "type": "validation_error",
                        "message": err.message,
                        "path": err.path,
                        "line": err.line,
                        "column": err.column,
                        "suggestions": err.suggestions,
                    }
                    for err in validation_result.errors
                ]
                return ToolResult(
                    success=True,
                    data={
                        "valid": False,
                        "errors": errors,
                        "symbols": list(symbols),
                    },
                )

        except ImportError:
            # DSL library not available - provide basic validation
            return self._basic_validation(dsl_code)
        except Exception as e:
            logger.warning("DSL validation failed: %s", e)
            return ToolResult(
                success=True,
                data={
                    "valid": False,
                    "errors": [{"type": "error", "message": str(e)}],
                },
            )

    def _basic_validation(self, dsl_code: str) -> ToolResult:
        """Perform basic validation when DSL library is unavailable."""
        errors = []

        # Check for balanced parentheses
        open_count = dsl_code.count("(")
        close_count = dsl_code.count(")")
        if open_count != close_count:
            errors.append(
                {
                    "type": "syntax_error",
                    "message": f"Unbalanced parentheses: {open_count} open, {close_count} close",
                }
            )

        # Check for required strategy wrapper
        if not dsl_code.strip().startswith("(strategy"):
            errors.append(
                {
                    "type": "syntax_error",
                    "message": "Strategy must start with (strategy ...)",
                }
            )

        # Check for rebalance keyword
        if ":rebalance" not in dsl_code:
            errors.append(
                {
                    "type": "validation_warning",
                    "message": "Missing :rebalance frequency",
                }
            )

        # Extract symbols (basic pattern matching)
        import re

        symbols = re.findall(r"\(asset\s+([A-Z]+)", dsl_code)
        unique_symbols = list(set(symbols))

        if errors:
            return ToolResult(
                success=True,
                data={
                    "valid": False,
                    "errors": errors,
                },
            )

        return ToolResult(
            success=True,
            data={
                "valid": True,
                "errors": [],
                "symbols": unique_symbols,
                "note": "Basic validation only - DSL library unavailable",
            },
        )


class GetAssetInfoTool(BaseTool):
    """Get fundamental information about assets."""

    @property
    def name(self) -> str:
        return "get_asset_info"

    @property
    def description(self) -> str:
        return (
            "Get fundamental information about assets (validates symbols exist). "
            "Use this to verify ticker symbols mentioned by the user are valid "
            "and to get context about assets before including them in strategies."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ticker symbols to look up (max 20)",
                    "maxItems": 20,
                },
            },
            "required": ["symbols"],
        }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the get_asset_info tool."""
        symbols = arguments.get("symbols", [])

        if not symbols:
            return ToolResult(
                success=False,
                error="symbols array is required",
            )

        if len(symbols) > 20:
            return ToolResult(
                success=False,
                error="Maximum 20 symbols allowed per request",
            )

        # Normalize symbols
        symbols = [s.upper().strip() for s in symbols]

        try:
            from llamatrade_proto.generated import market_data_pb2
            from llamatrade_proto.generated.market_data_connect import MarketDataServiceClient

            from src.tools.clients import MARKET_DATA_SERVICE_URL, tenant_headers

            client = MarketDataServiceClient(MARKET_DATA_SERVICE_URL)

            # Use GetSnapshots to check if symbols exist and get price data
            request = market_data_pb2.GetSnapshotsRequest(symbols=symbols)

            response = await client.get_snapshots(
                request,
                headers=tenant_headers(str(context.tenant_id), str(context.user_id)),
            )

            assets = {}
            found_symbols = set()
            for symbol, snapshot in response.snapshots.items():
                found_symbols.add(symbol)
                # Check if quote/trade have meaningful data by looking at nested fields
                has_quote = bool(snapshot.latest_quote.bid_price or snapshot.latest_quote.ask_price)
                has_trade = bool(snapshot.latest_trade.price)
                assets[symbol] = {
                    "symbol": symbol,
                    "tradable": True,
                    "has_quote": has_quote,
                    "has_trade": has_trade,
                }

            # Find symbols that weren't found
            not_found = [s for s in symbols if s not in found_symbols]

            return ToolResult(
                success=True,
                data={
                    "assets": assets,
                    "found_count": len(assets),
                    "not_found": not_found,
                },
            )

        except Exception as e:
            logger.warning("Market data service unavailable: %s", e)
            # Fall back to basic symbol validation
            return self._basic_symbol_check(symbols, str(e))

    def _basic_symbol_check(self, symbols: list[str], error: str) -> ToolResult:
        """Perform basic symbol validation when market data service is unavailable."""
        valid_symbols = []
        unknown_symbols = []

        for symbol in symbols:
            if symbol in KNOWN_ETFS:
                valid_symbols.append(symbol)
            else:
                unknown_symbols.append(symbol)

        return ToolResult(
            success=True,
            data={
                "valid_symbols": valid_symbols,
                "unknown_symbols": unknown_symbols,
                "note": "Market data service unavailable. Showing known ETFs only.",
            },
        )


def _extract_symbols(strategy: Any) -> set[str]:
    """Extract all symbols from a parsed strategy AST."""
    symbols: set[str] = set()

    def visit(node: Any) -> None:
        # Check if this node has a symbol attribute (Asset, Price, Indicator, etc.)
        if hasattr(node, "symbol") and node.symbol:
            symbols.add(node.symbol)
        # Recursively visit children
        if hasattr(node, "children"):
            for child in node.children:
                visit(child)
        # Visit if/else blocks
        if hasattr(node, "then_block"):
            visit(node.then_block)
        if hasattr(node, "else_block") and node.else_block:
            visit(node.else_block)
        # Visit condition components
        if hasattr(node, "condition"):
            visit(node.condition)
        if hasattr(node, "left"):
            visit(node.left)
        if hasattr(node, "right"):
            visit(node.right)
        if hasattr(node, "fast"):
            visit(node.fast)
        if hasattr(node, "slow"):
            visit(node.slow)
        if hasattr(node, "operands"):
            for operand in node.operands:
                visit(operand)

    visit(strategy)
    return symbols


def _extract_indicators(strategy: Any) -> set[str]:
    """Extract all indicator names from a parsed strategy AST."""
    indicators: set[str] = set()

    def visit(node: Any) -> None:
        # Indicator nodes have 'name' and 'params' attributes
        if hasattr(node, "name") and hasattr(node, "params") and hasattr(node, "symbol"):
            # This looks like an Indicator node
            indicators.add(node.name)
        # Recursively visit children
        if hasattr(node, "children"):
            for child in node.children:
                visit(child)
        # Visit if/else blocks
        if hasattr(node, "then_block"):
            visit(node.then_block)
        if hasattr(node, "else_block") and node.else_block:
            visit(node.else_block)
        # Visit condition components
        if hasattr(node, "condition"):
            visit(node.condition)
        if hasattr(node, "left"):
            visit(node.left)
        if hasattr(node, "right"):
            visit(node.right)
        if hasattr(node, "fast"):
            visit(node.fast)
        if hasattr(node, "slow"):
            visit(node.slow)
        if hasattr(node, "operands"):
            for operand in node.operands:
                visit(operand)

    visit(strategy)
    return indicators
