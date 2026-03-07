"""Convert allocation strategy AST to/from JSON for database storage."""

from __future__ import annotations

from typing import Any, TypedDict, cast

from llamatrade_dsl.ast import (
    Asset,
    Block,
    Comparison,
    ComparisonOperator,
    Condition,
    Crossover,
    CrossoverDirection,
    Filter,
    FilterCriteria,
    Group,
    If,
    Indicator,
    LogicalOp,
    LogicalOperator,
    Metric,
    NumericLiteral,
    Price,
    PriceField,
    RebalanceFrequency,
    SelectDirection,
    Strategy,
    Value,
    Weight,
    WeightMethod,
)

# =============================================================================
# JSON Type Definitions
# =============================================================================


class NumericLiteralJSON(TypedDict):
    type: str  # "numeric"
    value: float


class PriceJSON(TypedDict, total=False):
    type: str  # "price"
    symbol: str
    field: str  # "close", "open", "high", "low", "volume"


class IndicatorJSON(TypedDict, total=False):
    type: str  # "indicator"
    name: str
    symbol: str
    params: list[int | float]
    output: str | None


class MetricJSON(TypedDict, total=False):
    type: str  # "metric"
    name: str
    symbol: str
    period: int | None


ValueJSON = NumericLiteralJSON | PriceJSON | IndicatorJSON | MetricJSON


class ComparisonJSON(TypedDict):
    type: str  # "comparison"
    operator: str
    left: ValueJSON
    right: ValueJSON


class CrossoverJSON(TypedDict):
    type: str  # "crossover"
    direction: str  # "above" | "below"
    fast: ValueJSON
    slow: ValueJSON


class LogicalOpJSON(TypedDict):
    type: str  # "logical"
    operator: str  # "and" | "or" | "not"
    operands: list[ConditionJSON]


ConditionJSON = ComparisonJSON | CrossoverJSON | LogicalOpJSON


class AssetJSON(TypedDict, total=False):
    type: str  # "asset"
    symbol: str
    weight: float | None


class WeightJSON(TypedDict, total=False):
    type: str  # "weight"
    method: str
    lookback: int | None
    top: int | None
    children: list[BlockJSON]


class GroupJSON(TypedDict, total=False):
    type: str  # "group"
    name: str
    children: list[BlockJSON]


class IfJSON(TypedDict, total=False):
    type: str  # "if"
    condition: ConditionJSON
    then: BlockJSON
    else_block: BlockJSON | None


class FilterJSON(TypedDict, total=False):
    type: str  # "filter"
    by: str
    select_direction: str
    select_count: int
    lookback: int | None
    children: list[BlockJSON]


class StrategyJSON(TypedDict, total=False):
    type: str  # "strategy"
    name: str
    rebalance: str | None
    benchmark: str | None
    description: str | None
    children: list[BlockJSON]


BlockJSON = StrategyJSON | GroupJSON | WeightJSON | AssetJSON | IfJSON | FilterJSON


# =============================================================================
# To JSON Functions
# =============================================================================


def to_json(strategy: Strategy) -> StrategyJSON:
    """Convert Strategy AST to JSON-serializable dict."""
    return _strategy_to_json(strategy)


def _strategy_to_json(strategy: Strategy) -> StrategyJSON:
    """Convert Strategy to JSON."""
    result: StrategyJSON = {
        "type": "strategy",
        "name": strategy.name,
        "children": [_block_to_json(c) for c in strategy.children],
    }

    if strategy.rebalance:
        result["rebalance"] = strategy.rebalance
    if strategy.benchmark:
        result["benchmark"] = strategy.benchmark
    if strategy.description:
        result["description"] = strategy.description

    return result


def _block_to_json(block: Block) -> BlockJSON:
    """Convert any block to JSON."""
    match block:
        case Strategy():
            return _strategy_to_json(block)
        case Group():
            return _group_to_json(block)
        case Weight():
            return _weight_to_json(block)
        case Asset():
            return _asset_to_json(block)
        case If():
            return _if_to_json(block)
        case Filter():
            return _filter_to_json(block)
        case _:
            raise TypeError(f"Cannot convert to JSON: {type(block)}")


def _group_to_json(group: Group) -> GroupJSON:
    """Convert Group to JSON."""
    return {
        "type": "group",
        "name": group.name,
        "children": [_block_to_json(c) for c in group.children],
    }


def _weight_to_json(weight: Weight) -> WeightJSON:
    """Convert Weight to JSON."""
    result: WeightJSON = {
        "type": "weight",
        "method": weight.method,
        "children": [_block_to_json(c) for c in weight.children],
    }

    if weight.lookback is not None:
        result["lookback"] = weight.lookback
    if weight.top is not None:
        result["top"] = weight.top

    return result


def _asset_to_json(asset: Asset) -> AssetJSON:
    """Convert Asset to JSON."""
    result: AssetJSON = {
        "type": "asset",
        "symbol": asset.symbol,
    }

    if asset.weight is not None:
        result["weight"] = asset.weight

    return result


def _if_to_json(if_block: If) -> IfJSON:
    """Convert If to JSON."""
    result: IfJSON = {
        "type": "if",
        "condition": _condition_to_json(if_block.condition),
        "then": _block_to_json(if_block.then_block),
    }

    if if_block.else_block is not None:
        result["else_block"] = _block_to_json(if_block.else_block)

    return result


def _filter_to_json(filter_block: Filter) -> FilterJSON:
    """Convert Filter to JSON."""
    result: FilterJSON = {
        "type": "filter",
        "by": filter_block.by,
        "select_direction": filter_block.select_direction,
        "select_count": filter_block.select_count,
        "children": [_block_to_json(c) for c in filter_block.children],
    }

    if filter_block.lookback is not None:
        result["lookback"] = filter_block.lookback

    return result


def _condition_to_json(condition: Condition) -> ConditionJSON:
    """Convert Condition to JSON."""
    match condition:
        case Comparison():
            return {
                "type": "comparison",
                "operator": condition.operator,
                "left": _value_to_json(condition.left),
                "right": _value_to_json(condition.right),
            }

        case Crossover():
            return {
                "type": "crossover",
                "direction": condition.direction,
                "fast": _value_to_json(condition.fast),
                "slow": _value_to_json(condition.slow),
            }

        case LogicalOp():
            return {
                "type": "logical",
                "operator": condition.operator,
                "operands": [_condition_to_json(op) for op in condition.operands],
            }

        case _:
            raise TypeError(f"Cannot convert condition to JSON: {type(condition)}")


def _value_to_json(value: Value) -> ValueJSON:
    """Convert Value to JSON."""
    match value:
        case NumericLiteral():
            return {"type": "numeric", "value": value.value}

        case Price():
            result: PriceJSON = {"type": "price", "symbol": value.symbol}
            if value.field != "close":
                result["field"] = value.field
            return result

        case Indicator():
            result_ind: IndicatorJSON = {
                "type": "indicator",
                "name": value.name,
                "symbol": value.symbol,
            }
            if value.params:
                result_ind["params"] = list(value.params)
            if value.output:
                result_ind["output"] = value.output
            return result_ind

        case Metric():
            result_met: MetricJSON = {
                "type": "metric",
                "name": value.name,
                "symbol": value.symbol,
            }
            if value.period is not None:
                result_met["period"] = value.period
            return result_met

        case _:
            raise TypeError(f"Cannot convert value to JSON: {type(value)}")


# =============================================================================
# From JSON Functions
# =============================================================================


def from_json(data: StrategyJSON) -> Strategy:
    """Reconstruct Strategy AST from JSON dict."""
    return _strategy_from_json(cast(dict[str, Any], data))


def _strategy_from_json(data: dict[str, Any]) -> Strategy:
    """Reconstruct Strategy from JSON."""
    return Strategy(
        name=data["name"],
        children=[_block_from_json(c) for c in data.get("children", [])],
        rebalance=cast(RebalanceFrequency | None, data.get("rebalance")),
        benchmark=data.get("benchmark"),
        description=data.get("description"),
    )


def _block_from_json(data: dict[str, Any]) -> Block:
    """Reconstruct any block from JSON."""
    block_type = data.get("type")

    match block_type:
        case "strategy":
            return _strategy_from_json(data)
        case "group":
            return _group_from_json(data)
        case "weight":
            return _weight_from_json(data)
        case "asset":
            return _asset_from_json(data)
        case "if":
            return _if_from_json(data)
        case "filter":
            return _filter_from_json(data)
        case _:
            raise ValueError(f"Unknown block type: {block_type}")


def _group_from_json(data: dict[str, Any]) -> Group:
    """Reconstruct Group from JSON."""
    return Group(
        name=data["name"],
        children=[_block_from_json(c) for c in data.get("children", [])],
    )


def _weight_from_json(data: dict[str, Any]) -> Weight:
    """Reconstruct Weight from JSON."""
    return Weight(
        method=cast(WeightMethod, data["method"]),
        children=[_block_from_json(c) for c in data.get("children", [])],
        lookback=data.get("lookback"),
        top=data.get("top"),
    )


def _asset_from_json(data: dict[str, Any]) -> Asset:
    """Reconstruct Asset from JSON."""
    return Asset(
        symbol=data["symbol"],
        weight=data.get("weight"),
    )


def _if_from_json(data: dict[str, Any]) -> If:
    """Reconstruct If from JSON."""
    return If(
        condition=_condition_from_json(data["condition"]),
        then_block=_block_from_json(data["then"]),
        else_block=_block_from_json(data["else_block"]) if data.get("else_block") else None,
    )


def _filter_from_json(data: dict[str, Any]) -> Filter:
    """Reconstruct Filter from JSON."""
    return Filter(
        by=cast(FilterCriteria, data["by"]),
        select_direction=cast(SelectDirection, data["select_direction"]),
        select_count=data["select_count"],
        children=[_block_from_json(c) for c in data.get("children", [])],
        lookback=data.get("lookback"),
    )


def _condition_from_json(data: dict[str, Any]) -> Condition:
    """Reconstruct Condition from JSON."""
    cond_type = data.get("type")

    match cond_type:
        case "comparison":
            return Comparison(
                operator=cast(ComparisonOperator, data["operator"]),
                left=_value_from_json(data["left"]),
                right=_value_from_json(data["right"]),
            )

        case "crossover":
            return Crossover(
                direction=cast(CrossoverDirection, data["direction"]),
                fast=_value_from_json(data["fast"]),
                slow=_value_from_json(data["slow"]),
            )

        case "logical":
            return LogicalOp(
                operator=cast(LogicalOperator, data["operator"]),
                operands=tuple(_condition_from_json(op) for op in data["operands"]),
            )

        case _:
            raise ValueError(f"Unknown condition type: {cond_type}")


def _value_from_json(data: dict[str, Any]) -> Value:
    """Reconstruct Value from JSON."""
    value_type = data.get("type")

    match value_type:
        case "numeric":
            return NumericLiteral(value=data["value"])

        case "price":
            return Price(
                symbol=data["symbol"],
                field=cast(PriceField, data.get("field", "close")),
            )

        case "indicator":
            return Indicator(
                name=data["name"],
                symbol=data["symbol"],
                params=tuple(data.get("params", [])),
                output=data.get("output"),
            )

        case "metric":
            return Metric(
                name=data["name"],
                symbol=data["symbol"],
                period=data.get("period"),
            )

        case _:
            raise ValueError(f"Unknown value type: {value_type}")
