"""Serialize allocation strategy AST back to S-expression string."""

from __future__ import annotations

from llamatrade_dsl.ast import (
    Asset,
    Block,
    Comparison,
    Condition,
    Crossover,
    Filter,
    Group,
    If,
    Indicator,
    LogicalOp,
    Metric,
    NumericLiteral,
    Price,
    Strategy,
    Value,
    Weight,
)


def serialize(strategy: Strategy, pretty: bool = False) -> str:
    """
    Serialize a Strategy AST back to S-expression string.

    Args:
        strategy: Strategy AST to serialize
        pretty: If True, format with newlines and indentation

    Returns:
        S-expression string representation
    """
    return _serialize_strategy(strategy, pretty, 0)


def _serialize_strategy(strategy: Strategy, pretty: bool, indent: int) -> str:
    """Serialize a Strategy node."""
    parts: list[str] = [f'"{_escape_string(strategy.name)}"']

    # Optional attributes
    if strategy.rebalance:
        parts.append(f":rebalance {strategy.rebalance}")
    if strategy.benchmark:
        parts.append(f":benchmark {strategy.benchmark}")
    if strategy.description:
        parts.append(f':description "{_escape_string(strategy.description)}"')

    if not pretty:
        # Compact format
        children = " ".join(_serialize_block(c, False, 0) for c in strategy.children)
        attrs = " ".join(parts)
        return f"(strategy {attrs} {children})"

    # Pretty format
    ind = " " * indent
    inner_ind = " " * (indent + 2)

    lines = [f"{ind}(strategy"]
    for part in parts:
        lines.append(f"{inner_ind}{part}")
    for child in strategy.children:
        lines.append(_serialize_block(child, True, indent + 2))
    lines.append(f"{ind})")

    return "\n".join(lines)


def _serialize_block(block: Block, pretty: bool, indent: int) -> str:
    """Serialize any block type."""
    match block:
        case Strategy():
            return _serialize_strategy(block, pretty, indent)
        case Group():
            return _serialize_group(block, pretty, indent)
        case Weight():
            return _serialize_weight(block, pretty, indent)
        case Asset():
            return _serialize_asset(block, pretty, indent)
        case If():
            return _serialize_if(block, pretty, indent)
        case Filter():
            return _serialize_filter(block, pretty, indent)
        case _:
            raise TypeError(f"Cannot serialize: {type(block)}")


def _serialize_group(group: Group, pretty: bool, indent: int) -> str:
    """Serialize a Group block."""
    if not pretty:
        children = " ".join(_serialize_block(c, False, 0) for c in group.children)
        return f'(group "{_escape_string(group.name)}" {children})'

    ind = " " * indent

    lines = [f'{ind}(group "{_escape_string(group.name)}"']
    for child in group.children:
        lines.append(_serialize_block(child, True, indent + 2))
    lines.append(f"{ind})")

    return "\n".join(lines)


def _serialize_weight(weight: Weight, pretty: bool, indent: int) -> str:
    """Serialize a Weight block."""
    attrs: list[str] = [f":method {weight.method}"]
    if weight.lookback is not None:
        attrs.append(f":lookback {weight.lookback}")
    if weight.top is not None:
        attrs.append(f":top {weight.top}")

    if not pretty:
        children = " ".join(_serialize_block(c, False, 0) for c in weight.children)
        return f"(weight {' '.join(attrs)} {children})"

    ind = " " * indent

    lines = [f"{ind}(weight {' '.join(attrs)}"]
    for child in weight.children:
        lines.append(_serialize_block(child, True, indent + 2))
    lines.append(f"{ind})")

    return "\n".join(lines)


def _serialize_asset(asset: Asset, pretty: bool, indent: int) -> str:
    """Serialize an Asset block."""
    ind = " " * indent if pretty else ""

    if asset.weight is not None:
        # Format weight nicely (no decimal if whole number)
        if asset.weight == int(asset.weight):
            weight_str = str(int(asset.weight))
        else:
            weight_str = str(asset.weight)
        return f"{ind}(asset {asset.symbol} :weight {weight_str})"

    return f"{ind}(asset {asset.symbol})"


def _serialize_if(if_block: If, pretty: bool, indent: int) -> str:
    """Serialize an If block."""
    cond = _serialize_condition(if_block.condition, False)
    then_block = _serialize_block(if_block.then_block, pretty, indent + 2 if pretty else 0)

    if not pretty:
        result = f"(if {cond} {then_block}"
        if if_block.else_block:
            else_block = _serialize_block(if_block.else_block, False, 0)
            result += f" (else {else_block})"
        result += ")"
        return result

    ind = " " * indent
    inner_ind = " " * (indent + 2)

    lines = [f"{ind}(if {cond}"]
    lines.append(then_block)
    if if_block.else_block:
        lines.append(f"{inner_ind}(else")
        lines.append(_serialize_block(if_block.else_block, True, indent + 4))
        lines.append(f"{inner_ind})")
    lines.append(f"{ind})")

    return "\n".join(lines)


def _serialize_filter(filter_block: Filter, pretty: bool, indent: int) -> str:
    """Serialize a Filter block."""
    attrs = [
        f":by {filter_block.by}",
        f":select ({filter_block.select_direction} {filter_block.select_count})",
    ]
    if filter_block.lookback is not None:
        attrs.append(f":lookback {filter_block.lookback}")

    if not pretty:
        children = " ".join(_serialize_block(c, False, 0) for c in filter_block.children)
        return f"(filter {' '.join(attrs)} {children})"

    ind = " " * indent

    lines = [f"{ind}(filter {' '.join(attrs)}"]
    for child in filter_block.children:
        lines.append(_serialize_block(child, True, indent + 2))
    lines.append(f"{ind})")

    return "\n".join(lines)


def _serialize_condition(condition: Condition, pretty: bool) -> str:
    """Serialize a condition expression."""
    match condition:
        case Comparison():
            left = _serialize_value(condition.left)
            right = _serialize_value(condition.right)
            return f"({condition.operator} {left} {right})"

        case Crossover():
            fast = _serialize_value(condition.fast)
            slow = _serialize_value(condition.slow)
            return f"(crosses-{condition.direction} {fast} {slow})"

        case LogicalOp():
            operands = " ".join(_serialize_condition(op, False) for op in condition.operands)
            return f"({condition.operator} {operands})"

        case _:
            raise TypeError(f"Cannot serialize condition: {type(condition)}")


def _serialize_value(value: Value) -> str:
    """Serialize a value expression."""
    match value:
        case NumericLiteral():
            # Format nicely (no decimal if whole number)
            if value.value == int(value.value):
                return str(int(value.value))
            return str(value.value)

        case Price():
            if value.field == "close":
                return f"(price {value.symbol})"
            return f"(price {value.symbol} :{value.field})"

        case Indicator():
            parts = [value.name, value.symbol]
            for param in value.params:
                if param == int(param):
                    parts.append(str(int(param)))
                else:
                    parts.append(str(param))
            if value.output:
                parts.append(f":{value.output}")
            return f"({' '.join(parts)})"

        case Metric():
            if value.period:
                return f"({value.name} {value.symbol} {value.period})"
            return f"({value.name} {value.symbol})"

        case _:
            raise TypeError(f"Cannot serialize value: {type(value)}")


def _escape_string(s: str) -> str:
    """Escape special characters in a string."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
