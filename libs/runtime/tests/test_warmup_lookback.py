"""Warm-up requirement (`min_bars`) must include weight/filter/metric lookbacks.

Regression for the gap where a strategy with no condition indicators warmed up in just 2 bars
and traded a degenerate (equal-weight) allocation until its real lookback filled.
"""

from llamatrade_dsl import parse_strategy
from llamatrade_runtime import compile_strategy


def _min_bars(sexpr: str) -> int:
    return compile_strategy(parse_strategy(sexpr)).min_bars


def test_momentum_weight_lookback_counts_toward_warmup() -> None:
    # +1: momentum ranks by trailing_return, which reads bars[-(lookback+1)].
    s = (
        '(strategy "M" :rebalance monthly '
        "(weight :method momentum :lookback 30 (asset AAA) (asset BBB) (asset CCC)))"
    )
    assert _min_bars(s) == 31


def test_default_momentum_lookback() -> None:
    s = '(strategy "M" :rebalance monthly (weight :method momentum (asset AAA) (asset BBB)))'
    assert _min_bars(s) == 91  # 90 default + 1


def test_filter_lookback_counts_toward_warmup() -> None:
    s = (
        '(strategy "F" :rebalance monthly '
        "(filter :by momentum :select (top 2) :lookback 45 "
        "(weight :method equal (asset AAA) (asset BBB) (asset CCC))))"
    )
    assert _min_bars(s) == 46  # 45 + 1


def test_metric_period_counts_toward_warmup() -> None:
    # (return SYM N) reads bars[-(N+1)], so warm-up needs N+1 bars.
    s = (
        '(strategy "R" :rebalance daily '
        "(if (> (return SPY 60) 0) (asset SPY :weight 100) (else (asset BIL :weight 100))))"
    )
    assert _min_bars(s) == 61


def test_largest_lookback_wins() -> None:
    # A 200-bar indicator dominates a 30-bar momentum weight.
    s = (
        '(strategy "X" :rebalance monthly '
        "(if (> (sma SPY 200) 0) "
        "(weight :method momentum :lookback 30 (asset AAA) (asset BBB)) "
        "(else (asset BIL :weight 100))))"
    )
    assert _min_bars(s) == 200
