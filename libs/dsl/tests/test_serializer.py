"""Tests for AST serializer."""

import pytest

from llamatrade_dsl.ast import FunctionCall, Keyword, Literal, Strategy, Symbol
from llamatrade_dsl.parser import parse, parse_strategy
from llamatrade_dsl.serializer import serialize


class TestSerializeLiterals:
    """Test serialization of literal values."""

    def test_serialize_integer(self):
        node = Literal(42)
        assert serialize(node) == "42"

    def test_serialize_negative_integer(self):
        node = Literal(-5)
        assert serialize(node) == "-5"

    def test_serialize_float(self):
        node = Literal(3.14)
        assert serialize(node) == "3.14"

    def test_serialize_string(self):
        node = Literal("hello")
        assert serialize(node) == '"hello"'

    def test_serialize_string_with_quotes(self):
        node = Literal('say "hello"')
        assert serialize(node) == '"say \\"hello\\""'

    def test_serialize_boolean_true(self):
        node = Literal(True)
        assert serialize(node) == "true"

    def test_serialize_boolean_false(self):
        node = Literal(False)
        assert serialize(node) == "false"

    def test_serialize_list(self):
        node = Literal(["AAPL", "MSFT"])
        assert serialize(node) == '["AAPL" "MSFT"]'

    def test_serialize_dict(self):
        node = Literal({"key": "value", "num": 42})
        result = serialize(node)
        assert ":key" in result
        assert '"value"' in result
        assert ":num" in result
        assert "42" in result


class TestSerializeSymbols:
    """Test serialization of symbols."""

    def test_serialize_symbol(self):
        node = Symbol("close")
        assert serialize(node) == "close"

    def test_serialize_dollar_symbol(self):
        node = Symbol("$symbol")
        assert serialize(node) == "$symbol"


class TestSerializeKeywords:
    """Test serialization of keywords."""

    def test_serialize_keyword(self):
        node = Keyword("name")
        assert serialize(node) == ":name"

    def test_serialize_hyphenated_keyword(self):
        node = Keyword("stop-loss")
        assert serialize(node) == ":stop-loss"


class TestSerializeFunctions:
    """Test serialization of function calls."""

    def test_serialize_simple_function(self):
        node = FunctionCall("sma", (Symbol("close"), Literal(20)))
        assert serialize(node) == "(sma close 20)"

    def test_serialize_empty_function(self):
        node = FunctionCall("has-position", ())
        assert serialize(node) == "(has-position)"

    def test_serialize_nested_function(self):
        inner = FunctionCall("rsi", (Symbol("close"), Literal(14)))
        outer = FunctionCall(">", (inner, Literal(70)))
        assert serialize(outer) == "(> (rsi close 14) 70)"

    def test_serialize_function_with_keyword(self):
        node = FunctionCall(
            "macd",
            (Symbol("close"), Literal(12), Literal(26), Literal(9), Keyword("line")),
        )
        assert serialize(node) == "(macd close 12 26 9 :line)"


class TestSerializeStrategy:
    """Test serialization of strategy definitions."""

    def test_serialize_minimal_strategy(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=FunctionCall(">", (Symbol("close"), Literal(100))),
            exit=FunctionCall("<", (Symbol("close"), Literal(90))),
        )
        result = serialize(strategy)
        assert "(strategy" in result
        assert ':name "Test"' in result
        assert ':symbols ["AAPL"]' in result
        assert ':timeframe "1D"' in result
        assert ":entry" in result
        assert ":exit" in result

    def test_serialize_strategy_with_description(self):
        strategy = Strategy(
            name="Test",
            description="A test strategy",
            symbols=["AAPL"],
            timeframe="1D",
            entry=FunctionCall(">", (Symbol("close"), Literal(100))),
            exit=FunctionCall("<", (Symbol("close"), Literal(90))),
        )
        result = serialize(strategy)
        assert ':description "A test strategy"' in result

    def test_serialize_strategy_with_risk(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=FunctionCall(">", (Symbol("close"), Literal(100))),
            exit=FunctionCall("<", (Symbol("close"), Literal(90))),
            risk={"stop_loss_pct": 2.0, "take_profit_pct": 6.0},
        )
        result = serialize(strategy)
        assert ":stop-loss-pct 2.0" in result
        assert ":take-profit-pct 6.0" in result


class TestSerializePretty:
    """Test pretty-printing serialization."""

    def test_pretty_simple_function(self):
        node = FunctionCall("sma", (Symbol("close"), Literal(20)))
        result = serialize(node, pretty=True)
        assert result == "(sma close 20)"  # Short enough to inline

    def test_pretty_strategy(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=FunctionCall(">", (Symbol("close"), Literal(100))),
            exit=FunctionCall("<", (Symbol("close"), Literal(90))),
        )
        result = serialize(strategy, pretty=True)
        assert result.startswith("(strategy\n")
        assert "\n" in result


class TestSerializeRoundtrip:
    """Test that parsing then serializing produces equivalent results."""

    @pytest.mark.parametrize(
        "expr",
        [
            "42",
            "3.14",
            '"hello"',
            "true",
            "false",
            "close",
            ":name",
            '["AAPL" "MSFT"]',
            "(sma close 20)",
            "(> (rsi close 14) 70)",
            "(and (> a 1) (< b 2))",
            "(macd close 12 26 9 :line)",
        ],
    )
    def test_roundtrip_expression(self, expr: str):
        """Parse, serialize, parse again should give equivalent AST."""
        original = parse(expr)
        serialized = serialize(original)
        reparsed = parse(serialized)

        # Compare string representations
        assert repr(original) == repr(reparsed)

    def test_roundtrip_complex_expression(self):
        source = "(and (cross-above (ema close 12) (ema close 26)) (> (rsi close 14) 50))"
        original = parse(source)
        serialized = serialize(original)
        reparsed = parse(serialized)
        assert repr(original) == repr(reparsed)

    def test_roundtrip_strategy(self):
        source = """
        (strategy
          :name "Test Strategy"
          :symbols ["AAPL" "MSFT"]
          :timeframe "1D"
          :entry (> (rsi close 14) 30)
          :exit (< (rsi close 14) 70)
          :position-size 10
          :stop-loss-pct 2.0)
        """
        original = parse_strategy(source)
        serialized = serialize(original)
        reparsed = parse_strategy(serialized)

        assert original.name == reparsed.name
        assert original.symbols == reparsed.symbols
        assert original.timeframe == reparsed.timeframe
        assert repr(original.entry) == repr(reparsed.entry)
        assert repr(original.exit) == repr(reparsed.exit)
