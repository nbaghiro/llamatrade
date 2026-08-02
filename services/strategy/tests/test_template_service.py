"""Tests for TemplateService to improve coverage."""

import pytest

from llamatrade_proto.generated.strategy_pb2 import (
    TEMPLATE_CATEGORY_BUY_AND_HOLD,
    TEMPLATE_CATEGORY_MEAN_REVERSION,
    TEMPLATE_CATEGORY_TREND,
    TEMPLATE_DIFFICULTY_ADVANCED,
    TEMPLATE_DIFFICULTY_BEGINNER,
    TEMPLATE_DIFFICULTY_INTERMEDIATE,
    TemplateCategory,
)

from src.services.template_service import (
    TEMPLATES,
    TemplateService,
    _parse_template,
    get_template_service,
)

# === Test Fixtures ===


@pytest.fixture
def template_service() -> TemplateService:
    """Create a TemplateService instance."""
    return TemplateService()


def _valid_entry() -> dict[str, object]:
    return {
        "id": "sample",
        "name": "Sample",
        "description": "desc",
        "category": "TEMPLATE_CATEGORY_TREND",
        "asset_class": "ASSET_CLASS_EQUITY",
        "tags": ["a", "b"],
        "difficulty": "TEMPLATE_DIFFICULTY_BEGINNER",
        "config_sexpr": "(strategy)",
    }


class TestTemplateLoader:
    """The catalog is validated at import; the parser must reject malformed rows."""

    def test_parses_valid_entry_with_enum_names(self) -> None:
        parsed = _parse_template(_valid_entry())
        assert parsed["id"] == "sample"
        assert parsed["category"] == TEMPLATE_CATEGORY_TREND
        assert parsed["category"] == TemplateCategory.Value("TEMPLATE_CATEGORY_TREND")

    def test_rejects_non_object(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON object"):
            _parse_template(["not", "an", "object"])

    def test_rejects_missing_string_field(self) -> None:
        entry = _valid_entry()
        del entry["name"]
        with pytest.raises(ValueError, match="'name' must be a string"):
            _parse_template(entry)

    def test_rejects_unknown_enum_name(self) -> None:
        entry = _valid_entry()
        entry["category"] = "TEMPLATE_CATEGORY_DOES_NOT_EXIST"
        with pytest.raises(ValueError, match="unknown category"):
            _parse_template(entry)

    def test_rejects_non_string_enum(self) -> None:
        entry = _valid_entry()
        entry["difficulty"] = 3
        with pytest.raises(ValueError, match="'difficulty' must be an enum name string"):
            _parse_template(entry)

    def test_rejects_bad_tags(self) -> None:
        entry = _valid_entry()
        entry["tags"] = ["ok", 5]
        with pytest.raises(ValueError, match="'tags' must be a list of strings"):
            _parse_template(entry)


# === TEMPLATES Dict Tests ===


class TestTemplatesDict:
    """Tests for TEMPLATES constant dict."""

    def test_contains_ma_crossover(self) -> None:
        """Test TEMPLATES contains MA crossover template."""
        assert "ma-crossover" in TEMPLATES
        ma = TEMPLATES["ma-crossover"]
        assert ma["name"] == "Moving Average Crossover"
        assert ma["category"] == TEMPLATE_CATEGORY_TREND
        assert ma["difficulty"] == TEMPLATE_DIFFICULTY_BEGINNER

    def test_contains_rsi_mean_reversion(self) -> None:
        """Test TEMPLATES contains RSI mean reversion template."""
        assert "rsi-mean-reversion" in TEMPLATES
        rsi = TEMPLATES["rsi-mean-reversion"]
        assert rsi["category"] == TEMPLATE_CATEGORY_MEAN_REVERSION
        assert "rsi" in rsi["tags"]

    def test_contains_macd_strategy(self) -> None:
        """Test TEMPLATES contains MACD strategy template."""
        assert "macd-strategy" in TEMPLATES
        macd = TEMPLATES["macd-strategy"]
        assert macd["category"] == TEMPLATE_CATEGORY_MEAN_REVERSION

    def test_contains_bollinger_bounce(self) -> None:
        """Test TEMPLATES contains Bollinger bounce template."""
        assert "bollinger-bounce" in TEMPLATES
        bb = TEMPLATES["bollinger-bounce"]
        assert bb["difficulty"] == TEMPLATE_DIFFICULTY_INTERMEDIATE

    def test_contains_donchian_breakout(self) -> None:
        """Test TEMPLATES contains Donchian breakout template."""
        assert "donchian-breakout" in TEMPLATES
        dc = TEMPLATES["donchian-breakout"]
        assert dc["category"] == TEMPLATE_CATEGORY_TREND
        assert dc["difficulty"] == TEMPLATE_DIFFICULTY_ADVANCED

    def test_all_templates_have_required_fields(self) -> None:
        """Test all templates have required fields."""
        required_fields = [
            "id",
            "name",
            "description",
            "category",
            "asset_class",
            "tags",
            "difficulty",
            "config_sexpr",
        ]

        for _, template in TEMPLATES.items():
            for field in required_fields:
                assert field in template

    def test_all_templates_have_valid_sexpr(self) -> None:
        """Every template survives the full round trip: parse, validate, serialize,
        reparse, revalidate, with the reparsed AST identical to the original."""
        from llamatrade_dsl import parse, serialize, to_json, validate

        for key, template in TEMPLATES.items():
            source = template["config_sexpr"]
            ast = parse(source)
            result = validate(ast)
            assert result.valid, f"{key}: invalid template: {result.errors[:2]}"

            reparsed = parse(serialize(ast))
            assert to_json(reparsed) == to_json(ast), f"{key}: round trip lost AST content"
            assert validate(reparsed).valid, f"{key}: round-tripped template failed validation"

    def test_difficulty_levels_valid(self) -> None:
        """Test all templates have valid difficulty levels (proto enum values)."""
        valid_difficulties = [
            TEMPLATE_DIFFICULTY_BEGINNER,
            TEMPLATE_DIFFICULTY_INTERMEDIATE,
            TEMPLATE_DIFFICULTY_ADVANCED,
        ]

        for _, template in TEMPLATES.items():
            assert template["difficulty"] in valid_difficulties


# === TemplateService.list_templates Tests ===


class TestListTemplates:
    """Tests for list_templates method."""

    async def test_list_all_templates(self, template_service: TemplateService) -> None:
        """Test listing all templates."""
        templates = template_service.list_templates()

        assert len(templates) == len(TEMPLATES)

    async def test_list_templates_by_category(self, template_service: TemplateService) -> None:
        """Test filtering templates by category."""
        mean_reversion = template_service.list_templates(category=TEMPLATE_CATEGORY_MEAN_REVERSION)

        assert len(mean_reversion) > 0
        for template in mean_reversion:
            assert template["category"] == TEMPLATE_CATEGORY_MEAN_REVERSION

    async def test_list_templates_by_difficulty_beginner(
        self, template_service: TemplateService
    ) -> None:
        """Test filtering templates by beginner difficulty."""
        beginner = template_service.list_templates(difficulty=TEMPLATE_DIFFICULTY_BEGINNER)

        assert len(beginner) > 0
        for template in beginner:
            assert template["difficulty"] == TEMPLATE_DIFFICULTY_BEGINNER

    async def test_list_templates_by_difficulty_advanced(
        self, template_service: TemplateService
    ) -> None:
        """Test filtering templates by advanced difficulty."""
        advanced = template_service.list_templates(difficulty=TEMPLATE_DIFFICULTY_ADVANCED)

        assert len(advanced) > 0
        for template in advanced:
            assert template["difficulty"] == TEMPLATE_DIFFICULTY_ADVANCED

    async def test_list_templates_combined_filters(self, template_service: TemplateService) -> None:
        """Test filtering by both category and difficulty."""
        result = template_service.list_templates(
            category=TEMPLATE_CATEGORY_BUY_AND_HOLD,
            difficulty=TEMPLATE_DIFFICULTY_BEGINNER,
        )

        for template in result:
            assert template["category"] == TEMPLATE_CATEGORY_BUY_AND_HOLD
            assert template["difficulty"] == TEMPLATE_DIFFICULTY_BEGINNER

    async def test_list_templates_no_matches(self, template_service: TemplateService) -> None:
        """Test filtering with category that has no templates returns empty."""
        # Use an invalid category value to ensure no matches
        result = template_service.list_templates(category=9999)

        assert result == []

    async def test_list_templates_response_fields(self, template_service: TemplateService) -> None:
        """Test that template responses have all fields."""
        templates = template_service.list_templates()

        for template in templates:
            assert template["id"] is not None
            assert template["name"] is not None
            assert template["description"] is not None
            assert template["category"] is not None
            assert template["config_sexpr"] is not None
            assert template["tags"] is not None
            assert template["difficulty"] is not None


# === TemplateService.get_template Tests ===


class TestGetTemplate:
    """Tests for get_template method."""

    async def test_get_template_found(self, template_service: TemplateService) -> None:
        """Test getting an existing template."""
        template = template_service.get_template("ma-crossover")

        assert template is not None
        assert template["id"] == "ma-crossover"
        assert template["name"] == "Moving Average Crossover"
        assert template["category"] == TEMPLATE_CATEGORY_TREND

    async def test_get_template_not_found(self, template_service: TemplateService) -> None:
        """Test getting a non-existent template."""
        template = template_service.get_template("nonexistent")

        assert template is None

    async def test_get_template_rsi(self, template_service: TemplateService) -> None:
        """Test getting RSI template."""
        template = template_service.get_template("rsi-mean-reversion")

        assert template is not None
        assert "RSI" in template["name"]
        assert "rsi" in template["tags"]

    async def test_get_template_pairs_trading(self, template_service: TemplateService) -> None:
        """Test getting pairs trading template."""
        template = template_service.get_template("pairs-trading")

        assert template is not None
        assert "KO" in template["config_sexpr"]
        assert "PEP" in template["config_sexpr"]


# === TemplateService.get_template_config Tests ===


class TestGetTemplateConfig:
    """Tests for get_template_config method."""

    async def test_get_template_config_found(self, template_service: TemplateService) -> None:
        """Test getting config for existing template."""
        config = template_service.get_template_config("ma-crossover")

        assert config is not None
        assert "(strategy" in config
        assert "ema" in config.lower()

    async def test_get_template_config_not_found(self, template_service: TemplateService) -> None:
        """Test getting config for non-existent template."""
        config = template_service.get_template_config("nonexistent")

        assert config is None

    async def test_get_template_config_bollinger(self, template_service: TemplateService) -> None:
        """Test getting Bollinger bounce config."""
        config = template_service.get_template_config("bollinger-bounce")

        assert config is not None
        assert "bbands" in config
        assert ":lower" in config
        assert ":upper" in config

    async def test_get_template_config_dual_momentum(
        self, template_service: TemplateService
    ) -> None:
        """Test getting dual momentum config."""
        config = template_service.get_template_config("dual-momentum")

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
