"""Tests for AST validator."""

from llamatrade_dsl.ast import Strategy
from llamatrade_dsl.parser import parse, parse_strategy
from llamatrade_dsl.validator import validate, validate_strategy


class TestValidateIndicators:
    """Test validation of indicator function calls."""

    def test_valid_sma(self):
        node = parse("(sma close 20)")
        result = validate(node)
        assert result.valid
        assert len(result.errors) == 0

    def test_valid_rsi(self):
        node = parse("(rsi close 14)")
        result = validate(node)
        assert result.valid

    def test_valid_macd_with_output(self):
        node = parse("(macd close 12 26 9 :line)")
        result = validate(node)
        assert result.valid

    def test_valid_macd_histogram(self):
        node = parse("(macd close 12 26 9 :histogram)")
        result = validate(node)
        assert result.valid

    def test_valid_bbands_with_output(self):
        node = parse("(bbands close 20 2 :upper)")
        result = validate(node)
        assert result.valid

    def test_invalid_indicator_output(self):
        node = parse("(macd close 12 26 9 :invalid)")
        result = validate(node)
        assert not result.valid
        assert any("Invalid output selector" in str(e) for e in result.errors)

    def test_indicator_too_few_args(self):
        node = parse("(sma close)")
        result = validate(node)
        assert not result.valid
        assert any("requires at least 2 arguments" in str(e) for e in result.errors)

    def test_indicator_too_many_args(self):
        node = parse("(sma close 20 30 40)")
        result = validate(node)
        assert not result.valid
        assert any("at most" in str(e) for e in result.errors)


class TestValidateComparators:
    """Test validation of comparison operators."""

    def test_valid_comparison(self):
        node = parse("(> (rsi close 14) 70)")
        result = validate(node)
        assert result.valid

    def test_valid_less_than(self):
        node = parse("(< close 100)")
        result = validate(node)
        assert result.valid

    def test_comparison_wrong_arg_count(self):
        node = parse("(> a b c)")
        result = validate(node)
        assert not result.valid
        assert any("exactly 2 arguments" in str(e) for e in result.errors)


class TestValidateLogicalOps:
    """Test validation of logical operators."""

    def test_valid_and(self):
        node = parse("(and (> close 1) (< volume 2))")
        result = validate(node)
        assert result.valid

    def test_valid_or(self):
        node = parse("(or (> close 1) (< close 2) (> volume 3))")
        result = validate(node)
        assert result.valid

    def test_valid_not(self):
        node = parse("(not (> close 1))")
        result = validate(node)
        assert result.valid

    def test_and_too_few_args(self):
        node = parse("(and cond1)")
        result = validate(node)
        assert not result.valid
        assert any("at least 2 arguments" in str(e) for e in result.errors)

    def test_not_too_many_args(self):
        node = parse("(not a b)")
        result = validate(node)
        assert not result.valid
        assert any("at most 1 argument" in str(e) for e in result.errors)


class TestValidateCrossover:
    """Test validation of crossover operators."""

    def test_valid_cross_above(self):
        node = parse("(cross-above (ema close 12) (ema close 26))")
        result = validate(node)
        assert result.valid

    def test_valid_cross_below(self):
        node = parse("(cross-below (sma close 50) (sma close 200))")
        result = validate(node)
        assert result.valid

    def test_crossover_wrong_arg_count(self):
        node = parse("(cross-above a)")
        result = validate(node)
        assert not result.valid


class TestValidateArithmetic:
    """Test validation of arithmetic operators."""

    def test_valid_add(self):
        node = parse("(+ close high low)")
        result = validate(node)
        assert result.valid

    def test_valid_subtract(self):
        node = parse("(- close open)")
        result = validate(node)
        assert result.valid

    def test_valid_divide(self):
        # Z-score calculation
        node = parse("(/ close (sma close 20))")
        result = validate(node)
        assert result.valid

    def test_valid_abs(self):
        node = parse("(abs (- close open))")
        result = validate(node)
        assert result.valid

    def test_subtract_wrong_arg_count(self):
        node = parse("(- a)")
        result = validate(node)
        assert not result.valid


class TestValidateSymbols:
    """Test validation of symbol references."""

    def test_valid_price_symbols(self):
        for sym in ["close", "open", "high", "low", "volume"]:
            node = parse(sym)
            result = validate(node)
            assert result.valid, f"Symbol {sym} should be valid"

    def test_valid_dollar_prefix(self):
        node = parse("$symbol")
        result = validate(node)
        assert result.valid

    def test_invalid_symbol(self):
        node = parse("unknown_symbol")
        result = validate(node)
        assert not result.valid
        assert any("Unknown symbol" in str(e) for e in result.errors)


class TestValidateUnknownFunction:
    """Test validation of unknown functions."""

    def test_unknown_function(self):
        node = parse("(unknown_fn a b)")
        result = validate(node)
        assert not result.valid
        assert any("Unknown function" in str(e) for e in result.errors)


class TestValidateStrategy:
    """Test validation of complete strategy definitions."""

    def test_valid_minimal_strategy(self):
        source = """
        (strategy
          :name "Test"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry (> (rsi close 14) 30)
          :exit (< (rsi close 14) 70))
        """
        strategy = parse_strategy(source)
        result = validate_strategy(strategy)
        assert result.valid, f"Errors: {result.errors}"

    def test_valid_full_strategy(self):
        source = """
        (strategy
          :name "EMA Crossover"
          :description "Test strategy"
          :type trend_following
          :symbols ["AAPL" "MSFT"]
          :timeframe "1H"
          :entry (and
                   (cross-above (ema close 12) (ema close 26))
                   (> (rsi close 14) 50))
          :exit (cross-below (ema close 12) (ema close 26))
          :stop-loss-pct 2.0
          :take-profit-pct 6.0
          :max-positions 5)
        """
        strategy = parse_strategy(source)
        result = validate_strategy(strategy)
        assert result.valid, f"Errors: {result.errors}"

    def test_missing_name(self):
        strategy = Strategy(
            name="",
            symbols=["AAPL"],
            timeframe="1D",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("name is required" in str(e) for e in result.errors)

    def test_empty_symbols(self):
        strategy = Strategy(
            name="Test",
            symbols=[],
            timeframe="1D",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("At least one symbol" in str(e) for e in result.errors)

    def test_invalid_timeframe(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="2D",  # Invalid
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("Invalid timeframe" in str(e) for e in result.errors)

    def test_invalid_strategy_type(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            strategy_type="invalid_type",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("Invalid strategy type" in str(e) for e in result.errors)

    def test_invalid_entry_condition(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=parse("(sma close 20)"),  # Not a condition
            exit=parse("(< close 90)"),
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("Expected condition" in str(e) for e in result.errors)


class TestValidateRiskConfig:
    """Test validation of risk configuration."""

    def test_valid_risk_config(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
            risk={
                "stop_loss_pct": 2.0,
                "take_profit_pct": 6.0,
                "max_positions": 5,
            },
        )
        result = validate_strategy(strategy)
        assert result.valid

    def test_stop_loss_out_of_range(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
            risk={"stop_loss_pct": 150},  # > 100
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("stop_loss_pct" in str(e) for e in result.errors)

    def test_take_profit_out_of_range(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
            risk={"take_profit_pct": 1500},  # > 1000
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("take_profit_pct" in str(e) for e in result.errors)

    def test_max_positions_invalid(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
            risk={"max_positions": 0},  # Must be positive
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("max_positions" in str(e) for e in result.errors)


class TestValidateSizingConfig:
    """Test validation of position sizing configuration."""

    def test_valid_percent_equity(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
            sizing={"type": "percent-equity", "value": 10},
        )
        result = validate_strategy(strategy)
        assert result.valid

    def test_invalid_sizing_type(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
            sizing={"type": "invalid-type", "value": 10},
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("Invalid sizing type" in str(e) for e in result.errors)

    def test_percent_equity_out_of_range(self):
        strategy = Strategy(
            name="Test",
            symbols=["AAPL"],
            timeframe="1D",
            entry=parse("(> close 100)"),
            exit=parse("(< close 90)"),
            sizing={"type": "percent-equity", "value": 150},  # > 100
        )
        result = validate_strategy(strategy)
        assert not result.valid
        assert any("sizing.value" in str(e) for e in result.errors)
