"""Alpaca OAuth router — non-DB paths (start URL, callback guards)."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from llamatrade_common import TenantContext, reset_context, set_context

from src.oauth_state import verify_state
from src.routers.oauth import (
    ExchangeRequest,
    alpaca_oauth_authorize,
    alpaca_oauth_callback,
    alpaca_oauth_exchange,
    alpaca_oauth_start,
)


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
        await alpaca_oauth_exchange(ExchangeRequest(handoff="garbage"))
    assert exc.value.status_code == 400
