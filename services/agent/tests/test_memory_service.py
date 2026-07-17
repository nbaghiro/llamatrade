"""Tests for MemoryService fact storage and dedup."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.memory_service import MemoryService


def _fact(content: str, category: str = "asset_preference") -> SimpleNamespace:
    return SimpleNamespace(
        category=category,
        content=content,
        confidence=0.8,
        extraction_method="heuristic",
    )


@pytest.fixture
def service() -> MemoryService:
    db = AsyncMock()
    db.add = MagicMock()
    return MemoryService(db=db, tenant_id=uuid4(), user_id=uuid4())


def _where_pairs(stmt) -> dict[str, object]:
    """Map each top-level equality in a statement's WHERE to {column: bound value}."""
    clause = stmt.whereclause
    elements = list(clause.clauses) if hasattr(clause, "clauses") else [clause]
    pairs: dict[str, object] = {}
    for expr in elements:
        col = getattr(getattr(expr, "left", None), "key", None)
        val = getattr(getattr(expr, "right", None), "value", None)
        if col is not None:
            pairs[col] = val
    return pairs


class _FakeResult:
    """Minimal stand-in for a SQLAlchemy Result across the memory queries."""

    def scalar_one(self) -> int:
        return 1  # non-zero session count so get_memory_hint proceeds past the new-user check

    def scalar_one_or_none(self) -> None:
        return None

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[object]:
        return []

    def fetchall(self) -> list[object]:
        return []


def _capturing_service(tenant_id, user_id, captured: list[object]) -> MemoryService:
    async def capture(stmt: object) -> _FakeResult:
        captured.append(stmt)
        return _FakeResult()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=capture)
    return MemoryService(db=db, tenant_id=tenant_id, user_id=user_id)


@pytest.mark.asyncio
async def test_search_past_strategies_scopes_to_acting_user() -> None:
    """A tenant-mate's strategies must not surface — the query is created_by-scoped."""
    tenant_id, user_id = uuid4(), uuid4()
    captured: list[object] = []
    service = _capturing_service(tenant_id, user_id, captured)

    await service.search_past_strategies()

    pairs = _where_pairs(captured[0])
    assert pairs["tenant_id"] == tenant_id
    assert pairs["created_by"] == user_id


@pytest.mark.asyncio
async def test_memory_hint_recent_strategies_scopes_to_acting_user() -> None:
    """The recent-strategies prompt hint only lists the user's own authored strategies."""
    tenant_id, user_id = uuid4(), uuid4()
    captured: list[object] = []
    service = _capturing_service(tenant_id, user_id, captured)

    await service.get_memory_hint()

    strategy_stmts = [s for s in captured if "created_by" in _where_pairs(s)]
    assert len(strategy_stmts) == 1, "recent-strategies query should scope by created_by"
    pairs = _where_pairs(strategy_stmts[0])
    assert pairs["tenant_id"] == tenant_id
    assert pairs["created_by"] == user_id


@pytest.mark.asyncio
async def test_store_facts_skips_exact_duplicate(service: MemoryService) -> None:
    """An exact re-mention already on file is not stored again."""
    with patch.object(service, "_active_fact_exists", AsyncMock(return_value=True)):
        result = await service.store_facts([_fact("prefers low-cost ETFs")])

    assert result == []
    service.db.add.assert_not_called()
    service.db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_facts_stores_new_fact(service: MemoryService) -> None:
    """A genuinely new fact is persisted."""
    with (
        patch.object(service, "_active_fact_exists", AsyncMock(return_value=False)),
        patch.object(service, "_find_similar_fact", AsyncMock(return_value=None)),
    ):
        result = await service.store_facts([_fact("prefers low-cost ETFs")])

    assert len(result) == 1
    service.db.add.assert_called_once()
    service.db.commit.assert_awaited_once()
