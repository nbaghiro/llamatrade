"""Behaviour of the proto-int <-> PostgreSQL-ENUM TypeDecorators.

Two regressions are pinned here:

* An int with no entry in ``_int_to_str`` used to resolve to the *first* enum
  member, so writing ``EXECUTION_STATUS_PENDING`` to ``trading_sessions.status``
  stored ``'active'`` — a stopped-looking session became a live-looking one, and
  the same silent substitution applied to every bridged column.
* The decorators inherited ``cache_ok`` from their base. SQLAlchemy reads that
  flag from ``type(self).__dict__`` only, so it read as unset and every
  statement touching a bridged column was excluded from the statement cache.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Dialect, create_engine, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SAWarning, StatementError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.cache_key import NO_CACHE
from sqlalchemy.sql.compiler import GenericTypeCompiler

import llamatrade_db.models._enum_types as et
from llamatrade_db.base import Base
from llamatrade_db.models.agent import AgentMemoryFact
from llamatrade_db.models.trading import Order, TradingSession
from llamatrade_proto.generated import common_pb2

_DIALECT = cast(Dialect, None)


@compiles(JSONB, "sqlite")
def _render_jsonb_on_sqlite(type_: JSONB, compiler: GenericTypeCompiler, **kw: Any) -> str:
    """SQLite has no JSONB; its JSON type stores the same values."""
    return "JSON"


@pytest.fixture(scope="module")
def sqlite_engine() -> Iterator[Engine]:
    """A SQLite engine holding only the table this module writes to."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[TradingSession.__table__])
    yield engine
    engine.dispose()


@pytest.fixture
def orm_session(sqlite_engine: Engine) -> Iterator[Session]:
    session = sessionmaker(bind=sqlite_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _decorators() -> list[type[et._ProtoEnumType[int]]]:
    """Every concrete proto-backed decorator, discovered so new ones are covered."""
    found = [
        obj
        for obj in vars(et).values()
        if isinstance(obj, type)
        and issubclass(obj, et._ProtoEnumType)
        and obj is not et._ProtoEnumType
    ]
    assert len(found) >= 20  # guard the guard: introspection must not silently find nothing
    return found


_DECORATOR_CASES = _decorators()
_IDS = [d.__name__ for d in _DECORATOR_CASES]


@pytest.mark.parametrize("decorator", _DECORATOR_CASES, ids=_IDS)
def test_every_mapped_value_round_trips(decorator: type[et._ProtoEnumType[int]]) -> None:
    """int -> label -> int is the identity for every mapped proto value."""
    td = decorator()
    for proto_value, member in decorator._int_to_str.items():
        label = td.process_bind_param(proto_value, _DIALECT)
        assert label == member.value
        assert td.process_result_value(label, _DIALECT) == proto_value
        # A label supplied directly (not via the int map) survives unchanged.
        assert td.process_bind_param(cast(int, member.value.upper()), _DIALECT) == member.value


@pytest.mark.parametrize("decorator", _DECORATOR_CASES, ids=_IDS)
def test_unspecified_sentinel_write_raises(decorator: type[et._ProtoEnumType[int]]) -> None:
    """The proto zero sentinel has no label; writing it must not pick a member."""
    with pytest.raises(ValueError) as excinfo:
        decorator().process_bind_param(0, _DIALECT)
    message = str(excinfo.value)
    assert decorator.__name__ in message
    assert "0" in message


@pytest.mark.parametrize("decorator", _DECORATOR_CASES, ids=_IDS)
def test_unmapped_int_write_raises(decorator: type[et._ProtoEnumType[int]]) -> None:
    """An int outside the map names the decorator and the offending value."""
    unmapped = max(decorator._int_to_str) + 1000
    with pytest.raises(ValueError) as excinfo:
        decorator().process_bind_param(unmapped, _DIALECT)
    message = str(excinfo.value)
    assert decorator.__name__ in message
    assert str(unmapped) in message


@pytest.mark.parametrize("decorator", _DECORATOR_CASES, ids=_IDS)
def test_unknown_label_read_raises(decorator: type[et._ProtoEnumType[int]]) -> None:
    """A DB label the map does not know must not read back as the zero sentinel."""
    with pytest.raises(ValueError) as excinfo:
        decorator().process_result_value("not_a_real_label", _DIALECT)
    message = str(excinfo.value)
    assert decorator.__name__ in message
    assert "not_a_real_label" in message


@pytest.mark.parametrize("decorator", _DECORATOR_CASES, ids=_IDS)
def test_unknown_label_write_raises(decorator: type[et._ProtoEnumType[int]]) -> None:
    """A string that is not a label of this enum is rejected before it reaches PG."""
    with pytest.raises(ValueError) as excinfo:
        decorator().process_bind_param(cast(int, "not_a_real_label"), _DIALECT)
    assert decorator.__name__ in str(excinfo.value)


@pytest.mark.parametrize("decorator", _DECORATOR_CASES, ids=_IDS)
def test_none_passes_through(decorator: type[et._ProtoEnumType[int]]) -> None:
    td = decorator()
    assert td.process_bind_param(None, _DIALECT) is None
    assert td.process_result_value(None, _DIALECT) is None


# The PENDING case: ``session_status`` has no ``'pending'`` label and nothing
# writes EXECUTION_STATUS_PENDING to a session, so the bridge fails loudly
# rather than gaining a mapping.


def test_pending_execution_status_is_rejected_by_session_status() -> None:
    """EXECUTION_STATUS_PENDING has no session equivalent, in either direction."""
    td = et.SessionStatusType()

    with pytest.raises(ValueError, match="SessionStatusType"):
        td.process_bind_param(common_pb2.EXECUTION_STATUS_PENDING, _DIALECT)

    with pytest.raises(ValueError, match="SessionStatusType"):
        td.process_result_value("pending", _DIALECT)

    assert "pending" not in [member.value for member in et._SessionStatus]


def test_pending_execution_status_round_trips_on_executions() -> None:
    """The same value is legitimate on ``strategy_executions.status`` and maps there."""
    td = et.ExecutionStatusType()
    label = td.process_bind_param(common_pb2.EXECUTION_STATUS_PENDING, _DIALECT)
    assert label == "pending"
    assert td.process_result_value(label, _DIALECT) == common_pb2.EXECUTION_STATUS_PENDING


def _session_row(status: common_pb2.ExecutionStatus.ValueType) -> TradingSession:
    return TradingSession(
        id=uuid4(),
        tenant_id=UUID(int=1),
        strategy_id=uuid4(),
        strategy_version=1,
        credentials_id=uuid4(),
        name="session",
        mode=common_pb2.EXECUTION_MODE_PAPER,
        status=status,
        config={},
        symbols=["SPY"],
        created_by=UUID(int=2),
        created_at=datetime.now(UTC),
    )


def test_session_insert_with_pending_status_raises(orm_session: Session) -> None:
    """End to end: the ORM refuses the write instead of persisting ``'active'``."""
    orm_session.add(_session_row(common_pb2.EXECUTION_STATUS_PENDING))
    with pytest.raises(StatementError) as excinfo:
        orm_session.flush()
    assert "SessionStatusType" in str(excinfo.value)


def test_session_insert_with_running_status_stores_active(orm_session: Session) -> None:
    """The mapped neighbour still writes, so the guard is not blanket rejection."""
    row = _session_row(common_pb2.EXECUTION_STATUS_RUNNING)
    orm_session.add(row)
    orm_session.flush()

    # Raw SQL: the stored label, before the result processor maps it back.
    label = orm_session.execute(text("SELECT status FROM trading_sessions")).scalar_one()
    assert label == "active"
    assert row.status == common_pb2.EXECUTION_STATUS_RUNNING


# Statement caching.


@pytest.mark.parametrize("decorator", _DECORATOR_CASES, ids=_IDS)
def test_decorator_produces_a_static_cache_key(decorator: type[et._ProtoEnumType[int]]) -> None:
    """``cache_ok`` must live in the concrete class, otherwise the key is NO_CACHE."""
    assert "cache_ok" in decorator.__dict__
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        cache_key = decorator()._static_cache_key
    assert cache_key is not NO_CACHE
    assert isinstance(cache_key, tuple)


def test_memory_fact_category_produces_a_static_cache_key() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        cache_key = et.MemoryFactCategoryType()._static_cache_key
    assert cache_key is not NO_CACHE


def test_queries_on_bridged_columns_are_cacheable() -> None:
    """Compiling against a bridged column emits no SAWarning and yields a cache key."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        statements = [
            select(Order).where(Order.status == 1),
            select(Order).where(Order.side.in_([1, 2])),
            select(TradingSession).where(TradingSession.status == 2),
            select(AgentMemoryFact).where(AgentMemoryFact.category == "feedback"),
        ]
        for statement in statements:
            assert statement._generate_cache_key() is not None


def test_equal_statements_share_a_cache_key() -> None:
    """Two structurally identical statements hash to the same cached compilation."""
    first = select(Order).where(Order.status == 1)._generate_cache_key()
    second = select(Order).where(Order.status == 2)._generate_cache_key()
    assert first is not None and second is not None
    assert first.key == second.key
