"""Tests for history windowing — the bar-retention bound derived from a strategy AST.

``compute_window``/``max_lookback`` decide how much history the evaluator keeps and how
long it warms up, so an under-reported lookback silently evaluates indicators on
insufficient data. These cover every block/condition shape that contributes a lookback.
"""

import pytest

from llamatrade_dsl import parse_strategy
from llamatrade_dsl.window import collect_lookbacks, compute_window, max_lookback

_HEADER = '(strategy "S" :benchmark SPY :rebalance daily'
_WINDOW_BUFFER = 10
_MAX_WINDOW = 2000


def _parse(body: str):
    return parse_strategy(f"{_HEADER}\n{body})")


class TestBoundedLookbacks:
    """Strategies whose reads are all bounded cap at exactly the largest window read."""

    def test_plain_asset_falls_back_to_min_bars(self) -> None:
        strategy = _parse("(asset SPY :weight 100)")
        assert max_lookback(strategy, 14) == 14
        assert compute_window(strategy, 14) == 14 + _WINDOW_BUFFER

    def test_momentum_weight_uses_explicit_lookback(self) -> None:
        strategy = _parse("(weight :method momentum :lookback 250 (asset SPY))")
        assert max_lookback(strategy, 14) == 250

    def test_momentum_weight_defaults_to_90(self) -> None:
        strategy = _parse("(weight :method momentum (asset SPY))")
        assert max_lookback(strategy, 14) == 90

    @pytest.mark.parametrize("method", ["inverse-volatility", "risk-parity", "min-variance"])
    def test_volatility_weights_default_to_60(self, method: str) -> None:
        strategy = _parse(f"(weight :method {method} (asset SPY))")
        assert max_lookback(strategy, 14) == 60

    def test_equal_weight_contributes_no_lookback(self) -> None:
        strategy = _parse("(weight :method equal (asset SPY) (asset AGG))")
        assert max_lookback(strategy, 14) == 14

    def test_metric_with_period_is_bounded(self) -> None:
        strategy = _parse(
            "(if (> (return SPY 120) 0) (asset SPY :weight 100) (else (asset AGG :weight 100)))"
        )
        needed, unbounded = collect_lookbacks(strategy, 14)
        assert (needed, unbounded) == (120, False)
        assert compute_window(strategy, 14) == 120 + _WINDOW_BUFFER

    def test_min_bars_wins_when_larger_than_block_lookbacks(self) -> None:
        strategy = _parse("(weight :method momentum :lookback 20 (asset SPY))")
        assert max_lookback(strategy, 200) == 200


class TestUnboundedReads:
    """A period-less metric reads all history and is capped rather than left to grow."""

    def test_periodless_metric_caps_at_max_window(self) -> None:
        strategy = _parse(
            "(if (> (return SPY) 0) (asset SPY :weight 100) (else (asset AGG :weight 100)))"
        )
        assert collect_lookbacks(strategy, 14)[1] is True
        assert compute_window(strategy, 14) == _MAX_WINDOW

    def test_cap_never_falls_below_warmup_need(self) -> None:
        """A warm-up larger than the cap wins — the window must cover what warm-up reads."""
        strategy = _parse(
            "(if (> (return SPY) 0) (asset SPY :weight 100) (else (asset AGG :weight 100)))"
        )
        assert compute_window(strategy, 5000) == 5000 + _WINDOW_BUFFER

    def test_custom_max_window_is_honoured(self) -> None:
        strategy = _parse(
            "(if (> (return SPY) 0) (asset SPY :weight 100) (else (asset AGG :weight 100)))"
        )
        assert compute_window(strategy, 14, max_window=500) == 500


class TestAllSiblingsAreWalked:
    """An unbounded read must not stop the walk — later siblings still carry lookbacks."""

    _IF = "(if (> (return SPY) 0) (asset AAA :weight 100) (else (asset BBB :weight 100)))"
    _MOMENTUM = "(weight :method momentum :lookback 300 (asset CCC))"

    def test_lookback_survives_unbounded_sibling_regardless_of_order(self) -> None:
        first = _parse(f'(group "G" {self._IF} {self._MOMENTUM})')
        second = _parse(f'(group "G" {self._MOMENTUM} {self._IF})')
        assert max_lookback(first, 5) == 300
        assert max_lookback(second, 5) == max_lookback(first, 5)

    def test_lookback_survives_inside_weight_children(self) -> None:
        strategy = _parse(
            f"(weight :method equal {self._IF}"
            " (filter :by momentum :select (top 1) :lookback 400 (asset DDD) (asset EEE)))"
        )
        assert max_lookback(strategy, 5) == 400

    def test_filter_default_lookback_is_90(self) -> None:
        strategy = _parse("(filter :by momentum :select (top 1) (asset SPY) (asset AGG))")
        assert max_lookback(strategy, 5) == 90

    def test_both_sides_of_a_comparison_are_walked(self) -> None:
        strategy = _parse(
            "(if (> (return SPY) (return AGG 250))"
            " (asset SPY :weight 100) (else (asset AGG :weight 100)))"
        )
        needed, unbounded = collect_lookbacks(strategy, 5)
        assert unbounded is True
        assert needed == 250  # the bounded right-hand side still contributed

    def test_both_sides_of_a_crossover_are_walked(self) -> None:
        strategy = _parse(
            "(if (crosses-above (return SPY) (return AGG 180))"
            " (asset SPY :weight 100) (else (asset AGG :weight 100)))"
        )
        assert collect_lookbacks(strategy, 5) == (180, True)

    def test_every_logical_operand_is_walked(self) -> None:
        strategy = _parse(
            "(if (and (> (return SPY) 0) (> (return AGG 365) 0))"
            " (asset SPY :weight 100) (else (asset AGG :weight 100)))"
        )
        assert collect_lookbacks(strategy, 5) == (365, True)

    def test_else_branch_is_walked(self) -> None:
        strategy = _parse(
            f"(if (> (rsi SPY 14) 70) (asset SPY :weight 100) (else {self._MOMENTUM}))"
        )
        assert max_lookback(strategy, 5) == 300
