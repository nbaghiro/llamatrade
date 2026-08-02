"""Alpaca OAuth router — start URL, callback guards, exchange, complete-signup."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_db.models.auth import OAuthPendingSignup, User

from src.oauth_state import verify_state
from src.routers.oauth import (
    CompleteSignupRequest,
    ExchangeRequest,
    alpaca_oauth_authorize,
    alpaca_oauth_callback,
    alpaca_oauth_complete_signup,
    alpaca_oauth_exchange,
    alpaca_oauth_start,
)
from src.session import mint_handoff


def _req() -> Request:
    """Minimal ASGI request; the OAuth rate limiter reads only x-forwarded-for."""
    return Request({"type": "http", "headers": []})


async def test_start_requires_auth() -> None:
    with pytest.raises(HTTPException) as exc:
        await alpaca_oauth_start()
    assert exc.value.status_code == 401


async def test_start_builds_authorize_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ALPACA_OAUTH_REDIRECT_URI", "https://auth/oauth/alpaca/callback")
    monkeypatch.setenv("JWT_SECRET", "s")
    tid, uid = uuid4(), uuid4()
    reset = set_context(TenantContext(tenant_id=tid, user_id=uid))
    try:
        result = await alpaca_oauth_start()
    finally:
        reset_context(reset)

    url = result["authorizeUrl"]
    assert "client_id=cid" in url
    assert "env=paper" in url
    state = url.split("state=")[1].split("&")[0]
    verified = verify_state(state, secret="s")
    assert verified is not None
    assert verified.intent == "link"
    assert verified.tenant_id == str(tid)
    assert verified.user_id == str(uid)


async def test_start_unconfigured_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_OAUTH_CLIENT_ID", raising=False)
    tid, uid = uuid4(), uuid4()
    reset = set_context(TenantContext(tenant_id=tid, user_id=uid))
    try:
        with pytest.raises(HTTPException) as exc:
            await alpaca_oauth_start()
    finally:
        reset_context(reset)
    assert exc.value.status_code == 503


async def test_callback_error_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_APP_URL", "http://web")
    resp = await alpaca_oauth_callback(error="access_denied")
    assert resp.status_code == 302
    assert "error=access_denied" in resp.headers["location"]


async def test_callback_invalid_state_returns_400() -> None:
    with pytest.raises(HTTPException) as exc:
        await alpaca_oauth_callback(code="c", state="garbage")
    assert exc.value.status_code == 400


async def test_authorize_redirects_to_alpaca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ALPACA_OAUTH_REDIRECT_URI", "https://auth/oauth/alpaca/callback")
    resp = await alpaca_oauth_authorize(intent="auth")
    assert resp.status_code == 302
    loc = resp.headers["location"]
    assert "app.alpaca.markets/oauth/authorize" in loc
    assert "client_id=cid" in loc
    assert "env=paper" in loc


async def test_authorize_rejects_bad_intent() -> None:
    with pytest.raises(HTTPException) as exc:
        await alpaca_oauth_authorize(intent="link")
    assert exc.value.status_code == 400


async def test_exchange_rejects_bad_handoff() -> None:
    with pytest.raises(HTTPException) as exc:
        await alpaca_oauth_exchange(ExchangeRequest(handoff="garbage"), _req())
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Exchange (single-use handoff) and complete-signup (single-use ticket)
# ---------------------------------------------------------------------------


class _FakeRedis:
    """SET NX semantics for single-use consumption."""

    def __init__(self) -> None:
        self.store: dict[str, object] = {}

    async def set(self, key: str, value: object, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def incr(self, key: str) -> int:
        current = self.store.get(key, 0)
        count = (current if isinstance(current, int) else 0) + 1
        self.store[key] = count
        return count

    async def expire(self, key: str, seconds: int) -> bool:
        return True


class _ExchangeSession:
    """DB stand-in for the exchange route (user lookup + last_login commit)."""

    def __init__(self, user: User | None) -> None:
        self.user = user

    async def scalar(self, stmt: object) -> User | None:
        return self.user

    async def commit(self) -> None:
        pass

    async def close(self) -> None:
        pass


class _CompleteSignupSession:
    """DB stand-in for complete-signup: single-use DELETE..RETURNING on the ticket."""

    def __init__(self, pending: OAuthPendingSignup | None) -> None:
        self.pending = pending
        self.added: list[object] = []
        self.committed = False

    async def execute(self, stmt: object) -> MagicMock:
        result = MagicMock()
        result.scalar_one_or_none.return_value = self.pending
        self.pending = None
        return result

    async def scalar(self, stmt: object) -> None:
        return None

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def close(self) -> None:
        pass

    def add(self, obj: object) -> None:
        self.added.append(obj)


def _active_user() -> User:
    return User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="alpaca@example.com",
        password_hash="x",
        role="admin",
        is_active=True,
    )


def _pending_signup(expired: bool = False) -> OAuthPendingSignup:
    delta = timedelta(minutes=-1 if expired else 15)
    return OAuthPendingSignup(
        id=uuid4(),
        provider="alpaca",
        provider_account_id="acct-1",
        access_token_encrypted="enc",
        refresh_token_encrypted=None,
        token_expires_at=None,
        is_paper=True,
        expires_at=datetime.now(UTC) + delta,
    )


def _patched_db(session: object) -> tuple[object, object]:
    maker = MagicMock(return_value=MagicMock(return_value=session))
    return (
        patch("src.routers.oauth.get_session_maker", maker),
        patch("src.routers.oauth.set_rls_bypass", AsyncMock()),
    )


class TestExchangeSingleUse:
    async def test_replayed_handoff_rejected(self) -> None:
        user = _active_user()
        handoff = mint_handoff(str(user.id))
        redis = _FakeRedis()
        db_patch, rls_patch = _patched_db(_ExchangeSession(user))

        with (
            db_patch,
            rls_patch,
            patch("src.routers.oauth.get_redis", return_value=redis),
        ):
            first = await alpaca_oauth_exchange(ExchangeRequest(handoff=handoff), _req())
            assert first["accessToken"]

            with pytest.raises(HTTPException) as exc:
                await alpaca_oauth_exchange(ExchangeRequest(handoff=handoff), _req())

        assert exc.value.status_code == 401

    async def test_distinct_handoffs_both_accepted(self) -> None:
        user = _active_user()
        redis = _FakeRedis()
        db_patch, rls_patch = _patched_db(_ExchangeSession(user))

        with (
            db_patch,
            rls_patch,
            patch("src.routers.oauth.get_redis", return_value=redis),
        ):
            first = await alpaca_oauth_exchange(
                ExchangeRequest(handoff=mint_handoff(str(user.id))), _req()
            )
            second = await alpaca_oauth_exchange(
                ExchangeRequest(handoff=mint_handoff(str(user.id))), _req()
            )

        assert first["accessToken"] and second["accessToken"]


class TestCompleteSignupSingleUse:
    def _body(self, password: str = "SecurePass123") -> CompleteSignupRequest:
        return CompleteSignupRequest(
            ticket=str(uuid4()),
            email="new@example.com",
            password=password,
            first_name="New",
            last_name="User",
        )

    async def test_success_creates_account_and_session(self) -> None:
        session = _CompleteSignupSession(_pending_signup())
        db_patch, rls_patch = _patched_db(session)

        with db_patch, rls_patch:
            payload = await alpaca_oauth_complete_signup(self._body(), _req())

        assert payload["accessToken"]
        assert session.committed is True
        added_types = {type(obj).__name__ for obj in session.added}
        assert {"Tenant", "User", "AlpacaCredentials", "OAuthIdentity"} <= added_types

    async def test_replayed_ticket_rejected(self) -> None:
        session = _CompleteSignupSession(_pending_signup())
        db_patch, rls_patch = _patched_db(session)

        with db_patch, rls_patch:
            await alpaca_oauth_complete_signup(self._body(), _req())
            with pytest.raises(HTTPException) as exc:
                await alpaca_oauth_complete_signup(self._body(), _req())

        assert exc.value.status_code == 410

    async def test_expired_ticket_rejected(self) -> None:
        session = _CompleteSignupSession(_pending_signup(expired=True))
        db_patch, rls_patch = _patched_db(session)

        with db_patch, rls_patch:
            with pytest.raises(HTTPException) as exc:
                await alpaca_oauth_complete_signup(self._body(), _req())

        assert exc.value.status_code == 410
        assert session.committed is False

    async def test_weak_password_rejected(self) -> None:
        session = _CompleteSignupSession(_pending_signup())
        db_patch, rls_patch = _patched_db(session)

        with db_patch, rls_patch:
            with pytest.raises(HTTPException) as exc:
                await alpaca_oauth_complete_signup(self._body(password="short"), _req())

        assert exc.value.status_code == 400
        assert session.committed is False
        assert session.added == []

    async def test_malformed_ticket_rejected(self) -> None:
        body = CompleteSignupRequest(ticket="not-a-uuid", email="x@y.com", password="SecurePass123")
        with pytest.raises(HTTPException) as exc:
            await alpaca_oauth_complete_signup(body, _req())
        assert exc.value.status_code == 400
