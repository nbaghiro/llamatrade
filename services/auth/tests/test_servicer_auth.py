"""Verified-principal identity branches of the auth servicer (no HTTP layer).

``set_context(TenantContext(...))`` plays the part of ``AuthMiddleware``. The
servicer must take identity from that verified principal, never from the wire
body or the bearer header: cross-tenant reads return NOT_FOUND (no existence
leak), permission checks read roles from the token, and a service principal is
refused wherever a user identity is required.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from google.protobuf.message import Message

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_proto.generated import auth_pb2, common_pb2
from tests.fakes import (
    MockAsyncSession,
    MockRequestContext,
    MockTenant,
    MockUser,
    create_test_token,
)

if TYPE_CHECKING:
    from src.grpc.servicer import AuthServicer

os.environ["JWT_SECRET"] = "test-secret"
os.environ["JWT_ALGORITHM"] = "HS256"

TENANT_A = uuid4()
TENANT_B = uuid4()
USER = uuid4()


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


@pytest.fixture
def user_principal() -> Iterator[TenantContext]:
    """Verified user principal for tenant A, as AuthMiddleware would set it."""
    ctx = TenantContext(tenant_id=TENANT_A, user_id=USER, roles=["viewer"])
    token = set_context(ctx)
    try:
        yield ctx
    finally:
        reset_context(token)


@pytest.fixture
def service_principal() -> Iterator[TenantContext]:
    """Verified internal service principal (S2S), as AuthMiddleware would set it."""
    ctx = TenantContext(tenant_id=UUID(int=0), user_id=UUID(int=0), is_service=True, svc="trading")
    token = set_context(ctx)
    try:
        yield ctx
    finally:
        reset_context(token)


class TestGetUserCrossTenantGuard:
    """get_user: a user token reads only its own tenant; NOT_FOUND otherwise."""

    async def test_cross_tenant_read_is_not_found(
        self,
        servicer: AuthServicer,
        mock_db: MockAsyncSession,
        user_principal: TenantContext,
    ) -> None:
        foreign = MockUser(tenant_id=TENANT_B)
        mock_db._query_result = foreign

        with pytest.raises(ConnectError) as exc_info:
            await servicer.get_user(
                auth_pb2.GetUserRequest(user_id=str(foreign.id)), MockRequestContext()
            )

        assert exc_info.value.code == Code.NOT_FOUND

    async def test_cross_tenant_hit_and_miss_are_indistinguishable(
        self,
        servicer: AuthServicer,
        mock_db: MockAsyncSession,
        user_principal: TenantContext,
    ) -> None:
        """The error for another tenant's user matches a plain miss exactly, so
        the guard leaks no existence signal."""
        requested = uuid4()
        request = auth_pb2.GetUserRequest(user_id=str(requested))

        mock_db._query_result = MockUser(id=requested, tenant_id=TENANT_B)
        with pytest.raises(ConnectError) as foreign_exc:
            await servicer.get_user(request, MockRequestContext())

        mock_db._query_result = None
        with pytest.raises(ConnectError) as missing_exc:
            await servicer.get_user(request, MockRequestContext())

        assert foreign_exc.value.code == missing_exc.value.code == Code.NOT_FOUND
        assert str(foreign_exc.value) == str(missing_exc.value)

    async def test_same_tenant_read_succeeds(
        self,
        servicer: AuthServicer,
        mock_db: MockAsyncSession,
        user_principal: TenantContext,
    ) -> None:
        user = MockUser(tenant_id=TENANT_A)
        mock_db._query_result = user

        response = await servicer.get_user(
            auth_pb2.GetUserRequest(user_id=str(user.id)), MockRequestContext()
        )

        assert response.user.id == str(user.id)
        assert response.user.tenant_id == str(TENANT_A)

    async def test_service_principal_reads_any_tenant(
        self,
        servicer: AuthServicer,
        mock_db: MockAsyncSession,
        service_principal: TenantContext,
    ) -> None:
        user = MockUser(tenant_id=TENANT_B)
        mock_db._query_result = user

        response = await servicer.get_user(
            auth_pb2.GetUserRequest(user_id=str(user.id)), MockRequestContext()
        )

        assert response.user.tenant_id == str(TENANT_B)


class TestGetTenantCrossTenantGuard:
    """get_tenant: a user token reads only its own tenant; NOT_FOUND otherwise."""

    async def test_cross_tenant_is_not_found_before_any_query(
        self, servicer: AuthServicer, user_principal: TenantContext
    ) -> None:
        """The guard short-circuits before the database is ever touched."""

        async def forbidden_db() -> MockAsyncSession:
            raise AssertionError("get_tenant must not reach the DB for a foreign tenant")

        servicer._get_db = forbidden_db

        with pytest.raises(ConnectError) as exc_info:
            await servicer.get_tenant(
                auth_pb2.GetTenantRequest(tenant_id=str(TENANT_B)), MockRequestContext()
            )

        assert exc_info.value.code == Code.NOT_FOUND

    async def test_same_tenant_read_succeeds(
        self,
        servicer: AuthServicer,
        mock_db: MockAsyncSession,
        user_principal: TenantContext,
    ) -> None:
        mock_db._query_result = MockTenant(id=TENANT_A)

        response = await servicer.get_tenant(
            auth_pb2.GetTenantRequest(tenant_id=str(TENANT_A)), MockRequestContext()
        )

        assert response.tenant.id == str(TENANT_A)

    async def test_service_principal_reads_any_tenant(
        self,
        servicer: AuthServicer,
        mock_db: MockAsyncSession,
        service_principal: TenantContext,
    ) -> None:
        mock_db._query_result = MockTenant(id=TENANT_B)

        response = await servicer.get_tenant(
            auth_pb2.GetTenantRequest(tenant_id=str(TENANT_B)), MockRequestContext()
        )

        assert response.tenant.id == str(TENANT_B)


class TestCheckPermissionRoleSource:
    """check_permission authorizes off the verified token roles, not the wire body."""

    async def test_wire_admin_claim_cannot_escalate_token_viewer(
        self, servicer: AuthServicer, user_principal: TenantContext
    ) -> None:
        request = auth_pb2.CheckPermissionRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TENANT_A), user_id=str(USER), roles=["admin"]
            ),
            resource="strategies",
            action="create",
        )

        response = await servicer.check_permission(request, MockRequestContext())

        assert response.allowed is False

    async def test_token_roles_grant_without_wire_roles(
        self, servicer: AuthServicer, user_principal: TenantContext
    ) -> None:
        request = auth_pb2.CheckPermissionRequest(
            context=common_pb2.TenantContext(tenant_id=str(TENANT_A), user_id=str(USER)),
            resource="strategies",
            action="read",
        )

        response = await servicer.check_permission(request, MockRequestContext())

        assert response.allowed is True


_USER_ONLY_RPCS: list[tuple[str, Message]] = [
    (
        "change_password",
        auth_pb2.ChangePasswordRequest(current_password="OldPass123!", new_password="NewPass456!"),
    ),
    ("get_current_user", auth_pb2.GetCurrentUserRequest()),
    (
        "create_alpaca_credentials",
        auth_pb2.CreateAlpacaCredentialsRequest(
            name="Keys",
            api_key="PKTEST12345678901234",
            api_secret="SKTEST12345678901234567890123456789012345",
            is_paper=True,
        ),
    ),
    ("get_alpaca_credentials", auth_pb2.GetAlpacaCredentialsRequest(credentials_id=str(uuid4()))),
    ("list_alpaca_credentials", auth_pb2.ListAlpacaCredentialsRequest()),
    (
        "delete_alpaca_credentials",
        auth_pb2.DeleteAlpacaCredentialsRequest(credentials_id=str(uuid4())),
    ),
    (
        "validate_alpaca_credentials",
        auth_pb2.ValidateAlpacaCredentialsRequest(api_key="PK", api_secret="sk", is_paper=True),
    ),
]


class TestServiceTokenRejectedForUserRPCs:
    """A service principal is refused wherever a user identity is required."""

    @pytest.mark.parametrize(
        "method_name,request_msg",
        _USER_ONLY_RPCS,
        ids=[name for name, _ in _USER_ONLY_RPCS],
    )
    async def test_service_principal_is_unauthenticated(
        self,
        servicer: AuthServicer,
        service_principal: TenantContext,
        method_name: str,
        request_msg: Message,
    ) -> None:
        with pytest.raises(ConnectError) as exc_info:
            await getattr(servicer, method_name)(request_msg, MockRequestContext())

        assert exc_info.value.code == Code.UNAUTHENTICATED
        assert "user token" in str(exc_info.value).lower()


class TestPrincipalPrecedence:
    """The middleware-verified principal is the identity, not the bearer header."""

    async def test_user_principal_authenticates_without_bearer_header(
        self,
        servicer: AuthServicer,
        mock_db: MockAsyncSession,
        user_principal: TenantContext,
    ) -> None:
        response = await servicer.list_alpaca_credentials(
            auth_pb2.ListAlpacaCredentialsRequest(), MockRequestContext()
        )

        assert list(response.credentials) == []

    async def test_verified_principal_outranks_bearer_header(
        self,
        servicer: AuthServicer,
        mock_db: MockAsyncSession,
        user_principal: TenantContext,
    ) -> None:
        """A tenant-B bearer header cannot override the verified tenant-A principal."""
        header_token = create_test_token(str(uuid4()), str(TENANT_B))
        ctx = MockRequestContext(headers={"authorization": f"Bearer {header_token}"})
        mock_db._query_result = MockTenant(id=TENANT_B)

        with pytest.raises(ConnectError) as exc_info:
            await servicer.get_tenant(auth_pb2.GetTenantRequest(tenant_id=str(TENANT_B)), ctx)

        assert exc_info.value.code == Code.NOT_FOUND
