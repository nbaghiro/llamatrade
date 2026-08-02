"""E2E: registration, first login, and the broker-credential surface.

Mirrors the UI onboarding path: RegisterPage fires ``AuthService/Register`` then a
separate ``Login`` (Register does not auto-login); the Settings → Broker tab then
reads ``ListAlpacaCredentials`` and validates keys via ``ValidateAlpacaCredentials``
before saving. Everything runs on a freshly-registered throwaway tenant, so the
seeded demo account is never touched.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from .client import MeshClient, MeshError, login

pytestmark = pytest.mark.e2e


def test_register_then_login_issues_a_working_session(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("onboard")
    # register_and_login already ran Register + a separate Login (the UI sequence).
    assert client.token
    assert client.ctx["tenantId"]
    # GetCurrentUser proves the issued token authenticates against the real mesh.
    me = client.call("auth", "GetCurrentUser", {})
    user = me.get("user", {})
    assert user.get("tenantId") == client.ctx["tenantId"]
    assert user.get("email", "").startswith("onboard-")


def test_new_tenant_starts_with_no_broker_credentials(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("onboard")
    creds = client.call("auth", "ListAlpacaCredentials", {})
    assert creds.get("credentials", []) == []


def test_validate_rejects_bogus_alpaca_keys(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    # The broker tab validates before saving; bogus keys hit the REAL Alpaca
    # validation path and must come back invalid, leaving no credential stored.
    client = throwaway_tenant("onboard")
    resp = client.call(
        "auth",
        "ValidateAlpacaCredentials",
        {"apiKey": "PKINVALIDKEYE2E000000", "apiSecret": "not-a-real-secret", "isPaper": True},
    )
    # proto3 JSON omits false defaults, so ``valid`` is absent (falsy) with a reason.
    assert not resp.get("valid")
    assert resp.get("message")
    creds = client.call("auth", "ListAlpacaCredentials", {})
    assert creds.get("credentials", []) == []


def test_demo_tenant_has_a_seeded_paper_credential(demo: MeshClient) -> None:
    creds = demo.call("auth", "ListAlpacaCredentials", {})
    paper = [c for c in creds.get("credentials", []) if c.get("isPaper") and c.get("isActive")]
    assert paper, "seeded demo should expose an active paper Alpaca credential"


def test_login_rejects_a_wrong_password() -> None:
    with pytest.raises(MeshError) as excinfo:
        login("demo@llamatrade.ai", "wrong-password")
    err = excinfo.value
    assert err.http_status in (400, 401, 403) or err.code in (
        "unauthenticated",
        "invalid_argument",
        "permission_denied",
        "not_found",
    )


def test_duplicate_registration_is_rejected(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    # Registering, then re-registering the same email, must fail (unique account).
    client = throwaway_tenant("onboard")
    email = client.call("auth", "GetCurrentUser", {}).get("user", {}).get("email", "")
    assert email
    anon = MeshClient()
    with pytest.raises(MeshError) as excinfo:
        anon.call(
            "auth",
            "Register",
            {"tenantName": "dup", "email": email, "password": "e2e-Passw0rd!"},
            context=False,
        )
    assert excinfo.value.http_status >= 400
