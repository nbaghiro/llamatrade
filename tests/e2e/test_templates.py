"""E2E: the template catalog and both paths from a template to a saved strategy.

TemplatesPage lists the catalog, opens one, and hands its DSL to the builder. The
catalog is a built-in JSON asset, so this journey has no seed dependency and no
external seam. Both create paths are covered: the client-side one the builder
actually uses (template DSL then CreateStrategy) and the server-side shortcut
(``CreateStrategy`` with a ``templateId``).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from .client import MeshClient, MeshError

pytestmark = pytest.mark.e2e


def test_catalog_lists_usable_templates(demo: MeshClient) -> None:
    """Every listed template carries what the page renders and the builder needs."""
    resp = demo.call("strategy", "ListTemplates", {}, context=False)
    templates = resp.get("templates", [])

    assert templates, "the built-in template catalog is empty"
    for template in templates:
        assert template.get("id")
        assert template.get("name")
        assert template.get("configSexpr", "").startswith("(strategy")


def test_get_template_returns_the_listed_entry(demo: MeshClient) -> None:
    listed = demo.call("strategy", "ListTemplates", {}, context=False)["templates"][0]

    fetched = demo.call("strategy", "GetTemplate", {"templateId": listed["id"]}, context=False)[
        "template"
    ]

    assert fetched["id"] == listed["id"]
    assert fetched["configSexpr"] == listed["configSexpr"]


def test_unknown_template_is_not_found(demo: MeshClient) -> None:
    with pytest.raises(MeshError) as exc:
        demo.call("strategy", "GetTemplate", {"templateId": "no-such-template"}, context=False)
    assert "not_found" in str(exc.value).lower()


def test_builder_path_saves_a_strategy_from_template_dsl(
    throwaway_tenant: Callable[[str], MeshClient], demo: MeshClient
) -> None:
    """What the builder does: take the template's DSL, then CreateStrategy."""
    template = demo.call("strategy", "ListTemplates", {}, context=False)["templates"][0]
    client = throwaway_tenant("tpl-builder")

    created = client.call(
        "strategy",
        "CreateStrategy",
        {"name": f"From {template['name']}", "dslCode": template["configSexpr"]},
    )["strategy"]

    assert created["id"]
    fetched = client.call("strategy", "GetStrategy", {"strategyId": created["id"]})["strategy"]
    assert fetched["dslCode"] == template["configSexpr"]
    assert fetched["symbols"], "symbols are re-derived from the template DSL on save"


def test_server_side_template_id_creates_the_same_strategy(
    throwaway_tenant: Callable[[str], MeshClient], demo: MeshClient
) -> None:
    """The shortcut path: the server instantiates the template by id."""
    template = demo.call("strategy", "ListTemplates", {}, context=False)["templates"][0]
    client = throwaway_tenant("tpl-server")

    created = client.call(
        "strategy",
        "CreateStrategy",
        {"name": "Server-side template", "templateId": template["id"]},
    )["strategy"]

    fetched = client.call("strategy", "GetStrategy", {"strategyId": created["id"]})["strategy"]
    assert fetched["dslCode"] == template["configSexpr"]
