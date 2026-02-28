"""Tests for indicators module."""

from llamatrade_dsl.indicators import (
    INDICATORS,
    get_all_indicator_names,
    get_indicator_outputs,
    get_indicator_spec,
    is_valid_indicator,
    validate_indicator_output,
    validate_indicator_params,
)


class TestIndicatorRegistry:
    """Tests for the INDICATORS registry."""

    def test_registry_has_expected_indicators(self):
        """Verify all expected indicators are present."""
        expected = {
            "sma",
            "ema",
            "rsi",
            "macd",
            "bbands",
            "atr",
            "adx",
            "stoch",
            "cci",
            "williams-r",
            "obv",
            "mfi",
            "vwap",
            "keltner",
            "donchian",
            "stddev",
            "momentum",
        }
        assert set(INDICATORS.keys()) == expected

    def test_all_indicators_have_required_fields(self):
        """All indicators should have min_params and outputs."""
        for name, spec in INDICATORS.items():
            assert "min_params" in spec, f"{name} missing min_params"
            assert "outputs" in spec, f"{name} missing outputs"
            assert isinstance(spec["outputs"], list), f"{name} outputs should be a list"
            assert len(spec["outputs"]) > 0, f"{name} should have at least one output"


class TestGetIndicatorSpec:
    """Tests for get_indicator_spec function."""

    def test_returns_spec_for_valid_indicator(self):
        """Returns the spec dict for a known indicator."""
        spec = get_indicator_spec("sma")
        assert spec is not None
        assert spec["min_params"] == 2
        assert spec["outputs"] == ["value"]

    def test_returns_none_for_unknown_indicator(self):
        """Returns None for unknown indicators."""
        assert get_indicator_spec("unknown_indicator") is None
        assert get_indicator_spec("") is None

    def test_macd_has_multiple_outputs(self):
        """MACD should have line, signal, histogram outputs."""
        spec = get_indicator_spec("macd")
        assert spec is not None
        assert spec["outputs"] == ["line", "signal", "histogram"]


class TestIsValidIndicator:
    """Tests for is_valid_indicator function."""

    def test_returns_true_for_valid_indicators(self):
        """All registered indicators should return True."""
        for name in INDICATORS:
            assert is_valid_indicator(name) is True

    def test_returns_false_for_invalid_indicators(self):
        """Unknown indicators should return False."""
        assert is_valid_indicator("invalid") is False
        assert is_valid_indicator("SMA") is False  # Case-sensitive
        assert is_valid_indicator("") is False


class TestGetIndicatorOutputs:
    """Tests for get_indicator_outputs function."""

    def test_single_output_indicator(self):
        """SMA has a single 'value' output."""
        outputs = get_indicator_outputs("sma")
        assert outputs == ["value"]

    def test_multi_output_indicator(self):
        """BBands has upper/middle/lower outputs."""
        outputs = get_indicator_outputs("bbands")
        assert outputs == ["upper", "middle", "lower"]

    def test_unknown_indicator_returns_empty_list(self):
        """Unknown indicators return empty list."""
        outputs = get_indicator_outputs("unknown")
        assert outputs == []


class TestValidateIndicatorParams:
    """Tests for validate_indicator_params function."""

    def test_valid_param_count(self):
        """Valid param count returns True with no error."""
        valid, error = validate_indicator_params("sma", 2)
        assert valid is True
        assert error is None

    def test_too_few_params(self):
        """Too few params returns False with error message."""
        valid, error = validate_indicator_params("sma", 1)
        assert valid is False
        assert "requires at least 2 arguments" in error

    def test_too_many_params(self):
        """Too many params returns False with error message."""
        valid, error = validate_indicator_params("sma", 3)
        assert valid is False
        assert "accepts at most 2 arguments" in error

    def test_unknown_indicator(self):
        """Unknown indicator returns False with error."""
        valid, error = validate_indicator_params("unknown", 2)
        assert valid is False
        assert "Unknown indicator" in error

    def test_variable_param_count_indicators(self):
        """Test indicators with different param requirements."""
        # OBV only needs 1 param
        assert validate_indicator_params("obv", 1) == (True, None)
        assert validate_indicator_params("obv", 0)[0] is False

        # MACD needs exactly 4 params
        assert validate_indicator_params("macd", 4) == (True, None)
        assert validate_indicator_params("macd", 3)[0] is False
        assert validate_indicator_params("macd", 5)[0] is False


class TestValidateIndicatorOutput:
    """Tests for validate_indicator_output function."""

    def test_valid_output_selector(self):
        """Valid output selector returns True with no error."""
        valid, error = validate_indicator_output("sma", "value")
        assert valid is True
        assert error is None

    def test_invalid_output_selector(self):
        """Invalid output selector returns False with error."""
        valid, error = validate_indicator_output("sma", "upper")
        assert valid is False
        assert "Invalid output selector :upper for sma" in error
        assert "value" in error  # Lists valid outputs

    def test_multi_output_indicators(self):
        """Test indicators with multiple valid outputs."""
        # MACD outputs
        assert validate_indicator_output("macd", "line") == (True, None)
        assert validate_indicator_output("macd", "signal") == (True, None)
        assert validate_indicator_output("macd", "histogram") == (True, None)
        assert validate_indicator_output("macd", "value")[0] is False

        # Stochastic outputs
        assert validate_indicator_output("stoch", "k") == (True, None)
        assert validate_indicator_output("stoch", "d") == (True, None)

    def test_unknown_indicator(self):
        """Unknown indicator returns False with error."""
        valid, error = validate_indicator_output("unknown", "value")
        assert valid is False
        assert "Unknown indicator" in error


class TestGetAllIndicatorNames:
    """Tests for get_all_indicator_names function."""

    def test_returns_sorted_list(self):
        """Returns a sorted list of all indicator names."""
        names = get_all_indicator_names()
        assert isinstance(names, list)
        assert names == sorted(names)
        assert len(names) == len(INDICATORS)

    def test_contains_all_indicators(self):
        """Contains all registered indicators."""
        names = get_all_indicator_names()
        for indicator in INDICATORS:
            assert indicator in names
