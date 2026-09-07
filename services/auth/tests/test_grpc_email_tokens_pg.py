"""Email-token RPCs driven through the servicer over real Postgres.

The tokens layer has its own PG suite (test_auth_tokens_pg); these tests
exercise the four Connect RPCs end to end: uniform no-account-existence-leak
responses, single-use/expired token rejection, revoke-all-sessions on reset,
and the links carried by the emitted notifications.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import bcrypt
import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from llamatrade_db import system_session
from llamatrade_db.models.auth import AuthToken, Tenant, User
from llamatrade_proto.generated import auth_pb2, events_pb2
from tests.fakes import FakeRevocationStore, MockRequestContext, published_notifications

from src.services.tokens import PURPOSE_EMAIL_VERIFY, PURPOSE_PASSWORD_RESET, issue_token

if TYPE_CHECKING:
    from src.grpc.servicer import AuthServicer

OLD_PASSWORD = "OldSecret123"
NEW_PASSWORD = "NewSecret456"


@pytest.fixture
def revocation() -> FakeRevocationStore:
    return FakeRevocationStore()


@pytest.fixture
def servicer(session_factory: async_sessionmaker, revocation: FakeRevocationStore) -> AuthServicer:
    """Servicer on the real ``_get_db`` path (RLS bypass included) over test PG."""
    from src.grpc.servicer import AuthServicer

    instance = AuthServicer()
    instance._session_maker = session_factory
    instance._rate_limiter = None
    instance._revocation = revocation
    return instance


async def _seed_user(
    session_factory: async_sessionmaker,
    *,
    email: str = "resetme@example.com",
    is_active: bool = True,
    is_verified: bool = False,
) -> User:
    tenant_id, user_id = uuid4(), uuid4()
    async with system_session(session_factory) as db:
        db.add(Tenant(id=tenant_id, name="t", slug=f"t-{tenant_id.hex[:8]}"))
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email=email,
            password_hash=bcrypt.hashpw(OLD_PASSWORD.encode(), bcrypt.gensalt()).decode(),
            is_active=is_active,
            is_verified=is_verified,
        )
        db.add(user)
        await db.commit()
    return user


async def _issue(session_factory: async_sessionmaker, user: User, purpose: str) -> str:
    async with system_session(session_factory) as db:
        issued = await issue_token(db, tenant_id=user.tenant_id, user_id=user.id, purpose=purpose)
        await db.commit()
    return issued.token


async def _expire_all_tokens(session_factory: async_sessionmaker) -> None:
    async with system_session(session_factory) as db:
        rows = await db.execute(select(AuthToken))
        for row in rows.scalars():
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()


async def _token_rows(session_factory: async_sessionmaker) -> list[AuthToken]:
    async with system_session(session_factory) as db:
        result = await db.execute(select(AuthToken))
        return list(result.scalars().all())


async def _load_user(session_factory: async_sessionmaker, user_id: UUID) -> User:
    async with system_session(session_factory) as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        assert user is not None
        return user


def _link_token(link: str) -> str:
    assert "token=" in link
    return link.split("token=", 1)[1]


# ===================
# RequestPasswordReset
# ===================


async def test_request_password_reset_issues_token_and_link(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    user = await _seed_user(session_factory)

    response = await servicer.request_password_reset(
        auth_pb2.RequestPasswordResetRequest(email=user.email), MockRequestContext()
    )

    assert response.success is True
    rows = await _token_rows(session_factory)
    assert [(r.purpose, r.used_at, r.user_id) for r in rows] == [
        (PURPOSE_PASSWORD_RESET, None, user.id)
    ]
    events = published_notifications()
    assert [e.category for e in events] == [events_pb2.NOTIFICATION_CATEGORY_PASSWORD_RESET]
    assert "/reset-password?token=" in events[0].extra["link"]


async def test_request_password_reset_does_not_leak_account_existence(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    """Known and unknown emails get byte-identical responses; only the known
    email produces a token and an emission."""
    user = await _seed_user(session_factory)

    known = await servicer.request_password_reset(
        auth_pb2.RequestPasswordResetRequest(email=user.email), MockRequestContext()
    )
    unknown = await servicer.request_password_reset(
        auth_pb2.RequestPasswordResetRequest(email="ghost@example.com"), MockRequestContext()
    )

    assert unknown == known
    rows = await _token_rows(session_factory)
    assert [r.user_id for r in rows] == [user.id]
    assert len(published_notifications()) == 1


async def test_request_password_reset_inactive_user_uniform_and_silent(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    user = await _seed_user(session_factory, is_active=False)

    response = await servicer.request_password_reset(
        auth_pb2.RequestPasswordResetRequest(email=user.email), MockRequestContext()
    )

    assert response.success is True
    assert await _token_rows(session_factory) == []
    assert published_notifications() == []


# ===================
# ResetPassword
# ===================


async def test_reset_password_end_to_end(
    servicer: AuthServicer,
    session_factory: async_sessionmaker,
    revocation: FakeRevocationStore,
) -> None:
    """The emitted link's token resets the password, kills every session, and
    consumes the token."""
    user = await _seed_user(session_factory)
    await servicer.request_password_reset(
        auth_pb2.RequestPasswordResetRequest(email=user.email), MockRequestContext()
    )
    token = _link_token(published_notifications()[0].extra["link"])

    response = await servicer.reset_password(
        auth_pb2.ResetPasswordRequest(token=token, new_password=NEW_PASSWORD),
        MockRequestContext(),
    )

    assert response.success is True
    stored = await _load_user(session_factory, user.id)
    assert bcrypt.checkpw(NEW_PASSWORD.encode(), stored.password_hash.encode())
    assert str(user.id) in revocation.user_cutoffs
    assert all(r.used_at is not None for r in await _token_rows(session_factory))
    assert [e.category for e in published_notifications()] == [
        events_pb2.NOTIFICATION_CATEGORY_PASSWORD_RESET,
        events_pb2.NOTIFICATION_CATEGORY_PASSWORD_CHANGED,
    ]


async def test_reset_password_token_is_single_use(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    user = await _seed_user(session_factory)
    token = await _issue(session_factory, user, PURPOSE_PASSWORD_RESET)
    request = auth_pb2.ResetPasswordRequest(token=token, new_password=NEW_PASSWORD)

    await servicer.reset_password(request, MockRequestContext())
    with pytest.raises(ConnectError) as exc_info:
        await servicer.reset_password(request, MockRequestContext())

    assert exc_info.value.code == Code.INVALID_ARGUMENT


async def test_reset_password_expired_token_rejected(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    user = await _seed_user(session_factory)
    token = await _issue(session_factory, user, PURPOSE_PASSWORD_RESET)
    await _expire_all_tokens(session_factory)

    with pytest.raises(ConnectError) as exc_info:
        await servicer.reset_password(
            auth_pb2.ResetPasswordRequest(token=token, new_password=NEW_PASSWORD),
            MockRequestContext(),
        )

    assert exc_info.value.code == Code.INVALID_ARGUMENT
    stored = await _load_user(session_factory, user.id)
    assert bcrypt.checkpw(OLD_PASSWORD.encode(), stored.password_hash.encode())


async def test_reset_password_unknown_token_rejected(servicer: AuthServicer) -> None:
    with pytest.raises(ConnectError) as exc_info:
        await servicer.reset_password(
            auth_pb2.ResetPasswordRequest(token="not-a-real-token", new_password=NEW_PASSWORD),
            MockRequestContext(),
        )

    assert exc_info.value.code == Code.INVALID_ARGUMENT


async def test_reset_password_weak_password_leaves_token_unconsumed(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    """The strength check runs before consumption, so the link survives a typo."""
    user = await _seed_user(session_factory)
    token = await _issue(session_factory, user, PURPOSE_PASSWORD_RESET)

    with pytest.raises(ConnectError) as exc_info:
        await servicer.reset_password(
            auth_pb2.ResetPasswordRequest(token=token, new_password="short"),
            MockRequestContext(),
        )
    assert exc_info.value.code == Code.INVALID_ARGUMENT

    response = await servicer.reset_password(
        auth_pb2.ResetPasswordRequest(token=token, new_password=NEW_PASSWORD),
        MockRequestContext(),
    )
    assert response.success is True


async def test_reset_password_inactive_user_rejected(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    user = await _seed_user(session_factory, is_active=False)
    token = await _issue(session_factory, user, PURPOSE_PASSWORD_RESET)

    with pytest.raises(ConnectError) as exc_info:
        await servicer.reset_password(
            auth_pb2.ResetPasswordRequest(token=token, new_password=NEW_PASSWORD),
            MockRequestContext(),
        )

    assert exc_info.value.code == Code.INVALID_ARGUMENT


# ===================
# VerifyEmail
# ===================


async def test_verify_email_marks_user_verified(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    user = await _seed_user(session_factory, is_verified=False)
    token = await _issue(session_factory, user, PURPOSE_EMAIL_VERIFY)

    response = await servicer.verify_email(
        auth_pb2.VerifyEmailRequest(token=token), MockRequestContext()
    )

    assert response.success is True
    stored = await _load_user(session_factory, user.id)
    assert stored.is_verified is True


async def test_verify_email_token_is_single_use(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    user = await _seed_user(session_factory)
    token = await _issue(session_factory, user, PURPOSE_EMAIL_VERIFY)
    request = auth_pb2.VerifyEmailRequest(token=token)

    await servicer.verify_email(request, MockRequestContext())
    with pytest.raises(ConnectError) as exc_info:
        await servicer.verify_email(request, MockRequestContext())

    assert exc_info.value.code == Code.INVALID_ARGUMENT


async def test_verify_email_rejects_reset_token(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    """Purpose scoping: a password-reset token cannot verify an email."""
    user = await _seed_user(session_factory, is_verified=False)
    token = await _issue(session_factory, user, PURPOSE_PASSWORD_RESET)

    with pytest.raises(ConnectError) as exc_info:
        await servicer.verify_email(auth_pb2.VerifyEmailRequest(token=token), MockRequestContext())

    assert exc_info.value.code == Code.INVALID_ARGUMENT
    stored = await _load_user(session_factory, user.id)
    assert stored.is_verified is False


async def test_verify_email_expired_token_rejected(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    user = await _seed_user(session_factory, is_verified=False)
    token = await _issue(session_factory, user, PURPOSE_EMAIL_VERIFY)
    await _expire_all_tokens(session_factory)

    with pytest.raises(ConnectError) as exc_info:
        await servicer.verify_email(auth_pb2.VerifyEmailRequest(token=token), MockRequestContext())

    assert exc_info.value.code == Code.INVALID_ARGUMENT
    stored = await _load_user(session_factory, user.id)
    assert stored.is_verified is False


# ===================
# ResendVerification
# ===================


async def test_resend_verification_issues_working_link(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    user = await _seed_user(session_factory, is_verified=False)

    response = await servicer.resend_verification(
        auth_pb2.ResendVerificationRequest(email=user.email), MockRequestContext()
    )

    assert response.success is True
    events = published_notifications()
    assert [e.category for e in events] == [events_pb2.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION]
    link = events[0].extra["link"]
    assert "/verify-email?token=" in link

    await servicer.verify_email(
        auth_pb2.VerifyEmailRequest(token=_link_token(link)), MockRequestContext()
    )
    stored = await _load_user(session_factory, user.id)
    assert stored.is_verified is True


async def test_resend_verification_uniform_across_account_states(
    servicer: AuthServicer, session_factory: async_sessionmaker
) -> None:
    """Verified, inactive, and unknown accounts all get the identical response
    with no token issued and no emission."""
    verified = await _seed_user(session_factory, email="done@example.com", is_verified=True)
    inactive = await _seed_user(session_factory, email="gone@example.com", is_active=False)

    responses = [
        await servicer.resend_verification(
            auth_pb2.ResendVerificationRequest(email=email), MockRequestContext()
        )
        for email in (verified.email, inactive.email, "ghost@example.com")
    ]

    assert responses[0] == responses[1] == responses[2]
    assert responses[0].success is True
    assert await _token_rows(session_factory) == []
    assert published_notifications() == []
