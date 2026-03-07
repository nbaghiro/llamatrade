"""Tests for allocation-based strategy DSL JSON conversion."""

import json

from llamatrade_dsl import (
    Asset,
    Comparison,
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
    Weight,
    parse,
)
from llamatrade_dsl.to_json import from_json, to_json


class TestToJsonStrategy:
    """Test strategy to JSON conversion."""

    def test_minimal_strategy_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = to_json(strategy)

        assert result["type"] == "strategy"
        assert result["name"] == "Test"
        assert len(result["children"]) == 1

    def test_strategy_with_all_options(self):
        strategy = Strategy(
            name="Complete",
            rebalance="quarterly",
            benchmark="SPY",
            description="A complete strategy",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = to_json(strategy)

        assert result["name"] == "Complete"
        assert result["rebalance"] == "quarterly"
        assert result["benchmark"] == "SPY"
        assert result["description"] == "A complete strategy"


class TestToJsonAsset:
    """Test asset to JSON conversion."""

    def test_simple_asset_to_json(self):
        strategy = Strategy(name="Test", children=[Asset(symbol="VTI")])
        result = to_json(strategy)

        asset = result["children"][0]
        assert asset["type"] == "asset"
        assert asset["symbol"] == "VTI"
        assert "weight" not in asset

    def test_asset_with_weight_to_json(self):
        strategy = Strategy(name="Test", children=[Asset(symbol="VTI", weight=60)])
        result = to_json(strategy)

        asset = result["children"][0]
        assert asset["weight"] == 60


class TestToJsonWeight:
    """Test weight block to JSON conversion."""

    def test_equal_weight_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="equal",
                    children=[Asset(symbol="VTI"), Asset(symbol="BND")],
                )
            ],
        )
        result = to_json(strategy)

        weight = result["children"][0]
        assert weight["type"] == "weight"
        assert weight["method"] == "equal"
        assert len(weight["children"]) == 2

    def test_momentum_weight_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="momentum",
                    lookback=90,
                    top=3,
                    children=[Asset(symbol="XLK"), Asset(symbol="XLF")],
                )
            ],
        )
        result = to_json(strategy)

        weight = result["children"][0]
        assert weight["method"] == "momentum"
        assert weight["lookback"] == 90
        assert weight["top"] == 3


class TestToJsonGroup:
    """Test group block to JSON conversion."""

    def test_simple_group_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[Group(name="Equities", children=[Asset(symbol="VTI", weight=100)])],
        )
        result = to_json(strategy)

        group = result["children"][0]
        assert group["type"] == "group"
        assert group["name"] == "Equities"
        assert len(group["children"]) == 1


class TestToJsonIf:
    """Test if block to JSON conversion."""

    def test_simple_if_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Indicator(name="sma", symbol="SPY", params=(50,)),
                        right=Indicator(name="sma", symbol="SPY", params=(200,)),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        if_block = result["children"][0]
        assert if_block["type"] == "if"
        assert if_block["condition"]["type"] == "comparison"
        assert if_block["then"]["type"] == "asset"
        assert "else_block" not in if_block

    def test_if_else_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Price(symbol="SPY"),
                        right=NumericLiteral(value=100),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                    else_block=Asset(symbol="BND", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        if_block = result["children"][0]
        assert if_block["else_block"]["type"] == "asset"


class TestToJsonFilter:
    """Test filter block to JSON conversion."""

    def test_filter_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                Filter(
                    by="momentum",
                    select_direction="top",
                    select_count=3,
                    lookback=90,
                    children=[Asset(symbol="XLK"), Asset(symbol="XLF")],
                )
            ],
        )
        result = to_json(strategy)

        filter_block = result["children"][0]
        assert filter_block["type"] == "filter"
        assert filter_block["by"] == "momentum"
        assert filter_block["select_direction"] == "top"
        assert filter_block["select_count"] == 3
        assert filter_block["lookback"] == 90


class TestToJsonConditions:
    """Test condition to JSON conversion."""

    def test_comparison_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Indicator(name="rsi", symbol="SPY", params=(14,)),
                        right=NumericLiteral(value=70),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        cond = result["children"][0]["condition"]
        assert cond["type"] == "comparison"
        assert cond["operator"] == ">"
        assert cond["left"]["type"] == "indicator"
        assert cond["right"]["type"] == "numeric"

    def test_crossover_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Crossover(
                        direction="above",
                        fast=Indicator(name="sma", symbol="SPY", params=(50,)),
                        slow=Indicator(name="sma", symbol="SPY", params=(200,)),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        cond = result["children"][0]["condition"]
        assert cond["type"] == "crossover"
        assert cond["direction"] == "above"
        assert cond["fast"]["type"] == "indicator"
        assert cond["slow"]["type"] == "indicator"

    def test_logical_op_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=LogicalOp(
                        operator="and",
                        operands=(
                            Comparison(
                                operator=">",
                                left=Price(symbol="SPY"),
                                right=NumericLiteral(value=100),
                            ),
                            Comparison(
                                operator="<",
                                left=Indicator(name="rsi", symbol="SPY", params=(14,)),
                                right=NumericLiteral(value=70),
                            ),
                        ),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        cond = result["children"][0]["condition"]
        assert cond["type"] == "logical"
        assert cond["operator"] == "and"
        assert len(cond["operands"]) == 2


class TestToJsonValues:
    """Test value to JSON conversion."""

    def test_numeric_literal_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Price(symbol="SPY"),
                        right=NumericLiteral(value=100.5),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        value = result["children"][0]["condition"]["right"]
        assert value["type"] == "numeric"
        assert value["value"] == 100.5

    def test_price_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Price(symbol="SPY", field="high"),
                        right=NumericLiteral(value=100),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        value = result["children"][0]["condition"]["left"]
        assert value["type"] == "price"
        assert value["symbol"] == "SPY"
        assert value["field"] == "high"

    def test_price_default_field_not_in_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Price(symbol="SPY"),  # default field is "close"
                        right=NumericLiteral(value=100),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        value = result["children"][0]["condition"]["left"]
        assert "field" not in value  # default "close" is omitted

    def test_indicator_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Indicator(
                            name="macd", symbol="SPY", params=(12, 26, 9), output="signal"
                        ),
                        right=NumericLiteral(value=0),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        value = result["children"][0]["condition"]["left"]
        assert value["type"] == "indicator"
        assert value["name"] == "macd"
        assert value["symbol"] == "SPY"
        assert value["params"] == [12, 26, 9]
        assert value["output"] == "signal"

    def test_metric_to_json(self):
        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator="<",
                        left=Metric(name="drawdown", symbol="SPY", period=90),
                        right=NumericLiteral(value=0.10),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = to_json(strategy)

        value = result["children"][0]["condition"]["left"]
        assert value["type"] == "metric"
        assert value["name"] == "drawdown"
        assert value["symbol"] == "SPY"
        assert value["period"] == 90


class TestFromJsonStrategy:
    """Test JSON to strategy conversion."""

    def test_minimal_strategy_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [{"type": "asset", "symbol": "VTI", "weight": 100}],
        }
        result = from_json(data)

        assert isinstance(result, Strategy)
        assert result.name == "Test"
        assert len(result.children) == 1

    def test_strategy_with_all_options_from_json(self):
        data = {
            "type": "strategy",
            "name": "Complete",
            "rebalance": "quarterly",
            "benchmark": "SPY",
            "description": "A complete strategy",
            "children": [{"type": "asset", "symbol": "VTI", "weight": 100}],
        }
        result = from_json(data)

        assert result.name == "Complete"
        assert result.rebalance == "quarterly"
        assert result.benchmark == "SPY"
        assert result.description == "A complete strategy"


class TestFromJsonAsset:
    """Test JSON to asset conversion."""

    def test_simple_asset_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [{"type": "asset", "symbol": "VTI"}],
        }
        result = from_json(data)

        asset = result.children[0]
        assert isinstance(asset, Asset)
        assert asset.symbol == "VTI"
        assert asset.weight is None

    def test_asset_with_weight_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [{"type": "asset", "symbol": "VTI", "weight": 60}],
        }
        result = from_json(data)

        asset = result.children[0]
        assert asset.weight == 60


class TestFromJsonWeight:
    """Test JSON to weight block conversion."""

    def test_equal_weight_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "weight",
                    "method": "equal",
                    "children": [
                        {"type": "asset", "symbol": "VTI"},
                        {"type": "asset", "symbol": "BND"},
                    ],
                }
            ],
        }
        result = from_json(data)

        weight = result.children[0]
        assert isinstance(weight, Weight)
        assert weight.method == "equal"
        assert len(weight.children) == 2

    def test_momentum_weight_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "weight",
                    "method": "momentum",
                    "lookback": 90,
                    "top": 3,
                    "children": [
                        {"type": "asset", "symbol": "XLK"},
                        {"type": "asset", "symbol": "XLF"},
                    ],
                }
            ],
        }
        result = from_json(data)

        weight = result.children[0]
        assert weight.method == "momentum"
        assert weight.lookback == 90
        assert weight.top == 3


class TestFromJsonGroup:
    """Test JSON to group block conversion."""

    def test_group_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "group",
                    "name": "Equities",
                    "children": [{"type": "asset", "symbol": "VTI", "weight": 100}],
                }
            ],
        }
        result = from_json(data)

        group = result.children[0]
        assert isinstance(group, Group)
        assert group.name == "Equities"


class TestFromJsonIf:
    """Test JSON to if block conversion."""

    def test_simple_if_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "if",
                    "condition": {
                        "type": "comparison",
                        "operator": ">",
                        "left": {
                            "type": "indicator",
                            "name": "sma",
                            "symbol": "SPY",
                            "params": [50],
                        },
                        "right": {
                            "type": "indicator",
                            "name": "sma",
                            "symbol": "SPY",
                            "params": [200],
                        },
                    },
                    "then": {"type": "asset", "symbol": "VTI", "weight": 100},
                }
            ],
        }
        result = from_json(data)

        if_block = result.children[0]
        assert isinstance(if_block, If)
        assert isinstance(if_block.condition, Comparison)
        assert if_block.else_block is None

    def test_if_else_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "if",
                    "condition": {
                        "type": "comparison",
                        "operator": ">",
                        "left": {"type": "price", "symbol": "SPY"},
                        "right": {"type": "numeric", "value": 100},
                    },
                    "then": {"type": "asset", "symbol": "VTI", "weight": 100},
                    "else_block": {"type": "asset", "symbol": "BND", "weight": 100},
                }
            ],
        }
        result = from_json(data)

        if_block = result.children[0]
        assert isinstance(if_block.else_block, Asset)


class TestFromJsonFilter:
    """Test JSON to filter block conversion."""

    def test_filter_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "filter",
                    "by": "momentum",
                    "select_direction": "top",
                    "select_count": 3,
                    "lookback": 90,
                    "children": [
                        {"type": "asset", "symbol": "XLK"},
                        {"type": "asset", "symbol": "XLF"},
                    ],
                }
            ],
        }
        result = from_json(data)

        filter_block = result.children[0]
        assert isinstance(filter_block, Filter)
        assert filter_block.by == "momentum"
        assert filter_block.select_direction == "top"
        assert filter_block.select_count == 3
        assert filter_block.lookback == 90


class TestFromJsonConditions:
    """Test JSON to condition conversion."""

    def test_crossover_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "if",
                    "condition": {
                        "type": "crossover",
                        "direction": "above",
                        "fast": {
                            "type": "indicator",
                            "name": "sma",
                            "symbol": "SPY",
                            "params": [50],
                        },
                        "slow": {
                            "type": "indicator",
                            "name": "sma",
                            "symbol": "SPY",
                            "params": [200],
                        },
                    },
                    "then": {"type": "asset", "symbol": "VTI", "weight": 100},
                }
            ],
        }
        result = from_json(data)

        cond = result.children[0].condition
        assert isinstance(cond, Crossover)
        assert cond.direction == "above"

    def test_logical_op_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "if",
                    "condition": {
                        "type": "logical",
                        "operator": "and",
                        "operands": [
                            {
                                "type": "comparison",
                                "operator": ">",
                                "left": {"type": "price", "symbol": "SPY"},
                                "right": {"type": "numeric", "value": 100},
                            },
                            {
                                "type": "comparison",
                                "operator": "<",
                                "left": {
                                    "type": "indicator",
                                    "name": "rsi",
                                    "symbol": "SPY",
                                    "params": [14],
                                },
                                "right": {"type": "numeric", "value": 70},
                            },
                        ],
                    },
                    "then": {"type": "asset", "symbol": "VTI", "weight": 100},
                }
            ],
        }
        result = from_json(data)

        cond = result.children[0].condition
        assert isinstance(cond, LogicalOp)
        assert cond.operator == "and"
        assert len(cond.operands) == 2


class TestFromJsonValues:
    """Test JSON to value conversion."""

    def test_price_with_field_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "if",
                    "condition": {
                        "type": "comparison",
                        "operator": ">",
                        "left": {"type": "price", "symbol": "SPY", "field": "high"},
                        "right": {"type": "numeric", "value": 100},
                    },
                    "then": {"type": "asset", "symbol": "VTI", "weight": 100},
                }
            ],
        }
        result = from_json(data)

        value = result.children[0].condition.left
        assert isinstance(value, Price)
        assert value.field == "high"

    def test_indicator_with_output_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "if",
                    "condition": {
                        "type": "comparison",
                        "operator": ">",
                        "left": {
                            "type": "indicator",
                            "name": "macd",
                            "symbol": "SPY",
                            "params": [12, 26, 9],
                            "output": "signal",
                        },
                        "right": {"type": "numeric", "value": 0},
                    },
                    "then": {"type": "asset", "symbol": "VTI", "weight": 100},
                }
            ],
        }
        result = from_json(data)

        value = result.children[0].condition.left
        assert isinstance(value, Indicator)
        assert value.output == "signal"

    def test_metric_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "children": [
                {
                    "type": "if",
                    "condition": {
                        "type": "comparison",
                        "operator": "<",
                        "left": {
                            "type": "metric",
                            "name": "drawdown",
                            "symbol": "SPY",
                            "period": 90,
                        },
                        "right": {"type": "numeric", "value": 0.10},
                    },
                    "then": {"type": "asset", "symbol": "VTI", "weight": 100},
                }
            ],
        }
        result = from_json(data)

        value = result.children[0].condition.left
        assert isinstance(value, Metric)
        assert value.period == 90


class TestJsonRoundtrip:
    """Test that AST -> JSON -> AST produces equivalent results."""

    def test_roundtrip_simple_strategy(self):
        strategy = Strategy(
            name="Test",
            rebalance="monthly",
            benchmark="SPY",
            children=[
                Weight(
                    method="equal",
                    children=[Asset(symbol="VTI"), Asset(symbol="BND")],
                )
            ],
        )

        json_data = to_json(strategy)
        reconstructed = from_json(json_data)

        assert strategy.name == reconstructed.name
        assert strategy.rebalance == reconstructed.rebalance
        assert strategy.benchmark == reconstructed.benchmark
        assert len(strategy.children) == len(reconstructed.children)

    def test_roundtrip_complex_strategy(self):
        strategy = Strategy(
            name="Dual Moving Average",
            rebalance="daily",
            benchmark="SPY",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Indicator(name="sma", symbol="SPY", params=(50,)),
                        right=Indicator(name="sma", symbol="SPY", params=(200,)),
                    ),
                    then_block=Group(
                        name="Risk On",
                        children=[
                            Weight(
                                method="specified",
                                children=[
                                    Asset(symbol="VTI", weight=60),
                                    Asset(symbol="VXUS", weight=40),
                                ],
                            )
                        ],
                    ),
                    else_block=Group(
                        name="Risk Off",
                        children=[
                            Weight(
                                method="equal",
                                children=[Asset(symbol="BND"), Asset(symbol="SHY")],
                            )
                        ],
                    ),
                )
            ],
        )

        json_data = to_json(strategy)
        reconstructed = from_json(json_data)

        assert strategy.name == reconstructed.name
        assert strategy.rebalance == reconstructed.rebalance
        assert isinstance(reconstructed.children[0], If)
        assert isinstance(reconstructed.children[0].then_block, Group)
        assert isinstance(reconstructed.children[0].else_block, Group)

    def test_roundtrip_parsed_strategy(self):
        source = """
        (strategy "All-Weather"
          :rebalance quarterly
          (group "Growth"
            (weight :method specified
              (asset VTI :weight 30)))
          (group "Inflation Protection"
            (weight :method specified
              (asset DBC :weight 7.5)
              (asset GLD :weight 7.5)))
          (group "Bonds"
            (weight :method specified
              (asset TLT :weight 40)
              (asset IEF :weight 15))))
        """
        original = parse(source)
        json_data = to_json(original)
        reconstructed = from_json(json_data)

        assert original.name == reconstructed.name
        assert original.rebalance == reconstructed.rebalance
        assert len(original.children) == len(reconstructed.children)


class TestJsonSerializable:
    """Test that to_json output is JSON-serializable."""

    def test_strategy_json_serializable(self):
        strategy = Strategy(
            name="Test",
            rebalance="monthly",
            benchmark="SPY",
            description="A test strategy",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Indicator(name="sma", symbol="SPY", params=(50,)),
                        right=Indicator(name="sma", symbol="SPY", params=(200,)),
                    ),
                    then_block=Weight(
                        method="specified",
                        children=[
                            Asset(symbol="VTI", weight=60),
                            Asset(symbol="BND", weight=40),
                        ],
                    ),
                )
            ],
        )

        json_data = to_json(strategy)

        # Should not raise
        serialized = json.dumps(json_data)
        assert isinstance(serialized, str)

        # Should be deserializable
        deserialized = json.loads(serialized)
        assert deserialized == json_data

    def test_complex_strategy_json_serializable(self):
        source = """
        (strategy "Dual Moving Average"
          :rebalance daily
          :benchmark SPY
          (if (and (> (sma SPY 50) (sma SPY 200)) (< (rsi SPY 14) 70))
            (group "Risk On"
              (weight :method specified
                (asset VTI :weight 60)
                (asset VXUS :weight 40)))
            (else
              (filter :by momentum :select (top 2) :lookback 60
                (weight :method equal
                  (asset BND)
                  (asset SHY)
                  (asset TLT))))))
        """
        strategy = parse(source)
        json_data = to_json(strategy)

        # Full roundtrip through JSON string
        serialized = json.dumps(json_data)
        deserialized = json.loads(serialized)
        reconstructed = from_json(deserialized)

        assert strategy.name == reconstructed.name
        assert strategy.rebalance == reconstructed.rebalance
        assert strategy.benchmark == reconstructed.benchmark
