#!/usr/bin/env python3
"""Regenerate tests/conformance/*.canonical.json and tests/conformance/vocabulary.json.

The Python DSL implementation is the authority: each canonical file is
to_json(parse(source)), and vocabulary.json is the accepted grammar vocabulary read
straight off llamatrade_dsl.ast. Both the Python (libs/dsl) and TypeScript (apps/core)
conformance tests compare against these files, so any divergence between the
two implementations fails CI on the drifted side.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import get_args

from llamatrade_dsl.ast import (
    COMPARISON_OPS,
    CROSSOVER_OPS,
    FILTER_CRITERIA,
    INDICATORS,
    LOGICAL_OPS,
    METRICS,
    REBALANCE_FREQUENCIES,
    WEIGHT_METHODS,
    PriceField,
    SelectDirection,
)
from llamatrade_dsl.parser import parse
from llamatrade_dsl.to_json import to_json

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "tests" / "conformance"
VOCABULARY_PATH = CORPUS_DIR / "vocabulary.json"


def _literal_values(alias: object) -> list[str]:
    """Values of a PEP 695 type alias over a string Literal."""
    return sorted(str(v) for v in get_args(getattr(alias, "__value__")))


def _vocabulary() -> dict[str, list[str]]:
    """The grammar vocabulary the parser accepts, sorted for stable diffs."""
    return {
        "comparison_ops": sorted(COMPARISON_OPS),
        "crossover_ops": sorted(CROSSOVER_OPS),
        "filter_criteria": sorted(FILTER_CRITERIA),
        "indicators": sorted(INDICATORS),
        "logical_ops": sorted(LOGICAL_OPS),
        "metrics": sorted(METRICS),
        "price_fields": _literal_values(PriceField),
        "rebalance_frequencies": sorted(REBALANCE_FREQUENCIES),
        "select_directions": _literal_values(SelectDirection),
        "weight_methods": sorted(WEIGHT_METHODS),
    }


def main() -> int:
    cases = sorted(CORPUS_DIR.glob("*.sexpr"))
    if not cases:
        print(f"No .sexpr cases found in {CORPUS_DIR}", file=sys.stderr)
        return 1

    for case in cases:
        canonical = to_json(parse(case.read_text(encoding="utf-8")))
        out_path = case.with_suffix(".canonical.json")
        out_path.write_text(
            json.dumps(canonical, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {out_path.relative_to(REPO_ROOT)}")

    VOCABULARY_PATH.write_text(
        json.dumps(_vocabulary(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {VOCABULARY_PATH.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
