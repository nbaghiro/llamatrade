"""Tests for the connectrpc auth adapter (``resolve_identity_connect``)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_common.connect import resolve_identity_connect

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")
USER = UUID("33333333-3333-3333-3333-333333333333")


@dataclass
class _Wire:
    """Stand-in for the proto ``TenantContext`` (str fields)."""

    tenant_id: str = ""
    user_id: str = ""


def test_user_token_matching_wire_returns_token_identity() -> None:
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        tid, uid = resolve_identity_connect(_Wire(str(TENANT_A), str(USER)))
        assert (tid, uid) == (TENANT_A, USER)
    finally:
        reset_context(token)


def test_user_token_forged_wire_tenant_is_permission_denied() -> None:
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(ConnectError) as exc:
            resolve_identity_connect(_Wire(str(TENANT_B), str(USER)))
        assert exc.value.code == Code.PERMISSION_DENIED
    finally:
        reset_context(token)


def test_service_token_trusts_wire() -> None:
    token = set_context(TenantContext(tenant_id=UUID(int=0), user_id=UUID(int=0), is_service=True))
    try:
        tid, uid = resolve_identity_connect(_Wire(str(TENANT_B), str(USER)))
        assert (tid, uid) == (TENANT_B, USER)
    finally:
        reset_context(token)


def test_no_context_trusts_wire() -> None:
    tid, uid = resolve_identity_connect(_Wire(str(TENANT_A), str(USER)))
    assert (tid, uid) == (TENANT_A, USER)


def test_missing_wire_is_unauthenticated() -> None:
    with pytest.raises(ConnectError) as exc:
        resolve_identity_connect(_Wire("", ""))
    assert exc.value.code == Code.UNAUTHENTICATED


def test_bad_wire_uuid_is_invalid_argument() -> None:
    with pytest.raises(ConnectError) as exc:
        resolve_identity_connect(_Wire("not-a-uuid", "also-bad"))
    assert exc.value.code == Code.INVALID_ARGUMENT
