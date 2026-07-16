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
