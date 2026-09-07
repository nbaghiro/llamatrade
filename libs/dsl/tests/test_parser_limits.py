"""Parser resource limits: hostile nesting or size must fail as ParseError, never exhaustion."""

import pytest

from llamatrade_dsl import parse
from llamatrade_dsl.parser import _MAX_SOURCE_CHARS, ParseError


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


def test_oversized_source_raises_parse_error() -> None:
    source = '(strategy "Big" :rebalance daily (asset SPY :weight 100))'
    with pytest.raises(ParseError, match="Source exceeds"):
        parse(source.ljust(_MAX_SOURCE_CHARS + 1))


def test_source_at_cap_parses() -> None:
    source = '(strategy "Big" :rebalance daily (asset SPY :weight 100))'
    strategy = parse(source.ljust(_MAX_SOURCE_CHARS))
    assert strategy.name == "Big"
