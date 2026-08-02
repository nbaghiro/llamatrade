"""The indicator vocabulary has one authority (ast.INDICATORS); derived tables must match."""

from llamatrade_dsl.analysis import INDICATOR_DEFAULT_PERIODS
from llamatrade_dsl.ast import INDICATORS


def test_default_periods_table_matches_vocabulary() -> None:
    assert set(INDICATOR_DEFAULT_PERIODS) == set(INDICATORS)
