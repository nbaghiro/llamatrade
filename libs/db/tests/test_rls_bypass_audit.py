"""RLS-bypass audit trail: one log line + one counter increment per use.

The sessions here never reach a database: ``AsyncSession.execute`` is stubbed, so
the tests exercise the audit path of ``set_rls_bypass`` / ``system_session``
without Postgres.
"""

import logging
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import llamatrade_db.session as session_module
from llamatrade_db.rls import BYPASS_GUC
from llamatrade_db.session import (
    bind_tenant_guc,
    set_rls_bypass,
    system_session,
    tenant_session,
)

AUDIT_LOGGER = "llamatrade_db.session"


@pytest_asyncio.fixture
async def maker(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """Session factory whose sessions issue no SQL (execute is stubbed)."""
    monkeypatch.setattr(AsyncSession, "execute", AsyncMock())
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none", poolclass=NullPool)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def bypass_counter(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Spy replacing the telemetry counter the session module increments."""
    counter = MagicMock()
    monkeypatch.setattr(session_module, "DB_RLS_BYPASS", counter)
    return counter


def _audit_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "audit_event", None) == "rls_bypass"]


class TestSystemSessionAudit:
    async def test_logs_caller_reason_and_counts(
        self,
        maker: async_sessionmaker[AsyncSession],
        bypass_counter: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            async with system_session(maker, reason="equity snapshot sweep") as db:
                assert isinstance(db, AsyncSession)

        record = _audit_records(caplog)[0]
        assert record.operation == "system_session"
        assert record.reason == "equity snapshot sweep"
        assert record.caller.endswith("test_logs_caller_reason_and_counts")
        assert record.caller.startswith(__name__)
        assert record.tenant_scope is None

        bypass_counter.labels.assert_called_once_with(operation="system_session")
        bypass_counter.labels.return_value.inc.assert_called_once_with()

    async def test_audits_exactly_once_per_use(
        self,
        maker: async_sessionmaker[AsyncSession],
        bypass_counter: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The inner bypass statement must not double-count the outer entry point."""
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            async with system_session(maker):
                pass

        assert len(_audit_records(caplog)) == 1
        assert bypass_counter.labels.call_count == 1

    async def test_reason_is_optional(
        self,
        maker: async_sessionmaker[AsyncSession],
        bypass_counter: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Existing call sites pass no reason and still produce an audit line."""
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            async with system_session(maker):
                pass

        assert _audit_records(caplog)[0].reason is None

    async def test_applies_the_bypass_guc(
        self,
        maker: async_sessionmaker[AsyncSession],
        bypass_counter: MagicMock,
    ) -> None:
        """Auditing does not displace the statement it audits."""
        execute = AsyncSession.execute
        async with system_session(maker):
            pass

        assert BYPASS_GUC in str(execute.await_args.args[0])


class TestSetRlsBypassAudit:
    async def test_logs_caller_reason_and_counts(
        self,
        maker: async_sessionmaker[AsyncSession],
        bypass_counter: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            async with maker() as session:
                await set_rls_bypass(session, reason="oauth identity lookup")

        record = _audit_records(caplog)[0]
        assert record.operation == "set_rls_bypass"
        assert record.reason == "oauth identity lookup"
        assert record.caller.endswith("test_logs_caller_reason_and_counts")
        assert record.tenant_scope is None

        bypass_counter.labels.assert_called_once_with(operation="set_rls_bypass")
        bypass_counter.labels.return_value.inc.assert_called_once_with()

    async def test_records_bound_tenant_scope(
        self,
        maker: async_sessionmaker[AsyncSession],
        bypass_counter: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A bypass on a tenant-bound session names the tenant it overrides."""
        tenant = uuid4()
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            async with maker() as session:
                bind_tenant_guc(session, tenant)
                await set_rls_bypass(session)

        assert _audit_records(caplog)[0].tenant_scope == str(tenant)

    async def test_reason_is_optional(
        self,
        maker: async_sessionmaker[AsyncSession],
        bypass_counter: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            async with maker() as session:
                await set_rls_bypass(session)

        assert _audit_records(caplog)[0].reason is None


class TestTenantSessionIsNotAudited:
    async def test_no_log_and_no_counter(
        self,
        maker: async_sessionmaker[AsyncSession],
        bypass_counter: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Normal tenant work must leave the bypass audit trail untouched."""
        with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
            async with tenant_session(uuid4(), maker):
                pass

        assert _audit_records(caplog) == []
        bypass_counter.labels.assert_not_called()
