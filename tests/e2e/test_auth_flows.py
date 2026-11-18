"""E2E: session-lifecycle auth flows and the plain-HTTP OAuth routes.

Covers the flows beyond first onboarding (test_auth_onboarding): the
verify-email round trip through mailpit, the welcome email, ChangePassword's
revoke-all-sessions semantics, RefreshToken rotation (the presented refresh
token is revoked before the new pair is minted), and Logout revocation.

The Alpaca OAuth happy path needs the real provider (a genuine authorization
code), so it stays out of reach by design; these tests prove the route surface:
start is fail-closed without config, the public callback rejects a forged
``state``, and exchange/complete-signup reject invalid tickets. The dev mesh
ships without ALPACA_OAUTH_* configured, so the start assertions branch on the
config being present (both branches are exact).
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx
import pytest

from .client import (
    HOSTS,
    MeshClient,
    MeshError,
    find_mailpit_message,
    login,
    mailpit_available,
    mailpit_message_text,
)

pytestmark = pytest.mark.e2e

_AUTH_HTTP = HOSTS["auth"]


def _poll(check: Callable[[], bool], *, timeout: float = 30.0, interval: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(interval)
    return False


def _email_of(client: MeshClient) -> str:
    return str(client.call("auth", "GetCurrentUser", {}).get("user", {}).get("email", ""))


@pytest.mark.skipif(not mailpit_available(), reason="mailpit not running")
class TestEmailVerification:
    def test_verify_email_round_trip(self, throwaway_tenant: Callable[[str], MeshClient]) -> None:
        client = throwaway_tenant("verify")
        email = _email_of(client)

        assert _poll(lambda: find_mailpit_message(email, "Verify your email") is not None), (
            "verification email never arrived in mailpit"
        )
        message = find_mailpit_message(email, "Verify your email")
        assert message is not None
        text = mailpit_message_text(str(message.get("ID", "")))
        assert "verify-email?token=" in text
        token = text.split("token=")[1].split()[0].strip()

        anon = MeshClient()
        verified = anon.call("auth", "VerifyEmail", {"token": token}, context=False)
        assert verified.get("success") is True

        # The token is single-use.
        with pytest.raises(MeshError) as excinfo:
            anon.call("auth", "VerifyEmail", {"token": token}, context=False)
        assert excinfo.value.code == "invalid_argument"

    def test_registration_sends_the_welcome_email(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        client = throwaway_tenant("welcome")
        email = _email_of(client)
        assert _poll(lambda: find_mailpit_message(email, "Welcome to LlamaTrade") is not None), (
            "welcome email never arrived in mailpit"
        )


def _token_iat(token: str) -> int:
    """The iat claim of a JWT we minted for ourselves (payload read, no verify)."""
    import base64
    import json

    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return int(json.loads(base64.urlsafe_b64decode(payload)).get("iat", 0))


def test_change_password_revokes_all_sessions_and_old_password(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("chpass")
    email = _email_of(client)
    old_password = "e2e-Passw0rd!"
    new_password = "e2e-Rotated1!"

    # The revoke-all cutoff has one-second granularity (tokens with iat ==
    # cutoff survive), so make sure this session's token is strictly older
    # than the second in which the password change lands.
    assert client.token is not None
    iat = _token_iat(client.token)
    while int(time.time()) <= iat:
        time.sleep(0.2)

    changed = client.call(
        "auth",
        "ChangePassword",
        {"currentPassword": old_password, "newPassword": new_password},
    )
    assert changed.get("success") is True

    # Revoke-all-sessions includes the calling session.
    with pytest.raises(MeshError) as revoked:
        client.call("auth", "GetCurrentUser", {})
    assert revoked.value.http_status in (401, 403) or revoked.value.code == "unauthenticated"

    with pytest.raises(MeshError):
        login(email, old_password, retries=1)

    relogged = login(email, new_password)
    assert relogged.ctx["tenantId"] == client.ctx["tenantId"]


def test_refresh_token_rotation_revokes_the_used_token(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("refresh")
    email = _email_of(client)

    anon = MeshClient()
    session = anon.call(
        "auth", "Login", {"email": email, "password": "e2e-Passw0rd!"}, context=False
    )
    refresh = session.get("refreshToken")
    assert refresh, "Login must return a refresh token"

    rotated = anon.call("auth", "RefreshToken", {"refreshToken": refresh}, context=False)
    new_access = rotated.get("accessToken")
    new_refresh = rotated.get("refreshToken")
    assert new_access and new_refresh
    assert new_refresh != refresh

    # The new access token authenticates.
    fresh = MeshClient(token=new_access, ctx=client.ctx)
    assert fresh.call("auth", "GetCurrentUser", {}).get("user", {}).get("email") == email

    # The presented refresh token was revoked by the rotation.
    with pytest.raises(MeshError) as excinfo:
        anon.call("auth", "RefreshToken", {"refreshToken": refresh}, context=False)
    assert excinfo.value.http_status in (401, 403) or excinfo.value.code == "unauthenticated"


def test_logout_revokes_the_access_token(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("logout")
    assert client.call("auth", "Logout", {}).get("success") is True
    with pytest.raises(MeshError) as excinfo:
        client.call("auth", "GetCurrentUser", {})
    assert excinfo.value.http_status in (401, 403) or excinfo.value.code == "unauthenticated"


# --- Alpaca OAuth plain-HTTP routes (happy path stays provider-gated) --------
class TestOAuthRoutes:
    def test_start_requires_auth_and_is_fail_closed_without_config(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        unauthed = httpx.post(f"{_AUTH_HTTP}/oauth/alpaca/start", timeout=10.0)
        assert unauthed.status_code == 401

        client = throwaway_tenant("oauth")
        resp = httpx.post(
            f"{_AUTH_HTTP}/oauth/alpaca/start",
            headers={"Authorization": f"Bearer {client.token}"},
            timeout=10.0,
        )
        if resp.status_code == 503:
            # The mesh ships without ALPACA_OAUTH_* configured: fail closed.
            assert resp.json().get("detail") == "Alpaca OAuth is not configured"
        else:
            assert resp.status_code == 200
            authorize_url = resp.json().get("authorizeUrl", "")
            assert authorize_url.startswith("https://app.alpaca.markets/oauth/authorize?")
            assert "state=" in authorize_url and "client_id=" in authorize_url

    def test_callback_rejects_a_forged_state(self) -> None:
        resp = httpx.get(
            f"{_AUTH_HTTP}/oauth/alpaca/callback",
            params={"code": "anything", "state": "forged-state"},
            follow_redirects=False,
            timeout=10.0,
        )
        assert resp.status_code == 400
        assert resp.json().get("detail") == "invalid or expired state"

    def test_callback_relays_a_provider_error_to_the_connect_page(self) -> None:
        resp = httpx.get(
            f"{_AUTH_HTTP}/oauth/alpaca/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
            timeout=10.0,
        )
        assert resp.status_code == 302
        location = resp.headers.get("location", "")
        assert location.endswith("/connect/alpaca?error=access_denied")

    def test_exchange_rejects_a_garbage_handoff(self) -> None:
        resp = httpx.post(
            f"{_AUTH_HTTP}/oauth/alpaca/exchange",
            json={"handoff": "not-a-real-handoff"},
            timeout=10.0,
        )
        assert resp.status_code == 400
        assert resp.json().get("detail") == "invalid or expired handoff"

    def test_complete_signup_rejects_invalid_tickets(self) -> None:
        malformed = httpx.post(
            f"{_AUTH_HTTP}/oauth/alpaca/complete-signup",
            json={
                "ticket": "not-a-uuid",
                "email": "oauth-e2e@e2e.llamatrade.test",
                "password": "e2e-Passw0rd!",
            },
            timeout=10.0,
        )
        assert malformed.status_code == 400
        assert malformed.json().get("detail") == "invalid signup ticket"

        unknown = httpx.post(
            f"{_AUTH_HTTP}/oauth/alpaca/complete-signup",
            json={
                "ticket": "00000000-0000-0000-0000-000000000000",
                "email": "oauth-e2e@e2e.llamatrade.test",
                "password": "e2e-Passw0rd!",
            },
            timeout=10.0,
        )
        assert unknown.status_code == 410
        assert unknown.json().get("detail") == "invalid or already used signup ticket"
