"""Tests for S-expression parser."""

import pytest
from llamatrade_dsl.ast import FunctionCall, Keyword, Literal, Symbol
from llamatrade_dsl.parser import ParseError, parse, parse_strategy


class TestParseLiterals:
    """Test parsing of literal values."""

    def test_parse_integer(self):
        result = parse("42")
        assert isinstance(result, Literal)
        assert result.value == 42

    def test_parse_negative_integer(self):
        result = parse("-5")
        assert isinstance(result, Literal)
        assert result.value == -5

    def test_parse_float(self):
        result = parse("3.14")
        assert isinstance(result, Literal)
        assert result.value == 3.14

    def test_parse_negative_float(self):
        result = parse("-0.5")
        assert isinstance(result, Literal)
        assert result.value == -0.5

    def test_parse_string(self):
        result = parse('"hello world"')
        assert isinstance(result, Literal)
        assert result.value == "hello world"

    def test_parse_string_with_escapes(self):
        result = parse(r'"say \"hello\""')
        assert isinstance(result, Literal)
        assert result.value == 'say "hello"'

    def test_parse_boolean_true(self):
        result = parse("true")
        assert isinstance(result, Literal)
        assert result.value is True

    def test_parse_boolean_false(self):
        result = parse("false")
        assert isinstance(result, Literal)
        assert result.value is False


class TestParseSymbols:
    """Test parsing of symbols."""

    def test_parse_simple_symbol(self):
        result = parse("close")
        assert isinstance(result, Symbol)
        assert result.name == "close"

    def test_parse_symbol_with_hyphen(self):
        result = parse("my-indicator")
        assert isinstance(result, Symbol)
        assert result.name == "my-indicator"

    def test_parse_symbol_with_underscore(self):
        result = parse("my_indicator")
        assert isinstance(result, Symbol)
        assert result.name == "my_indicator"

    def test_parse_dollar_symbol(self):
        result = parse("$symbol")
        assert isinstance(result, Symbol)
        assert result.name == "$symbol"


class TestParseKeywords:
    """Test parsing of keywords."""

    def test_parse_keyword(self):
        result = parse(":name")
        assert isinstance(result, Keyword)
        assert result.name == "name"

    def test_parse_keyword_with_hyphen(self):
        result = parse(":stop-loss")
        assert isinstance(result, Keyword)
        assert result.name == "stop-loss"


class TestParseVectors:
    """Test parsing of vector literals."""

    def test_parse_string_vector(self):
        result = parse('["AAPL" "MSFT" "GOOGL"]')
        assert isinstance(result, Literal)
        assert result.value == ["AAPL", "MSFT", "GOOGL"]

    def test_parse_number_vector(self):
        result = parse("[1 2 3]")
        assert isinstance(result, Literal)
        assert result.value == [1, 2, 3]

    def test_parse_mixed_vector(self):
        result = parse('["AAPL" 100]')
        assert isinstance(result, Literal)
        assert result.value == ["AAPL", 100]

    def test_parse_empty_vector(self):
        result = parse("[]")
        assert isinstance(result, Literal)
        assert result.value == []


class TestParseMaps:
    """Test parsing of map literals."""

    def test_parse_simple_map(self):
        result = parse('{:name "test" :value 42}')
        assert isinstance(result, Literal)
        assert result.value == {"name": "test", "value": 42}

    def test_parse_empty_map(self):
        result = parse("{}")
        assert isinstance(result, Literal)
        assert result.value == {}


class TestParseFunctionCalls:
    """Test parsing of function calls."""

    def test_parse_simple_function(self):
        result = parse("(sma close 20)")
        assert isinstance(result, FunctionCall)
        assert result.name == "sma"
        assert len(result.args) == 2
        assert isinstance(result.args[0], Symbol)
        assert result.args[0].name == "close"
        assert isinstance(result.args[1], Literal)
        assert result.args[1].value == 20

    def test_parse_nested_function(self):
        result = parse("(> (rsi close 14) 70)")
        assert isinstance(result, FunctionCall)
        assert result.name == ">"
        assert len(result.args) == 2
        assert isinstance(result.args[0], FunctionCall)
        assert result.args[0].name == "rsi"
        assert isinstance(result.args[1], Literal)
        assert result.args[1].value == 70

    def test_parse_deeply_nested(self):
        result = parse("(and (> (rsi close 14) 70) (< price 100))")
        assert isinstance(result, FunctionCall)
        assert result.name == "and"
        assert len(result.args) == 2
        assert all(isinstance(arg, FunctionCall) for arg in result.args)

    def test_parse_function_with_keyword_args(self):
        result = parse("(macd close 12 26 9 :line)")
        assert isinstance(result, FunctionCall)
        assert result.name == "macd"
        assert len(result.args) == 5
        assert isinstance(result.args[4], Keyword)
        assert result.args[4].name == "line"

    def test_parse_variadic_function(self):
        result = parse("(and cond1 cond2 cond3 cond4)")
        assert isinstance(result, FunctionCall)
        assert result.name == "and"
        assert len(result.args) == 4


class TestParseComments:
    """Test that comments are ignored."""

    def test_comment_ignored(self):
        result = parse("; this is a comment\n42")
        assert isinstance(result, Literal)
        assert result.value == 42

    def test_inline_comment_ignored(self):
        result = parse("(sma close 20) ; trailing comment")
        assert isinstance(result, FunctionCall)
        assert result.name == "sma"


class TestParseWhitespace:
    """Test whitespace handling."""

    def test_multiline_expression(self):
        source = """
        (and
          (> (rsi close 14) 70)
          (< price 100))
        """
        result = parse(source)
        assert isinstance(result, FunctionCall)
        assert result.name == "and"

    def test_various_whitespace(self):
        result = parse("(sma\tclose\n20)")
        assert isinstance(result, FunctionCall)
        assert len(result.args) == 2


class TestParseErrors:
    """Test parse error handling."""

    def test_empty_input_error(self):
        with pytest.raises(ParseError, match="Empty input"):
            parse("")

    def test_empty_list_error(self):
        with pytest.raises(ParseError, match="Empty list"):
            parse("()")

    def test_unclosed_paren_error(self):
        with pytest.raises(ParseError, match="Expected RPAREN"):
            parse("(sma close 20")

    def test_unexpected_token_error(self):
        with pytest.raises(ParseError):
            parse(")")

    def test_trailing_tokens_error(self):
        with pytest.raises(ParseError, match="Unexpected tokens"):
            parse("42 43")


class TestParseStrategy:
    """Test parsing complete strategy definitions."""

    def test_parse_minimal_strategy(self):
        source = """
        (strategy
          :name "Test Strategy"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (rsi close 14) 30)
          :exit (< (rsi close 14) 70))
        """
        strategy = parse_strategy(source)
        assert strategy.name == "Test Strategy"
        assert strategy.symbols == ["AAPL"]
        assert strategy.timeframe == "1D"
        assert isinstance(strategy.entry, FunctionCall)
        assert isinstance(strategy.exit, FunctionCall)

    def test_parse_full_strategy(self):
        source = """
        (strategy
          :name "EMA Crossover"
          :description "Simple EMA crossover strategy"
          :type trend_following
          :symbols ["AAPL" "MSFT" "GOOGL"]
          :timeframe "1H"
          :entry (and
                   (cross-above (ema close 12) (ema close 26))
                   (> (rsi close 14) 50))
          :exit (cross-below (ema close 12) (ema close 26))
          :position-size 10
          :stop-loss-pct 2.0
          :take-profit-pct 6.0
          :max-positions 5)
        """
        strategy = parse_strategy(source)
        assert strategy.name == "EMA Crossover"
        assert strategy.description == "Simple EMA crossover strategy"
        assert strategy.strategy_type == "trend_following"
        assert strategy.symbols == ["AAPL", "MSFT", "GOOGL"]
        assert strategy.timeframe == "1H"
        assert strategy.sizing["value"] == 10
        assert strategy.risk["stop_loss_pct"] == 2.0
        assert strategy.risk["take_profit_pct"] == 6.0
        assert strategy.risk["max_positions"] == 5

    def test_parse_strategy_with_risk_map(self):
        source = """
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> close 100)
          :exit (< close 90)
          :risk {:stop-loss-pct 2 :take-profit-pct 6})
        """
        strategy = parse_strategy(source)
        assert strategy.risk["stop_loss_pct"] == 2
        assert strategy.risk["take_profit_pct"] == 6

    def test_parse_strategy_missing_name_error(self):
        source = """
        (strategy
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> close 100)
          :exit (< close 90))
        """
        with pytest.raises(ParseError, match="requires :name"):
            parse_strategy(source)

    def test_parse_strategy_missing_entry_error(self):
        source = """
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :exit (< close 90))
        """
        with pytest.raises(ParseError, match="requires :entry"):
            parse_strategy(source)

    def test_parse_non_strategy_error(self):
        with pytest.raises(ParseError, match="Expected .strategy"):
            parse_strategy("(sma close 20)")


class TestParseComplexExpressions:
    """Test parsing complex, real-world expressions."""

    def test_parse_complex_entry_condition(self):
        source = """
        (and
          (cross-above (ema close 12) (ema close 26))
          (> (rsi close 14) 50)
          (> volume (sma volume 20))
          (> (macd close 12 26 9 :histogram) 0))
        """
        result = parse(source)
        assert isinstance(result, FunctionCall)
        assert result.name == "and"
        assert len(result.args) == 4

    def test_parse_nested_arithmetic(self):
        source = "(/ (- close (sma close 20)) (stddev close 20))"
        result = parse(source)
        assert isinstance(result, FunctionCall)
        assert result.name == "/"
        assert len(result.args) == 2

    def test_parse_bollinger_band_condition(self):
        source = "(< close (bbands close 20 2 :lower))"
        result = parse(source)
        assert isinstance(result, FunctionCall)
        assert result.name == "<"
        inner = result.args[1]
        assert isinstance(inner, FunctionCall)
        assert inner.name == "bbands"
        assert isinstance(inner.args[3], Keyword)
        assert inner.args[3].name == "lower"
