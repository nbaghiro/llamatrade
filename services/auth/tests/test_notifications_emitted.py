"""Auth security events land on the notification stream.

Mirrors strategy's test_notifications_emitted: publish through the
FakeTransport-backed shared stream, decode envelopes, and assert category,
identity, link, and deterministic dedup id for every ``_notify_security`` /
``_notify_lockout`` site.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_db.models.auth import AuthToken, User
from llamatrade_events.idempotency import derive_event_id
from llamatrade_proto.generated import auth_pb2, events_pb2
from tests.fakes import (
    FakeRateLimiter,
    MockAsyncSession,
    MockRequestContext,
    MockUser,
    create_test_token,
    published_envelopes,
    published_notifications,
)

from src.services.tokens import PURPOSE_PASSWORD_RESET

if TYPE_CHECKING:
    from src.grpc.servicer import AuthServicer

_E = events_pb2

# Set test environment before importing servicer
os.environ["JWT_SECRET"] = "test-secret"
os.environ["JWT_ALGORITHM"] = "HS256"


@pytest.fixture
def mock_db() -> MockAsyncSession:
    return MockAsyncSession()


@pytest.fixture
def servicer(mock_db: MockAsyncSession) -> AuthServicer:
    from src.grpc.servicer import AuthServicer

    instance = AuthServicer()

    async def mock_get_db() -> MockAsyncSession:
        return mock_db

    instance._get_db = mock_get_db
    instance._rate_limiter = None
    instance._revocation = None
    return instance


def _auth_context(user: MockUser) -> MockRequestContext:
    token = create_test_token(str(user.id), str(user.tenant_id))
    return MockRequestContext(headers={"authorization": f"Bearer {token}"})


def _ids_over_window(
    category: int, tenant_id: object, user_id: object, part: str, before: int, after: int
) -> set[str]:
    """Every dedup id derivable from a second-resolution timestamp part in [before, after]."""
    return {
        derive_event_id(str(category), str(tenant_id), str(user_id), part, str(ts))
        for ts in range(before, after + 1)
    }


async def test_change_password_emits_password_changed(
    servicer: AuthServicer, mock_db: MockAsyncSession
) -> None:
    user = MockUser(password="OldPass123!")
    mock_db._query_result = user

    before = int(datetime.now(UTC).timestamp())
    await servicer.change_password(
        auth_pb2.ChangePasswordRequest(current_password="OldPass123!", new_password="NewPass456!"),
        _auth_context(user),
    )
    after = int(datetime.now(UTC).timestamp())

    events = published_notifications()
    envelopes = published_envelopes()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_PASSWORD_CHANGED]
    assert envelopes[0].tenant_id == str(user.tenant_id)
    assert envelopes[0].user_id == str(user.id)
    assert envelopes[0].id in _ids_over_window(
        _E.NOTIFICATION_CATEGORY_PASSWORD_CHANGED,
        user.tenant_id,
        user.id,
        "pwchange",
        before,
        after,
    )


async def test_login_lockout_emits_account_locked(
    servicer: AuthServicer, mock_db: MockAsyncSession
) -> None:
    servicer._rate_limiter = FakeRateLimiter(allowed=False)
    user = MockUser(email="victim@example.com")
    mock_db.queue_result(User, user)

    hour_before = datetime.now(UTC).strftime("%Y%m%d%H")
    with pytest.raises(ConnectError) as exc_info:
        await servicer.login(
            auth_pb2.LoginRequest(email=user.email, password="x"), MockRequestContext()
        )
    hour_after = datetime.now(UTC).strftime("%Y%m%d%H")

    assert exc_info.value.code == Code.RESOURCE_EXHAUSTED
    events = published_notifications()
    envelopes = published_envelopes()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_ACCOUNT_LOCKED]
    assert envelopes[0].user_id == str(user.id)
    assert envelopes[0].id in {
        derive_event_id(
            str(_E.NOTIFICATION_CATEGORY_ACCOUNT_LOCKED),
            str(user.tenant_id),
            str(user.id),
            "lockout",
            hour,
        )
        for hour in {hour_before, hour_after}
    }


async def test_lockout_same_hour_collapses_to_one_dedup_id(
    servicer: AuthServicer, mock_db: MockAsyncSession
) -> None:
    servicer._rate_limiter = FakeRateLimiter(allowed=False)
    user = MockUser(email="victim@example.com")
    mock_db.queue_result(User, user)
    mock_db.queue_result(User, user)
    request = auth_pb2.LoginRequest(email=user.email, password="x")

    for _ in range(2):
        with pytest.raises(ConnectError):
            await servicer.login(request, MockRequestContext())

    envelopes = published_envelopes()
    assert len(envelopes) == 2
    assert len({env.id for env in envelopes}) == 1


async def test_lockout_for_unknown_email_emits_nothing(
    servicer: AuthServicer, mock_db: MockAsyncSession
) -> None:
    servicer._rate_limiter = FakeRateLimiter(allowed=False)
    mock_db.queue_result(User, None)

    with pytest.raises(ConnectError):
        await servicer.login(
            auth_pb2.LoginRequest(email="ghost@example.com", password="x"), MockRequestContext()
        )

    assert published_notifications() == []


async def test_lockout_db_failure_is_swallowed(servicer: AuthServicer) -> None:
    """A DB outage cannot turn the lockout notify into a new failure mode."""
    servicer._rate_limiter = FakeRateLimiter(allowed=False)

    async def broken_get_db() -> MockAsyncSession:
        raise RuntimeError("db down")

    servicer._get_db = broken_get_db

    with pytest.raises(ConnectError) as exc_info:
        await servicer.login(
            auth_pb2.LoginRequest(email="victim@example.com", password="x"), MockRequestContext()
        )

    assert exc_info.value.code == Code.RESOURCE_EXHAUSTED
    assert published_notifications() == []


@pytest.mark.usefixtures("accept_any_invite")
async def test_register_emits_welcome_then_verification_link(
    servicer: AuthServicer, mock_db: MockAsyncSession
) -> None:
    await servicer.register(
        auth_pb2.RegisterRequest(
            tenant_name="Acme", email="new@example.com", password="SecurePass123"
        ),
        MockRequestContext(),
    )

    events = published_notifications()
    envelopes = published_envelopes()
    assert [e.category for e in events] == [
        _E.NOTIFICATION_CATEGORY_WELCOME,
        _E.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION,
    ]
    user = next(o for o in mock_db.added if isinstance(o, User))
    assert envelopes[0].id == derive_event_id(
        str(_E.NOTIFICATION_CATEGORY_WELCOME), str(user.tenant_id), str(user.id), "welcome"
    )
    link = events[1].extra["link"]
    assert "/verify-email?token=" in link
    token = link.split("token=", 1)[1]
    assert envelopes[1].id == derive_event_id(
        str(_E.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION),
        str(user.tenant_id),
        str(user.id),
        "verify",
        token[:8],
    )


async def test_request_password_reset_emits_reset_link(
    servicer: AuthServicer, mock_db: MockAsyncSession
) -> None:
    user = MockUser(email="resetme@example.com")
    mock_db.queue_result(User, user)

    await servicer.request_password_reset(
        auth_pb2.RequestPasswordResetRequest(email=user.email), MockRequestContext()
    )

    events = published_notifications()
    envelopes = published_envelopes()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_PASSWORD_RESET]
    assert envelopes[0].user_id == str(user.id)
    link = events[0].extra["link"]
    assert "/reset-password?token=" in link
    token = link.split("token=", 1)[1]
    assert envelopes[0].id == derive_event_id(
        str(_E.NOTIFICATION_CATEGORY_PASSWORD_RESET),
        str(user.tenant_id),
        str(user.id),
        "reset",
        token[:8],
    )


async def test_reset_password_emits_password_changed(
    servicer: AuthServicer, mock_db: MockAsyncSession
) -> None:
    user = MockUser()
    row = AuthToken(
        tenant_id=user.tenant_id,
        user_id=user.id,
        token_hash="irrelevant",
        purpose=PURPOSE_PASSWORD_RESET,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    mock_db.queue_result(AuthToken, row)
    mock_db.queue_result(User, user)

    before = int(datetime.now(UTC).timestamp())
    await servicer.reset_password(
        auth_pb2.ResetPasswordRequest(token="whatever", new_password="NewPass456!"),
        MockRequestContext(),
    )
    after = int(datetime.now(UTC).timestamp())

    events = published_notifications()
    envelopes = published_envelopes()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_PASSWORD_CHANGED]
    assert envelopes[0].id in _ids_over_window(
        _E.NOTIFICATION_CATEGORY_PASSWORD_CHANGED, user.tenant_id, user.id, "pwreset", before, after
    )


async def test_resend_verification_emits_verification_link(
    servicer: AuthServicer, mock_db: MockAsyncSession
) -> None:
    user = MockUser(email="unverified@example.com", is_verified=False)
    mock_db.queue_result(User, user)

    await servicer.resend_verification(
        auth_pb2.ResendVerificationRequest(email=user.email), MockRequestContext()
    )

    events = published_notifications()
    envelopes = published_envelopes()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION]
    link = events[0].extra["link"]
    assert "/verify-email?token=" in link
    token = link.split("token=", 1)[1]
    assert envelopes[0].id == derive_event_id(
        str(_E.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION),
        str(user.tenant_id),
        str(user.id),
        "verify",
        token[:8],
    )


async def test_resend_verification_for_verified_user_emits_nothing(
    servicer: AuthServicer, mock_db: MockAsyncSession
) -> None:
    user = MockUser(email="done@example.com", is_verified=True)
    mock_db.queue_result(User, user)

    response = await servicer.resend_verification(
        auth_pb2.ResendVerificationRequest(email=user.email), MockRequestContext()
    )

    assert response.success is True
    assert published_notifications() == []
