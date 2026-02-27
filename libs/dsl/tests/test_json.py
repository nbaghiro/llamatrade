"""Tests for AST to/from JSON conversion."""

import pytest

from llamatrade_dsl.ast import FunctionCall, Keyword, Literal, Strategy, Symbol
from llamatrade_dsl.parser import parse, parse_strategy
from llamatrade_dsl.to_json import from_json, to_json


class TestToJsonLiterals:
    """Test JSON conversion of literals."""

    def test_integer_to_json(self):
        node = Literal(42)
        result = to_json(node)
        assert result == {"type": "literal", "value": 42}

    def test_float_to_json(self):
        node = Literal(3.14)
        result = to_json(node)
        assert result == {"type": "literal", "value": 3.14}

    def test_string_to_json(self):
        node = Literal("hello")
        result = to_json(node)
        assert result == {"type": "literal", "value": "hello"}

    def test_boolean_to_json(self):
        node = Literal(True)
        result = to_json(node)
        assert result == {"type": "literal", "value": True}

    def test_list_to_json(self):
        node = Literal(["AAPL", "MSFT"])
        result = to_json(node)
        assert result == {"type": "literal", "value": ["AAPL", "MSFT"]}


class TestToJsonSymbols:
    """Test JSON conversion of symbols."""

    def test_symbol_to_json(self):
        node = Symbol("close")
        result = to_json(node)
        assert result == {"type": "symbol", "name": "close"}

    def test_dollar_symbol_to_json(self):
        node = Symbol("$symbol")
        result = to_json(node)
        assert result == {"type": "symbol", "name": "$symbol"}


class TestToJsonKeywords:
    """Test JSON conversion of keywords."""

    def test_keyword_to_json(self):
        node = Keyword("name")
        result = to_json(node)
        assert result == {"type": "keyword", "name": "name"}


class TestToJsonFunctions:
    """Test JSON conversion of function calls."""

    def test_simple_function_to_json(self):
        node = FunctionCall("sma", (Symbol("close"), Literal(20)))
        result = to_json(node)
        assert result == {
            "type": "function",
            "name": "sma",
            "args": [
                {"type": "symbol", "name": "close"},
                {"type": "literal", "value": 20},
            ],
        }

    def test_nested_function_to_json(self):
        inner = FunctionCall("rsi", (Symbol("close"), Literal(14)))
        outer = FunctionCall(">", (inner, Literal(70)))
        result = to_json(outer)
        assert result["type"] == "function"
        assert result["name"] == ">"
        assert result["args"][0]["type"] == "function"
        assert result["args"][0]["name"] == "rsi"

    def test_empty_function_to_json(self):
        node = FunctionCall("has-position", ())
        result = to_json(node)
        assert result == {"type": "function", "name": "has-position", "args": []}


class TestToJsonStrategy:
    """Test JSON conversion of strategy definitions."""

    def test_strategy_to_json(self):
        strategy = Strategy(
            name="Test",
            description="A test strategy",
            strategy_type="momentum",
            symbols=["AAPL", "MSFT"],
            timeframe="1D",
            entry=FunctionCall(">", (Symbol("close"), Literal(100))),
            exit=FunctionCall("<", (Symbol("close"), Literal(90))),
            sizing={"type": "percent-equity", "value": 10},
            risk={"stop_loss_pct": 2.0},
        )
        result = to_json(strategy)

        assert result["type"] == "strategy"
        assert result["name"] == "Test"
        assert result["description"] == "A test strategy"
        assert result["strategy_type"] == "momentum"
        assert result["symbols"] == ["AAPL", "MSFT"]
        assert result["timeframe"] == "1D"
        assert result["entry"]["type"] == "function"
        assert result["exit"]["type"] == "function"
        assert result["sizing"] == {"type": "percent-equity", "value": 10}
        assert result["risk"] == {"stop_loss_pct": 2.0}


class TestFromJsonLiterals:
    """Test JSON to AST conversion of literals."""

    def test_integer_from_json(self):
        data = {"type": "literal", "value": 42}
        result = from_json(data)
        assert isinstance(result, Literal)
        assert result.value == 42

    def test_string_from_json(self):
        data = {"type": "literal", "value": "hello"}
        result = from_json(data)
        assert isinstance(result, Literal)
        assert result.value == "hello"

    def test_list_from_json(self):
        data = {"type": "literal", "value": ["AAPL", "MSFT"]}
        result = from_json(data)
        assert isinstance(result, Literal)
        assert result.value == ["AAPL", "MSFT"]


class TestFromJsonSymbols:
    """Test JSON to AST conversion of symbols."""

    def test_symbol_from_json(self):
        data = {"type": "symbol", "name": "close"}
        result = from_json(data)
        assert isinstance(result, Symbol)
        assert result.name == "close"


class TestFromJsonKeywords:
    """Test JSON to AST conversion of keywords."""

    def test_keyword_from_json(self):
        data = {"type": "keyword", "name": "line"}
        result = from_json(data)
        assert isinstance(result, Keyword)
        assert result.name == "line"


class TestFromJsonFunctions:
    """Test JSON to AST conversion of function calls."""

    def test_simple_function_from_json(self):
        data = {
            "type": "function",
            "name": "sma",
            "args": [
                {"type": "symbol", "name": "close"},
                {"type": "literal", "value": 20},
            ],
        }
        result = from_json(data)
        assert isinstance(result, FunctionCall)
        assert result.name == "sma"
        assert len(result.args) == 2
        assert isinstance(result.args[0], Symbol)
        assert isinstance(result.args[1], Literal)

    def test_nested_function_from_json(self):
        data = {
            "type": "function",
            "name": ">",
            "args": [
                {
                    "type": "function",
                    "name": "rsi",
                    "args": [
                        {"type": "symbol", "name": "close"},
                        {"type": "literal", "value": 14},
                    ],
                },
                {"type": "literal", "value": 70},
            ],
        }
        result = from_json(data)
        assert isinstance(result, FunctionCall)
        assert result.name == ">"
        assert isinstance(result.args[0], FunctionCall)
        assert result.args[0].name == "rsi"


class TestFromJsonStrategy:
    """Test JSON to AST conversion of strategy definitions."""

    def test_strategy_from_json(self):
        data = {
            "type": "strategy",
            "name": "Test",
            "description": "A test",
            "strategy_type": "momentum",
            "symbols": ["AAPL"],
            "timeframe": "1D",
            "entry": {
                "type": "function",
                "name": ">",
                "args": [
                    {"type": "symbol", "name": "close"},
                    {"type": "literal", "value": 100},
                ],
            },
            "exit": {
                "type": "function",
                "name": "<",
                "args": [
                    {"type": "symbol", "name": "close"},
                    {"type": "literal", "value": 90},
                ],
            },
            "sizing": {"type": "percent-equity", "value": 10},
            "risk": {"stop_loss_pct": 2.0},
        }
        result = from_json(data)

        assert isinstance(result, Strategy)
        assert result.name == "Test"
        assert result.description == "A test"
        assert result.strategy_type == "momentum"
        assert result.symbols == ["AAPL"]
        assert result.timeframe == "1D"
        assert isinstance(result.entry, FunctionCall)
        assert isinstance(result.exit, FunctionCall)
        assert result.sizing == {"type": "percent-equity", "value": 10}
        assert result.risk == {"stop_loss_pct": 2.0}


class TestJsonRoundtrip:
    """Test that AST -> JSON -> AST produces equivalent results."""

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
            "(sma close 20)",
            "(> (rsi close 14) 70)",
            "(and (> a 1) (< b 2))",
            "(macd close 12 26 9 :line)",
        ],
    )
    def test_roundtrip_expression(self, expr: str):
        """Parse -> to_json -> from_json should give equivalent AST."""
        original = parse(expr)
        json_data = to_json(original)
        reconstructed = from_json(json_data)

        assert repr(original) == repr(reconstructed)

    def test_roundtrip_complex_expression(self):
        source = "(and (cross-above (ema close 12) (ema close 26)) (> (rsi close 14) 50))"
        original = parse(source)
        json_data = to_json(original)
        reconstructed = from_json(json_data)
        assert repr(original) == repr(reconstructed)

    def test_roundtrip_strategy(self):
        source = """
        (strategy
          :name "Test Strategy"
          :description "A test"
          :type momentum
          :symbols ["AAPL" "MSFT"]
          :timeframe "1D"
          :entry (and (> (rsi close 14) 30) (< close 200))
          :exit (< (rsi close 14) 70)
          :position-size 10
          :stop-loss-pct 2.0
          :take-profit-pct 6.0)
        """
        original = parse_strategy(source)
        json_data = to_json(original)
        reconstructed = from_json(json_data)

        assert isinstance(reconstructed, Strategy)
        assert original.name == reconstructed.name
        assert original.description == reconstructed.description
        assert original.strategy_type == reconstructed.strategy_type
        assert original.symbols == reconstructed.symbols
        assert original.timeframe == reconstructed.timeframe
        assert repr(original.entry) == repr(reconstructed.entry)
        assert repr(original.exit) == repr(reconstructed.exit)
        assert original.sizing == reconstructed.sizing
        assert original.risk == reconstructed.risk


class TestJsonSerializable:
    """Test that to_json output is JSON-serializable."""

    def test_json_serializable(self):
        import json

        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=FunctionCall(">", (Symbol("close"), Literal(100))),
            exit=FunctionCall("<", (Symbol("close"), Literal(90))),
        )
        json_data = to_json(strategy)

        # Should not raise
        serialized = json.dumps(json_data)
        assert isinstance(serialized, str)

        # Should be deserializable
        deserialized = json.loads(serialized)
        assert deserialized == json_data
