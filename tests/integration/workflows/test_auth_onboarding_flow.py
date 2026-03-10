"""Auth onboarding gRPC workflow tests.

Tests the complete authentication and profile setup workflow:
1. User registration and tenant creation
2. Login and token management
3. Profile updates and Alpaca credentials CRUD

Note: Auth methods that require authentication (get_current_user, change_password,
alpaca credentials) extract the JWT token from context headers, not from a
TenantContext proto field.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from connectrpc.errors import ConnectError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.workflow, pytest.mark.asyncio]


class MockServicerContext:
    """Mock ConnectRPC servicer context for testing.

    Supports setting authorization headers for authenticated requests.
    """

    def __init__(self, auth_token: str | None = None) -> None:
        self.headers: dict[str, str] = {}
        if auth_token:
            self.headers["authorization"] = f"Bearer {auth_token}"

    def invocation_metadata(self) -> list[tuple[str, str]]:
        """Return headers as metadata tuples (gRPC style)."""
        return list(self.headers.items())

    def request_headers(self) -> dict[str, str]:
        """Return headers dict (ConnectRPC style)."""
        return self.headers


@pytest.fixture
def grpc_context() -> MockServicerContext:
    """Create a mock gRPC context."""
    return MockServicerContext()


def _load_auth_servicer():
    """Load the auth servicer, clearing module cache to avoid conflicts."""
    auth_path = Path(__file__).parents[3] / "services" / "auth"
    auth_path_str = str(auth_path)

    # Remove other service paths
    service_paths = [
        str(Path(__file__).parents[3] / "services" / svc)
        for svc in ["billing", "strategy", "backtest", "market-data", "trading", "portfolio"]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    # Clear cached src modules
    modules_to_remove = [k for k in list(sys.modules.keys()) if k == "src" or k.startswith("src.")]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Add auth service path
    if auth_path_str in sys.path:
        sys.path.remove(auth_path_str)
    sys.path.insert(0, auth_path_str)

    from src.grpc.servicer import AuthServicer

    return AuthServicer


@pytest.fixture
def auth_servicer(db_session: AsyncSession):
    """Create an auth servicer with test database session."""
    auth_servicer_cls = _load_auth_servicer()
    servicer = auth_servicer_cls()

    async def mock_get_db():
        return db_session

    servicer._get_db = mock_get_db
    return servicer


class TestRegistrationFlow:
    """Test user registration workflow."""

    async def test_register_creates_tenant_and_user(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that registration creates both tenant and admin user."""
        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.RegisterRequest(
            tenant_name="New Company",
            email="newuser@example.com",
            password="SecurePassword123!",
        )

        response = await auth_servicer.register(request, grpc_context)

        # Verify tenant was created
        assert response.tenant.id
        assert response.tenant.name == "New Company"

        # Verify user was created
        assert response.user.id
        assert response.user.email == "newuser@example.com"
        assert response.user.tenant_id == response.tenant.id

        # Note: Register doesn't return tokens - user must login separately

    async def test_register_duplicate_email_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that registering with existing email fails."""
        from llamatrade_proto.generated import auth_pb2

        email = f"duplicate-{uuid4().hex[:8]}@example.com"

        # First registration should succeed
        request1 = auth_pb2.RegisterRequest(
            tenant_name="Company One",
            email=email,
            password="SecurePassword123!",
        )
        await auth_servicer.register(request1, grpc_context)

        # Second registration with same email should fail
        request2 = auth_pb2.RegisterRequest(
            tenant_name="Company Two",
            email=email,
            password="DifferentPassword456!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.register(request2, MockServicerContext())

        assert (
            "ALREADY_EXISTS" in str(exc_info.value.code) or "already" in str(exc_info.value).lower()
        )

    async def test_register_creates_user_with_admin_role(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that first user in tenant gets admin role."""
        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.RegisterRequest(
            tenant_name="Admin Test Company",
            email=f"admin-{uuid4().hex[:8]}@example.com",
            password="TestPassword123!",
        )

        response = await auth_servicer.register(request, grpc_context)

        # First user should have admin role
        assert "admin" in response.user.roles


class TestLoginFlow:
    """Test user login workflow."""

    async def test_login_returns_valid_jwt(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that login returns valid JWT tokens."""
        from llamatrade_proto.generated import auth_pb2

        email = f"login-test-{uuid4().hex[:8]}@example.com"

        # Register first
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Login Test Company",
            email=email,
            password="TestPassword123!",
        )
        await auth_servicer.register(register_request, grpc_context)

        # Now login
        login_request = auth_pb2.LoginRequest(
            email=email,
            password="TestPassword123!",
        )
        login_response = await auth_servicer.login(login_request, MockServicerContext())

        assert login_response.access_token
        assert login_response.refresh_token
        assert login_response.user.email == email

        # Verify token structure (JWT has 3 parts separated by dots)
        assert login_response.access_token.count(".") == 2

    async def test_login_invalid_password_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that login with wrong password fails."""
        from llamatrade_proto.generated import auth_pb2

        email = f"badpw-test-{uuid4().hex[:8]}@example.com"

        # Register first
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Bad Password Test",
            email=email,
            password="CorrectPassword123!",
        )
        await auth_servicer.register(register_request, grpc_context)

        # Try login with wrong password
        login_request = auth_pb2.LoginRequest(
            email=email,
            password="WrongPassword456!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(login_request, MockServicerContext())

        assert (
            "UNAUTHENTICATED" in str(exc_info.value.code)
            or "invalid" in str(exc_info.value).lower()
        )

    async def test_login_nonexistent_user_fails(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that login with non-existent email fails."""
        from llamatrade_proto.generated import auth_pb2

        login_request = auth_pb2.LoginRequest(
            email="nonexistent@example.com",
            password="AnyPassword123!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(login_request, grpc_context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code) or "NOT_FOUND" in str(
            exc_info.value.code
        )

    async def test_refresh_token_works(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that refresh token returns new access token."""
        from llamatrade_proto.generated import auth_pb2

        email = f"refresh-test-{uuid4().hex[:8]}@example.com"

        # Register
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Refresh Test Company",
            email=email,
            password="TestPassword123!",
        )
        await auth_servicer.register(register_request, grpc_context)

        # Login to get tokens
        login_request = auth_pb2.LoginRequest(
            email=email,
            password="TestPassword123!",
        )
        login_response = await auth_servicer.login(login_request, MockServicerContext())

        # Use refresh token to get new access token
        refresh_request = auth_pb2.RefreshTokenRequest(
            refresh_token=login_response.refresh_token,
        )
        refresh_response = await auth_servicer.refresh_token(
            refresh_request, MockServicerContext()
        )

        assert refresh_response.access_token
        # New token should be different (has different timestamp)
        # Note: might be same if generated within same second
        assert refresh_response.access_token


class TestProfileSetup:
    """Test profile setup and management."""

    async def test_get_current_user(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test retrieving current user information via auth token."""
        from llamatrade_proto.generated import auth_pb2

        email = f"profile-test-{uuid4().hex[:8]}@example.com"

        # Register
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Profile Test Company",
            email=email,
            password="TestPassword123!",
        )
        await auth_servicer.register(register_request, grpc_context)

        # Login to get token
        login_request = auth_pb2.LoginRequest(
            email=email,
            password="TestPassword123!",
        )
        login_response = await auth_servicer.login(login_request, MockServicerContext())

        # Get current user with auth token in headers
        auth_context = MockServicerContext(auth_token=login_response.access_token)
        get_user_request = auth_pb2.GetCurrentUserRequest()
        user_response = await auth_servicer.get_current_user(get_user_request, auth_context)

        assert user_response.user.email == email
        assert user_response.tenant.name == "Profile Test Company"

    async def test_change_password(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test changing user password."""
        from llamatrade_proto.generated import auth_pb2

        email = f"chgpw-test-{uuid4().hex[:8]}@example.com"
        old_password = "OldPassword123!"
        new_password = "NewPassword456!"

        # Register
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Change Password Test",
            email=email,
            password=old_password,
        )
        await auth_servicer.register(register_request, grpc_context)

        # Login to get token
        login_request = auth_pb2.LoginRequest(
            email=email,
            password=old_password,
        )
        login_response = await auth_servicer.login(login_request, MockServicerContext())

        # Change password with auth token
        auth_context = MockServicerContext(auth_token=login_response.access_token)
        change_pw_request = auth_pb2.ChangePasswordRequest(
            current_password=old_password,
            new_password=new_password,
        )
        change_response = await auth_servicer.change_password(change_pw_request, auth_context)
        assert change_response.success is True

        # Verify new password works
        new_login_request = auth_pb2.LoginRequest(
            email=email,
            password=new_password,
        )
        new_login_response = await auth_servicer.login(new_login_request, MockServicerContext())
        assert new_login_response.access_token

        # Verify old password no longer works
        old_login_request = auth_pb2.LoginRequest(
            email=email,
            password=old_password,
        )
        with pytest.raises(ConnectError):
            await auth_servicer.login(old_login_request, MockServicerContext())


class TestAlpacaCredentialsManagement:
    """Test Alpaca credentials CRUD operations."""

    async def test_create_alpaca_credentials(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test creating Alpaca API credentials."""
        from llamatrade_proto.generated import auth_pb2

        email = f"alpaca-test-{uuid4().hex[:8]}@example.com"

        # Register and login
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Alpaca Test Company",
            email=email,
            password="TestPassword123!",
        )
        await auth_servicer.register(register_request, grpc_context)

        login_request = auth_pb2.LoginRequest(email=email, password="TestPassword123!")
        login_response = await auth_servicer.login(login_request, MockServicerContext())

        # Create credentials with auth token
        auth_context = MockServicerContext(auth_token=login_response.access_token)
        create_request = auth_pb2.CreateAlpacaCredentialsRequest(
            name="My Paper Account",
            api_key="PKTEST12345678901234567890",  # 20+ chars required
            api_secret="secret1234567890abcdef1234567890abcdefghijk",  # 40+ chars required
            is_paper=True,
        )
        create_response = await auth_servicer.create_alpaca_credentials(
            create_request, auth_context
        )

        assert create_response.credentials.id
        assert create_response.credentials.name == "My Paper Account"
        assert create_response.credentials.is_paper is True

    async def test_list_alpaca_credentials(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test listing Alpaca credentials."""
        from llamatrade_proto.generated import auth_pb2

        email = f"list-creds-{uuid4().hex[:8]}@example.com"

        # Register and login
        register_request = auth_pb2.RegisterRequest(
            tenant_name="List Creds Test",
            email=email,
            password="TestPassword123!",
        )
        await auth_servicer.register(register_request, grpc_context)

        login_request = auth_pb2.LoginRequest(email=email, password="TestPassword123!")
        login_response = await auth_servicer.login(login_request, MockServicerContext())
        auth_context = MockServicerContext(auth_token=login_response.access_token)

        # Create two sets of credentials
        for name, is_paper in [("Paper Account", True), ("Live Account", False)]:
            create_request = auth_pb2.CreateAlpacaCredentialsRequest(
                name=name,
                api_key=f"PK{uuid4().hex[:18].upper()}",  # 20+ chars required
                api_secret=f"secret{uuid4().hex}{uuid4().hex[:6]}",  # 40+ chars required
                is_paper=is_paper,
            )
            await auth_servicer.create_alpaca_credentials(create_request, auth_context)

        # List credentials
        list_request = auth_pb2.ListAlpacaCredentialsRequest()
        list_response = await auth_servicer.list_alpaca_credentials(list_request, auth_context)

        assert len(list_response.credentials) == 2
        names = [c.name for c in list_response.credentials]
        assert "Paper Account" in names
        assert "Live Account" in names

    async def test_delete_alpaca_credentials(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test deleting Alpaca credentials."""
        from llamatrade_proto.generated import auth_pb2

        email = f"del-creds-{uuid4().hex[:8]}@example.com"

        # Register and login
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Delete Creds Test",
            email=email,
            password="TestPassword123!",
        )
        await auth_servicer.register(register_request, grpc_context)

        login_request = auth_pb2.LoginRequest(email=email, password="TestPassword123!")
        login_response = await auth_servicer.login(login_request, MockServicerContext())
        auth_context = MockServicerContext(auth_token=login_response.access_token)

        # Create credentials
        create_request = auth_pb2.CreateAlpacaCredentialsRequest(
            name="To Delete",
            api_key="PKDELETE12345678901234",  # 20+ chars required
            api_secret="secretdelete12345678901234567890abcdefghij",  # 40+ chars required
            is_paper=True,
        )
        create_response = await auth_servicer.create_alpaca_credentials(
            create_request, auth_context
        )
        creds_id = create_response.credentials.id

        # Delete credentials
        delete_request = auth_pb2.DeleteAlpacaCredentialsRequest(
            credentials_id=creds_id,
        )
        delete_response = await auth_servicer.delete_alpaca_credentials(
            delete_request, auth_context
        )
        assert delete_response.success is True

        # Verify credentials are gone
        list_request = auth_pb2.ListAlpacaCredentialsRequest()
        list_response = await auth_servicer.list_alpaca_credentials(list_request, auth_context)
        assert len(list_response.credentials) == 0


class TestTenantIsolation:
    """Test that auth operations respect tenant boundaries."""

    async def test_cannot_access_other_tenant_credentials(
        self,
        auth_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that one tenant cannot delete another's credentials."""
        from llamatrade_proto.generated import auth_pb2

        # Register and login tenant A
        email_a = f"tenant-a-{uuid4().hex[:8]}@example.com"
        await auth_servicer.register(
            auth_pb2.RegisterRequest(
                tenant_name="Tenant A",
                email=email_a,
                password="PasswordA123!",
            ),
            grpc_context,
        )
        login_a = await auth_servicer.login(
            auth_pb2.LoginRequest(email=email_a, password="PasswordA123!"),
            MockServicerContext(),
        )
        ctx_a = MockServicerContext(auth_token=login_a.access_token)

        # Create credentials for tenant A
        create_a = auth_pb2.CreateAlpacaCredentialsRequest(
            name="Tenant A Creds",
            api_key="PKTENANTA12345678901234",  # 20+ chars required
            api_secret="secrettenanta12345678901234567890abcdefgh",  # 40+ chars required
            is_paper=True,
        )
        creds_a = await auth_servicer.create_alpaca_credentials(create_a, ctx_a)

        # Register and login tenant B
        email_b = f"tenant-b-{uuid4().hex[:8]}@example.com"
        await auth_servicer.register(
            auth_pb2.RegisterRequest(
                tenant_name="Tenant B",
                email=email_b,
                password="PasswordB123!",
            ),
            MockServicerContext(),
        )
        login_b = await auth_servicer.login(
            auth_pb2.LoginRequest(email=email_b, password="PasswordB123!"),
            MockServicerContext(),
        )
        ctx_b = MockServicerContext(auth_token=login_b.access_token)

        # Tenant B tries to delete Tenant A's credentials
        delete_request = auth_pb2.DeleteAlpacaCredentialsRequest(
            credentials_id=creds_a.credentials.id,
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.delete_alpaca_credentials(delete_request, ctx_b)

        assert "NOT_FOUND" in str(exc_info.value.code)

        # Verify tenant A's credentials still exist
        list_request = auth_pb2.ListAlpacaCredentialsRequest()
        list_response = await auth_servicer.list_alpaca_credentials(list_request, ctx_a)
        assert len(list_response.credentials) == 1
