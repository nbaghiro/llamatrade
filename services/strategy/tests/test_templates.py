"""Tests for strategy templates router and service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from llamatrade_common.middleware import require_auth
from llamatrade_common.models import TenantContext
from src.main import app
from src.models import StrategyDetailResponse, StrategyStatus, StrategyType, TemplateResponse
from src.services.strategy_service import StrategyService, get_strategy_service
from src.services.template_service import (
    TEMPLATES,
    TemplateService,
    get_template_service,
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
def tenant_id():
    return uuid4()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def mock_template_service():
    """Create a mock template service."""
    return AsyncMock(spec=TemplateService)


@pytest.fixture
def mock_strategy_service():
    """Create a mock strategy service."""
    return AsyncMock(spec=StrategyService)


def make_auth_context(tenant_id, user_id, roles=None):
    """Create a mock TenantContext for auth override."""
    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        email="user@example.com",
        roles=roles or ["user"],
    )


def make_template_dict(template_id="ma_crossover"):
    """Create a mock template dict (as returned by service internally)."""
    return {
        "id": template_id,
        "name": "Moving Average Crossover",
        "description": "Classic trend-following strategy",
        "strategy_type": StrategyType.TREND_FOLLOWING,
        "config_sexpr": '(strategy :name "Test" :symbols ["AAPL"])',
        "tags": ["trend", "ema"],
        "difficulty": "beginner",
    }


def make_strategy_response(tenant_id, user_id, name="Test Strategy"):
    """Create a mock StrategyDetailResponse."""
    return StrategyDetailResponse(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        description="Created from template",
        strategy_type=StrategyType.TREND_FOLLOWING,
        status=StrategyStatus.DRAFT,
        config_sexpr='(strategy :name "Test" :symbols ["AAPL"])',
        config_json={},
        version=1,
        current_version=1,
        symbols=["AAPL"],
        timeframe="1D",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ===================
# Template Service Unit Tests
# ===================


class TestTemplateService:
    """Unit tests for TemplateService."""

    @pytest.fixture
    def template_service(self):
        """Create a real TemplateService."""
        return TemplateService()

    @pytest.mark.asyncio
    async def test_list_templates_all(self, template_service):
        """Test listing all templates."""
        templates = await template_service.list_templates()

        assert len(templates) == len(TEMPLATES)
        assert all(isinstance(t, TemplateResponse) for t in templates)

    @pytest.mark.asyncio
    async def test_list_templates_by_type(self, template_service):
        """Test filtering templates by strategy type."""
        templates = await template_service.list_templates(
            strategy_type=StrategyType.TREND_FOLLOWING
        )

        assert len(templates) > 0
        assert all(t.strategy_type == StrategyType.TREND_FOLLOWING for t in templates)

    @pytest.mark.asyncio
    async def test_list_templates_by_difficulty(self, template_service):
        """Test filtering templates by difficulty."""
        templates = await template_service.list_templates(difficulty="beginner")

        assert len(templates) > 0
        assert all(t.difficulty == "beginner" for t in templates)

    @pytest.mark.asyncio
    async def test_list_templates_by_type_and_difficulty(self, template_service):
        """Test filtering by both type and difficulty."""
        templates = await template_service.list_templates(
            strategy_type=StrategyType.MOMENTUM,
            difficulty="beginner",
        )

        assert len(templates) > 0
        for t in templates:
            assert t.strategy_type == StrategyType.MOMENTUM
            assert t.difficulty == "beginner"

    @pytest.mark.asyncio
    async def test_get_template_found(self, template_service):
        """Test getting an existing template."""
        template = await template_service.get_template("ma_crossover")

        assert template is not None
        assert template.id == "ma_crossover"
        assert template.name == "Moving Average Crossover"
        assert template.strategy_type == StrategyType.TREND_FOLLOWING

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, template_service):
        """Test getting a non-existent template."""
        template = await template_service.get_template("nonexistent")

        assert template is None

    @pytest.mark.asyncio
    async def test_get_template_config_found(self, template_service):
        """Test getting template config."""
        config = await template_service.get_template_config("ma_crossover")

        assert config is not None
        assert "(strategy" in config
        assert ":name" in config

    @pytest.mark.asyncio
    async def test_get_template_config_not_found(self, template_service):
        """Test getting config for non-existent template."""
        config = await template_service.get_template_config("nonexistent")

        assert config is None

    @pytest.mark.asyncio
    async def test_all_templates_have_required_fields(self, template_service):
        """Test all templates have required fields."""
        templates = await template_service.list_templates()

        for t in templates:
            assert t.id is not None
            assert t.name is not None
            assert t.strategy_type is not None
            assert t.config_sexpr is not None
            assert t.difficulty is not None


# ===================
# Templates Router Tests
# ===================


class TestListTemplatesRouter:
    """Tests for GET /templates endpoint."""

    @pytest.mark.asyncio
    async def test_list_templates_success(self, mock_template_service):
        """Test listing templates successfully."""
        # Router expects dicts from the service
        mock_template_service.list_templates.return_value = [
            make_template_dict("ma_crossover"),
            make_template_dict("rsi_mean_reversion"),
        ]

        app.dependency_overrides[get_template_service] = lambda: mock_template_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/templates")
                assert response.status_code == 200
                data = response.json()
                assert len(data) == 2
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_templates_with_type_filter(self, mock_template_service):
        """Test listing templates with type filter."""
        mock_template_service.list_templates.return_value = [
            make_template_dict("ma_crossover"),
        ]

        app.dependency_overrides[get_template_service] = lambda: mock_template_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/templates?strategy_type=trend_following")
                assert response.status_code == 200
                mock_template_service.list_templates.assert_called_once_with(
                    strategy_type=StrategyType.TREND_FOLLOWING,
                    difficulty=None,
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_templates_with_difficulty_filter(self, mock_template_service):
        """Test listing templates with difficulty filter."""
        mock_template_service.list_templates.return_value = []

        app.dependency_overrides[get_template_service] = lambda: mock_template_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/templates?difficulty=intermediate")
                assert response.status_code == 200
                mock_template_service.list_templates.assert_called_once_with(
                    strategy_type=None,
                    difficulty="intermediate",
                )
        finally:
            app.dependency_overrides.clear()


class TestGetTemplateRouter:
    """Tests for GET /templates/{template_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_template_success(self, mock_template_service):
        """Test getting a template successfully."""
        mock_template_service.get_template.return_value = make_template_dict()

        app.dependency_overrides[get_template_service] = lambda: mock_template_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/templates/ma_crossover")
                assert response.status_code == 200
                data = response.json()
                assert data["id"] == "ma_crossover"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, mock_template_service):
        """Test getting a non-existent template."""
        mock_template_service.get_template.return_value = None

        app.dependency_overrides[get_template_service] = lambda: mock_template_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/templates/nonexistent")
                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()


class TestCreateFromTemplateRouter:
    """Tests for POST /templates/{template_id}/create endpoint."""

    @pytest.mark.asyncio
    async def test_create_from_template_success(
        self, tenant_id, user_id, mock_template_service, mock_strategy_service
    ):
        """Test creating strategy from template successfully."""
        ctx = make_auth_context(tenant_id, user_id)
        # Use the actual TEMPLATES dict which has the right structure
        mock_template_service.get_template.return_value = TEMPLATES["ma_crossover"]
        mock_strategy_service.create_strategy.return_value = make_strategy_response(
            tenant_id, user_id, name="My Strategy"
        )

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_template_service] = lambda: mock_template_service
        app.dependency_overrides[get_strategy_service] = lambda: mock_strategy_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/templates/ma_crossover/create?name=My%20Strategy")
                assert response.status_code == 201
                data = response.json()
                assert data["name"] == "My Strategy"
                mock_strategy_service.create_strategy.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_from_template_with_symbols(
        self, tenant_id, user_id, mock_template_service, mock_strategy_service
    ):
        """Test creating strategy from template with custom symbols."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_template_service.get_template.return_value = TEMPLATES["ma_crossover"]
        mock_strategy_service.create_strategy.return_value = make_strategy_response(
            tenant_id, user_id
        )

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_template_service] = lambda: mock_template_service
        app.dependency_overrides[get_strategy_service] = lambda: mock_strategy_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/templates/ma_crossover/create?name=My%20Strategy&symbols=TSLA&symbols=GOOGL"
                )
                assert response.status_code == 201
                # Verify the symbols were replaced in the config
                call_args = mock_strategy_service.create_strategy.call_args
                strategy_data = call_args.kwargs["data"]
                assert "TSLA" in strategy_data.config_sexpr
                assert "GOOGL" in strategy_data.config_sexpr
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_from_template_not_found(self, tenant_id, user_id, mock_template_service):
        """Test creating from non-existent template."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_template_service.get_template.return_value = None

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_template_service] = lambda: mock_template_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/templates/nonexistent/create?name=Test")
                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_from_template_validation_error(
        self, tenant_id, user_id, mock_template_service, mock_strategy_service
    ):
        """Test creating from template with validation error."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_template_service.get_template.return_value = TEMPLATES["ma_crossover"]
        mock_strategy_service.create_strategy.side_effect = ValueError("Invalid strategy")

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_template_service] = lambda: mock_template_service
        app.dependency_overrides[get_strategy_service] = lambda: mock_strategy_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/templates/ma_crossover/create?name=Test")
                assert response.status_code == 400
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_from_template_unauthorized(self, client):
        """Test creating from template without authentication."""
        response = await client.post("/templates/ma_crossover/create?name=Test")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_from_template_missing_name(self, tenant_id, user_id):
        """Test creating from template without name."""
        ctx = make_auth_context(tenant_id, user_id)
        app.dependency_overrides[require_auth] = lambda: ctx

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/templates/ma_crossover/create")
                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()


# ===================
# Template Data Tests
# ===================


class TestTemplateData:
    """Tests for the built-in template data."""

    def test_all_templates_exist(self):
        """Test that all expected templates exist."""
        expected_templates = [
            "ma_crossover",
            "rsi_mean_reversion",
            "macd_strategy",
            "bollinger_bounce",
            "donchian_breakout",
            "dual_momentum",
            "zscore_mean_reversion",
            "vwap_strategy",
            "pairs_trading",
            "adx_trend_filter",
        ]

        for template_id in expected_templates:
            assert template_id in TEMPLATES, f"Template {template_id} not found"

    def test_all_templates_have_valid_strategy_type(self):
        """Test all templates have valid strategy type."""
        for template_id, template in TEMPLATES.items():
            assert "strategy_type" in template, f"Template {template_id} missing strategy_type"
            assert isinstance(template["strategy_type"], StrategyType), (
                f"Template {template_id} has invalid strategy_type"
            )

    def test_all_templates_have_valid_sexpr(self):
        """Test all templates have valid S-expression config."""
        for template_id, template in TEMPLATES.items():
            config = template["config_sexpr"]
            assert config.startswith("(strategy"), f"Template {template_id} invalid config"
            assert ":name" in config, f"Template {template_id} missing :name"
            assert ":symbols" in config, f"Template {template_id} missing :symbols"
            assert ":entry" in config, f"Template {template_id} missing :entry"
            assert ":exit" in config, f"Template {template_id} missing :exit"

    def test_template_difficulty_values(self):
        """Test all templates have valid difficulty values."""
        valid_difficulties = {"beginner", "intermediate", "advanced"}

        for template_id, template in TEMPLATES.items():
            difficulty = template.get("difficulty", "beginner")
            assert difficulty in valid_difficulties, (
                f"Template {template_id} has invalid difficulty: {difficulty}"
            )

    def test_template_tags_are_lists(self):
        """Test all templates have tags as lists."""
        for template_id, template in TEMPLATES.items():
            tags = template.get("tags", [])
            assert isinstance(tags, list), f"Template {template_id} tags should be a list"
