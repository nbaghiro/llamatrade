"""Deep round-trip fidelity: serialize(parse(x)) must preserve the whole AST.

The JSON IR is used as the canonical comparison form, so any field the
serializer drops (the group :weight regression) fails loudly instead of
passing a shallow shape check.
"""

import pytest

from llamatrade_dsl import parse, serialize, to_json, validate

CASES = [
    (
        "group-weights-specified",
        """
        (strategy "Classic 60/40" :rebalance monthly :benchmark SPY
            (weight :method specified
                (group "Equities" :weight 60
                    (asset VTI)
                    (asset QQQ))
                (group "Bonds" :weight 40
                    (asset TLT))))
        """,
    ),
    (
        "nested-weight-blocks",
        """
        (strategy "Nested" :rebalance weekly
            (weight :method equal
                (weight :method specified
                    (asset AAA :weight 70)
                    (asset BBB :weight 30))
                (asset CCC)))
        """,
    ),
    (
        "conditional-with-groups",
        """
        (strategy "Defensive" :rebalance monthly
            (if (> (rsi SPY 14) 70)
                (weight :method specified
                    (group "Safety" :weight 100
                        (asset TLT)
                        (asset GLD)))
                (else
                    (weight :method momentum :lookback 90 :top 2
                        (asset VTI)
                        (asset QQQ)
                        (asset IWM)))))
        """,
    ),
]


@pytest.mark.parametrize("name,source", CASES, ids=[c[0] for c in CASES])
def test_serialize_round_trip_is_lossless(name: str, source: str) -> None:
    original = parse(source)
    assert validate(original).valid, f"{name}: source must validate"

    reparsed = parse(serialize(original))
    assert to_json(reparsed) == to_json(original), f"{name}: round trip lost AST content"

    result = validate(reparsed)
    assert result.valid, f"{name}: round-tripped DSL failed validation: {result.errors}"


@pytest.mark.parametrize("name,source", CASES, ids=[c[0] for c in CASES])
def test_pretty_serialize_round_trip_is_lossless(name: str, source: str) -> None:
    original = parse(source)
    reparsed = parse(serialize(original, pretty=True))
    assert to_json(reparsed) == to_json(original), f"{name}: pretty round trip lost AST content"
