"""Tests for inter-service client helpers."""

from __future__ import annotations

from uuid import uuid4

from llamatrade_common.auth import verify_credential

from src.tools.clients import tenant_headers


def test_tenant_headers_carry_identity_and_verifiable_service_token() -> None:
    """Headers carry tenant/user and a service token that authenticates past the
    callees' fail-closed AuthMiddleware."""
    tenant_id = str(uuid4())
    user_id = str(uuid4())

    headers = tenant_headers(tenant_id, user_id)

    assert headers["X-Tenant-ID"] == tenant_id
    assert headers["X-User-ID"] == user_id

    auth = headers["Authorization"]
    assert auth.startswith("Bearer ")
    ctx = verify_credential(auth.split(" ", 1)[1])
    assert ctx is not None
    assert ctx.is_service
