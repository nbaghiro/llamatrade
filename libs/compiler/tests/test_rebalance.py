"""Tests for the single rebalance clock."""

from datetime import date

from llamatrade_compiler.rebalance import should_rebalance


def test_first_evaluation_always_rebalances():
    assert should_rebalance(date(2024, 1, 2), None, "daily") is True
    assert should_rebalance(date(2024, 1, 2), None, "monthly") is True
    assert should_rebalance(date(2024, 1, 2), None, None) is True


def test_same_day_never_rebalances():
    d = date(2024, 1, 2)
    assert should_rebalance(d, d, "daily") is False
    assert should_rebalance(d, d, "monthly") is False


def test_daily():
    assert should_rebalance(date(2024, 1, 3), date(2024, 1, 2), "daily") is True


def test_weekly_only_on_monday():
    # 2024-01-08 is a Monday; 2024-01-09 a Tuesday.
    assert should_rebalance(date(2024, 1, 8), date(2024, 1, 2), "weekly") is True
    assert should_rebalance(date(2024, 1, 9), date(2024, 1, 2), "weekly") is False


def test_monthly():
    assert should_rebalance(date(2024, 2, 1), date(2024, 1, 31), "monthly") is True
    assert should_rebalance(date(2024, 1, 31), date(2024, 1, 2), "monthly") is False


def test_quarterly():
    assert should_rebalance(date(2024, 4, 1), date(2024, 3, 31), "quarterly") is True
    assert should_rebalance(date(2024, 3, 31), date(2024, 1, 2), "quarterly") is False


def test_annually():
    assert should_rebalance(date(2025, 1, 1), date(2024, 12, 31), "annually") is True
    assert should_rebalance(date(2024, 12, 31), date(2024, 1, 2), "annually") is False


def test_none_frequency_defaults_to_daily():
    assert should_rebalance(date(2024, 1, 3), date(2024, 1, 2), None) is True
