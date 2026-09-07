"""The confirm lock must serialize two confirmations of one tool proposal.

``lock_message_with_proposal`` matches a proposal by JSONB containment and takes
``FOR UPDATE``, which is the only thing standing between a double-clicked confirm
and a tool executing twice (for the backtest tool that is wasted work; for any
future write tool it would be a duplicate action). Neither the containment
operator nor the lock exists on SQLite, and the unit test only asserts the
compiled SQL string, so this drives both against real Postgres.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from llamatrade_db.base import Base
from llamatrade_db.models.agent import AgentMessage, AgentSession
from llamatrade_proto.generated.agent_pb2 import (
    AGENT_SESSION_STATUS_ACTIVE,
    MESSAGE_ROLE_ASSISTANT,
)

from src.services.conversation_service import ConversationService

_REQUIRE_DOCKER = os.environ.get("CI_REQUIRE_DOCKER") == "1"

if _REQUIRE_DOCKER:
    from testcontainers.postgres import PostgresContainer
else:
    PostgresContainer = pytest.importorskip("testcontainers.postgres").PostgresContainer


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


_docker_up = _docker_available()
if _REQUIRE_DOCKER and not _docker_up:
    pytest.fail("CI_REQUIRE_DOCKER=1: Docker is required but unavailable", pytrace=False)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _docker_up, reason="Docker not available for testcontainers"),
]

_TABLES = [AgentSession.__table__, AgentMessage.__table__]
CONFIRMATION_ID = "toolu_confirm_1"


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    with PostgresContainer(
        image="postgres:16-alpine",
        username="postgres",
        password="postgres",
        dbname="agent_confirm",
        driver="asyncpg",
    ) as pg:
        yield pg.get_connection_url().replace("psycopg2", "asyncpg")


@pytest.fixture(scope="module")
def schema(pg_url: str) -> str:
    async def _create() -> None:
        engine = create_async_engine(pg_url)
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, tables=_TABLES, checkfirst=True)
            )
        await engine.dispose()

    asyncio.run(_create())
    return pg_url


@pytest_asyncio.fixture
async def maker(schema: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(schema, poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed_proposal(
    maker: async_sessionmaker[AsyncSession], tenant_id: UUID, confirmation_id: str
) -> UUID:
    """An assistant message carrying one pending tool proposal."""
    async with maker() as db:
        session = AgentSession(
            tenant_id=tenant_id,
            user_id=uuid4(),
            status=AGENT_SESSION_STATUS_ACTIVE,
            last_activity_at=datetime.now(UTC),
        )
        db.add(session)
        await db.flush()
        db.add(
            AgentMessage(
                tenant_id=tenant_id,
                session_id=session.id,
                role=MESSAGE_ROLE_ASSISTANT,
                content="Shall I run that backtest?",
                tool_calls_json=[
                    {"id": confirmation_id, "name": "run_backtest", "status": "pending"}
                ],
            )
        )
        await db.commit()
        return session.id


class TestProposalLookup:
    async def test_containment_match_finds_the_proposal(
        self, maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """The JSONB @> operator only runs on Postgres, so this is its first real proof."""
        tenant_id = uuid4()
        session_id = await _seed_proposal(maker, tenant_id, CONFIRMATION_ID)

        async with maker() as db:
            found = await ConversationService(db).lock_message_with_proposal(
                session_id, CONFIRMATION_ID
            )

        assert found is not None
        assert found.tool_calls_json is not None
        assert found.tool_calls_json[0]["id"] == CONFIRMATION_ID

    async def test_unknown_confirmation_id_finds_nothing(
        self, maker: async_sessionmaker[AsyncSession]
    ) -> None:
        tenant_id = uuid4()
        session_id = await _seed_proposal(maker, tenant_id, CONFIRMATION_ID)

        async with maker() as db:
            assert (
                await ConversationService(db).lock_message_with_proposal(
                    session_id, "toolu_never_issued"
                )
            ) is None

    async def test_a_prefix_of_the_id_does_not_match(
        self, maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Containment matches the whole value, not a substring."""
        tenant_id = uuid4()
        session_id = await _seed_proposal(maker, tenant_id, CONFIRMATION_ID)

        async with maker() as db:
            assert (
                await ConversationService(db).lock_message_with_proposal(
                    session_id, CONFIRMATION_ID[:-1]
                )
            ) is None


class TestConcurrentConfirms:
    async def test_second_confirm_blocks_until_the_first_commits(
        self, maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """The row lock is what makes a double-clicked confirm safe.

        The first holder marks the proposal consumed and commits; the second must
        wait on the lock and then observe the consumed status rather than
        executing the tool again.
        """
        tenant_id = uuid4()
        session_id = await _seed_proposal(maker, tenant_id, CONFIRMATION_ID)
        first_locked = asyncio.Event()
        release = asyncio.Event()
        observed: list[str] = []

        async def winner() -> None:
            async with maker() as db:
                message = await ConversationService(db).lock_message_with_proposal(
                    session_id, CONFIRMATION_ID
                )
                assert message is not None
                first_locked.set()
                await release.wait()
                calls = list(message.tool_calls_json or [])
                calls[0] = {**calls[0], "status": "consumed"}
                message.tool_calls_json = calls
                await db.commit()

        async def loser() -> None:
            await first_locked.wait()
            async with maker() as db:
                # Blocks here until the winner commits, then sees the new status.
                release.set()
                message = await ConversationService(db).lock_message_with_proposal(
                    session_id, CONFIRMATION_ID
                )
                assert message is not None
                observed.append((message.tool_calls_json or [{}])[0].get("status", ""))
                await db.commit()

        await asyncio.wait_for(asyncio.gather(winner(), loser()), timeout=30)

        assert observed == ["consumed"], "the second confirm must see the consumed proposal"

    async def test_the_lock_is_scoped_to_the_session(
        self, maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Another session's identical confirmation id is a different row."""
        tenant_id = uuid4()
        mine = await _seed_proposal(maker, tenant_id, CONFIRMATION_ID)
        theirs = await _seed_proposal(maker, tenant_id, CONFIRMATION_ID)

        async with maker() as db:
            service = ConversationService(db)
            a = await service.lock_message_with_proposal(mine, CONFIRMATION_ID)
            b = await service.lock_message_with_proposal(theirs, CONFIRMATION_ID)

        assert a is not None and b is not None
        assert a.id != b.id
        assert a.session_id == mine and b.session_id == theirs
