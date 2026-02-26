"""Tests for data validation module."""

from datetime import UTC, datetime, timedelta

import pytest
from src.engine.validation import (
    DataValidator,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    log_validation_result,
    validate_bars,
)


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_issue_str_with_timestamp(self):
        """Test string representation with timestamp."""
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            symbol="AAPL",
            bar_index=5,
            timestamp=datetime(2024, 1, 5, tzinfo=UTC),
            field="high",
            message="High is less than close",
        )

        result = str(issue)
        assert "ERROR" in result
        assert "AAPL" in result
        assert "high" in result

    def test_issue_str_without_timestamp(self):
        """Test string representation without timestamp."""
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            symbol="AAPL",
            bar_index=5,
            timestamp=None,
            field="volume",
            message="Low volume",
        )

        result = str(issue)
        assert "WARNING" in result
        assert "index 5" in result


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_empty_result(self):
        """Test empty validation result."""
        result = ValidationResult(valid=True)

        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_result_with_errors(self):
        """Test result with errors."""
        issues = [
            ValidationIssue(ValidationSeverity.ERROR, "AAPL", 0, None, "high", "error"),
            ValidationIssue(ValidationSeverity.WARNING, "AAPL", 1, None, "volume", "warning"),
            ValidationIssue(ValidationSeverity.ERROR, "AAPL", 2, None, "low", "error2"),
        ]
        result = ValidationResult(valid=False, issues=issues, symbols_checked=1, bars_checked=3)

        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_result_summary(self):
        """Test result summary."""
        issues = [
            ValidationIssue(ValidationSeverity.ERROR, "AAPL", 0, None, "high", "error"),
            ValidationIssue(ValidationSeverity.WARNING, "AAPL", 1, None, "volume", "warning"),
        ]
        result = ValidationResult(valid=False, issues=issues, symbols_checked=2, bars_checked=100)

        summary = result.summary()
        assert "100 bars" in summary
        assert "2 symbols" in summary
        assert "1 errors" in summary
        assert "1 warnings" in summary


class TestDataValidator:
    """Tests for DataValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return DataValidator()

    @pytest.fixture
    def valid_bars(self):
        """Create valid bar data."""
        base_date = datetime(2024, 1, 1, tzinfo=UTC)
        return {
            "AAPL": [
                {
                    "timestamp": base_date + timedelta(days=i),
                    "open": 100.0 + i,
                    "high": 105.0 + i,
                    "low": 95.0 + i,
                    "close": 102.0 + i,
                    "volume": 10000,
                }
                for i in range(10)
            ]
        }

    def test_validate_valid_data(self, validator, valid_bars):
        """Test validating correct data."""
        result = validator.validate(valid_bars)

        assert result.valid is True
        assert len(result.errors) == 0
        assert result.symbols_checked == 1
        assert result.bars_checked == 10

    def test_validate_high_less_than_open_close(self, validator):
        """Test detection of high < open/close."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 95.0,  # Invalid: high < open
                    "low": 90.0,
                    "close": 98.0,
                    "volume": 10000,
                }
            ]
        }

        result = validator.validate(bars)

        assert result.valid is False
        assert len(result.errors) >= 1
        assert any("high" in str(e).lower() for e in result.errors)

    def test_validate_low_greater_than_open_close(self, validator):
        """Test detection of low > open/close."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 102.0,  # Invalid: low > open
                    "close": 98.0,  # Invalid: low > close
                    "volume": 10000,
                }
            ]
        }

        result = validator.validate(bars)

        assert result.valid is False
        assert len(result.errors) >= 1

    def test_validate_high_less_than_low(self, validator):
        """Test detection of high < low."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 90.0,  # Invalid: high < low
                    "low": 95.0,
                    "close": 92.0,
                    "volume": 10000,
                }
            ]
        }

        result = validator.validate(bars)

        assert result.valid is False
        assert any("high" in str(e).lower() and "low" in str(e).lower() for e in result.errors)

    def test_validate_negative_price(self, validator):
        """Test detection of negative prices."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": -100.0,  # Invalid: negative price
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 10000,
                }
            ]
        }

        result = validator.validate(bars)

        assert result.valid is False
        assert any("non-positive" in str(e).lower() for e in result.errors)

    def test_validate_zero_price(self, validator):
        """Test detection of zero prices."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 0.0,  # Invalid: zero price
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 10000,
                }
            ]
        }

        result = validator.validate(bars)

        assert result.valid is False

    def test_validate_negative_volume(self, validator):
        """Test detection of negative volume."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": -1000,  # Invalid
                }
            ]
        }

        result = validator.validate(bars)

        assert result.valid is False
        assert any("negative volume" in str(e).lower() for e in result.errors)

    def test_validate_timestamp_ordering(self, validator):
        """Test detection of non-increasing timestamps."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 10000,
                },
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),  # Before previous
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 10000,
                },
            ]
        }

        result = validator.validate(bars)

        assert result.valid is False
        assert any("timestamp" in str(e).lower() for e in result.errors)

    def test_validate_large_gap_warning(self, validator):
        """Test warning for large gaps in data."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 10000,
                },
                {
                    "timestamp": datetime(2024, 1, 15, tzinfo=UTC),  # 14 day gap
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 10000,
                },
            ]
        }

        result = validator.validate(bars)

        # Large gap should trigger warning, not error
        assert result.valid is True  # Still valid
        assert len(result.warnings) >= 1
        assert any("gap" in str(w).lower() for w in result.warnings)

    def test_validate_extreme_price_change_warning(self, validator):
        """Test warning for extreme price changes."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 100.0,
                    "volume": 10000,
                },
                {
                    "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
                    "open": 200.0,
                    "high": 205.0,
                    "low": 195.0,
                    "close": 200.0,  # 100% change
                    "volume": 10000,
                },
            ]
        }

        result = validator.validate(bars)

        # Extreme change should trigger warning
        assert len(result.warnings) >= 1
        assert any(
            "extreme" in str(w).lower() or "split" in str(w).lower() for w in result.warnings
        )

    def test_validate_empty_symbol_bars(self, validator):
        """Test validation of empty bar list."""
        bars = {"AAPL": []}

        result = validator.validate(bars)

        assert len(result.warnings) >= 1
        assert any("no bar data" in str(w).lower() for w in result.warnings)

    def test_validate_low_volume_warning(self):
        """Test warning for low volume."""
        validator = DataValidator(min_volume=1000)
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 100,  # Below minimum
                }
            ]
        }

        result = validator.validate(bars)

        assert len(result.warnings) >= 1
        assert any("low volume" in str(w).lower() for w in result.warnings)


class TestValidateBarsFunction:
    """Tests for the validate_bars convenience function."""

    def test_validate_bars_basic(self):
        """Test basic validation."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 10000,
                }
            ]
        }

        result = validate_bars(bars)

        assert result.valid is True

    def test_validate_bars_strict_mode(self):
        """Test strict mode elevates warnings to errors."""
        bars = {
            "AAPL": [
                {
                    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 100.0,
                    "volume": 10000,
                },
                {
                    "timestamp": datetime(2024, 1, 15, tzinfo=UTC),  # Large gap
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 10000,
                },
            ]
        }

        # Normal mode: warnings don't make it invalid
        result_normal = validate_bars(bars, strict=False)
        assert result_normal.valid is True

        # Strict mode: warnings become errors
        result_strict = validate_bars(bars, strict=True)
        assert result_strict.valid is False


class TestLogValidationResult:
    """Tests for log_validation_result function."""

    def test_log_valid_result(self, caplog):
        """Test logging valid result."""
        result = ValidationResult(valid=True, symbols_checked=1, bars_checked=10)
        log_validation_result(result)
        # Should log info level for valid result

    def test_log_invalid_result(self, caplog):
        """Test logging invalid result."""
        issues = [
            ValidationIssue(ValidationSeverity.ERROR, "AAPL", 0, None, "high", "error"),
        ]
        result = ValidationResult(valid=False, issues=issues)
        log_validation_result(result)
        # Should log warning/error level for invalid result
