"""Convert AST to/from JSON for database storage."""

from __future__ import annotations

from typing import TypedDict

from llamatrade_dsl.ast import (
    ASTNode,
    FunctionCall,
    Keyword,
    Literal,
    LiteralValue,
    RiskConfig,
    SizingConfig,
    Strategy,
    Symbol,
)


class LiteralJSON(TypedDict):
    """JSON representation of Literal node."""

    type: str
    value: LiteralValue


class SymbolJSON(TypedDict):
    """JSON representation of Symbol node."""

    type: str
    name: str


class KeywordJSON(TypedDict):
    """JSON representation of Keyword node."""

    type: str
    name: str


class FunctionJSON(TypedDict):
    """JSON representation of FunctionCall node."""

    type: str
    name: str
    args: list[ASTNodeJSON]


# Union of all AST node JSON types
ASTNodeJSON = LiteralJSON | SymbolJSON | KeywordJSON | FunctionJSON


class StrategyJSON(TypedDict, total=False):
    """JSON representation of Strategy."""

    type: str
    name: str
    description: str | None
    strategy_type: str
    symbols: list[str]
    timeframe: str
    entry: ASTNodeJSON
    exit: ASTNodeJSON
    sizing: SizingConfig
    risk: RiskConfig


def to_json(node: ASTNode | Strategy) -> ASTNodeJSON | StrategyJSON:
    """
    Convert AST node to JSON-serializable dict.

    The JSON format preserves full type information for reconstruction:
    - Literal: {"type": "literal", "value": ...}
    - Symbol: {"type": "symbol", "name": "..."}
    - Keyword: {"type": "keyword", "name": "..."}
    - FunctionCall: {"type": "function", "name": "...", "args": [...]}
    - Strategy: {"type": "strategy", ...all fields...}
    """
    if isinstance(node, Strategy):
        return _strategy_to_json(node)

    return _node_to_json(node)


def _node_to_json(node: ASTNode) -> ASTNodeJSON:
    """Convert a single AST node to JSON."""
    match node:
        case Literal(value=value):
            return {"type": "literal", "value": value}

        case Symbol(name=name):
            return {"type": "symbol", "name": name}

        case Keyword(name=name):
            return {"type": "keyword", "name": name}

        case FunctionCall(name=name, args=args):
            return {
                "type": "function",
                "name": name,
                "args": [_node_to_json(arg) for arg in args],
            }

        case _:
            raise TypeError(f"Cannot convert to JSON: {type(node)}")


def _strategy_to_json(strategy: Strategy) -> StrategyJSON:
    """Convert Strategy to JSON."""
    return {
        "type": "strategy",
        "name": strategy.name,
        "description": strategy.description,
        "strategy_type": strategy.strategy_type,
        "symbols": strategy.symbols,
        "timeframe": strategy.timeframe,
        "entry": _node_to_json(strategy.entry),
        "exit": _node_to_json(strategy.exit),
        "sizing": strategy.sizing,
        "risk": strategy.risk,
    }


def from_json(data: ASTNodeJSON | StrategyJSON) -> ASTNode | Strategy:
    """
    Reconstruct AST node from JSON dict.

    Inverse of to_json().
    """
    node_type = data.get("type")

    if node_type == "strategy":
        return _strategy_from_json(data)

    return _node_from_json(data)


def _node_from_json(data: ASTNodeJSON) -> ASTNode:
    """Reconstruct a single AST node from JSON."""
    node_type = data.get("type")

    match node_type:
        case "literal":
            return Literal(data["value"])

        case "symbol":
            return Symbol(data["name"])

        case "keyword":
            return Keyword(data["name"])

        case "function":
            args = tuple(_node_from_json(arg) for arg in data.get("args", []))
            return FunctionCall(data["name"], args)

        case _:
            raise ValueError(f"Unknown node type: {node_type}")


def _strategy_from_json(data: StrategyJSON) -> Strategy:
    """Reconstruct Strategy from JSON."""
    return Strategy(
        name=data["name"],
        description=data.get("description"),
        strategy_type=data.get("strategy_type", "custom"),
        symbols=data["symbols"],
        timeframe=data["timeframe"],
        entry=_node_from_json(data["entry"]),
        exit=_node_from_json(data["exit"]),
        sizing=data.get("sizing", SizingConfig(type="percent-equity", value=10)),
        risk=data.get("risk", RiskConfig()),
    )
