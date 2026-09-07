"""Deep round-trip fidelity: serialize(parse(x)) must preserve the whole AST.

The JSON IR is used as the canonical comparison form, so any field the
serializer drops (the group :weight regression) fails loudly instead of
passing a shallow shape check.
"""

import pytest

from llamatrade_dsl import Asset, Strategy, parse, serialize, to_json, validate

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


ESCAPE_TEXTS = [
    ("literal-backslash-n", "Uses \\n literally"),
    ("double-backslash-n", "Uses \\\\n literally"),
    ("backslash-n-and-quotes", 'Mix "q" then \\n end'),
    ("backslash-before-quote", 'Trail \\" edge'),
    ("trailing-backslash", "Ends with \\"),
    ("real-newline", "Line1\nLine2"),
    ("real-newline-after-backslash-n", "A \\n B\nC"),
]


@pytest.mark.parametrize("pretty", [False, True], ids=["compact", "pretty"])
@pytest.mark.parametrize("case_id,text", ESCAPE_TEXTS, ids=[c[0] for c in ESCAPE_TEXTS])
def test_escape_round_trip_preserves_text(case_id: str, text: str, pretty: bool) -> None:
    original = Strategy(
        name=text,
        description=text,
        children=[Asset(symbol="SPY", weight=100)],
    )
    reparsed = parse(serialize(original, pretty=pretty))
    assert reparsed.name == text, f"{case_id}: name corrupted by escape round trip"
    assert reparsed.description == text, f"{case_id}: description corrupted by escape round trip"
