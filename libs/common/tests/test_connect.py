"""Tests for the connectrpc auth adapter (``resolve_identity_connect``)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_common.connect import (
    handle_service_errors,
    parse_uuid,
    resolve_identity_connect,
)

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


def test_user_token_forged_wire_user_is_permission_denied() -> None:
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(ConnectError) as exc:
            resolve_identity_connect(_Wire(str(TENANT_A), "99999999-9999-9999-9999-999999999999"))
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


class TestParseUuid:
    """Shared UUID parsing to a user-safe ConnectError."""

    def test_valid(self) -> None:
        assert parse_uuid(str(TENANT_A), "tenant_id") == TENANT_A

    def test_empty_is_required(self) -> None:
        with pytest.raises(ConnectError) as exc:
            parse_uuid("", "tenant_id")
        assert exc.value.code == Code.INVALID_ARGUMENT
        assert "required" in exc.value.message

    def test_invalid_is_bad_uuid(self) -> None:
        with pytest.raises(ConnectError) as exc:
            parse_uuid("not-a-uuid", "tenant_id")
        assert exc.value.code == Code.INVALID_ARGUMENT
        assert "valid UUID" in exc.value.message


class TestHandleServiceErrors:
    """Shared decorator mapping database/service errors to safe ConnectErrors."""

    async def test_passes_through_result(self) -> None:
        @handle_service_errors
        async def ok() -> int:
            return 42

        assert await ok() == 42

    async def test_connect_error_reraised_unchanged(self) -> None:
        @handle_service_errors
        async def boom() -> None:
            raise ConnectError(Code.NOT_FOUND, "nope")

        with pytest.raises(ConnectError) as exc:
            await boom()
        assert exc.value.code == Code.NOT_FOUND
        assert exc.value.message == "nope"

    async def test_integrity_error_generic_message_no_sql_leak(self) -> None:
        @handle_service_errors
        async def boom() -> None:
            raise IntegrityError("INSERT INTO secrets", {}, Exception("dup"))

        with pytest.raises(ConnectError) as exc:
            await boom()
        assert exc.value.code == Code.FAILED_PRECONDITION
        assert "constraint" in exc.value.message.lower()
        assert "INSERT" not in exc.value.message

    async def test_integrity_error_hook_message_used(self) -> None:
        def hook(_e: IntegrityError) -> str | None:
            return "A strategy with this name already exists."

        @handle_service_errors(on_integrity_error=hook)
        async def boom() -> None:
            raise IntegrityError("INSERT", {}, Exception("uq_strategy_tenant_name"))

        with pytest.raises(ConnectError) as exc:
            await boom()
        assert exc.value.code == Code.FAILED_PRECONDITION
        assert exc.value.message == "A strategy with this name already exists."

    async def test_integrity_hook_none_falls_back_to_generic(self) -> None:
        def hook(_e: IntegrityError) -> str | None:
            return None

        @handle_service_errors(on_integrity_error=hook)
        async def boom() -> None:
            raise IntegrityError("INSERT", {}, Exception("x"))

        with pytest.raises(ConnectError) as exc:
            await boom()
        assert "constraint" in exc.value.message.lower()

    async def test_operational_error_is_unavailable(self) -> None:
        @handle_service_errors
        async def boom() -> None:
            raise OperationalError("SELECT 1", {}, Exception("down"))

        with pytest.raises(ConnectError) as exc:
            await boom()
        assert exc.value.code == Code.UNAVAILABLE

    async def test_sqlalchemy_error_is_internal_no_leak(self) -> None:
        @handle_service_errors
        async def boom() -> None:
            raise SQLAlchemyError("secret detail")

        with pytest.raises(ConnectError) as exc:
            await boom()
        assert exc.value.code == Code.INTERNAL
        assert "secret detail" not in exc.value.message

    async def test_value_error_is_invalid_argument_with_message(self) -> None:
        @handle_service_errors
        async def boom() -> None:
            raise ValueError("bad input")

        with pytest.raises(ConnectError) as exc:
            await boom()
        assert exc.value.code == Code.INVALID_ARGUMENT
        assert exc.value.message == "bad input"

    async def test_unexpected_error_is_internal_no_leak(self) -> None:
        @handle_service_errors
        async def boom() -> None:
            raise RuntimeError("internal hostname db-prod-1")

        with pytest.raises(ConnectError) as exc:
            await boom()
        assert exc.value.code == Code.INTERNAL
        assert "db-prod-1" not in exc.value.message
