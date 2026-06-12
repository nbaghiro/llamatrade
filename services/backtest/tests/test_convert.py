"""Tests for the shared safe_float converter."""

from decimal import Decimal

from src.convert import safe_float


class TestSafeFloat:
    def test_none_returns_default(self):
        assert safe_float(None) == 0.0
        assert safe_float(None, default=1.5) == 1.5

    def test_numbers_pass_through(self):
        assert safe_float(3) == 3.0
        assert safe_float(2.5) == 2.5

    def test_numeric_string(self):
        assert safe_float("4.25") == 4.25

    def test_unparseable_string_returns_default(self):
        assert safe_float("not a number") == 0.0
        assert safe_float("", default=-1.0) == -1.0

    def test_decimal_converts(self):
        assert safe_float(Decimal("7.50")) == 7.5

    def test_unconvertible_object_returns_default(self):
        assert safe_float(object(), default=9.0) == 9.0

    def test_failing_dunder_float_returns_default(self):
        class Broken:
            def __float__(self) -> float:
                raise ValueError("nope")

        assert safe_float(Broken(), default=2.0) == 2.0
