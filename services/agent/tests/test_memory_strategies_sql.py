"""search_past_strategies on real SQL (see ``_sqlite_tier``).

The live failure was a lazy load of ``Strategy.versions`` off the async session
(``MissingGreenlet``). The query now selects columns joined to the current
version, so these tests pin its results and that it never returns ORM entities.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from llamatrade_db.base import Base
from llamatrade_db.models import Strategy, StrategyVersion
from tests._sqlite_tier import as_async_session

from src.services.memory_service import MemoryService

_TABLES = [Base.metadata.tables[name] for name in ("strategies", "strategy_versions")]


@pytest.fixture(scope="module")
def sqlite_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=_TABLES)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(sqlite_engine: Engine) -> Iterator[Session]:
    session = sessionmaker(bind=sqlite_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _seed(
    db: Session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    name: str,
    versions: list[tuple[str, list[str]]],
    current_version: int | None = None,
) -> Strategy:
    strategy = Strategy(
        tenant_id=tenant_id,
        name=name,
        description=f"{name} description",
        status=2,
        current_version=current_version or max(len(versions), 1),
        created_by=user_id,
    )
    db.add(strategy)
    db.flush()
    for number, (dsl, symbols) in enumerate(versions, start=1):
        db.add(
            StrategyVersion(
                tenant_id=tenant_id,
                strategy_id=strategy.id,
                version=number,
                config_sexpr=dsl,
                symbols=symbols,
                rebalance="daily",
                created_by=user_id,
            )
        )
    db.flush()
    db.expire_all()
    return strategy


@pytest.mark.asyncio
async def test_returns_current_version_dsl_and_symbols(db_session: Session) -> None:
    tenant_id, user_id = uuid4(), uuid4()
    _seed(
        db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        name="Recession Radar",
        versions=[("(strategy v1)", ["SPY"]), ("(strategy v2)", ["TLT", "GLD"])],
        current_version=1,
    )
    service = MemoryService(db=as_async_session(db_session), tenant_id=tenant_id, user_id=user_id)

    results = await service.search_past_strategies(query="Recession")

    assert len(results) == 1
    assert results[0].strategy_name == "Recession Radar"
    assert results[0].dsl_snippet == "(strategy v1)"
    assert results[0].symbols == ["SPY"]


@pytest.mark.asyncio
async def test_does_not_touch_strategy_relationships(db_session: Session) -> None:
    """No row is an ORM Strategy, so no relationship can lazy-load on an async session."""
    tenant_id, user_id = uuid4(), uuid4()
    _seed(
        db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        name="A",
        versions=[("(strategy a)", ["QQQ"])],
    )
    db_session.expunge_all()
    service = MemoryService(db=as_async_session(db_session), tenant_id=tenant_id, user_id=user_id)

    results = await service.search_past_strategies()

    assert [r.strategy_name for r in results] == ["A"]
    assert not any(isinstance(obj, Strategy) for obj in db_session.identity_map.values())


@pytest.mark.asyncio
async def test_strategy_without_versions_and_symbol_filter(db_session: Session) -> None:
    tenant_id, user_id = uuid4(), uuid4()
    _seed(db_session, tenant_id=tenant_id, user_id=user_id, name="Empty", versions=[])
    _seed(
        db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        name="Bonds",
        versions=[("(strategy b)", ["TLT"])],
    )
    service = MemoryService(db=as_async_session(db_session), tenant_id=tenant_id, user_id=user_id)

    everything = await service.search_past_strategies()
    by_symbol = await service.search_past_strategies(symbols=["TLT"])

    empty = next(r for r in everything if r.strategy_name == "Empty")
    assert empty.dsl_snippet is None
    assert empty.symbols == []
    assert [r.strategy_name for r in by_symbol] == ["Bonds"]


@pytest.mark.asyncio
async def test_other_users_and_tenants_are_excluded(db_session: Session) -> None:
    tenant_id, user_id = uuid4(), uuid4()
    _seed(db_session, tenant_id=tenant_id, user_id=user_id, name="Mine", versions=[("(m)", [])])
    _seed(db_session, tenant_id=tenant_id, user_id=uuid4(), name="Mate", versions=[("(x)", [])])
    _seed(db_session, tenant_id=uuid4(), user_id=user_id, name="Other", versions=[("(o)", [])])
    service = MemoryService(db=as_async_session(db_session), tenant_id=tenant_id, user_id=user_id)

    results = await service.search_past_strategies()

    assert [r.strategy_name for r in results] == ["Mine"]
