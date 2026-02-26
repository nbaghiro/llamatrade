"""Serialize AST back to S-expression string."""

from __future__ import annotations

from llamatrade_dsl.ast import (
    ASTNode,
    FunctionCall,
    Keyword,
    Literal,
    LiteralValue,
    Strategy,
    Symbol,
)


def serialize(node: ASTNode | Strategy, pretty: bool = False, indent: int = 0) -> str:
    """
    Serialize an AST node back to S-expression string.

    Args:
        node: AST node to serialize
        pretty: If True, format with newlines and indentation
        indent: Current indentation level (for pretty printing)

    Returns:
        S-expression string representation
    """
    if isinstance(node, Strategy):
        return _serialize_strategy(node, pretty, indent)

    return _serialize_node(node, pretty, indent)


def _serialize_node(node: ASTNode, pretty: bool = False, indent: int = 0) -> str:
    """Serialize a single AST node."""
    match node:
        case Literal(value=value):
            return _serialize_literal(value)

        case Symbol(name=name):
            return name

        case Keyword(name=name):
            return f":{name}"

        case FunctionCall(name=name, args=args):
            return _serialize_function(name, args, pretty, indent)

        case _:
            raise TypeError(f"Cannot serialize: {type(node)}")


def _serialize_literal(value: LiteralValue) -> str:
    """Serialize a literal value."""
    if isinstance(value, str):
        # Escape special characters
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, list):
        items = " ".join(_serialize_literal(item) for item in value)
        return f"[{items}]"

    if isinstance(value, dict):
        pairs = " ".join(f":{k} {_serialize_literal(v)}" for k, v in value.items())
        return f"{{{pairs}}}"

    if isinstance(value, (int, float)):
        return str(value)

    return str(value)


def _serialize_function(name: str, args: tuple[ASTNode, ...], pretty: bool, indent: int) -> str:
    """Serialize a function call."""
    if not args:
        return f"({name})"

    if not pretty:
        # Compact format
        args_str = " ".join(_serialize_node(arg, False, 0) for arg in args)
        return f"({name} {args_str})"

    # Pretty format - decide whether to inline or multiline
    args_strs = [_serialize_node(arg, True, indent + 2) for arg in args]
    total_len = len(name) + sum(len(s) for s in args_strs) + len(args) + 2

    if total_len < 60 and "\n" not in "".join(args_strs):
        # Inline if short enough
        return f"({name} {' '.join(args_strs)})"

    # Multiline
    ind = " " * indent
    inner_ind = " " * (indent + 2)
    lines = [f"({name}"]
    for arg_str in args_strs:
        lines.append(f"{inner_ind}{arg_str}")
    lines.append(f"{ind})")
    return "\n".join(lines)


def _serialize_strategy(strategy: Strategy, pretty: bool, indent: int) -> str:
    """Serialize a Strategy object to S-expression."""
    parts: list[str] = []
    ind = " " * 2 if pretty else ""

    # Name
    parts.append(f'{ind}:name "{strategy.name}"')

    # Description
    if strategy.description:
        escaped = strategy.description.replace('"', '\\"')
        parts.append(f'{ind}:description "{escaped}"')

    # Type
    if strategy.strategy_type != "custom":
        parts.append(f"{ind}:type {strategy.strategy_type}")

    # Symbols
    symbols_str = " ".join(f'"{s}"' for s in strategy.symbols)
    parts.append(f"{ind}:symbols [{symbols_str}]")

    # Timeframe
    parts.append(f'{ind}:timeframe "{strategy.timeframe}"')

    # Entry condition
    entry_str = _serialize_node(strategy.entry, pretty, 4 if pretty else 0)
    parts.append(f"{ind}:entry {entry_str}")

    # Exit condition
    exit_str = _serialize_node(strategy.exit, pretty, 4 if pretty else 0)
    parts.append(f"{ind}:exit {exit_str}")

    # Position sizing
    if strategy.sizing:
        size_val = strategy.sizing.get("value", 10)
        parts.append(f"{ind}:position-size {size_val}")

    # Risk config
    if strategy.risk:
        for key, value in strategy.risk.items():
            if value is not None:
                # Convert snake_case to kebab-case
                kebab_key = key.replace("_", "-")
                parts.append(f"{ind}:{kebab_key} {value}")

    if pretty:
        body = "\n".join(parts)
        return f"(strategy\n{body})"
    else:
        body = " ".join(parts)
        return f"(strategy {body})"
