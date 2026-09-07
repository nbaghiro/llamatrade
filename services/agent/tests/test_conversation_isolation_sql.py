"""Tenant-isolation predicate tests for conversation persistence, on real SQL.

The mock-based suite in ``test_conversation_service.py`` stubs ``db.execute``,
so it cannot catch a dropped tenant filter. These tests seed two tenants'
sessions, messages, and artifacts through the real models and run the real
``ConversationService`` queries against a SQLite schema (see ``_sqlite_tier``),
so a wrong predicate fails. The delete RPC is also driven through the real
servicer over the same schema, covering success, not-found, and cross-tenant.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, sessionmaker

from llamatrade_db.base import Base
from llamatrade_db.models import AgentMessage, AgentSession, PendingArtifact
from llamatrade_proto.generated import agent_pb2, common_pb2
from llamatrade_proto.generated.agent_pb2 import (
    AGENT_SESSION_STATUS_ACTIVE,
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_USER,
)
from tests._sqlite_tier import as_async_session

from src.grpc.servicer import AgentServicer
from src.services.conversation_service import ConversationService

_TABLES = [
    Base.metadata.tables[name]
    for name in ("agent_sessions", "agent_messages", "pending_artifacts", "tool_call_logs")
]


@pytest.fixture(scope="module")
def sqlite_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=_TABLES)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(sqlite_engine: Engine) -> Iterator[Session]:
    """A rolled-back session per test, so rows never leak between them."""
    session = sessionmaker(bind=sqlite_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def adapted(db_session: Session) -> AsyncSession:
    return as_async_session(db_session)


@pytest.fixture
def service(adapted: AsyncSession) -> ConversationService:
    return ConversationService(adapted)


def _make_session(
    db: Session,
    *,
    tenant_id: UUID,
    user_id: UUID | None = None,
    title: str = "seeded",
) -> AgentSession:
    row = AgentSession(
        tenant_id=tenant_id,
        user_id=user_id or uuid4(),
        title=title,
        status=AGENT_SESSION_STATUS_ACTIVE,
        message_count=0,
        last_activity_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return row


def _make_message(
    db: Session,
    *,
    agent_session: AgentSession,
    content: str,
    role: agent_pb2.MessageRole.ValueType = MESSAGE_ROLE_USER,
    age: timedelta = timedelta(0),
) -> AgentMessage:
    row = AgentMessage(
        session_id=agent_session.id,
        tenant_id=agent_session.tenant_id,
        role=role,
        content=content,
        created_at=datetime.now(UTC) - age,
    )
    db.add(row)
    db.flush()
    return row


def _make_artifact(db: Session, *, agent_session: AgentSession, name: str) -> PendingArtifact:
    row = PendingArtifact(
        session_id=agent_session.id,
        tenant_id=agent_session.tenant_id,
        artifact_type=1,
        name=name,
        artifact_json={"name": name},
        is_committed=False,
    )
    db.add(row)
    db.flush()
    return row


# =============================================================================
# Service-level predicates
# =============================================================================


async def test_get_session_does_not_cross_tenants(
    service: ConversationService, db_session: Session
) -> None:
    """Tenant A's read of tenant B's session id returns None; own reads work."""
    tenant_a, tenant_b = uuid4(), uuid4()
    session_a = _make_session(db_session, tenant_id=tenant_a)
    session_b = _make_session(db_session, tenant_id=tenant_b)

    assert await service.get_session(tenant_a, session_b.id) is None
    assert await service.get_session(tenant_b, session_a.id) is None
    found = await service.get_session(tenant_a, session_a.id)
    assert found is not None
    assert found.id == session_a.id


async def test_list_sessions_scoped_to_tenant_even_for_same_user_id(
    service: ConversationService, db_session: Session
) -> None:
    """The same user uuid in two tenants never sees the other tenant's rows."""
    tenant_a, tenant_b, shared_user = uuid4(), uuid4(), uuid4()
    own = _make_session(db_session, tenant_id=tenant_a, user_id=shared_user, title="mine")
    _make_session(db_session, tenant_id=tenant_b, user_id=shared_user, title="theirs")

    sessions, total = await service.list_sessions(tenant_a, shared_user)

    assert total == 1
    assert [s.id for s in sessions] == [own.id]


async def test_list_sessions_scoped_to_user_within_tenant(
    service: ConversationService, db_session: Session
) -> None:
    tenant_id, user_a, user_b = uuid4(), uuid4(), uuid4()
    own = _make_session(db_session, tenant_id=tenant_id, user_id=user_a)
    _make_session(db_session, tenant_id=tenant_id, user_id=user_b)

    sessions, total = await service.list_sessions(tenant_id, user_a)

    assert total == 1
    assert [s.id for s in sessions] == [own.id]


async def test_message_reads_scoped_to_the_requested_session(
    service: ConversationService, db_session: Session
) -> None:
    """get_messages and get_recent_messages never return another session's rows."""
    session_a = _make_session(db_session, tenant_id=uuid4())
    session_b = _make_session(db_session, tenant_id=uuid4())
    _make_message(db_session, agent_session=session_a, content="a-oldest", age=timedelta(minutes=2))
    _make_message(
        db_session,
        agent_session=session_a,
        content="a-newest",
        role=MESSAGE_ROLE_ASSISTANT,
        age=timedelta(minutes=1),
    )
    _make_message(db_session, agent_session=session_b, content="b-secret")

    messages = await service.get_messages(session_a.id)
    assert [m.content for m in messages] == ["a-oldest", "a-newest"]

    recent = await service.get_recent_messages(session_a.id, limit=10)
    assert [m.content for m in recent] == ["a-oldest", "a-newest"]


async def test_cross_tenant_message_read_is_gated_by_the_session_lookup(
    service: ConversationService, db_session: Session
) -> None:
    """The servicer guards message reads with a tenant-scoped get_session; that
    gate must refuse before any message query runs for a foreign session."""
    tenant_a = uuid4()
    session_b = _make_session(db_session, tenant_id=uuid4())
    _make_message(db_session, agent_session=session_b, content="b-secret")

    assert await service.get_session(tenant_a, session_b.id) is None


async def test_pending_artifacts_scoped_to_the_requested_session(
    service: ConversationService, db_session: Session
) -> None:
    session_a = _make_session(db_session, tenant_id=uuid4())
    session_b = _make_session(db_session, tenant_id=uuid4())
    _make_artifact(db_session, agent_session=session_a, name="mine")
    _make_artifact(db_session, agent_session=session_b, name="theirs")

    artifacts = await service.get_pending_artifacts(session_a.id)

    assert [a.name for a in artifacts] == ["mine"]


async def test_delete_session_cross_tenant_returns_false_and_keeps_the_row(
    service: ConversationService, db_session: Session
) -> None:
    tenant_a = uuid4()
    session_b = _make_session(db_session, tenant_id=uuid4())
    _make_message(db_session, agent_session=session_b, content="b-secret")

    assert await service.delete_session(tenant_a, session_b.id) is False
    assert (
        db_session.scalar(select(AgentSession).where(AgentSession.id == session_b.id)) is not None
    )


async def test_delete_session_own_tenant_removes_session_and_messages(
    service: ConversationService, db_session: Session
) -> None:
    tenant_id = uuid4()
    session_a = _make_session(db_session, tenant_id=tenant_id)
    _make_message(db_session, agent_session=session_a, content="gone with the session")

    assert await service.delete_session(tenant_id, session_a.id) is True
    assert db_session.scalar(select(AgentSession).where(AgentSession.id == session_a.id)) is None
    assert (
        db_session.scalar(select(AgentMessage).where(AgentMessage.session_id == session_a.id))
        is None
    )


# =============================================================================
# delete_session RPC layer over the same real schema (2.7)
# =============================================================================


@pytest.fixture
def servicer(adapted: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AgentServicer:
    """A real servicer whose tenant_session yields the SQLite-adapted session."""

    @asynccontextmanager
    async def _sqlite_tenant_session(tenant_id: UUID, maker: object) -> AsyncIterator[AsyncSession]:
        yield adapted

    monkeypatch.setattr("src.grpc.servicer.tenant_session", _sqlite_tenant_session)
    svc = AgentServicer()
    svc._session_maker = MagicMock()
    return svc


def _delete_request(tenant_id: UUID, session_id: UUID) -> agent_pb2.DeleteSessionRequest:
    return agent_pb2.DeleteSessionRequest(
        context=common_pb2.TenantContext(tenant_id=str(tenant_id), user_id=str(uuid4())),
        session_id=str(session_id),
    )


async def test_delete_session_rpc_success(
    servicer: AgentServicer, db_session: Session, mock_request_context: MagicMock
) -> None:
    tenant_id = uuid4()
    session_a = _make_session(db_session, tenant_id=tenant_id)

    response = await servicer.delete_session(
        _delete_request(tenant_id, session_a.id), mock_request_context
    )

    assert response.success is True
    assert db_session.scalar(select(AgentSession).where(AgentSession.id == session_a.id)) is None


async def test_delete_session_rpc_not_found(
    servicer: AgentServicer, mock_request_context: MagicMock
) -> None:
    with pytest.raises(ConnectError) as exc_info:
        await servicer.delete_session(_delete_request(uuid4(), uuid4()), mock_request_context)

    assert exc_info.value.code == Code.NOT_FOUND


async def test_delete_session_rpc_cross_tenant_not_found_row_survives(
    servicer: AgentServicer, db_session: Session, mock_request_context: MagicMock
) -> None:
    """Another tenant's delete is indistinguishable from not-found and mutates nothing."""
    session_b = _make_session(db_session, tenant_id=uuid4())

    with pytest.raises(ConnectError) as exc_info:
        await servicer.delete_session(_delete_request(uuid4(), session_b.id), mock_request_context)

    assert exc_info.value.code == Code.NOT_FOUND
    assert (
        db_session.scalar(select(AgentSession).where(AgentSession.id == session_b.id)) is not None
    )
