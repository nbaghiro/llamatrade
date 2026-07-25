"""Tests for llamatrade_runtime.types module."""

from datetime import UTC, datetime

import pytest

from llamatrade_runtime.types import Bar


class TestBar:
    """Tests for Bar dataclass."""

    def test_bar_creation_with_valid_data(self) -> None:
        """Test creating a Bar with valid OHLCV data."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        bar = Bar(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        assert bar.timestamp == timestamp
        assert bar.open == 100.0
        assert bar.high == 105.0
        assert bar.low == 98.0
        assert bar.close == 103.0
        assert bar.volume == 1000000

    def test_bar_to_dict(self) -> None:
        """Test Bar.to_dict() method."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        bar = Bar(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        d = bar.to_dict()

        assert d["timestamp"] == timestamp
        assert d["open"] == 100.0
        assert d["high"] == 105.0
        assert d["low"] == 98.0
        assert d["close"] == 103.0
        assert d["volume"] == 1000000

    def test_bar_to_dict_round_trip(self) -> None:
        """Test that to_dict() output can recreate equivalent Bar."""
        timestamp = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        original = Bar(
            timestamp=timestamp,
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        d = original.to_dict()
        recreated = Bar(**d)

        assert recreated == original

    def test_bar_with_zero_volume(self) -> None:
        """Test Bar with zero volume (valid but unusual)."""
        bar = Bar(
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=0,
        )

        assert bar.volume == 0
        d = bar.to_dict()
        assert d["volume"] == 0

    def test_bar_with_float_prices(self) -> None:
        """Test Bar with precise float prices."""
        bar = Bar(
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            open=123.456789,
            high=124.987654,
            low=122.111111,
            close=123.999999,
            volume=100,
        )

        assert bar.open == pytest.approx(123.456789)
        assert bar.high == pytest.approx(124.987654)
        assert bar.low == pytest.approx(122.111111)
        assert bar.close == pytest.approx(123.999999)

    def test_bar_with_negative_prices(self) -> None:
        """Test Bar allows negative prices (no validation at type level)."""
        # This tests that the dataclass doesn't validate - validation happens elsewhere
        bar = Bar(
            timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
            open=-10.0,
            high=-5.0,
            low=-15.0,
            close=-8.0,
            volume=100,
        )

        assert bar.open == -10.0
