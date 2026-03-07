"""Tests for allocation-based strategy DSL serializer."""

import pytest

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
    serialize,
)


class TestSerializeAsset:
    """Test serialization of asset blocks."""

    def test_serialize_asset_simple(self):
        asset = Asset(symbol="VTI")
        strategy = Strategy(name="Test", children=[asset])
        result = serialize(strategy)
        assert "(asset VTI)" in result

    def test_serialize_asset_with_weight(self):
        asset = Asset(symbol="VTI", weight=60)
        strategy = Strategy(name="Test", children=[asset])
        result = serialize(strategy)
        assert "(asset VTI :weight 60)" in result

    def test_serialize_asset_with_decimal_weight(self):
        asset = Asset(symbol="VTI", weight=33.33)
        strategy = Strategy(name="Test", children=[asset])
        result = serialize(strategy)
        assert "(asset VTI :weight 33.33)" in result


class TestSerializeWeight:
    """Test serialization of weight blocks."""

    def test_serialize_equal_weight(self):
        weight = Weight(
            method="equal",
            children=[Asset(symbol="VTI"), Asset(symbol="BND")],
        )
        strategy = Strategy(name="Test", children=[weight])
        result = serialize(strategy)
        assert "(weight :method equal" in result
        assert "(asset VTI)" in result
        assert "(asset BND)" in result

    def test_serialize_specified_weight(self):
        weight = Weight(
            method="specified",
            children=[
                Asset(symbol="VTI", weight=60),
                Asset(symbol="BND", weight=40),
            ],
        )
        strategy = Strategy(name="Test", children=[weight])
        result = serialize(strategy)
        assert "(weight :method specified" in result
        assert "(asset VTI :weight 60)" in result
        assert "(asset BND :weight 40)" in result

    def test_serialize_momentum_weight(self):
        weight = Weight(
            method="momentum",
            lookback=90,
            children=[Asset(symbol="XLK"), Asset(symbol="XLF")],
        )
        strategy = Strategy(name="Test", children=[weight])
        result = serialize(strategy)
        assert "(weight :method momentum :lookback 90" in result

    def test_serialize_momentum_with_top(self):
        weight = Weight(
            method="momentum",
            lookback=60,
            top=3,
            children=[
                Asset(symbol="XLK"),
                Asset(symbol="XLF"),
                Asset(symbol="XLE"),
                Asset(symbol="XLV"),
            ],
        )
        strategy = Strategy(name="Test", children=[weight])
        result = serialize(strategy)
        assert ":lookback 60" in result
        assert ":top 3" in result


class TestSerializeGroup:
    """Test serialization of group blocks."""

    def test_serialize_simple_group(self):
        group = Group(
            name="Equities",
            children=[
                Weight(
                    method="equal",
                    children=[Asset(symbol="VTI"), Asset(symbol="VXUS")],
                )
            ],
        )
        strategy = Strategy(name="Test", children=[group])
        result = serialize(strategy)
        assert '(group "Equities"' in result

    def test_serialize_nested_groups(self):
        inner = Group(name="Large Cap", children=[Asset(symbol="VTI", weight=100)])
        outer = Group(name="US", children=[inner])
        strategy = Strategy(name="Test", children=[outer])
        result = serialize(strategy)
        assert '(group "US"' in result
        assert '(group "Large Cap"' in result


class TestSerializeIf:
    """Test serialization of if blocks."""

    def test_serialize_simple_if(self):
        if_block = If(
            condition=Comparison(
                operator=">",
                left=Indicator(name="sma", symbol="SPY", params=(50,)),
                right=Indicator(name="sma", symbol="SPY", params=(200,)),
            ),
            then_block=Weight(method="equal", children=[Asset(symbol="VTI")]),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(if (> (sma SPY 50) (sma SPY 200))" in result

    def test_serialize_if_else(self):
        if_block = If(
            condition=Comparison(
                operator=">",
                left=Indicator(name="sma", symbol="SPY", params=(50,)),
                right=Indicator(name="sma", symbol="SPY", params=(200,)),
            ),
            then_block=Asset(symbol="VTI", weight=100),
            else_block=Asset(symbol="BND", weight=100),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(else" in result
        assert "(asset BND" in result

    def test_serialize_crossover_condition(self):
        if_block = If(
            condition=Crossover(
                direction="above",
                fast=Indicator(name="sma", symbol="SPY", params=(50,)),
                slow=Indicator(name="sma", symbol="SPY", params=(200,)),
            ),
            then_block=Asset(symbol="VTI", weight=100),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(crosses-above" in result

    def test_serialize_logical_condition(self):
        if_block = If(
            condition=LogicalOp(
                operator="and",
                operands=(
                    Comparison(
                        operator=">",
                        left=Indicator(name="sma", symbol="SPY", params=(50,)),
                        right=Indicator(name="sma", symbol="SPY", params=(200,)),
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
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(and" in result
        assert "(> (sma SPY 50) (sma SPY 200))" in result
        assert "(< (rsi SPY 14) 70)" in result


class TestSerializeFilter:
    """Test serialization of filter blocks."""

    def test_serialize_simple_filter(self):
        filter_block = Filter(
            by="momentum",
            select_direction="top",
            select_count=3,
            children=[
                Weight(
                    method="equal",
                    children=[
                        Asset(symbol="XLK"),
                        Asset(symbol="XLF"),
                        Asset(symbol="XLE"),
                    ],
                )
            ],
        )
        strategy = Strategy(name="Test", children=[filter_block])
        result = serialize(strategy)
        assert "(filter :by momentum :select (top 3)" in result

    def test_serialize_filter_with_lookback(self):
        filter_block = Filter(
            by="momentum",
            select_direction="bottom",
            select_count=2,
            lookback=60,
            children=[Asset(symbol="XLK"), Asset(symbol="XLF")],
        )
        strategy = Strategy(name="Test", children=[filter_block])
        result = serialize(strategy)
        assert ":select (bottom 2)" in result
        assert ":lookback 60" in result


class TestSerializeStrategy:
    """Test serialization of strategy blocks."""

    def test_serialize_minimal_strategy(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="equal",
                    children=[Asset(symbol="VTI"), Asset(symbol="BND")],
                )
            ],
        )
        result = serialize(strategy)
        assert '(strategy "Test"' in result

    def test_serialize_strategy_with_rebalance(self):
        strategy = Strategy(
            name="My Portfolio",
            rebalance="monthly",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = serialize(strategy)
        assert ":rebalance monthly" in result

    def test_serialize_strategy_with_benchmark(self):
        strategy = Strategy(
            name="Test",
            benchmark="SPY",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = serialize(strategy)
        assert ":benchmark SPY" in result

    def test_serialize_strategy_with_description(self):
        strategy = Strategy(
            name="Test",
            description="A test strategy",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = serialize(strategy)
        assert ':description "A test strategy"' in result

    def test_serialize_strategy_with_all_options(self):
        strategy = Strategy(
            name="Complete",
            rebalance="quarterly",
            benchmark="SPY",
            description="Full test",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = serialize(strategy)
        assert ":rebalance quarterly" in result
        assert ":benchmark SPY" in result
        assert ':description "Full test"' in result


class TestSerializeValues:
    """Test serialization of value expressions."""

    def test_serialize_numeric_literal(self):
        if_block = If(
            condition=Comparison(
                operator=">",
                left=Indicator(name="rsi", symbol="SPY", params=(14,)),
                right=NumericLiteral(value=70),
            ),
            then_block=Asset(symbol="VTI", weight=100),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "70)" in result

    def test_serialize_price(self):
        if_block = If(
            condition=Comparison(
                operator=">",
                left=Price(symbol="SPY"),
                right=NumericLiteral(value=100),
            ),
            then_block=Asset(symbol="VTI", weight=100),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(price SPY)" in result

    def test_serialize_price_with_field(self):
        if_block = If(
            condition=Comparison(
                operator=">",
                left=Price(symbol="SPY", field="high"),
                right=NumericLiteral(value=100),
            ),
            then_block=Asset(symbol="VTI", weight=100),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(price SPY :high)" in result

    def test_serialize_indicator(self):
        if_block = If(
            condition=Comparison(
                operator=">",
                left=Indicator(name="sma", symbol="SPY", params=(50,)),
                right=Indicator(name="sma", symbol="SPY", params=(200,)),
            ),
            then_block=Asset(symbol="VTI", weight=100),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(sma SPY 50)" in result
        assert "(sma SPY 200)" in result

    def test_serialize_indicator_with_output(self):
        if_block = If(
            condition=Comparison(
                operator=">",
                left=Indicator(name="macd", symbol="SPY", params=(12, 26, 9), output="signal"),
                right=NumericLiteral(value=0),
            ),
            then_block=Asset(symbol="VTI", weight=100),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(macd SPY 12 26 9 :signal)" in result

    def test_serialize_metric(self):
        if_block = If(
            condition=Comparison(
                operator="<",
                left=Metric(name="drawdown", symbol="SPY"),
                right=NumericLiteral(value=0.10),
            ),
            then_block=Asset(symbol="VTI", weight=100),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(drawdown SPY)" in result

    def test_serialize_metric_with_period(self):
        if_block = If(
            condition=Comparison(
                operator=">",
                left=Metric(name="momentum", symbol="SPY", period=90),
                right=NumericLiteral(value=0),
            ),
            then_block=Asset(symbol="VTI", weight=100),
        )
        strategy = Strategy(name="Test", children=[if_block])
        result = serialize(strategy)
        assert "(momentum SPY 90)" in result


class TestSerializePretty:
    """Test pretty-printing serialization."""

    def test_pretty_strategy(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="equal",
                    children=[Asset(symbol="VTI"), Asset(symbol="BND")],
                )
            ],
        )
        result = serialize(strategy, pretty=True)
        assert "\n" in result
        assert result.startswith("(strategy\n")

    def test_pretty_nested_groups(self):
        strategy = Strategy(
            name="Test",
            children=[
                Group(
                    name="Equities",
                    children=[
                        Weight(
                            method="specified",
                            children=[
                                Asset(symbol="VTI", weight=60),
                                Asset(symbol="VXUS", weight=40),
                            ],
                        )
                    ],
                )
            ],
        )
        result = serialize(strategy, pretty=True)
        lines = result.split("\n")
        # Check indentation
        assert any("  " in line for line in lines)


class TestSerializeRoundtrip:
    """Test that parsing then serializing produces equivalent results."""

    @pytest.mark.parametrize(
        "source",
        [
            '(strategy "Test" (asset VTI :weight 100))',
            '(strategy "Test" (weight :method equal (asset VTI) (asset BND)))',
            '(strategy "Test" :rebalance monthly (asset VTI :weight 100))',
            '(strategy "Test" :benchmark SPY (asset VTI :weight 100))',
            '(strategy "Test" (group "Equities" (asset VTI :weight 100)))',
            '(strategy "Test" (weight :method momentum :lookback 90 (asset XLK) (asset XLF)))',
        ],
    )
    def test_roundtrip_simple(self, source: str):
        """Parse, serialize, parse again should give equivalent AST."""
        original = parse(source)
        serialized = serialize(original)
        reparsed = parse(serialized)

        assert original.name == reparsed.name
        assert original.rebalance == reparsed.rebalance
        assert original.benchmark == reparsed.benchmark
        assert len(original.children) == len(reparsed.children)

    def test_roundtrip_complex_strategy(self):
        source = """
        (strategy "Dual Moving Average"
          :rebalance daily
          :benchmark SPY
          (if (> (sma SPY 50) (sma SPY 200))
            (group "Risk On"
              (weight :method specified
                (asset VTI :weight 60)
                (asset VXUS :weight 40)))
            (else
              (group "Risk Off"
                (weight :method equal
                  (asset BND)
                  (asset SHY))))))
        """
        original = parse(source)
        serialized = serialize(original)
        reparsed = parse(serialized)

        assert original.name == reparsed.name
        assert original.rebalance == reparsed.rebalance
        assert original.benchmark == reparsed.benchmark

    def test_roundtrip_all_weather(self):
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
        serialized = serialize(original)
        reparsed = parse(serialized)

        assert original.name == reparsed.name
        assert len(original.children) == 3
        assert len(reparsed.children) == 3


class TestSerializeEscaping:
    """Test string escaping in serialization."""

    def test_escape_quotes_in_name(self):
        strategy = Strategy(
            name='Test "Strategy"',
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = serialize(strategy)
        assert '\\"Strategy\\"' in result

    def test_escape_backslash(self):
        strategy = Strategy(
            name="Test\\Strategy",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = serialize(strategy)
        assert "\\\\" in result

    def test_escape_newline(self):
        strategy = Strategy(
            name="Test",
            description="Line1\nLine2",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = serialize(strategy)
        assert "\\n" in result
