"""Parser resource limits: hostile nesting must fail as ParseError, never RecursionError."""

import pytest

from llamatrade_dsl import parse
from llamatrade_dsl.parser import ParseError


def _nested_if(depth: int) -> str:
    open_ifs = "".join("(if (> (price SPY) 1) " for _ in range(depth))
    close = ")" * depth
    return f'(strategy "Deep" :rebalance daily {open_ifs}(asset SPY :weight 100){close})'


def test_deep_nesting_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="Nesting exceeds"):
        parse(_nested_if(500))


def test_moderate_nesting_parses() -> None:
    strategy = parse(_nested_if(30))
    assert strategy.name == "Deep"
