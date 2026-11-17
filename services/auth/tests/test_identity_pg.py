"""Identity flows over real Postgres (enforcing RLS role, see conftest).

Covers what mocks cannot: the duplicate-email unique index firing at the DB,
register's multi-commit flow under RLS enforcement, the last_login write, the
API-key prefix lookup with last_used_at persistence, and the FOR UPDATE
single-winner semantics of reset-token redemption under real concurrency.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import bcrypt
import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from llamatrade_db import system_session
from llamatrade_db.models.auth import APIKey, AuthToken, Tenant, User
from llamatrade_proto.generated import auth_pb2
from tests.conftest import NewInvite
from tests.fakes import MockRequestContext

from src.services.tokens import PURPOSE_PASSWORD_RESET, consume_token, issue_token

if TYPE_CHECKING:
    from src.grpc.servicer import AuthServicer

PASSWORD = "Sup3rSecret!"
API_KEY = "ltak_1234_secretpart_5678"


@pytest.fixture
def servicer(session_factory: async_sessionmaker) -> AuthServicer:
    """Servicer on the real ``_get_db`` path (RLS bypass included) over test PG."""
    from src.grpc.servicer import AuthServicer

    instance = AuthServicer()
    instance._session_maker = session_factory
    instance._rate_limiter = None
    instance._revocation = None
    return instance


async def _seed_tenant_user(
    session_factory: async_sessionmaker, *, email: str = "user@example.com"
) -> tuple[UUID, UUID]:
    tenant_id, user_id = uuid4(), uuid4()
    async with system_session(session_factory) as db:
        db.add(Tenant(id=tenant_id, name="t", slug=f"t-{tenant_id.hex[:8]}"))
        db.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                email=email,
                password_hash=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
                is_active=True,
            )
        )
        await db.commit()
    return tenant_id, user_id


# ===================
# Register / duplicate email
# ===================


async def test_register_survives_multiple_commits_under_rls(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    """Register commits twice (user+tenant, then the verify token); both writes
    must land with the session's RLS system scope intact."""
    response = await servicer.register(
        auth_pb2.RegisterRequest(
            tenant_name="Acme",
            email="new@example.com",
            password="SecurePass123",
            invite_code=await new_invite(),
        ),
        MockRequestContext(),
    )

    assert response.user.email == "new@example.com"
    async with system_session(session_factory) as db:
        tokens = (await db.execute(select(AuthToken))).scalars().all()
        users = (await db.execute(select(User))).scalars().all()
    assert [t.user_id for t in tokens] == [UUID(response.user.id)]
    assert [u.email for u in users] == ["new@example.com"]


async def test_register_duplicate_email_is_already_exists(
    servicer: AuthServicer, session_factory: async_sessionmaker, new_invite: NewInvite
) -> None:
    def request(code: str) -> auth_pb2.RegisterRequest:
        return auth_pb2.RegisterRequest(
            tenant_name="Acme", email="dup@example.com", password="SecurePass123", invite_code=code
        )

    await servicer.register(request(await new_invite()), MockRequestContext())

    with pytest.raises(ConnectError) as exc_info:
        await servicer.register(request(await new_invite()), MockRequestContext())

    assert exc_info.value.code == Code.ALREADY_EXISTS


async def test_duplicate_email_in_tenant_rejected_by_the_database(
    session_factory: async_sessionmaker,
) -> None:
    """The (tenant_id, email) unique index holds even when the pre-check is
    bypassed, so a race cannot create two accounts in one tenant."""
    tenant_id, _ = await _seed_tenant_user(session_factory, email="taken@example.com")

    with pytest.raises(IntegrityError):
        async with system_session(session_factory) as db:
            db.add(
                User(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    email="taken@example.com",
                    password_hash="x",
                    is_active=True,
                )
            )
            await db.commit()


# ===================
# Login
# ===================


async def test_login_persists_last_login(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    _, user_id = await _seed_tenant_user(session_factory, email="login@example.com")

    response = await servicer.login(
        auth_pb2.LoginRequest(email="login@example.com", password=PASSWORD),
        MockRequestContext(),
    )

    assert response.access_token
    async with system_session(session_factory) as db:
        stored = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    assert stored.last_login is not None


# ===================
# API-key lookup
# ===================


async def _seed_api_key(
    session_factory: async_sessionmaker, *, is_active: bool = True
) -> tuple[UUID, UUID]:
    tenant_id, user_id = await _seed_tenant_user(
        session_factory, email=f"{uuid4().hex[:8]}@example.com"
    )
    async with system_session(session_factory) as db:
        db.add(
            APIKey(
                tenant_id=tenant_id,
                user_id=user_id,
                name="CI key",
                key_prefix=API_KEY[:8],
                key_hash=hashlib.sha256(API_KEY.encode()).hexdigest(),
                scopes=["read"],
                is_active=is_active,
            )
        )
        await db.commit()
    return tenant_id, user_id


async def test_validate_api_key_lookup_and_last_used_persistence(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    tenant_id, user_id = await _seed_api_key(session_factory)

    response = await servicer.validate_a_p_i_key(
        auth_pb2.ValidateAPIKeyRequest(api_key=API_KEY, required_scopes=["read"]),
        MockRequestContext(),
    )

    assert response.valid is True
    assert response.context.tenant_id == str(tenant_id)
    assert response.context.user_id == str(user_id)
    async with system_session(session_factory) as db:
        stored = (await db.execute(select(APIKey))).scalar_one()
    assert stored.last_used_at is not None


async def test_validate_api_key_inactive_row_not_matched(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    """The is_active filter runs in SQL: a deactivated key never validates."""
    await _seed_api_key(session_factory, is_active=False)

    response = await servicer.validate_a_p_i_key(
        auth_pb2.ValidateAPIKeyRequest(api_key=API_KEY), MockRequestContext()
    )

    assert response.valid is False


# ===================
# Concurrent token redemption
# ===================


async def test_concurrent_reset_redemption_has_exactly_one_winner(
    session_factory: async_sessionmaker,
) -> None:
    """Two coroutines race consume of one reset token on separate connections;
    the FOR UPDATE row lock lets exactly one redeem it."""
    tenant_id, user_id = await _seed_tenant_user(session_factory, email="race@example.com")
    async with system_session(session_factory) as db:
        issued = await issue_token(
            db, tenant_id=tenant_id, user_id=user_id, purpose=PURPOSE_PASSWORD_RESET
        )
        await db.commit()

    async def redeem() -> bool:
        async with system_session(session_factory) as db:
            row = await consume_token(db, token=issued.token, purpose=PURPOSE_PASSWORD_RESET)
            await db.commit()
            return row is not None

    results = await asyncio.gather(redeem(), redeem())

    assert sorted(results) == [False, True]
