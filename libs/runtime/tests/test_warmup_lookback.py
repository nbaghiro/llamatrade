"""Warm-up requirement (`min_bars`) must include weight/filter/metric lookbacks.

Regression for the gap where a strategy with no condition indicators warmed up in just 2 bars
and traded a degenerate (equal-weight) allocation until its real lookback filled.
"""

from llamatrade_dsl import parse_strategy
from llamatrade_runtime import compile_strategy


def _min_bars(sexpr: str) -> int:
    return compile_strategy(parse_strategy(sexpr)).min_bars


def test_momentum_weight_lookback_counts_toward_warmup() -> None:
    s = (
        '(strategy "M" :rebalance monthly '
        "(weight :method momentum :lookback 30 (asset AAA) (asset BBB) (asset CCC)))"
    )
    assert _min_bars(s) == 30


def test_default_momentum_lookback_is_90() -> None:
    s = '(strategy "M" :rebalance monthly (weight :method momentum (asset AAA) (asset BBB)))'
    assert _min_bars(s) == 90


def test_filter_lookback_counts_toward_warmup() -> None:
    s = (
        '(strategy "F" :rebalance monthly '
        "(filter :by momentum :select (top 2) :lookback 45 "
        "(weight :method equal (asset AAA) (asset BBB) (asset CCC))))"
    )
    assert _min_bars(s) == 45


def test_metric_period_counts_toward_warmup() -> None:
    s = (
        '(strategy "R" :rebalance daily '
        "(if (> (return SPY 60) 0) (asset SPY :weight 100) (else (asset BIL :weight 100))))"
    )
    assert _min_bars(s) == 60


def test_largest_lookback_wins() -> None:
    # A 200-bar indicator dominates a 30-bar momentum weight.
    s = (
        '(strategy "X" :rebalance monthly '
        "(if (> (sma SPY 200) 0) "
        "(weight :method momentum :lookback 30 (asset AAA) (asset BBB)) "
        "(else (asset BIL :weight 100))))"
    )
    assert _min_bars(s) == 200
