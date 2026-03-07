"""Data validation for backtest inputs.

Validates OHLCV data to catch anomalies before they corrupt backtest results.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TypedDict

from src.engine.backtester import BarData

logger = logging.getLogger(__name__)


class ValidationSeverity(StrEnum):
    """Severity level for validation issues."""

    ERROR = "error"  # Data cannot be used
    WARNING = "warning"  # Data may produce unexpected results
    INFO = "info"  # Minor issue, informational


@dataclass
class ValidationIssue:
    """A single validation issue."""

    severity: ValidationSeverity
    symbol: str
    bar_index: int
    timestamp: datetime | None
    field: str
    message: str
    value: float | int | None = None

    def __str__(self) -> str:
        ts = self.timestamp.isoformat() if self.timestamp else f"index {self.bar_index}"
        return f"[{self.severity.upper()}] {self.symbol} @ {ts}: {self.field} - {self.message}"


@dataclass
class ValidationResult:
    """Result of data validation."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=lambda: [])
    symbols_checked: int = 0
    bars_checked: int = 0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def summary(self) -> str:
        return (
            f"Validated {self.bars_checked} bars across {self.symbols_checked} symbols. "
            f"Found {len(self.errors)} errors, {len(self.warnings)} warnings."
        )


class BarDataDict(TypedDict):
    """Bar data in dictionary format."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class DataValidator:
    """Validates OHLCV bar data for backtesting."""

    def __init__(
        self,
        max_gap_days: int = 5,  # Max gap between bars before warning
        max_price_change_pct: float = 50.0,  # Max single-bar % change before warning
        min_volume: int = 0,  # Minimum acceptable volume
        check_splits: bool = True,  # Check for potential split anomalies
    ):
        self.max_gap_days = max_gap_days
        self.max_price_change_pct = max_price_change_pct
        self.min_volume = min_volume
        self.check_splits = check_splits

    def validate(
        self,
        bars: dict[str, list[BarData | BarDataDict]],
    ) -> ValidationResult:
        """Validate bar data for all symbols.

        Args:
            bars: Dictionary mapping symbol to list of bars

        Returns:
            ValidationResult with issues found
        """
        issues: list[ValidationIssue] = []
        bars_checked = 0

        for symbol, symbol_bars in bars.items():
            symbol_issues = self._validate_symbol(symbol, symbol_bars)
            issues.extend(symbol_issues)
            bars_checked += len(symbol_bars)

        # Determine if data is valid (no errors)
        has_errors = any(i.severity == ValidationSeverity.ERROR for i in issues)

        return ValidationResult(
            valid=not has_errors,
            issues=issues,
            symbols_checked=len(bars),
            bars_checked=bars_checked,
        )

    def _validate_symbol(
        self,
        symbol: str,
        bars: list[BarData | BarDataDict],
    ) -> list[ValidationIssue]:
        """Validate bars for a single symbol."""
        issues: list[ValidationIssue] = []

        if not bars:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    symbol=symbol,
                    bar_index=0,
                    timestamp=None,
                    field="bars",
                    message="No bar data",
                )
            )
            return issues

        prev_bar = None
        for i, bar in enumerate(bars):
            bar_issues = self._validate_bar(symbol, i, bar, prev_bar)
            issues.extend(bar_issues)
            prev_bar = bar

        return issues

    def _validate_bar(
        self,
        symbol: str,
        index: int,
        bar: BarData | BarDataDict,
        prev_bar: BarData | BarDataDict | None,
    ) -> list[ValidationIssue]:
        """Validate a single bar."""
        issues: list[ValidationIssue] = []
        ts = bar.get("timestamp")

        # Check OHLC relationships
        bar_o = bar["open"]
        bar_h = bar["high"]
        bar_l = bar["low"]
        bar_c = bar["close"]

        if bar_h < max(bar_o, bar_c):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    symbol=symbol,
                    bar_index=index,
                    timestamp=ts,
                    field="high",
                    message=f"High ({bar_h}) is less than open ({bar_o}) or close ({bar_c})",
                    value=bar_h,
                )
            )

        if bar_l > min(bar_o, bar_c):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    symbol=symbol,
                    bar_index=index,
                    timestamp=ts,
                    field="low",
                    message=f"Low ({bar_l}) is greater than open ({bar_o}) or close ({bar_c})",
                    value=bar_l,
                )
            )

        if bar_h < bar_l:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    symbol=symbol,
                    bar_index=index,
                    timestamp=ts,
                    field="high/low",
                    message=f"High ({bar_h}) is less than low ({bar_l})",
                    value=bar_h,
                )
            )

        # Check for zero/negative prices
        for field_name, value in [
            ("open", bar_o),
            ("high", bar_h),
            ("low", bar_l),
            ("close", bar_c),
        ]:
            if value <= 0:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        symbol=symbol,
                        bar_index=index,
                        timestamp=ts,
                        field=field_name,
                        message=f"{field_name.capitalize()} price is non-positive ({value})",
                        value=value,
                    )
                )

        # Check volume
        volume = bar.get("volume", 0)
        if volume < 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    symbol=symbol,
                    bar_index=index,
                    timestamp=ts,
                    field="volume",
                    message=f"Negative volume ({volume})",
                    value=volume,
                )
            )

        if volume < self.min_volume and self.min_volume > 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    symbol=symbol,
                    bar_index=index,
                    timestamp=ts,
                    field="volume",
                    message=f"Low volume ({volume}), minimum expected: {self.min_volume}",
                    value=volume,
                )
            )

        # Check against previous bar
        if prev_bar is not None:
            prev_ts = prev_bar.get("timestamp")
            prev_c = prev_bar["close"]

            # Check timestamp ordering
            if ts <= prev_ts:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        symbol=symbol,
                        bar_index=index,
                        timestamp=ts,
                        field="timestamp",
                        message=f"Timestamp not increasing (prev: {prev_ts})",
                    )
                )

            # Check for gaps
            gap = ts - prev_ts
            if gap > timedelta(days=self.max_gap_days):
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        symbol=symbol,
                        bar_index=index,
                        timestamp=ts,
                        field="timestamp",
                        message=f"Large gap in data ({gap.days} days)",
                    )
                )

            # Check for extreme price changes
            if prev_c > 0:
                pct_change = abs((bar_c - prev_c) / prev_c) * 100
                if pct_change > self.max_price_change_pct:
                    # Could be a split or data error
                    issues.append(
                        ValidationIssue(
                            severity=ValidationSeverity.WARNING,
                            symbol=symbol,
                            bar_index=index,
                            timestamp=ts,
                            field="close",
                            message=(
                                f"Extreme price change ({pct_change:.1f}%). "
                                "Possible split or data error"
                            ),
                            value=pct_change,
                        )
                    )

        return issues


def validate_bars(
    bars: dict[str, list[BarData | BarDataDict]],
    strict: bool = False,
) -> ValidationResult:
    """Validate bar data with default settings.

    Args:
        bars: Bar data by symbol
        strict: If True, treat warnings as errors

    Returns:
        ValidationResult
    """
    validator = DataValidator()
    result = validator.validate(bars)

    if strict and result.warnings:
        # Elevate warnings to errors
        for issue in result.warnings:
            issue.severity = ValidationSeverity.ERROR
        result.valid = False

    return result


def log_validation_result(result: ValidationResult) -> None:
    """Log validation result with appropriate log levels."""
    if result.valid:
        logger.info(result.summary())
    else:
        logger.warning(result.summary())

    for issue in result.errors:
        logger.error(str(issue))

    for issue in result.warnings:
        logger.warning(str(issue))
