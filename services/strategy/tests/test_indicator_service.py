"""Tests for IndicatorService to improve coverage."""

import pytest
from src.models import IndicatorType
from src.services.indicator_service import (
    CATEGORIES,
    INDICATORS,
    IndicatorService,
    _param,
    get_indicator_service,
)

# === Test Fixtures ===


@pytest.fixture
def indicator_service():
    """Create an IndicatorService instance."""
    return IndicatorService()


# === _param Helper Tests ===


class TestParamHelper:
    """Tests for _param helper function."""

    def test_param_basic(self):
        """Test creating a basic parameter."""
        param = _param("period", "int", 20)

        assert param["name"] == "period"
        assert param["type"] == "int"
        assert param["default"] == 20
        assert param["min"] is None
        assert param["max"] is None
        assert param["description"] == ""

    def test_param_with_range(self):
        """Test creating a parameter with min/max range."""
        param = _param("period", "int", 14, 1, 100, "Lookback period")

        assert param["name"] == "period"
        assert param["min"] == 1
        assert param["max"] == 100
        assert param["description"] == "Lookback period"

    def test_param_float_type(self):
        """Test creating a float parameter."""
        param = _param("std_dev", "float", 2.0, 0.5, 5.0, "Standard deviation")

        assert param["type"] == "float"
        assert param["default"] == 2.0
        assert param["min"] == 0.5
        assert param["max"] == 5.0


# === INDICATORS Dict Tests ===


class TestIndicatorsDict:
    """Tests for INDICATORS constant dict."""

    def test_contains_all_indicator_types(self):
        """Test that INDICATORS contains entries for all expected types."""
        expected_types = [
            IndicatorType.SMA,
            IndicatorType.EMA,
            IndicatorType.MACD,
            IndicatorType.RSI,
            IndicatorType.BOLLINGER_BANDS,
            IndicatorType.ATR,
        ]

        for indicator_type in expected_types:
            assert indicator_type in INDICATORS

    def test_sma_indicator_info(self):
        """Test SMA indicator metadata."""
        sma = INDICATORS[IndicatorType.SMA]

        assert sma.type == IndicatorType.SMA
        assert sma.name == "Simple Moving Average"
        assert sma.category == "trend"
        assert len(sma.params) == 1
        assert sma.params[0]["name"] == "period"
        assert sma.outputs == ["value"]

    def test_macd_indicator_has_multiple_params(self):
        """Test MACD indicator has multiple parameters."""
        macd = INDICATORS[IndicatorType.MACD]

        assert len(macd.params) == 3
        param_names = [p["name"] for p in macd.params]
        assert "fast_period" in param_names
        assert "slow_period" in param_names
        assert "signal_period" in param_names

    def test_macd_indicator_has_multiple_outputs(self):
        """Test MACD indicator has multiple outputs."""
        macd = INDICATORS[IndicatorType.MACD]

        assert macd.outputs == ["line", "signal", "histogram"]

    def test_bollinger_bands_params(self):
        """Test Bollinger Bands has correct params."""
        bb = INDICATORS[IndicatorType.BOLLINGER_BANDS]

        assert len(bb.params) == 2
        assert bb.params[0]["name"] == "period"
        assert bb.params[1]["name"] == "std_dev"
        assert bb.params[1]["type"] == "float"
        assert bb.outputs == ["upper", "middle", "lower"]

    def test_volume_indicators_exist(self):
        """Test volume category indicators."""
        obv = INDICATORS[IndicatorType.OBV]
        mfi = INDICATORS[IndicatorType.MFI]
        vwap = INDICATORS[IndicatorType.VWAP]

        assert obv.category == "volume"
        assert mfi.category == "volume"
        assert vwap.category == "volume"

    def test_obv_has_no_params(self):
        """Test OBV has no parameters."""
        obv = INDICATORS[IndicatorType.OBV]

        assert len(obv.params) == 0


# === CATEGORIES Constant Tests ===


class TestCategories:
    """Tests for CATEGORIES constant."""

    def test_categories_contains_expected(self):
        """Test CATEGORIES contains all expected categories."""
        assert "trend" in CATEGORIES
        assert "momentum" in CATEGORIES
        assert "volatility" in CATEGORIES
        assert "volume" in CATEGORIES
        assert "channel" in CATEGORIES

    def test_categories_count(self):
        """Test CATEGORIES has expected count."""
        assert len(CATEGORIES) == 5


# === IndicatorService.list_indicators Tests ===


class TestListIndicators:
    """Tests for list_indicators method."""

    async def test_list_all_indicators(self, indicator_service):
        """Test listing all indicators."""
        indicators = await indicator_service.list_indicators()

        assert len(indicators) == len(INDICATORS)

    async def test_list_indicators_filter_by_category(self, indicator_service):
        """Test filtering indicators by category."""
        trend_indicators = await indicator_service.list_indicators(category="trend")

        assert len(trend_indicators) > 0
        for indicator in trend_indicators:
            assert indicator.category == "trend"

    async def test_list_indicators_momentum_category(self, indicator_service):
        """Test filtering by momentum category."""
        momentum_indicators = await indicator_service.list_indicators(category="momentum")

        assert len(momentum_indicators) > 0
        assert all(i.category == "momentum" for i in momentum_indicators)

    async def test_list_indicators_volatility_category(self, indicator_service):
        """Test filtering by volatility category."""
        volatility_indicators = await indicator_service.list_indicators(category="volatility")

        assert len(volatility_indicators) > 0
        assert all(i.category == "volatility" for i in volatility_indicators)

    async def test_list_indicators_empty_category(self, indicator_service):
        """Test filtering by non-existent category returns empty."""
        indicators = await indicator_service.list_indicators(category="nonexistent")

        assert indicators == []


# === IndicatorService.get_indicator Tests ===


class TestGetIndicator:
    """Tests for get_indicator method."""

    async def test_get_indicator_found(self, indicator_service):
        """Test getting an existing indicator."""
        indicator = await indicator_service.get_indicator(IndicatorType.RSI)

        assert indicator is not None
        assert indicator.type == IndicatorType.RSI
        assert indicator.name == "Relative Strength Index"
        assert indicator.category == "momentum"

    async def test_get_indicator_not_found(self, indicator_service):
        """Test getting a non-existent indicator returns None."""
        # Use a mock type that doesn't exist in the dict
        # Since IndicatorType is an enum, we need to test with all valid types
        # All valid types should return something
        for indicator_type in IndicatorType:
            result = await indicator_service.get_indicator(indicator_type)
            if indicator_type in INDICATORS:
                assert result is not None
            else:
                assert result is None

    async def test_get_stochastic_indicator(self, indicator_service):
        """Test getting Stochastic indicator details."""
        indicator = await indicator_service.get_indicator(IndicatorType.STOCHASTIC)

        assert indicator is not None
        assert len(indicator.params) == 3
        assert indicator.outputs == ["k", "d"]


# === IndicatorService.list_categories Tests ===


class TestListCategories:
    """Tests for list_categories method."""

    async def test_list_categories(self, indicator_service):
        """Test listing categories."""
        categories = await indicator_service.list_categories()

        assert categories == CATEGORIES
        assert len(categories) == 5


# === get_indicator_service Dependency ===


class TestGetIndicatorServiceDependency:
    """Tests for get_indicator_service dependency."""

    def test_returns_service_instance(self):
        """Test that get_indicator_service returns an IndicatorService."""
        service = get_indicator_service()

        assert isinstance(service, IndicatorService)
