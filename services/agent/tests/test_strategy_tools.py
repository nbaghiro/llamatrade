"""Tests for the agent's strategy tools against mocked Connect clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llamatrade_proto.generated import common_pb2, strategy_pb2

from src.tools.base import ToolContext
from src.tools.strategy_tools import (
    GetStrategyTool,
    ListStrategiesTool,
    ListTemplatesTool,
    _get_builtin_templates,
)

pytestmark = pytest.mark.asyncio

CLIENT_PATH = "llamatrade_proto.generated.strategy_connect.StrategyServiceClient"


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(tenant_id=uuid4(), user_id=uuid4(), session_id=uuid4())


def _client_class(**methods: AsyncMock) -> MagicMock:
    """A patchable StrategyServiceClient class whose instance exposes methods."""
    client = MagicMock()
    for name, method in methods.items():
        setattr(client, name, method)
    return MagicMock(return_value=client)


def _strategy(
    name: str = "Momentum",
    status: int = strategy_pb2.STRATEGY_STATUS_ACTIVE,
    dsl_code: str = '(strategy "Momentum" (asset SPY))',
) -> strategy_pb2.Strategy:
    return strategy_pb2.Strategy(
        id=str(uuid4()),
        name=name,
        description="A momentum strategy",
        status=status,
        version=3,
        dsl_code=dsl_code,
        symbols=["SPY", "QQQ"],
    )


def _list_response(*strategies: strategy_pb2.Strategy) -> strategy_pb2.ListStrategiesResponse:
    return strategy_pb2.ListStrategiesResponse(
        strategies=list(strategies),
        pagination=common_pb2.PaginationResponse(total_items=len(strategies)),
    )


class TestListStrategiesTool:
    """list_strategies success mapping, filters, and failure masking."""

    async def test_success_maps_strategies(self, ctx: ToolContext) -> None:
        call = AsyncMock(return_value=_list_response(_strategy()))
        with patch(CLIENT_PATH, _client_class(list_strategies=call)):
            result = await ListStrategiesTool().execute({}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["total_count"] == 1
        listed = result.data["strategies"][0]
        assert listed["name"] == "Momentum"
        assert listed["status"] == "active"
        assert listed["symbols"] == ["SPY", "QQQ"]

    async def test_long_dsl_is_truncated(self, ctx: ToolContext) -> None:
        call = AsyncMock(return_value=_list_response(_strategy(dsl_code="x" * 300)))
        with patch(CLIENT_PATH, _client_class(list_strategies=call)):
            result = await ListStrategiesTool().execute({}, ctx)

        assert result.data is not None
        dsl = result.data["strategies"][0]["dsl_code"]
        assert dsl == "x" * 200 + "..."

    async def test_threads_tenant_identity(self, ctx: ToolContext) -> None:
        call = AsyncMock(return_value=_list_response())
        with patch(CLIENT_PATH, _client_class(list_strategies=call)):
            await ListStrategiesTool().execute({}, ctx)

        request = call.call_args.args[0]
        assert request.context.tenant_id == str(ctx.tenant_id)
        assert request.context.user_id == str(ctx.user_id)
        headers = call.call_args.kwargs["headers"]
        assert headers["X-Tenant-ID"] == str(ctx.tenant_id)
        assert headers["X-User-ID"] == str(ctx.user_id)
        assert headers["Authorization"].startswith("Bearer ")

    async def test_status_filter_and_limit_map_to_request(self, ctx: ToolContext) -> None:
        call = AsyncMock(return_value=_list_response())
        with patch(CLIENT_PATH, _client_class(list_strategies=call)):
            await ListStrategiesTool().execute({"status_filter": "paused", "limit": 5}, ctx)

        request = call.call_args.args[0]
        assert list(request.statuses) == [strategy_pb2.STRATEGY_STATUS_PAUSED]
        assert request.pagination.page_size == 5

    async def test_all_filter_sends_no_statuses(self, ctx: ToolContext) -> None:
        call = AsyncMock(return_value=_list_response())
        with patch(CLIENT_PATH, _client_class(list_strategies=call)):
            await ListStrategiesTool().execute({"status_filter": "all"}, ctx)

        assert list(call.call_args.args[0].statuses) == []

    async def test_service_error_degrades_to_empty_list_with_note(self, ctx: ToolContext) -> None:
        call = AsyncMock(side_effect=ConnectionError("strategy down"))
        with patch(CLIENT_PATH, _client_class(list_strategies=call)):
            result = await ListStrategiesTool().execute({}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["strategies"] == []
        assert result.data["total_count"] == 0
        assert "unavailable" in result.data["note"]


class TestGetStrategyTool:
    """get_strategy success mapping and error surfacing."""

    async def test_success_maps_full_strategy(self, ctx: ToolContext) -> None:
        strategy = _strategy(dsl_code="y" * 300)
        call = AsyncMock(return_value=strategy_pb2.GetStrategyResponse(strategy=strategy))
        with patch(CLIENT_PATH, _client_class(get_strategy=call)):
            result = await GetStrategyTool().execute({"strategy_id": strategy.id}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["id"] == strategy.id
        assert result.data["status"] == "active"
        assert result.data["version"] == 3
        assert result.data["dsl_code"] == "y" * 300  # full DSL, no truncation

        request = call.call_args.args[0]
        assert request.strategy_id == strategy.id
        assert request.context.tenant_id == str(ctx.tenant_id)

    async def test_missing_strategy_id_fails_without_calling_service(
        self, ctx: ToolContext
    ) -> None:
        call = AsyncMock()
        with patch(CLIENT_PATH, _client_class(get_strategy=call)):
            result = await GetStrategyTool().execute({}, ctx)

        assert result.success is False
        assert result.error == "strategy_id is required"
        call.assert_not_awaited()

    async def test_service_error_returns_failure(self, ctx: ToolContext) -> None:
        call = AsyncMock(side_effect=RuntimeError("not found"))
        with patch(CLIENT_PATH, _client_class(get_strategy=call)):
            result = await GetStrategyTool().execute({"strategy_id": str(uuid4())}, ctx)

        assert result.success is False
        assert result.error is not None and "not found" in result.error


class TestListTemplatesTool:
    """list_templates enum mapping and builtin fallback."""

    async def test_success_maps_templates(self, ctx: ToolContext) -> None:
        template = strategy_pb2.StrategyTemplate(
            id=str(uuid4()),
            name="Trend Rider",
            description="Follows the trend",
            category=strategy_pb2.TEMPLATE_CATEGORY_TREND,
            difficulty=strategy_pb2.TEMPLATE_DIFFICULTY_INTERMEDIATE,
            config_sexpr='(strategy "Trend Rider")',
        )
        call = AsyncMock(return_value=strategy_pb2.ListTemplatesResponse(templates=[template]))
        with patch(CLIENT_PATH, _client_class(list_templates=call)):
            result = await ListTemplatesTool().execute({}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["count"] == 1
        mapped = result.data["templates"][0]
        assert mapped["category"] == "trend"
        assert mapped["difficulty"] == "intermediate"
        assert mapped["config_sexpr"] == '(strategy "Trend Rider")'

    async def test_filters_map_to_request_enums(self, ctx: ToolContext) -> None:
        call = AsyncMock(return_value=strategy_pb2.ListTemplatesResponse())
        with patch(CLIENT_PATH, _client_class(list_templates=call)):
            await ListTemplatesTool().execute(
                {"category": "mean-reversion", "difficulty": "advanced"}, ctx
            )

        request = call.call_args.args[0]
        assert request.category == strategy_pb2.TEMPLATE_CATEGORY_MEAN_REVERSION
        assert request.difficulty == strategy_pb2.TEMPLATE_DIFFICULTY_ADVANCED

    async def test_no_filters_send_unspecified_enums(self, ctx: ToolContext) -> None:
        call = AsyncMock(return_value=strategy_pb2.ListTemplatesResponse())
        with patch(CLIENT_PATH, _client_class(list_templates=call)):
            await ListTemplatesTool().execute({}, ctx)

        request = call.call_args.args[0]
        assert request.category == strategy_pb2.TEMPLATE_CATEGORY_UNSPECIFIED
        assert request.difficulty == strategy_pb2.TEMPLATE_DIFFICULTY_UNSPECIFIED

    async def test_threads_tenant_headers(self, ctx: ToolContext) -> None:
        call = AsyncMock(return_value=strategy_pb2.ListTemplatesResponse())
        with patch(CLIENT_PATH, _client_class(list_templates=call)):
            await ListTemplatesTool().execute({}, ctx)

        headers = call.call_args.kwargs["headers"]
        assert headers["X-Tenant-ID"] == str(ctx.tenant_id)
        assert headers["X-User-ID"] == str(ctx.user_id)

    async def test_service_error_falls_back_to_builtin_templates(self, ctx: ToolContext) -> None:
        call = AsyncMock(side_effect=ConnectionError("strategy down"))
        with patch(CLIENT_PATH, _client_class(list_templates=call)):
            result = await ListTemplatesTool().execute({}, ctx)

        assert result.success is True
        assert result.data is not None
        assert result.data["templates"] == _get_builtin_templates()
        assert result.data["count"] == len(_get_builtin_templates())
        assert "service unavailable" in result.data["note"]
