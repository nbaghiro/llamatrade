"""Template service - pre-built strategy templates using allocation-based S-expression DSL.

The template catalog is the SINGLE SOURCE OF TRUTH for all strategy templates and
lives as editable product content in ``src/data/templates.json``. It is loaded and
validated once at import against :class:`TemplateData`; enum fields are stored by
their proto name (e.g. ``TEMPLATE_CATEGORY_TREND``) so the file survives proto
renumbering and reads without a code review. Frontend fetches these via the API and
parses the S-expressions into visual blocks.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict, cast

from llamatrade_proto.generated.strategy_pb2 import (
    AssetClass,
    TemplateCategory,
    TemplateDifficulty,
)


class TemplateData(TypedDict):
    """Template data structure for internal storage."""

    id: str
    name: str
    description: str
    category: TemplateCategory.ValueType
    asset_class: AssetClass.ValueType
    tags: list[str]
    difficulty: TemplateDifficulty.ValueType
    config_sexpr: str


_TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "data" / "templates.json"


def _require_str(entry: dict[str, object], key: str, template_id: str) -> str:
    """A required string field, rejecting a missing or non-string value."""
    value = entry.get(key)
    if not isinstance(value, str):
        raise ValueError(f"template {template_id!r}: field {key!r} must be a string")
    return value


def _require_tags(entry: dict[str, object], template_id: str) -> list[str]:
    """The required ``tags`` field, rejecting anything but a list of strings."""
    value = entry.get("tags")
    if not isinstance(value, list) or not all(isinstance(tag, str) for tag in value):
        raise ValueError(f"template {template_id!r}: field 'tags' must be a list of strings")
    return [tag for tag in value if isinstance(tag, str)]


def _enum_value[V](convert: Callable[[str], V], raw: object, field: str, template_id: str) -> V:
    """Convert a proto enum name to its value, rejecting a missing/unknown name."""
    if not isinstance(raw, str):
        raise ValueError(f"template {template_id!r}: field {field!r} must be an enum name string")
    try:
        return convert(raw)
    except ValueError as e:
        raise ValueError(f"template {template_id!r}: unknown {field} {raw!r}") from e


def _parse_template(entry: object) -> TemplateData:
    """Validate one raw JSON entry into a typed :class:`TemplateData`."""
    if not isinstance(entry, dict):
        raise ValueError("each template entry must be a JSON object")
    data = cast(dict[str, object], entry)
    template_id = _require_str(data, "id", "<unknown>")
    return TemplateData(
        id=template_id,
        name=_require_str(data, "name", template_id),
        description=_require_str(data, "description", template_id),
        category=_enum_value(TemplateCategory.Value, data.get("category"), "category", template_id),
        asset_class=_enum_value(
            AssetClass.Value, data.get("asset_class"), "asset_class", template_id
        ),
        tags=_require_tags(data, template_id),
        difficulty=_enum_value(
            TemplateDifficulty.Value, data.get("difficulty"), "difficulty", template_id
        ),
        config_sexpr=_require_str(data, "config_sexpr", template_id),
    )


def _load_templates() -> dict[str, TemplateData]:
    """Load and validate the catalog once at import, keyed by template id."""
    parsed: object = json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError(f"{_TEMPLATES_PATH} must contain a JSON list of template objects")
    entries = cast(list[object], parsed)
    templates: dict[str, TemplateData] = {}
    for entry in entries:
        template = _parse_template(entry)
        if template["id"] in templates:
            raise ValueError(f"duplicate template id: {template['id']!r}")
        templates[template["id"]] = template
    return templates


# Curated strategy templates, loaded and validated at import.
TEMPLATES: dict[str, TemplateData] = _load_templates()


class TemplateService:
    """Service for strategy template operations."""

    def list_templates(
        self,
        category: TemplateCategory.ValueType | None = None,
        asset_class: AssetClass.ValueType | None = None,
        difficulty: TemplateDifficulty.ValueType | None = None,
    ) -> list[TemplateData]:
        """List available strategy templates.

        Args:
            category: Filter by template category (proto enum value)
            asset_class: Filter by asset class (proto enum value)
            difficulty: Filter by difficulty level (proto enum value)

        Returns:
            List of TemplateData entries (mapped to proto by the servicer)
        """
        templates = list(TEMPLATES.values())

        if category:
            templates = [t for t in templates if t["category"] == category]

        if asset_class:
            templates = [t for t in templates if t["asset_class"] == asset_class]

        if difficulty:
            templates = [t for t in templates if t["difficulty"] == difficulty]

        return templates

    def get_template(self, template_id: str) -> TemplateData | None:
        """Get a specific template by ID.

        Args:
            template_id: The template identifier

        Returns:
            TemplateData or None if not found
        """
        return TEMPLATES.get(template_id)

    def get_template_config(self, template_id: str) -> str | None:
        """Get just the S-expression config for a template.

        Args:
            template_id: The template identifier

        Returns:
            S-expression config string or None if not found
        """
        template = TEMPLATES.get(template_id)
        return template["config_sexpr"] if template else None


def get_template_service() -> TemplateService:
    """Dependency to get template service."""
    return TemplateService()
