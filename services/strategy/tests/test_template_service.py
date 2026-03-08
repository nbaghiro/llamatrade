"""Tests for TemplateService to improve coverage."""

import pytest

from src.models import StrategyType
from src.services.template_service import (
    TEMPLATES,
    TemplateService,
    get_template_service,
)

# === Test Fixtures ===


@pytest.fixture
def template_service() -> TemplateService:
    """Create a TemplateService instance."""
    return TemplateService()


# === TEMPLATES Dict Tests ===


class TestTemplatesDict:
    """Tests for TEMPLATES constant dict."""

    def test_contains_ma_crossover(self) -> None:
        """Test TEMPLATES contains MA crossover template."""
        assert "ma-crossover" in TEMPLATES
        ma = TEMPLATES["ma-crossover"]
        assert ma["name"] == "Moving Average Crossover"
        assert ma["strategy_type"] == StrategyType.TREND_FOLLOWING
        assert ma["difficulty"] == "beginner"

    def test_contains_rsi_mean_reversion(self) -> None:
        """Test TEMPLATES contains RSI mean reversion template."""
        assert "rsi-mean-reversion" in TEMPLATES
        rsi = TEMPLATES["rsi-mean-reversion"]
        assert rsi["strategy_type"] == StrategyType.MEAN_REVERSION
        assert "rsi" in rsi["tags"]

    def test_contains_macd_strategy(self) -> None:
        """Test TEMPLATES contains MACD strategy template."""
        assert "macd-strategy" in TEMPLATES
        macd = TEMPLATES["macd-strategy"]
        assert macd["strategy_type"] == StrategyType.MOMENTUM

    def test_contains_bollinger_bounce(self) -> None:
        """Test TEMPLATES contains Bollinger bounce template."""
        assert "bollinger-bounce" in TEMPLATES
        bb = TEMPLATES["bollinger-bounce"]
        assert bb["difficulty"] == "intermediate"

    def test_contains_donchian_breakout(self) -> None:
        """Test TEMPLATES contains Donchian breakout template."""
        assert "donchian-breakout" in TEMPLATES
        dc = TEMPLATES["donchian-breakout"]
        assert dc["strategy_type"] == StrategyType.BREAKOUT
        assert dc["difficulty"] == "advanced"

    def test_all_templates_have_required_fields(self) -> None:
        """Test all templates have required fields."""
        required_fields = [
            "id",
            "name",
            "description",
            "strategy_type",
            "tags",
            "difficulty",
            "config_sexpr",
        ]

        for _, template in TEMPLATES.items():
            for field in required_fields:
                assert field in template

    def test_all_templates_have_valid_sexpr(self) -> None:
        """Test all templates have non-empty S-expression configs."""
        for _, template in TEMPLATES.items():
            config = template["config_sexpr"]
            assert config.strip().startswith("(strategy")

    def test_difficulty_levels_valid(self) -> None:
        """Test all templates have valid difficulty levels."""
        valid_difficulties = ["beginner", "intermediate", "advanced"]

        for _, template in TEMPLATES.items():
            assert template["difficulty"] in valid_difficulties


# === TemplateService.list_templates Tests ===


class TestListTemplates:
    """Tests for list_templates method."""

    async def test_list_all_templates(self, template_service: TemplateService) -> None:
        """Test listing all templates."""
        templates = await template_service.list_templates()

        assert len(templates) == len(TEMPLATES)

    async def test_list_templates_by_strategy_type(self, template_service: TemplateService) -> None:
        """Test filtering templates by strategy type."""
        mean_reversion = await template_service.list_templates(
            strategy_type=StrategyType.MEAN_REVERSION
        )

        assert len(mean_reversion) > 0
        for template in mean_reversion:
            assert template.strategy_type == StrategyType.MEAN_REVERSION

    async def test_list_templates_by_difficulty_beginner(
        self, template_service: TemplateService
    ) -> None:
        """Test filtering templates by beginner difficulty."""
        beginner = await template_service.list_templates(difficulty="beginner")

        assert len(beginner) > 0
        for template in beginner:
            assert template.difficulty == "beginner"

    async def test_list_templates_by_difficulty_advanced(
        self, template_service: TemplateService
    ) -> None:
        """Test filtering templates by advanced difficulty."""
        advanced = await template_service.list_templates(difficulty="advanced")

        assert len(advanced) > 0
        for template in advanced:
            assert template.difficulty == "advanced"

    async def test_list_templates_combined_filters(self, template_service: TemplateService) -> None:
        """Test filtering by both type and difficulty."""
        result = await template_service.list_templates(
            strategy_type=StrategyType.MEAN_REVERSION,
            difficulty="intermediate",
        )

        for template in result:
            assert template.strategy_type == StrategyType.MEAN_REVERSION
            assert template.difficulty == "intermediate"

    async def test_list_templates_no_matches(self, template_service: TemplateService) -> None:
        """Test filtering with no matching templates."""
        result = await template_service.list_templates(difficulty="expert")

        assert result == []

    async def test_list_templates_response_fields(self, template_service: TemplateService) -> None:
        """Test that template responses have all fields."""
        templates = await template_service.list_templates()

        for template in templates:
            assert template.id is not None
            assert template.name is not None
            assert template.description is not None
            assert template.strategy_type is not None
            assert template.config_sexpr is not None
            assert template.tags is not None
            assert template.difficulty is not None


# === TemplateService.get_template Tests ===


class TestGetTemplate:
    """Tests for get_template method."""

    async def test_get_template_found(self, template_service: TemplateService) -> None:
        """Test getting an existing template."""
        template = await template_service.get_template("ma-crossover")

        assert template is not None
        assert template.id == "ma-crossover"
        assert template.name == "Moving Average Crossover"
        assert template.strategy_type == StrategyType.TREND_FOLLOWING

    async def test_get_template_not_found(self, template_service: TemplateService) -> None:
        """Test getting a non-existent template."""
        template = await template_service.get_template("nonexistent")

        assert template is None

    async def test_get_template_rsi(self, template_service: TemplateService) -> None:
        """Test getting RSI template."""
        template = await template_service.get_template("rsi-mean-reversion")

        assert template is not None
        assert "RSI" in template.name
        assert "rsi" in template.tags

    async def test_get_template_pairs_trading(self, template_service: TemplateService) -> None:
        """Test getting pairs trading template."""
        template = await template_service.get_template("pairs-trading")

        assert template is not None
        assert "KO" in template.config_sexpr
        assert "PEP" in template.config_sexpr

    async def test_get_template_has_config_json(self, template_service: TemplateService) -> None:
        """Test that returned template has config_json field (empty dict)."""
        template = await template_service.get_template("ma-crossover")

        assert template is not None
        assert template.config_json == {}


# === TemplateService.get_template_config Tests ===


class TestGetTemplateConfig:
    """Tests for get_template_config method."""

    async def test_get_template_config_found(self, template_service: TemplateService) -> None:
        """Test getting config for existing template."""
        config = await template_service.get_template_config("ma-crossover")

        assert config is not None
        assert "(strategy" in config
        assert "ema" in config.lower()

    async def test_get_template_config_not_found(self, template_service: TemplateService) -> None:
        """Test getting config for non-existent template."""
        config = await template_service.get_template_config("nonexistent")

        assert config is None

    async def test_get_template_config_bollinger(self, template_service: TemplateService) -> None:
        """Test getting Bollinger bounce config."""
        config = await template_service.get_template_config("bollinger-bounce")

        assert config is not None
        assert "bbands" in config
        assert ":output lower" in config
        assert ":output upper" in config

    async def test_get_template_config_dual_momentum(
        self, template_service: TemplateService
    ) -> None:
        """Test getting dual momentum config."""
        config = await template_service.get_template_config("dual-momentum")

        assert config is not None
        assert "SPY" in config
        assert "EFA" in config


# === get_template_service Dependency ===


class TestGetTemplateServiceDependency:
    """Tests for get_template_service dependency."""

    def test_returns_service_instance(self) -> None:
        """Test that get_template_service returns a TemplateService."""
        service = get_template_service()

        assert isinstance(service, TemplateService)
