"""Tests for the shared platform auth (llamatrade_common.auth)."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import jwt
import pytest

from llamatrade_common.auth import (
    AuthError,
    AuthMiddleware,
    TenantContext,
    current_context,
    mint_service_token,
    reset_context,
    resolve_identity,
    set_context,
    verify_credential,
)

SECRET = "unit-test-secret-key-which-is-long-enough-32b"
TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")
USER = UUID("33333333-3333-3333-3333-333333333333")


def _user_token(
    tenant_id: UUID = TENANT_A, user_id: UUID = USER, token_type: str = "access"
) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "type": token_type,
            "roles": ["user"],
            "email": "u@example.com",
            "exp": int(time.time()) + 60,
        },
        SECRET,
        algorithm="HS256",
    )


# --------------------------------------------------------------------------- #
# verify_credential
# --------------------------------------------------------------------------- #


def test_verify_user_token() -> None:
    ctx = verify_credential(_user_token(), secret=SECRET)
    assert ctx is not None
    assert ctx.tenant_id == TENANT_A
    assert ctx.user_id == USER
    assert ctx.is_service is False


def test_verify_service_token() -> None:
    ctx = verify_credential(mint_service_token(secret=SECRET), secret=SECRET)
    assert ctx is not None
    assert ctx.is_service is True


def test_verify_refresh_token_rejected() -> None:
    assert verify_credential(_user_token(token_type="refresh"), secret=SECRET) is None


def test_verify_expired_token_rejected() -> None:
    expired = jwt.encode(
        {
            "sub": str(USER),
            "tenant_id": str(TENANT_A),
            "type": "access",
            "exp": int(time.time()) - 1,
        },
        SECRET,
        algorithm="HS256",
    )
    assert verify_credential(expired, secret=SECRET) is None


def test_verify_wrong_secret_rejected() -> None:
    assert verify_credential(_user_token(), secret="a-different-secret-key-32-bytes-xx") is None


def test_verify_garbage_rejected() -> None:
    assert verify_credential("not-a-jwt", secret=SECRET) is None


# --------------------------------------------------------------------------- #
# resolve_identity
# --------------------------------------------------------------------------- #


def test_resolve_user_context_uses_token_identity() -> None:
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        # Even if the wire claims a different user, the token's user wins.
        tid, uid = resolve_identity(str(TENANT_A), "99999999-9999-9999-9999-999999999999")
        assert tid == TENANT_A
        assert uid == USER
    finally:
        reset_context(token)


def test_resolve_user_context_cross_tenant_blocked() -> None:
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(AuthError) as exc:
            resolve_identity(str(TENANT_B), str(USER))
        assert exc.value.code == "permission_denied"
    finally:
        reset_context(token)


def test_resolve_service_context_trusts_wire() -> None:
    token = set_context(TenantContext(tenant_id=UUID(int=0), user_id=UUID(int=0), is_service=True))
    try:
        tid, uid = resolve_identity(str(TENANT_B), str(USER))
        assert tid == TENANT_B
        assert uid == USER
    finally:
        reset_context(token)


def test_resolve_no_context_trusts_wire() -> None:
    assert current_context() is None
    tid, uid = resolve_identity(str(TENANT_A), str(USER))
    assert tid == TENANT_A
    assert uid == USER


def test_resolve_no_context_missing_wire_rejected() -> None:
    with pytest.raises(AuthError) as exc:
        resolve_identity(None, None)
    assert exc.value.code == "unauthenticated"


def test_resolve_nil_uuid_rejected() -> None:
    with pytest.raises(AuthError) as exc:
        resolve_identity("00000000-0000-0000-0000-000000000000", str(USER))
    assert exc.value.code == "unauthenticated"


def test_resolve_bad_type_rejected() -> None:
    # A non-string wire value (e.g. an unconfigured mock) is invalid, not a crash.
    bad_wire: Any = object()
    with pytest.raises(AuthError) as exc:
        resolve_identity(bad_wire, bad_wire)
    assert exc.value.code in {"unauthenticated", "invalid_argument"}


# --------------------------------------------------------------------------- #
# AuthMiddleware (pure ASGI)
# --------------------------------------------------------------------------- #


class _Downstream:
    """Records the verified context seen by the wrapped app, and 200s."""

    def __init__(self) -> None:
        self.called = False
        self.seen: TenantContext | None = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.called = True
        self.seen = current_context()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _scope(path: str, method: str = "POST", token: str | None = None) -> dict[str, Any]:
    headers: list[tuple[bytes, bytes]] = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return {"type": "http", "method": method, "path": path, "headers": headers}


async def _run(mw: AuthMiddleware, scope: dict[str, Any]) -> dict[str, Any]:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b""}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await mw(scope, receive, send)
    start = next((m for m in sent if m["type"] == "http.response.start"), None)
    return {"status": start["status"] if start else None, "sent": sent}


async def test_middleware_health_is_public() -> None:
    app = _Downstream()
    mw = AuthMiddleware(app, jwt_secret=SECRET)
    result = await _run(mw, _scope("/health", method="GET"))
    assert app.called is True
    assert result["status"] == 200


async def test_middleware_protected_no_token_rejected() -> None:
    app = _Downstream()
    mw = AuthMiddleware(app, jwt_secret=SECRET)
    result = await _run(mw, _scope("/llamatrade.v1.TradingService/SubmitOrder"))
    assert app.called is False
    assert result["status"] == 401


async def test_middleware_protected_valid_user_token_sets_context() -> None:
    app = _Downstream()
    mw = AuthMiddleware(app, jwt_secret=SECRET)
    result = await _run(
        mw, _scope("/llamatrade.v1.TradingService/SubmitOrder", token=_user_token())
    )
    assert app.called is True
    assert result["status"] == 200
    assert app.seen is not None
    assert app.seen.tenant_id == TENANT_A
    assert app.seen.is_service is False
    # Context is reset after the request.
    assert current_context() is None


async def test_middleware_service_token_sets_service_context() -> None:
    app = _Downstream()
    mw = AuthMiddleware(app, jwt_secret=SECRET)
    await _run(
        mw,
        _scope(
            "/llamatrade.v1.PortfolioService/GetSleeve",
            token=mint_service_token(secret=SECRET),
        ),
    )
    assert app.called is True
    assert app.seen is not None
    assert app.seen.is_service is True


async def test_middleware_invalid_token_rejected() -> None:
    app = _Downstream()
    mw = AuthMiddleware(app, jwt_secret=SECRET)
    result = await _run(mw, _scope("/svc/Method", token="garbage"))
    assert app.called is False
    assert result["status"] == 401


async def test_middleware_options_preflight_passes() -> None:
    app = _Downstream()
    mw = AuthMiddleware(app, jwt_secret=SECRET)
    await _run(mw, _scope("/svc/Method", method="OPTIONS"))
    assert app.called is True


async def test_middleware_public_suffix_passes() -> None:
    app = _Downstream()
    mw = AuthMiddleware(app, jwt_secret=SECRET, public_suffixes=["/Login", "/Register"])
    result = await _run(mw, _scope("/llamatrade.v1.AuthService/Login"))
    assert app.called is True
    assert result["status"] == 200
