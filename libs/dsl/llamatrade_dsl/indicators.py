"""Technical indicator definitions and validation helpers.

This module defines the indicator registry used by the DSL validator and
provides helper functions for validating indicator parameters and outputs.
"""

from __future__ import annotations

from typing import TypedDict


class IndicatorSpec(TypedDict, total=False):
    """Specification for a technical indicator."""

    min_params: int  # Minimum required positional parameters
    max_params: int  # Maximum allowed positional parameters (defaults to min_params)
    outputs: list[str]  # Valid output selectors (e.g., ["value"] or ["upper", "middle", "lower"])


# Registry of all supported technical indicators
INDICATORS: dict[str, IndicatorSpec] = {
    # Moving averages
    "sma": {"min_params": 2, "max_params": 2, "outputs": ["value"]},
    "ema": {"min_params": 2, "max_params": 2, "outputs": ["value"]},
    # Momentum oscillators
    "rsi": {"min_params": 2, "max_params": 2, "outputs": ["value"]},
    "macd": {"min_params": 4, "max_params": 4, "outputs": ["line", "signal", "histogram"]},
    "stoch": {"min_params": 4, "max_params": 4, "outputs": ["k", "d"]},
    "cci": {"min_params": 2, "max_params": 2, "outputs": ["value"]},
    "williams-r": {"min_params": 2, "max_params": 2, "outputs": ["value"]},
    "momentum": {"min_params": 2, "max_params": 2, "outputs": ["value"]},
    "mfi": {"min_params": 2, "max_params": 2, "outputs": ["value"]},
    # Volatility indicators
    "bbands": {"min_params": 3, "max_params": 3, "outputs": ["upper", "middle", "lower"]},
    "atr": {"min_params": 2, "max_params": 2, "outputs": ["value"]},
    "keltner": {"min_params": 3, "max_params": 3, "outputs": ["upper", "middle", "lower"]},
    "donchian": {"min_params": 2, "max_params": 2, "outputs": ["upper", "lower"]},
    "stddev": {"min_params": 2, "max_params": 2, "outputs": ["value"]},
    # Trend indicators
    "adx": {"min_params": 2, "max_params": 2, "outputs": ["value", "plus_di", "minus_di"]},
    # Volume indicators
    "obv": {"min_params": 1, "max_params": 1, "outputs": ["value"]},
    "vwap": {"min_params": 1, "max_params": 1, "outputs": ["value"]},
}


def get_indicator_spec(name: str) -> IndicatorSpec | None:
    """Get the specification for an indicator by name.

    Args:
        name: The indicator name (e.g., "sma", "macd").

    Returns:
        The indicator spec if found, None otherwise.
    """
    return INDICATORS.get(name)


def is_valid_indicator(name: str) -> bool:
    """Check if a name is a valid indicator.

    Args:
        name: The indicator name to check.

    Returns:
        True if the name is a known indicator.
    """
    return name in INDICATORS


def get_indicator_outputs(name: str) -> list[str]:
    """Get the valid output selectors for an indicator.

    Args:
        name: The indicator name.

    Returns:
        List of valid output selector names, or empty list if indicator unknown.
    """
    spec = INDICATORS.get(name)
    if spec is None:
        return []
    return spec.get("outputs", ["value"])


def validate_indicator_params(name: str, param_count: int) -> tuple[bool, str | None]:
    """Validate the number of parameters for an indicator.

    Args:
        name: The indicator name.
        param_count: The number of positional parameters provided.

    Returns:
        Tuple of (is_valid, error_message). Error message is None if valid.
    """
    spec = INDICATORS.get(name)
    if spec is None:
        return False, f"Unknown indicator: {name}"

    min_params = spec.get("min_params", 0)
    max_params = spec.get("max_params", min_params)

    if param_count < min_params:
        return False, f"{name} requires at least {min_params} arguments, got {param_count}"
    if param_count > max_params:
        return False, f"{name} accepts at most {max_params} arguments, got {param_count}"

    return True, None


def validate_indicator_output(name: str, output: str) -> tuple[bool, str | None]:
    """Validate an output selector for an indicator.

    Args:
        name: The indicator name.
        output: The output selector (without the leading colon).

    Returns:
        Tuple of (is_valid, error_message). Error message is None if valid.
    """
    spec = INDICATORS.get(name)
    if spec is None:
        return False, f"Unknown indicator: {name}"

    valid_outputs = spec.get("outputs", ["value"])
    if output not in valid_outputs:
        return False, (
            f"Invalid output selector :{output} for {name}. "
            f"Valid outputs: {', '.join(valid_outputs)}"
        )

    return True, None


def get_all_indicator_names() -> list[str]:
    """Get a sorted list of all indicator names.

    Returns:
        Sorted list of indicator names.
    """
    return sorted(INDICATORS.keys())
