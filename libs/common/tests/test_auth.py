"""Tests for the shared platform auth (llamatrade_common.auth)."""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import json
import time
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from llamatrade_common.auth import (
    SERVICE_AUDIENCE,
    AuthError,
    AuthMiddleware,
    TenantContext,
    current_context,
    decode_token_claims,
    mint_service_token,
    reset_context,
    resolve_identity,
    set_context,
    user_token_signing_key,
    user_token_verification_key,
    verify_credential,
)

SECRET = "unit-test-secret-key-which-is-long-enough-32b"
TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")
USER = UUID("33333333-3333-3333-3333-333333333333")


def _rsa_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem


PRIVATE_PEM, PUBLIC_PEM = _rsa_pair()
OTHER_PRIVATE_PEM, _OTHER_PUBLIC_PEM = _rsa_pair()


@pytest.fixture(autouse=True)
def _clean_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ambient AUTH_JWT_* env vars from leaking into HS256-mode tests."""
    monkeypatch.delenv("AUTH_JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("AUTH_JWT_PRIVATE_KEY", raising=False)


def _user_payload(
    tenant_id: UUID = TENANT_A,
    user_id: UUID = USER,
    token_type: str = "access",
    jti: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "type": token_type,
        "roles": ["user"],
        "email": "u@example.com",
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
    }
    if jti is not None:
        payload["jti"] = jti
    return payload


def _user_token(
    tenant_id: UUID = TENANT_A,
    user_id: UUID = USER,
    token_type: str = "access",
    jti: str | None = None,
) -> str:
    return jwt.encode(_user_payload(tenant_id, user_id, token_type, jti), SECRET, algorithm="HS256")


def _rs256_token(payload: dict[str, Any], private_pem: str = PRIVATE_PEM) -> str:
    return jwt.encode(payload, private_pem, algorithm="RS256")


def _forge_hs256(payload: dict[str, Any], hmac_key: str) -> str:
    """Manually build an HS256 JWT (bypasses PyJWT's PEM-as-HMAC-secret guard)."""

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    signature = b64(
        hmac_mod.new(hmac_key.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{body}.{signature}"


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
        tid, uid = resolve_identity(str(TENANT_A), str(USER))
        assert tid == TENANT_A
        assert uid == USER
    finally:
        reset_context(token)


def test_resolve_user_context_empty_wire_user_uses_token_identity() -> None:
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        tid, uid = resolve_identity(str(TENANT_A), None)
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


def test_resolve_user_context_cross_tenant_increments_metric() -> None:
    from llamatrade_telemetry import metrics

    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with patch.object(metrics.auth, "cross_tenant_access_attempt") as attempt:
            with pytest.raises(AuthError):
                resolve_identity(str(TENANT_B), str(USER))
        attempt.assert_called_once()
    finally:
        reset_context(token)


def test_resolve_user_context_forged_wire_user_blocked() -> None:
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(AuthError) as exc:
            resolve_identity(str(TENANT_A), "99999999-9999-9999-9999-999999999999")
        assert exc.value.code == "permission_denied"
    finally:
        reset_context(token)


def test_resolve_user_context_invalid_wire_user_rejected() -> None:
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(AuthError) as exc:
            resolve_identity(str(TENANT_A), "not-a-uuid")
        assert exc.value.code == "invalid_argument"
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


async def test_middleware_websocket_scope_rejected() -> None:
    app = _Downstream()
    mw = AuthMiddleware(app, jwt_secret=SECRET)
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "websocket.connect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await mw({"type": "websocket", "path": "/ws", "headers": []}, receive, send)
    assert app.called is False
    assert sent == [{"type": "websocket.close", "code": 1008}]


async def test_middleware_lifespan_scope_passes_through() -> None:
    app = _Downstream()
    mw = AuthMiddleware(app, jwt_secret=SECRET)
    await _run(mw, {"type": "lifespan", "headers": []})
    assert app.called is True


class _FakeRedis:
    """Minimal async Redis stand-in for revocation checks."""

    def __init__(self, *, error: bool = False) -> None:
        self.store: dict[str, object] = {}
        self.error = error

    def _maybe_fail(self) -> None:
        if self.error:
            raise ConnectionError("redis down")

    async def setex(self, key: str, ttl: int, value: object) -> None:
        self._maybe_fail()
        self.store[key] = value

    async def set(self, key: str, value: object, nx: bool = False, ex: int | None = None) -> bool:
        self._maybe_fail()
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def exists(self, key: str) -> int:
        self._maybe_fail()
        return int(key in self.store)

    async def get(self, key: str) -> object | None:
        self._maybe_fail()
        return self.store.get(key)


class TestMiddlewareRevocation:
    """Revocation checking when the middleware is constructed with Redis."""

    async def test_revoked_jti_rejected(self) -> None:
        from llamatrade_common.revocation import RevocationStore

        redis = _FakeRedis()
        jti = uuid4().hex
        store = RevocationStore(redis)
        await store.revoke_token(jti, int(time.time()) + 60)

        app = _Downstream()
        mw = AuthMiddleware(app, jwt_secret=SECRET, redis_client=redis)
        result = await _run(mw, _scope("/svc/Method", token=_user_token(jti=jti)))
        assert app.called is False
        assert result["status"] == 401

    async def test_unrevoked_token_passes(self) -> None:
        app = _Downstream()
        mw = AuthMiddleware(app, jwt_secret=SECRET, redis_client=_FakeRedis())
        result = await _run(mw, _scope("/svc/Method", token=_user_token(jti=uuid4().hex)))
        assert app.called is True
        assert result["status"] == 200

    async def test_user_cutoff_rejects_older_tokens(self) -> None:
        from llamatrade_common.revocation import RevocationStore

        redis = _FakeRedis()
        store = RevocationStore(redis)
        await store.revoke_all_for_user(str(USER), int(time.time()) + 5)

        app = _Downstream()
        mw = AuthMiddleware(app, jwt_secret=SECRET, redis_client=redis)
        result = await _run(mw, _scope("/svc/Method", token=_user_token(jti=uuid4().hex)))
        assert app.called is False
        assert result["status"] == 401

    async def test_redis_error_fails_open(self) -> None:
        app = _Downstream()
        mw = AuthMiddleware(app, jwt_secret=SECRET, redis_client=_FakeRedis(error=True))
        result = await _run(mw, _scope("/svc/Method", token=_user_token(jti=uuid4().hex)))
        assert app.called is True
        assert result["status"] == 200

    async def test_service_token_skips_revocation(self) -> None:
        app = _Downstream()
        mw = AuthMiddleware(app, jwt_secret=SECRET, redis_client=_FakeRedis(error=True))
        await _run(mw, _scope("/svc/Method", token=mint_service_token(secret=SECRET)))
        assert app.called is True


class TestServiceTokenClaims:
    """Service tokens carry the internal audience + svc and are HS256."""

    def test_mint_includes_type_svc_and_audience(self) -> None:
        claims = jwt.decode(
            mint_service_token(service_name="trading", secret=SECRET),
            SECRET,
            algorithms=["HS256"],
            audience=SERVICE_AUDIENCE,
        )
        assert claims["type"] == "service"
        assert claims["svc"] == "trading"
        assert claims["aud"] == SERVICE_AUDIENCE

    def test_service_token_without_audience_rejected(self) -> None:
        legacy = jwt.encode(
            {
                "sub": "llamatrade-service",
                "type": "service",
                "svc": "trading",
                "iat": int(time.time()),
                "exp": int(time.time()) + 60,
            },
            SECRET,
            algorithm="HS256",
        )
        assert decode_token_claims(legacy, secret=SECRET) is None
        assert verify_credential(legacy, secret=SECRET) is None

    def test_user_token_with_internal_audience_rejected(self) -> None:
        payload = _user_payload()
        payload["aud"] = SERVICE_AUDIENCE
        crossed = jwt.encode(payload, SECRET, algorithm="HS256")
        assert decode_token_claims(crossed, secret=SECRET) is None


class TestAsymmetricVerification:
    """RS256 user tokens with the alg/type/aud pinning matrix."""

    def test_rs256_token_verifies_with_public_key(self) -> None:
        token = _rs256_token(_user_payload())
        claims = decode_token_claims(token, secret=SECRET, public_key=PUBLIC_PEM)
        assert claims is not None
        assert claims["sub"] == str(USER)
        ctx = verify_credential(token, secret=SECRET, public_key=PUBLIC_PEM)
        assert ctx is not None
        assert ctx.tenant_id == TENANT_A
        assert ctx.is_service is False

    def test_env_public_key_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTH_JWT_PUBLIC_KEY", PUBLIC_PEM)
        ctx = verify_credential(_rs256_token(_user_payload()), secret=SECRET)
        assert ctx is not None
        assert ctx.user_id == USER

    def test_hs256_user_token_rejected_when_rs256_pinned(self) -> None:
        # Alg confusion: a symmetric user token where the public key is configured.
        assert decode_token_claims(_user_token(), secret=SECRET, public_key=PUBLIC_PEM) is None

    def test_public_key_as_hmac_secret_rejected(self) -> None:
        # The classic confusion attack: HS256 signed with the public PEM as secret.
        forged = _forge_hs256(_user_payload(), PUBLIC_PEM)
        assert decode_token_claims(forged, secret=SECRET, public_key=PUBLIC_PEM) is None
        assert decode_token_claims(forged, secret=SECRET) is None

    def test_forged_service_claims_with_public_key_secret_rejected(self) -> None:
        payload = _user_payload()
        payload["type"] = "service"
        payload["aud"] = SERVICE_AUDIENCE
        forged = _forge_hs256(payload, PUBLIC_PEM)
        assert decode_token_claims(forged, secret=SECRET, public_key=PUBLIC_PEM) is None

    def test_service_token_still_accepted_alongside_rs256(self) -> None:
        token = mint_service_token(secret=SECRET)
        ctx = verify_credential(token, secret=SECRET, public_key=PUBLIC_PEM)
        assert ctx is not None
        assert ctx.is_service is True

    def test_rs256_service_typed_token_rejected(self) -> None:
        # Service tokens are HS256-only; an RS256 one is never legitimate.
        payload = _user_payload()
        payload["type"] = "service"
        assert (
            decode_token_claims(_rs256_token(payload), secret=SECRET, public_key=PUBLIC_PEM) is None
        )

    def test_rs256_token_with_internal_audience_rejected(self) -> None:
        payload = _user_payload()
        payload["aud"] = SERVICE_AUDIENCE
        assert (
            decode_token_claims(_rs256_token(payload), secret=SECRET, public_key=PUBLIC_PEM) is None
        )

    def test_rs256_refresh_token_cannot_authenticate(self) -> None:
        token = _rs256_token(_user_payload(token_type="refresh"))
        assert decode_token_claims(token, secret=SECRET, public_key=PUBLIC_PEM) is not None
        assert verify_credential(token, secret=SECRET, public_key=PUBLIC_PEM) is None

    def test_wrong_rsa_key_rejected(self) -> None:
        token = _rs256_token(_user_payload(), private_pem=OTHER_PRIVATE_PEM)
        assert decode_token_claims(token, secret=SECRET, public_key=PUBLIC_PEM) is None

    def test_expired_rs256_rejected(self) -> None:
        payload = _user_payload()
        payload["exp"] = int(time.time()) - 1
        assert (
            decode_token_claims(_rs256_token(payload), secret=SECRET, public_key=PUBLIC_PEM) is None
        )

    def test_unpinned_algorithm_rejected(self) -> None:
        # ES256 (or any non-pinned alg) fails in both modes.
        token = _rs256_token(_user_payload())
        assert decode_token_claims(token, secret=SECRET) is None  # HS256-only mode

    def test_garbage_rejected_in_asymmetric_mode(self) -> None:
        assert decode_token_claims("not-a-jwt", secret=SECRET, public_key=PUBLIC_PEM) is None


class TestAsymmetricMiddleware:
    """AuthMiddleware pins RS256 for user tokens when given a public key."""

    async def test_rs256_user_token_sets_context(self) -> None:
        app = _Downstream()
        mw = AuthMiddleware(app, jwt_secret=SECRET, jwt_public_key=PUBLIC_PEM)
        result = await _run(mw, _scope("/svc/Method", token=_rs256_token(_user_payload())))
        assert app.called is True
        assert result["status"] == 200
        assert app.seen is not None
        assert app.seen.tenant_id == TENANT_A

    async def test_hs256_user_token_rejected(self) -> None:
        app = _Downstream()
        mw = AuthMiddleware(app, jwt_secret=SECRET, jwt_public_key=PUBLIC_PEM)
        result = await _run(mw, _scope("/svc/Method", token=_user_token()))
        assert app.called is False
        assert result["status"] == 401

    async def test_service_token_accepted(self) -> None:
        app = _Downstream()
        mw = AuthMiddleware(app, jwt_secret=SECRET, jwt_public_key=PUBLIC_PEM)
        result = await _run(mw, _scope("/svc/Method", token=mint_service_token(secret=SECRET)))
        assert app.called is True
        assert result["status"] == 200
        assert app.seen is not None
        assert app.seen.is_service is True


class TestKeyResolution:
    """user_token_signing_key / user_token_verification_key config handling."""

    def test_dev_fallback_is_hs256_shared_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_SECRET", SECRET)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert user_token_signing_key() == (SECRET, "HS256")
        assert user_token_verification_key() == (SECRET, "HS256")

    def test_configured_pair_selects_rs256(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTH_JWT_PRIVATE_KEY", PRIVATE_PEM)
        monkeypatch.setenv("AUTH_JWT_PUBLIC_KEY", PUBLIC_PEM)
        assert user_token_signing_key() == (PRIVATE_PEM, "RS256")
        assert user_token_verification_key() == (PUBLIC_PEM, "RS256")

    @pytest.mark.parametrize("environment", ["production", "staging"])
    def test_production_requires_the_pair(
        self, monkeypatch: pytest.MonkeyPatch, environment: str
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", environment)
        monkeypatch.setenv("JWT_SECRET", SECRET)
        with pytest.raises(RuntimeError, match="asymmetrically signed"):
            user_token_signing_key()

    def test_half_configured_pair_always_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTH_JWT_PRIVATE_KEY", PRIVATE_PEM)
        with pytest.raises(RuntimeError, match="together"):
            user_token_signing_key()
        monkeypatch.delenv("AUTH_JWT_PRIVATE_KEY")
        monkeypatch.setenv("AUTH_JWT_PUBLIC_KEY", PUBLIC_PEM)
        with pytest.raises(RuntimeError, match="together"):
            user_token_signing_key()

    def test_public_key_alone_is_valid_for_verifiers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Non-auth services only hold the public half.
        monkeypatch.setenv("AUTH_JWT_PUBLIC_KEY", PUBLIC_PEM)
        assert user_token_verification_key() == (PUBLIC_PEM, "RS256")


class TestTenantContextUnified:
    """3A: llamatrade_common exposes a single canonical TenantContext (from auth.py)."""

    def test_package_reexports_canonical_context(self) -> None:
        from llamatrade_common import TenantContext as PackageContext

        assert PackageContext is TenantContext

    def test_context_carries_is_service_flag(self) -> None:
        user_ctx = TenantContext(tenant_id=UUID(int=1), user_id=UUID(int=2), email="u@example.com")
        assert user_ctx.is_service is False
        service_ctx = TenantContext(
            tenant_id=UUID(int=1), user_id=UUID(int=2), email="", is_service=True
        )
        assert service_ctx.is_service is True


def _service_ctx(svc: str) -> TenantContext:
    return TenantContext(tenant_id=UUID(int=0), user_id=UUID(int=0), is_service=True, svc=svc)


class TestServiceTokenPrincipal:
    """The svc claim rides on the context and an allowlist can gate it."""

    def test_context_preserves_svc(self) -> None:
        ctx = verify_credential(
            mint_service_token(service_name="trading", secret=SECRET), secret=SECRET
        )
        assert ctx is not None
        assert ctx.is_service is True
        assert ctx.svc == "trading"

    def test_service_ctx_allowed_by_param(self) -> None:
        token = set_context(_service_ctx("trading"))
        try:
            result = resolve_identity(
                str(TENANT_B), str(USER), accepted_services={"trading", "backtest"}
            )
            assert result == (TENANT_B, USER)
        finally:
            reset_context(token)

    def test_service_ctx_rejected_by_param(self) -> None:
        token = set_context(_service_ctx("agent"))
        try:
            with pytest.raises(AuthError) as exc:
                resolve_identity(str(TENANT_B), str(USER), accepted_services={"trading"})
            assert exc.value.code == "permission_denied"
        finally:
            reset_context(token)

    def test_service_ctx_gated_by_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTH_ACCEPTED_SERVICES", "trading, backtest")
        token = set_context(_service_ctx("agent"))
        try:
            with pytest.raises(AuthError) as exc:
                resolve_identity(str(TENANT_B), str(USER))
            assert exc.value.code == "permission_denied"
        finally:
            reset_context(token)

    def test_env_allowlist_accepts_listed_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTH_ACCEPTED_SERVICES", "trading,backtest")
        token = set_context(_service_ctx("backtest"))
        try:
            assert resolve_identity(str(TENANT_B), str(USER)) == (TENANT_B, USER)
        finally:
            reset_context(token)

    def test_no_allowlist_accepts_any_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUTH_ACCEPTED_SERVICES", raising=False)
        token = set_context(_service_ctx("whatever"))
        try:
            assert resolve_identity(str(TENANT_B), str(USER)) == (TENANT_B, USER)
        finally:
            reset_context(token)

    def test_allowlist_does_not_apply_without_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AUTH_ACCEPTED_SERVICES", "trading")
        assert current_context() is None
        assert resolve_identity(str(TENANT_A), str(USER)) == (TENANT_A, USER)


class TestMiddlewareRevocationDefault:
    """Revocation defaults on from REDIS_URL; prod refuses to run without it."""

    async def test_builds_redis_from_env_and_enforces(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamatrade_common import auth as auth_mod
        from llamatrade_common.revocation import RevocationStore

        redis = _FakeRedis()
        jti = uuid4().hex
        await RevocationStore(redis).revoke_token(jti, int(time.time()) + 60)

        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setattr(auth_mod.Redis, "from_url", classmethod(lambda cls, url: redis))

        app = _Downstream()
        mw = AuthMiddleware(app, jwt_secret=SECRET)
        result = await _run(mw, _scope("/svc/Method", token=_user_token(jti=jti)))
        assert app.called is False
        assert result["status"] == 401

    def test_no_client_no_env_disables_in_dev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        mw = AuthMiddleware(_Downstream(), jwt_secret=SECRET)
        assert mw._revocation is None

    @pytest.mark.parametrize("environment", ["production", "staging"])
    def test_production_without_revocation_refuses_to_start(
        self, monkeypatch: pytest.MonkeyPatch, environment: str
    ) -> None:
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("ENVIRONMENT", environment)
        with pytest.raises(RuntimeError, match="revocation"):
            AuthMiddleware(_Downstream(), jwt_secret=SECRET)

    def test_production_with_redis_url_starts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from llamatrade_common import auth as auth_mod

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setattr(auth_mod.Redis, "from_url", classmethod(lambda cls, url: _FakeRedis()))
        mw = AuthMiddleware(_Downstream(), jwt_secret=SECRET)
        assert mw._revocation is not None

    def test_explicit_client_not_overridden_by_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REDIS_URL", raising=False)
        redis = _FakeRedis()
        mw = AuthMiddleware(_Downstream(), jwt_secret=SECRET, redis_client=redis)
        assert mw._revocation is not None
