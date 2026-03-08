"""Tests for allocation-based strategy DSL parser."""

import pytest

from llamatrade_dsl import (
    Comparison,
    Crossover,
    Filter,
    Group,
    If,
    Indicator,
    LogicalOp,
    Metric,
    NumericLiteral,
    ParseError,
    Price,
    SourceLocation,
    Strategy,
    Weight,
    parse,
    parse_strategy,
)


class TestParseSimpleStrategy:
    """Test parsing simple strategies."""

    def test_parse_minimal_strategy(self):
        source = '(strategy "Test" (weight :method equal (asset VTI) (asset BND)))'
        result = parse(source)

        assert isinstance(result, Strategy)
        assert result.name == "Test"
        assert len(result.children) == 1
        assert isinstance(result.children[0], Weight)

    def test_parse_strategy_with_rebalance(self):
        source = """
        (strategy "My Portfolio"
          :rebalance monthly
          (weight :method equal
            (asset VTI)
            (asset BND)))
        """
        result = parse(source)

        assert result.name == "My Portfolio"
        assert result.rebalance == "monthly"

    def test_parse_strategy_with_benchmark(self):
        source = """
        (strategy "Test"
          :benchmark SPY
          (weight :method equal (asset VTI)))
        """
        result = parse(source)

        assert result.benchmark == "SPY"

    def test_parse_strategy_with_all_options(self):
        source = """
        (strategy "Complete Strategy"
          :rebalance quarterly
          :benchmark SPY
          :description "A test strategy"
          (weight :method specified
            (asset VTI :weight 60)
            (asset BND :weight 40)))
        """
        result = parse(source)

        assert result.name == "Complete Strategy"
        assert result.rebalance == "quarterly"
        assert result.benchmark == "SPY"
        assert result.description == "A test strategy"


class TestParseWeightBlocks:
    """Test parsing weight blocks."""

    def test_parse_specified_weights(self):
        source = """
        (strategy "Test"
          (weight :method specified
            (asset VTI :weight 60)
            (asset BND :weight 40)))
        """
        result = parse(source)
        weight = result.children[0]

        assert isinstance(weight, Weight)
        assert weight.method == "specified"
        assert len(weight.children) == 2
        assert weight.children[0].weight == 60
        assert weight.children[1].weight == 40

    def test_parse_equal_weights(self):
        source = """
        (strategy "Test"
          (weight :method equal
            (asset VTI)
            (asset VXUS)
            (asset BND)))
        """
        result = parse(source)
        weight = result.children[0]

        assert weight.method == "equal"
        assert len(weight.children) == 3
        assert all(c.weight is None for c in weight.children)

    def test_parse_momentum_with_lookback(self):
        source = """
        (strategy "Test"
          (weight :method momentum :lookback 90
            (asset XLK)
            (asset XLF)))
        """
        result = parse(source)
        weight = result.children[0]

        assert weight.method == "momentum"
        assert weight.lookback == 90

    def test_parse_momentum_with_top(self):
        source = """
        (strategy "Test"
          (weight :method momentum :lookback 60 :top 3
            (asset XLK)
            (asset XLF)
            (asset XLE)
            (asset XLV)))
        """
        result = parse(source)
        weight = result.children[0]

        assert weight.method == "momentum"
        assert weight.lookback == 60
        assert weight.top == 3


class TestParseGroupBlocks:
    """Test parsing group blocks."""

    def test_parse_simple_group(self):
        source = """
        (strategy "Test"
          (group "Equities"
            (weight :method equal
              (asset VTI)
              (asset VXUS))))
        """
        result = parse(source)
        group = result.children[0]

        assert isinstance(group, Group)
        assert group.name == "Equities"
        assert len(group.children) == 1

    def test_parse_nested_groups(self):
        source = """
        (strategy "Test"
          (group "US"
            (group "Large Cap"
              (asset VTI :weight 100))))
        """
        result = parse(source)
        outer = result.children[0]
        inner = outer.children[0]

        assert outer.name == "US"
        assert inner.name == "Large Cap"


class TestParseIfBlocks:
    """Test parsing if/else blocks."""

    def test_parse_simple_if(self):
        source = """
        (strategy "Test"
          (if (> (sma SPY 50) (sma SPY 200))
            (weight :method equal (asset VTI))))
        """
        result = parse(source)
        if_block = result.children[0]

        assert isinstance(if_block, If)
        assert isinstance(if_block.condition, Comparison)
        assert if_block.condition.operator == ">"
        assert if_block.else_block is None

    def test_parse_if_else(self):
        source = """
        (strategy "Test"
          (if (> (sma SPY 50) (sma SPY 200))
            (weight :method equal (asset VTI))
            (else (weight :method equal (asset BND)))))
        """
        result = parse(source)
        if_block = result.children[0]

        assert if_block.else_block is not None
        assert isinstance(if_block.else_block, Weight)

    def test_parse_crossover_condition(self):
        source = """
        (strategy "Test"
          (if (crosses-above (sma SPY 50) (sma SPY 200))
            (asset VTI :weight 100)))
        """
        result = parse(source)
        if_block = result.children[0]

        assert isinstance(if_block.condition, Crossover)
        assert if_block.condition.direction == "above"

    def test_parse_logical_conditions(self):
        source = """
        (strategy "Test"
          (if (and (> (sma SPY 50) (sma SPY 200)) (< (rsi SPY 14) 70))
            (asset VTI :weight 100)))
        """
        result = parse(source)
        if_block = result.children[0]

        assert isinstance(if_block.condition, LogicalOp)
        assert if_block.condition.operator == "and"
        assert len(if_block.condition.operands) == 2


class TestParseFilterBlocks:
    """Test parsing filter blocks."""

    def test_parse_simple_filter(self):
        source = """
        (strategy "Test"
          (filter :by momentum :select (top 3)
            (weight :method equal
              (asset XLK)
              (asset XLF)
              (asset XLE))))
        """
        result = parse(source)
        filter_block = result.children[0]

        assert isinstance(filter_block, Filter)
        assert filter_block.by == "momentum"
        assert filter_block.select_direction == "top"
        assert filter_block.select_count == 3

    def test_parse_filter_with_lookback(self):
        source = """
        (strategy "Test"
          (filter :by momentum :select (bottom 2) :lookback 60
            (asset XLK)
            (asset XLF)))
        """
        result = parse(source)
        filter_block = result.children[0]

        assert filter_block.select_direction == "bottom"
        assert filter_block.lookback == 60


class TestParseConditions:
    """Test parsing condition expressions."""

    def test_parse_comparison_with_price(self):
        source = """
        (strategy "Test"
          (if (> (price SPY) 100)
            (asset VTI :weight 100)))
        """
        result = parse(source)
        if_block = result.children[0]

        assert isinstance(if_block.condition.left, Price)
        assert if_block.condition.left.symbol == "SPY"
        assert isinstance(if_block.condition.right, NumericLiteral)
        assert if_block.condition.right.value == 100

    def test_parse_indicator_with_params(self):
        source = """
        (strategy "Test"
          (if (< (rsi QQQ 14) 30)
            (asset QQQ :weight 100)))
        """
        result = parse(source)
        if_block = result.children[0]

        assert isinstance(if_block.condition.left, Indicator)
        assert if_block.condition.left.name == "rsi"
        assert if_block.condition.left.symbol == "QQQ"
        assert if_block.condition.left.params == (14,)

    def test_parse_indicator_with_output(self):
        source = """
        (strategy "Test"
          (if (> (macd SPY 12 26 9 :signal) 0)
            (asset SPY :weight 100)))
        """
        result = parse(source)
        if_block = result.children[0]

        ind = if_block.condition.left
        assert ind.name == "macd"
        assert ind.params == (12, 26, 9)
        assert ind.output == "signal"

    def test_parse_metric(self):
        source = """
        (strategy "Test"
          (if (< (drawdown SPY) 0.10)
            (asset SPY :weight 100)))
        """
        result = parse(source)
        if_block = result.children[0]

        assert isinstance(if_block.condition.left, Metric)
        assert if_block.condition.left.name == "drawdown"
        assert if_block.condition.left.symbol == "SPY"


class TestParseComplexStrategies:
    """Test parsing complex, real-world strategies."""

    def test_parse_dual_moving_average(self):
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
        result = parse(source)

        assert result.name == "Dual Moving Average"
        assert result.rebalance == "daily"
        assert result.benchmark == "SPY"

        if_block = result.children[0]
        assert isinstance(if_block, If)
        assert isinstance(if_block.then_block, Group)
        assert if_block.then_block.name == "Risk On"
        assert if_block.else_block is not None

    def test_parse_all_weather(self):
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
        result = parse(source)

        assert len(result.children) == 3
        assert all(isinstance(c, Group) for c in result.children)


class TestParseErrors:
    """Test parse error handling."""

    def test_empty_input_error(self):
        with pytest.raises(ParseError, match="Empty input"):
            parse("")

    def test_missing_strategy_name(self):
        with pytest.raises(ParseError, match="Expected string"):
            parse("(strategy (weight :method equal (asset VTI)))")

    def test_invalid_rebalance_frequency(self):
        with pytest.raises(ParseError, match="Invalid rebalance"):
            parse('(strategy "Test" :rebalance invalid (asset VTI))')

    def test_unknown_block_type(self):
        with pytest.raises(ParseError, match="Unknown block type"):
            parse('(strategy "Test" (unknown (asset VTI)))')

    def test_missing_weight_method(self):
        with pytest.raises(ParseError, match="Expected ':method'"):
            parse('(strategy "Test" (weight (asset VTI)))')

    def test_invalid_weight_method(self):
        with pytest.raises(ParseError, match="Invalid weight method"):
            parse('(strategy "Test" (weight :method invalid (asset VTI)))')


class TestParseStrategyAlias:
    """Test that parse_strategy is an alias for parse."""

    def test_parse_strategy_works(self):
        source = '(strategy "Test" (asset VTI :weight 100))'
        result = parse_strategy(source)
        assert isinstance(result, Strategy)
        assert result.name == "Test"


class TestSourceLocation:
    """Test source location tracking in AST nodes."""

    def test_strategy_location(self):
        source = '(strategy "Test" (asset VTI :weight 100))'
        result = parse(source)

        assert result.location is not None
        assert isinstance(result.location, SourceLocation)
        assert result.location.line == 1
        assert result.location.column == 1
        assert result.location.start == 0
        assert result.location.end == len(source)

    def test_asset_location(self):
        source = '(strategy "Test" (asset VTI :weight 100))'
        result = parse(source)
        asset = result.children[0]

        assert asset.location is not None
        assert asset.location.line == 1
        # Asset starts at column 18 (0-indexed position 17)
        assert asset.location.column == 18

    def test_multiline_locations(self):
        source = """(strategy "Test"
  :rebalance monthly
  (asset VTI :weight 100))"""
        result = parse(source)

        # Strategy starts at line 1
        assert result.location is not None
        assert result.location.line == 1

        # Asset starts at line 3
        asset = result.children[0]
        assert asset.location is not None
        assert asset.location.line == 3

    def test_condition_locations(self):
        source = '(strategy "Test" (if (> 50 30) (asset VTI :weight 100)))'
        result = parse(source)
        if_block = result.children[0]

        assert if_block.location is not None
        assert if_block.condition.location is not None
        # Condition starts at position of "("
        assert if_block.condition.location.column == 22

    def test_indicator_location(self):
        source = '(strategy "Test" (if (> (sma SPY 50) 200) (asset VTI :weight 100)))'
        result = parse(source)
        if_block = result.children[0]
        indicator = if_block.condition.left

        assert isinstance(indicator, Indicator)
        assert indicator.location is not None
        assert indicator.location.column == 25

    def test_weight_block_location(self):
        source = """(strategy "Test"
  (weight :method equal
    (asset VTI)
    (asset BND)))"""
        result = parse(source)
        weight = result.children[0]

        assert isinstance(weight, Weight)
        assert weight.location is not None
        assert weight.location.line == 2

    def test_group_location(self):
        source = """(strategy "Test"
  (group "Equities"
    (asset VTI :weight 100)))"""
        result = parse(source)
        group = result.children[0]

        assert isinstance(group, Group)
        assert group.location is not None
        assert group.location.line == 2

    def test_filter_location(self):
        source = """(strategy "Test"
  (filter :by momentum :select (top 3)
    (asset VTI)))"""
        result = parse(source)
        filter_block = result.children[0]

        assert isinstance(filter_block, Filter)
        assert filter_block.location is not None
        assert filter_block.location.line == 2

    def test_numeric_literal_location(self):
        source = '(strategy "Test" (if (> 100 50) (asset VTI :weight 100)))'
        result = parse(source)
        if_block = result.children[0]
        left = if_block.condition.left

        assert isinstance(left, NumericLiteral)
        assert left.location is not None

    def test_price_location(self):
        source = '(strategy "Test" (if (> (price SPY) 100) (asset VTI :weight 100)))'
        result = parse(source)
        if_block = result.children[0]
        left = if_block.condition.left

        assert isinstance(left, Price)
        assert left.location is not None

    def test_crossover_location(self):
        source = '(strategy "Test" (if (crosses-above (sma SPY 50) (sma SPY 200)) (asset VTI :weight 100)))'
        result = parse(source)
        if_block = result.children[0]

        assert isinstance(if_block.condition, Crossover)
        assert if_block.condition.location is not None

    def test_logical_op_location(self):
        source = '(strategy "Test" (if (and (> 10 5) (< 3 7)) (asset VTI :weight 100)))'
        result = parse(source)
        if_block = result.children[0]

        assert isinstance(if_block.condition, LogicalOp)
        assert if_block.condition.location is not None

    def test_location_repr(self):
        loc = SourceLocation(line=5, column=10, start=42, end=50)
        assert repr(loc) == "line 5, col 10"
