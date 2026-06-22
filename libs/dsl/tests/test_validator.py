"""Tests for allocation-based strategy DSL validator."""

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
    validate,
    validate_strategy,
)


class TestValidateStrategy:
    """Test strategy validation."""

    def test_valid_simple_strategy(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="equal",
                    children=[Asset(symbol="VTI"), Asset(symbol="BND")],
                )
            ],
        )
        result = validate(strategy)
        assert result.valid

    def test_strategy_missing_name(self):
        strategy = Strategy(
            name="",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("name is required" in str(e) for e in result.errors)

    def test_strategy_no_children(self):
        strategy = Strategy(name="Test", children=[])
        result = validate(strategy)
        assert not result.valid
        assert any("at least one allocation block" in str(e) for e in result.errors)

    def test_strategy_invalid_rebalance(self):
        strategy = Strategy(
            name="Test",
            rebalance="invalid",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("rebalance frequency" in str(e) for e in result.errors)


class TestValidateWeight:
    """Test weight block validation."""

    def test_valid_specified_weights(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="specified",
                    children=[
                        Asset(symbol="VTI", weight=60),
                        Asset(symbol="BND", weight=40),
                    ],
                )
            ],
        )
        result = validate(strategy)
        assert result.valid

    def test_specified_weights_not_100(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="specified",
                    children=[
                        Asset(symbol="VTI", weight=60),
                        Asset(symbol="BND", weight=30),  # Only 90%
                    ],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("sum to 100%" in str(e) for e in result.errors)

    def test_specified_missing_weights(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="specified",
                    children=[
                        Asset(symbol="VTI", weight=60),
                        Asset(symbol="BND"),  # Missing weight
                    ],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("must have :weight" in str(e) for e in result.errors)

    def test_equal_with_weights_error(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="equal",
                    children=[
                        Asset(symbol="VTI", weight=50),  # Should not have weight
                        Asset(symbol="BND", weight=50),
                    ],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("should not have :weight" in str(e) for e in result.errors)

    def test_valid_equal_weights(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="equal",
                    children=[Asset(symbol="VTI"), Asset(symbol="BND")],
                )
            ],
        )
        result = validate(strategy)
        assert result.valid

    def test_valid_momentum_with_lookback(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="momentum",
                    lookback=90,
                    children=[Asset(symbol="XLK"), Asset(symbol="XLF")],
                )
            ],
        )
        result = validate(strategy)
        assert result.valid

    def test_invalid_lookback(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="momentum",
                    lookback=-10,  # Invalid
                    children=[Asset(symbol="XLK")],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("positive integer" in str(e) for e in result.errors)

    def test_market_cap_method_rejected(self):
        # market-cap needs fundamental data the engine does not have -> rejected.
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="market-cap",
                    children=[Asset(symbol="AAA"), Asset(symbol="BBB")],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("market-cap" in str(e) for e in result.errors)

    def test_invalid_top_exceeds_children(self):
        strategy = Strategy(
            name="Test",
            children=[
                Weight(
                    method="momentum",
                    lookback=90,
                    top=5,  # Only 2 children
                    children=[Asset(symbol="XLK"), Asset(symbol="XLF")],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("exceeds children" in str(e) for e in result.errors)

    def test_weight_no_children(self):
        strategy = Strategy(
            name="Test",
            children=[Weight(method="equal", children=[])],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("at least one child" in str(e) for e in result.errors)


class TestValidateGroup:
    """Test group block validation."""

    def test_valid_group(self):
        strategy = Strategy(
            name="Test",
            children=[
                Group(
                    name="Equities",
                    children=[
                        Weight(
                            method="equal",
                            children=[Asset(symbol="VTI"), Asset(symbol="VXUS")],
                        )
                    ],
                )
            ],
        )
        result = validate(strategy)
        assert result.valid

    def test_group_missing_name(self):
        strategy = Strategy(
            name="Test",
            children=[Group(name="", children=[Asset(symbol="VTI", weight=100)])],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("Group name is required" in str(e) for e in result.errors)

    def test_group_no_children(self):
        strategy = Strategy(
            name="Test",
            children=[Group(name="Empty", children=[])],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("at least one child block" in str(e) for e in result.errors)


class TestValidateAsset:
    """Test asset block validation."""

    def test_valid_asset(self):
        strategy = Strategy(
            name="Test",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = validate(strategy)
        assert result.valid

    def test_asset_empty_symbol(self):
        strategy = Strategy(
            name="Test",
            children=[Asset(symbol="", weight=100)],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("symbol is required" in str(e) for e in result.errors)

    def test_asset_invalid_symbol_start(self):
        strategy = Strategy(
            name="Test",
            children=[Asset(symbol="123ABC", weight=100)],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("start with a letter" in str(e) for e in result.errors)

    def test_asset_negative_weight(self):
        strategy = Strategy(
            name="Test",
            children=[Asset(symbol="VTI", weight=-10)],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("must be positive" in str(e) for e in result.errors)


class TestValidateFilter:
    """Test filter block validation."""

    def test_valid_filter(self):
        strategy = Strategy(
            name="Test",
            children=[
                Filter(
                    by="momentum",
                    select_direction="top",
                    select_count=3,
                    lookback=90,
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
            ],
        )
        result = validate(strategy)
        assert result.valid

    def test_filter_select_exceeds_assets(self):
        strategy = Strategy(
            name="Test",
            children=[
                Filter(
                    by="momentum",
                    select_direction="top",
                    select_count=5,  # Only 2 assets
                    children=[
                        Weight(
                            method="equal",
                            children=[Asset(symbol="XLK"), Asset(symbol="XLF")],
                        )
                    ],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("exceeds available assets" in str(e) for e in result.errors)

    def test_filter_no_children(self):
        strategy = Strategy(
            name="Test",
            children=[
                Filter(
                    by="momentum",
                    select_direction="top",
                    select_count=2,
                    children=[],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("at least one child" in str(e) for e in result.errors)


class TestValidateConditions:
    """Test condition validation (in if blocks)."""

    def test_valid_comparison(self):
        from llamatrade_dsl import If

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
        result = validate(strategy)
        assert result.valid

    def test_invalid_indicator(self):
        from llamatrade_dsl import If

        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Indicator(name="unknown", symbol="SPY", params=(14,)),
                        right=NumericLiteral(value=50),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("Unknown indicator" in str(e) for e in result.errors)

    def test_invalid_indicator_params(self):
        from llamatrade_dsl import If

        strategy = Strategy(
            name="Test",
            children=[
                If(
                    condition=Comparison(
                        operator=">",
                        left=Indicator(name="rsi", symbol="SPY", params=(-14,)),
                        right=NumericLiteral(value=50),
                    ),
                    then_block=Asset(symbol="VTI", weight=100),
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("must be positive" in str(e) for e in result.errors)


class TestValidateStrategyAlias:
    """Test that validate_strategy is an alias for validate."""

    def test_validate_strategy_works(self):
        strategy = Strategy(
            name="Test",
            children=[Asset(symbol="VTI", weight=100)],
        )
        result = validate_strategy(strategy)
        assert result.valid


class TestValidatorRejectPaths:
    """Reject paths that gate bad strategies before persistence/funding (Issue 11A)."""

    @staticmethod
    def _wrap_condition(condition) -> Strategy:
        """Embed a condition in a minimal strategy so the validator reaches it."""
        return Strategy(
            name="T",
            children=[If(condition=condition, then_block=Asset(symbol="VTI", weight=100))],
        )

    # --- Filter block ---

    def test_filter_invalid_criteria(self):
        strategy = Strategy(
            name="T",
            children=[
                Filter(
                    by="bogus",
                    select_direction="top",
                    select_count=1,
                    children=[Asset(symbol="VTI")],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("filter criteria" in str(e).lower() for e in result.errors)

    def test_filter_invalid_direction(self):
        strategy = Strategy(
            name="T",
            children=[
                Filter(
                    by="momentum",
                    select_direction="sideways",
                    select_count=1,
                    children=[Asset(symbol="VTI")],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("select direction" in str(e).lower() for e in result.errors)

    def test_filter_nonpositive_select_count(self):
        strategy = Strategy(
            name="T",
            children=[
                Filter(
                    by="momentum",
                    select_direction="top",
                    select_count=0,
                    children=[Asset(symbol="VTI")],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("select count" in str(e).lower() for e in result.errors)

    def test_filter_select_count_exceeds_assets(self):
        strategy = Strategy(
            name="T",
            children=[
                Filter(
                    by="momentum",
                    select_direction="top",
                    select_count=5,
                    children=[Asset(symbol="VTI"), Asset(symbol="BND")],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("exceeds available" in str(e).lower() for e in result.errors)

    def test_filter_no_children(self):
        strategy = Strategy(
            name="T",
            children=[Filter(by="momentum", select_direction="top", select_count=1, children=[])],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("at least one child" in str(e).lower() for e in result.errors)

    def test_filter_nonpositive_lookback(self):
        strategy = Strategy(
            name="T",
            children=[
                Filter(
                    by="momentum",
                    select_direction="top",
                    select_count=1,
                    lookback=0,
                    children=[Asset(symbol="VTI")],
                )
            ],
        )
        result = validate(strategy)
        assert not result.valid
        assert any("lookback" in str(e).lower() for e in result.errors)

    # --- Conditions ---

    def test_comparison_invalid_operator(self):
        cond = Comparison(
            operator="~=", left=NumericLiteral(value=1), right=NumericLiteral(value=2)
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("comparison operator" in str(e).lower() for e in result.errors)

    def test_crossover_invalid_direction(self):
        cond = Crossover(
            direction="sideways",
            fast=Indicator(name="sma", symbol="SPY", params=(10,)),
            slow=Indicator(name="sma", symbol="SPY", params=(20,)),
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("crossover direction" in str(e).lower() for e in result.errors)

    def test_logical_not_requires_one_operand(self):
        cond = LogicalOp(
            operator="not",
            operands=[
                Comparison(
                    operator=">", left=NumericLiteral(value=1), right=NumericLiteral(value=0)
                ),
                Comparison(
                    operator="<", left=NumericLiteral(value=1), right=NumericLiteral(value=0)
                ),
            ],
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("'not' requires exactly 1" in str(e) for e in result.errors)

    def test_logical_and_requires_two_operands(self):
        cond = LogicalOp(
            operator="and",
            operands=[
                Comparison(
                    operator=">", left=NumericLiteral(value=1), right=NumericLiteral(value=0)
                ),
            ],
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("at least 2 operands" in str(e) for e in result.errors)

    def test_invalid_logical_operator(self):
        cond = LogicalOp(
            operator="xor",
            operands=[
                Comparison(
                    operator=">", left=NumericLiteral(value=1), right=NumericLiteral(value=0)
                ),
                Comparison(
                    operator="<", left=NumericLiteral(value=1), right=NumericLiteral(value=0)
                ),
            ],
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("logical operator" in str(e).lower() for e in result.errors)

    # --- Values: price / indicator / metric ---

    def test_price_invalid_field(self):
        cond = Comparison(
            operator=">", left=Price(symbol="SPY", field="vwap"), right=NumericLiteral(value=1)
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("price field" in str(e).lower() for e in result.errors)

    def test_price_empty_symbol(self):
        cond = Comparison(
            operator=">", left=Price(symbol="  ", field="close"), right=NumericLiteral(value=1)
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("price symbol is required" in str(e).lower() for e in result.errors)

    def test_unknown_indicator_reports_suggestions(self):
        cond = Comparison(
            operator=">",
            left=Indicator(name="smaa", symbol="SPY", params=(14,)),
            right=NumericLiteral(value=1),
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("unknown indicator" in str(e).lower() for e in result.errors)

    def test_indicator_nonpositive_param(self):
        cond = Comparison(
            operator=">",
            left=Indicator(name="sma", symbol="SPY", params=(0,)),
            right=NumericLiteral(value=1),
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("parameter must be positive" in str(e).lower() for e in result.errors)

    def test_indicator_empty_symbol(self):
        cond = Comparison(
            operator=">",
            left=Indicator(name="sma", symbol="", params=(14,)),
            right=NumericLiteral(value=1),
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("indicator symbol is required" in str(e).lower() for e in result.errors)

    def test_unknown_metric(self):
        cond = Comparison(
            operator=">", left=Metric(name="sharpe", symbol="SPY"), right=NumericLiteral(value=1)
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("unknown metric" in str(e).lower() for e in result.errors)

    def test_metric_nonpositive_period(self):
        cond = Comparison(
            operator=">",
            left=Metric(name="return", symbol="SPY", period=0),
            right=NumericLiteral(value=1),
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("metric period must be positive" in str(e).lower() for e in result.errors)

    def test_metric_empty_symbol(self):
        cond = Comparison(
            operator=">", left=Metric(name="return", symbol=" "), right=NumericLiteral(value=1)
        )
        result = validate(self._wrap_condition(cond))
        assert not result.valid
        assert any("metric symbol is required" in str(e).lower() for e in result.errors)
