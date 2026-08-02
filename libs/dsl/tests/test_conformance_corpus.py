"""Python side of the shared Python/TypeScript DSL conformance corpus.

Each tests/conformance/*.sexpr case has a committed *.canonical.json produced by
scripts/generate_conformance_corpus.py (the Python to_json(parse(x)) output is
the authority). This suite fails if the Python parser, serializer, or JSON
projection drifts from the committed canonical form.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llamatrade_dsl.parser import ParseError, parse
from llamatrade_dsl.serializer import serialize
from llamatrade_dsl.to_json import to_json

CORPUS_DIR = Path(__file__).resolve().parents[3] / "tests" / "conformance"
CASES = sorted(CORPUS_DIR.glob("*.sexpr"))


def _load_canonical(case: Path) -> object:
    canonical_path = case.with_suffix(".canonical.json")
    assert canonical_path.exists(), (
        f"Missing {canonical_path.name}; run scripts/generate_conformance_corpus.py"
    )
    return json.loads(canonical_path.read_text(encoding="utf-8"))


def test_corpus_is_present() -> None:
    assert len(CASES) >= 10, f"Expected at least 10 conformance cases in {CORPUS_DIR}"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.stem)
def test_parse_matches_canonical(case: Path) -> None:
    canonical = _load_canonical(case)
    actual = to_json(parse(case.read_text(encoding="utf-8")))
    assert actual == canonical


@pytest.mark.parametrize("pretty", [False, True], ids=["compact", "pretty"])
@pytest.mark.parametrize("case", CASES, ids=lambda case: case.stem)
def test_serialize_round_trip_matches_canonical(case: Path, pretty: bool) -> None:
    canonical = _load_canonical(case)
    round_tripped = parse(serialize(parse(case.read_text(encoding="utf-8")), pretty=pretty))
    assert to_json(round_tripped) == canonical


@pytest.mark.parametrize(
    "retired", [":stop-loss-pct 5", ":take-profit-pct 15", ":position-size 50"]
)
def test_retired_strategy_keywords_rejected(retired: str) -> None:
    source = f'(strategy "Retired" :rebalance daily {retired} (weight :method equal (asset SPY)))'
    with pytest.raises(ParseError):
        parse(source)
