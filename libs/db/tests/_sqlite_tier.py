"""Shared plumbing for the real-SQL-on-SQLite test tier.

Suites on this tier run a helper's real SQL against a real (SQLite) schema
rather than mocks, so a dropped tenant filter or a wrong predicate fails. Two
adaptations make that work: JSONB needs a SQLite rendering, and the helpers are
async while SQLite has no async driver installed, so a thin facade forwards the
awaited calls to a synchronous session.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import Executable
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Result
from sqlalchemy.engine.result import ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.sql.compiler import GenericTypeCompiler

_jsonb_registered = False


def install_sqlite_jsonb() -> None:
    """Render JSONB as JSON on SQLite (idempotent, process-global registration)."""
    global _jsonb_registered
    if _jsonb_registered:
        return

    @compiles(JSONB, "sqlite")
    def _render_jsonb_on_sqlite(type_: JSONB, compiler: GenericTypeCompiler, **kw: object) -> str:
        return "JSON"

    _jsonb_registered = True


install_sqlite_jsonb()


class SyncSessionAdapter:
    """Awaitable facade over a synchronous Session (SQLite has no async driver here)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, statement: Executable) -> Result[tuple[object, ...]]:
        return self._session.execute(statement)

    async def scalars(self, statement: Executable) -> ScalarResult[object]:
        return self._session.scalars(statement)

    async def scalar(self, statement: Executable) -> object | None:
        return self._session.scalar(statement)


def as_async_session(session: Session) -> AsyncSession:
    """Type the adapter as AsyncSession at the seam (one cast, not per line)."""
    return cast(AsyncSession, SyncSessionAdapter(session))
