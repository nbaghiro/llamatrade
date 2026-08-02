"""Golden tests for hierarchical weight composition.

These pin the documented semantics from strategy-dsl.md: a weight block gives each
child block a share of capital, and the child subdivides its share by its own
method; group :weight scales the group's subtree; sibling contributions to the
same symbol sum; a bare asset allocates rather than liquidating.
"""

from datetime import UTC, datetime, timedelta

import pytest

from llamatrade_dsl import parse
from llamatrade_runtime.evaluation.compiled import compile_strategy
from llamatrade_runtime.types import Bar


def allocate(sexpr: str, symbols: list[str]) -> dict[str, float]:
    """Compile and evaluate with just enough flat-price history to pass the gate."""
    compiled = compile_strategy(parse(sexpr))
    base = datetime(2024, 1, 1, tzinfo=UTC)
    weights: dict[str, float] = {}
    for i in range(max(compiled.min_bars, 2) + 1):
        ts = base + timedelta(days=i)
        bars = {
            s: Bar(timestamp=ts, open=100.0, high=100.5, low=99.5, close=100.0, volume=1000)
            for s in symbols
        }
        weights = compiled.compute_allocation(bars)["weights"]
    return weights


def test_group_weights_scale_their_subtrees() -> None:
    sexpr = """
    (strategy "Classic" :rebalance monthly
        (weight :method specified
            (group "Equities" :weight 60
                (asset VTI)
                (asset QQQ))
            (group "Bonds" :weight 40
                (asset TLT))))
    """
    weights = allocate(sexpr, ["VTI", "QQQ", "TLT"])
    assert weights["VTI"] == pytest.approx(30.0)
    assert weights["QQQ"] == pytest.approx(30.0)
    assert weights["TLT"] == pytest.approx(40.0)


def test_nested_equal_composes_hierarchically() -> None:
    sexpr = """
    (strategy "Nested" :rebalance monthly
        (weight :method equal
            (weight :method equal
                (asset AAA)
                (asset BBB))
            (asset CCC)))
    """
    weights = allocate(sexpr, ["AAA", "BBB", "CCC"])
    assert weights["AAA"] == pytest.approx(25.0)
    assert weights["BBB"] == pytest.approx(25.0)
    assert weights["CCC"] == pytest.approx(50.0)


def test_specified_inside_equal() -> None:
    sexpr = """
    (strategy "Mixed" :rebalance monthly
        (weight :method equal
            (weight :method specified
                (asset AAA :weight 70)
                (asset BBB :weight 30))
            (weight :method equal
                (asset CCC)
                (asset DDD))))
    """
    weights = allocate(sexpr, ["AAA", "BBB", "CCC", "DDD"])
    assert weights["AAA"] == pytest.approx(35.0)
    assert weights["BBB"] == pytest.approx(15.0)
    assert weights["CCC"] == pytest.approx(25.0)
    assert weights["DDD"] == pytest.approx(25.0)


def test_duplicate_symbol_sums_across_branches() -> None:
    sexpr = """
    (strategy "Dup" :rebalance monthly
        (weight :method equal
            (group "One"
                (asset SPY))
            (group "Two"
                (asset SPY)
                (asset TLT))))
    """
    weights = allocate(sexpr, ["SPY", "TLT"])
    assert weights["SPY"] == pytest.approx(75.0)
    assert weights["TLT"] == pytest.approx(25.0)


def test_bare_asset_holds_instead_of_liquidating() -> None:
    weights = allocate('(strategy "Solo" :rebalance daily (asset VTI))', ["VTI"])
    assert weights == {"VTI": pytest.approx(100.0)}


def test_bare_sibling_assets_split_equally() -> None:
    sexpr = '(strategy "Pair" :rebalance daily (asset VTI) (asset TLT))'
    weights = allocate(sexpr, ["VTI", "TLT"])
    assert weights["VTI"] == pytest.approx(50.0)
    assert weights["TLT"] == pytest.approx(50.0)


def test_group_of_bare_assets_splits_its_share_equally() -> None:
    sexpr = """
    (strategy "OneGroup" :rebalance monthly
        (weight :method specified
            (group "All" :weight 100
                (asset AAA)
                (asset BBB)
                (asset CCC))))
    """
    weights = allocate(sexpr, ["AAA", "BBB", "CCC"])
    for symbol in ("AAA", "BBB", "CCC"):
        assert weights[symbol] == pytest.approx(100.0 / 3)


def test_flat_specified_unchanged() -> None:
    sexpr = """
    (strategy "Flat" :rebalance monthly
        (weight :method specified
            (asset SPY :weight 60)
            (asset TLT :weight 40)))
    """
    weights = allocate(sexpr, ["SPY", "TLT"])
    assert weights["SPY"] == pytest.approx(60.0)
    assert weights["TLT"] == pytest.approx(40.0)
