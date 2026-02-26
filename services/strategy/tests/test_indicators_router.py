"""Tests for indicators router and indicator service."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.models import IndicatorInfoResponse, IndicatorParamInfo, IndicatorType
from src.services.indicator_service import (
    CATEGORIES,
    INDICATORS,
    IndicatorService,
    get_indicator_service,
)

# ===================
# Fixtures
# ===================


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_indicator_service():
    """Create a mock indicator service."""
    return AsyncMock(spec=IndicatorService)


def make_indicator_info(indicator_type=IndicatorType.RSI):
    """Create a mock IndicatorInfoResponse."""
    return IndicatorInfoResponse(
        type=indicator_type,
        name="Test Indicator",
        description="Test description",
        category="momentum",
        params=[
            IndicatorParamInfo(
                name="period",
                type="int",
                default=14,
                min=1,
                max=100,
                description="Lookback period",
            )
        ],
        outputs=["value"],
    )


# ===================
# Indicator Service Unit Tests
# ===================


class TestIndicatorService:
    """Unit tests for IndicatorService."""

    @pytest.fixture
    def indicator_service(self):
        """Create a real IndicatorService."""
        return IndicatorService()

    @pytest.mark.asyncio
    async def test_list_indicators_all(self, indicator_service):
        """Test listing all indicators."""
        indicators = await indicator_service.list_indicators()

        assert len(indicators) == len(INDICATORS)
        assert all(isinstance(i, IndicatorInfoResponse) for i in indicators)

    @pytest.mark.asyncio
    async def test_list_indicators_by_category(self, indicator_service):
        """Test filtering indicators by category."""
        indicators = await indicator_service.list_indicators(category="momentum")

        assert len(indicators) > 0
        assert all(i.category == "momentum" for i in indicators)

    @pytest.mark.asyncio
    async def test_list_indicators_by_invalid_category(self, indicator_service):
        """Test filtering by non-existent category returns empty list."""
        indicators = await indicator_service.list_indicators(category="nonexistent")

        assert indicators == []

    @pytest.mark.asyncio
    async def test_get_indicator_found(self, indicator_service):
        """Test getting an existing indicator."""
        indicator = await indicator_service.get_indicator(IndicatorType.RSI)

        assert indicator is not None
        assert indicator.type == IndicatorType.RSI
        assert indicator.name == "Relative Strength Index"
        assert indicator.category == "momentum"

    @pytest.mark.asyncio
    async def test_get_indicator_all_types(self, indicator_service):
        """Test that all indicator types are available."""
        for indicator_type in IndicatorType:
            indicator = await indicator_service.get_indicator(indicator_type)
            assert indicator is not None, f"Indicator {indicator_type} not found"
            assert indicator.type == indicator_type

    @pytest.mark.asyncio
    async def test_list_categories(self, indicator_service):
        """Test listing categories."""
        categories = await indicator_service.list_categories()

        assert categories == CATEGORIES
        assert "trend" in categories
        assert "momentum" in categories
        assert "volatility" in categories
        assert "volume" in categories

    @pytest.mark.asyncio
    async def test_all_indicators_have_required_fields(self, indicator_service):
        """Test all indicators have required fields."""
        indicators = await indicator_service.list_indicators()

        for i in indicators:
            assert i.type is not None
            assert i.name is not None
            assert i.description is not None
            assert i.category is not None
            assert i.outputs is not None
            assert len(i.outputs) > 0


# ===================
# Indicators Router Tests
# ===================


class TestListIndicatorsRouter:
    """Tests for GET /indicators endpoint."""

    @pytest.mark.asyncio
    async def test_list_indicators_success(self, mock_indicator_service):
        """Test listing indicators successfully."""
        mock_indicator_service.list_indicators.return_value = [
            make_indicator_info(IndicatorType.RSI),
            make_indicator_info(IndicatorType.SMA),
        ]

        app.dependency_overrides[get_indicator_service] = lambda: mock_indicator_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/indicators")
                assert response.status_code == 200
                data = response.json()
                assert len(data) == 2
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_indicators_with_category_filter(self, mock_indicator_service):
        """Test listing indicators with category filter."""
        mock_indicator_service.list_indicators.return_value = [
            make_indicator_info(IndicatorType.RSI),
        ]

        app.dependency_overrides[get_indicator_service] = lambda: mock_indicator_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/indicators?category=momentum")
                assert response.status_code == 200
                mock_indicator_service.list_indicators.assert_called_once_with(category="momentum")
        finally:
            app.dependency_overrides.clear()


class TestGetIndicatorRouter:
    """Tests for GET /indicators/{indicator_type} endpoint."""

    @pytest.mark.asyncio
    async def test_get_indicator_success(self, mock_indicator_service):
        """Test getting an indicator successfully."""
        mock_indicator_service.get_indicator.return_value = make_indicator_info(IndicatorType.RSI)

        app.dependency_overrides[get_indicator_service] = lambda: mock_indicator_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/indicators/rsi")
                assert response.status_code == 200
                data = response.json()
                assert data["type"] == "rsi"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_indicator_not_found(self, mock_indicator_service):
        """Test getting a non-existent indicator."""
        mock_indicator_service.get_indicator.return_value = None

        app.dependency_overrides[get_indicator_service] = lambda: mock_indicator_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Use a valid enum value that returns None
                response = await client.get("/indicators/rsi")
                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestListCategoriesRouter:
    """Tests for GET /indicators/categories endpoint."""

    @pytest.mark.asyncio
    async def test_list_categories_success(self, mock_indicator_service):
        """Test listing categories successfully."""
        mock_indicator_service.list_categories.return_value = [
            "trend",
            "momentum",
            "volatility",
        ]

        app.dependency_overrides[get_indicator_service] = lambda: mock_indicator_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/indicators/categories")
                assert response.status_code == 200
                data = response.json()
                assert "trend" in data
                assert "momentum" in data
        finally:
            app.dependency_overrides.clear()


# ===================
# Indicator Data Tests
# ===================


class TestIndicatorData:
    """Tests for the built-in indicator metadata."""

    def test_all_indicator_types_defined(self):
        """Test all IndicatorType enum values have metadata."""
        for indicator_type in IndicatorType:
            assert indicator_type in INDICATORS, f"Missing metadata for {indicator_type}"

    def test_indicator_params_have_valid_types(self):
        """Test indicator params have valid types."""
        valid_types = {"int", "float", "str", "bool"}

        for indicator_type, info in INDICATORS.items():
            for param in info.params:
                assert param["type"] in valid_types, (
                    f"Invalid param type for {indicator_type}.{param['name']}: {param['type']}"
                )

    def test_indicator_outputs_non_empty(self):
        """Test all indicators have at least one output."""
        for indicator_type, info in INDICATORS.items():
            assert len(info.outputs) > 0, f"Indicator {indicator_type} has no outputs"

    def test_indicator_categories_valid(self):
        """Test all indicators have valid categories."""
        for indicator_type, info in INDICATORS.items():
            assert info.category in CATEGORIES, (
                f"Invalid category for {indicator_type}: {info.category}"
            )
