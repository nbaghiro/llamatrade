"""Tests for Auth Connect servicer.

Tests the AuthServicer directly without HTTP layer.
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import bcrypt
import jwt
import pytest
from connectrpc.errors import ConnectError

if TYPE_CHECKING:
    from src.grpc.servicer import AuthServicer

# Set test environment before importing servicer
os.environ["JWT_SECRET"] = "test-secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"

JWT_SECRET = "test-secret"
JWT_ALGORITHM = "HS256"


# ===================
# Mock Classes
# ===================


class MockUser:
    """Mock User database model."""

    def __init__(
        self,
        id: UUID | None = None,
        tenant_id: UUID | None = None,
        email: str = "test@example.com",
        password: str = "Test123!",
        first_name: str = "Test",
        last_name: str = "User",
        role: str = "admin",
        is_active: bool = True,
        avatar_url: str | None = None,
    ) -> None:
        self.id = id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.email = email
        self.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.is_active = is_active
        self.avatar_url = avatar_url
        self.created_at = datetime.now(UTC)
        self.last_login: datetime | None = None


class MockTenant:
    """Mock Tenant database model."""

    def __init__(
        self,
        id: UUID | None = None,
        name: str = "Test Tenant",
        slug: str = "test-tenant",
        is_active: bool = True,
    ) -> None:
        self.id = id or uuid4()
        self.name = name
        self.slug = slug
        self.is_active = is_active
        self.created_at = datetime.now(UTC)
        self.settings: dict[str, str] = {}


_STANDARD_TEST_API_KEY = "testkey_secretpart123"


def _default_key_hash() -> str:
    import hashlib

    return hashlib.sha256(_STANDARD_TEST_API_KEY.encode()).hexdigest()


class MockAPIKey:
    """Mock APIKey database model."""

    def __init__(
        self,
        id: UUID | None = None,
        tenant_id: UUID | None = None,
        user_id: UUID | None = None,
        name: str = "Test Key",
        key_prefix: str = "testkey_",
        key_hash: str | None = None,
        scopes: list[str] | None = None,
        is_active: bool = True,
        expires_at: datetime | None = None,
    ) -> None:
        self.id = id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.user_id = user_id
        self.name = name
        self.key_prefix = key_prefix
        self.key_hash = key_hash or _default_key_hash()
        self.scopes = scopes or ["read", "write"]
        self.is_active = is_active
        self.expires_at = expires_at
        self.last_used_at: datetime | None = None
        self.created_at = datetime.now(UTC)


class MockRequestContext:
    """Mock ConnectRPC RequestContext."""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}

    def request_headers(self) -> dict[str, str]:
        """Return request headers (ConnectRPC API)."""
        return self.headers


class MockAsyncSession:
    """Mock async database session."""

    def __init__(self) -> None:
        self._users: dict[str, MockUser] = {}
        self._tenants: dict[str, MockTenant] = {}
        self._api_keys: dict[str, MockAPIKey] = {}
        self._query_result: MockUser | MockTenant | MockAPIKey | None = None

    def set_user(self, user: MockUser) -> None:
        self._users[str(user.id)] = user
        self._users[user.email] = user

    def set_tenant(self, tenant: MockTenant) -> None:
        self._tenants[str(tenant.id)] = tenant

    def set_api_key(self, api_key: MockAPIKey) -> None:
        self._api_keys[api_key.key_prefix] = api_key

    async def execute(self, query: object) -> MagicMock:
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._query_result
        rows = [self._query_result] if self._query_result is not None else []
        result.scalars.return_value.all.return_value = rows
        return result

    async def scalar(self, query: object) -> object | None:
        return self._query_result

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    def add(self, obj: object) -> None:
        # Ensure created_at is set
        if hasattr(obj, "created_at") and getattr(obj, "created_at") is None:
            setattr(obj, "created_at", datetime.now(UTC))
        if hasattr(obj, "email"):
            self.set_user(obj)
        elif hasattr(obj, "slug"):
            self.set_tenant(obj)

    async def __aenter__(self) -> MockAsyncSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        pass


class FakeRateLimiter:
    """Records check_and_count calls and returns a fixed decision."""

    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, int, int]] = []

    async def check_and_count(self, key: str, limit: int, window_seconds: int) -> bool:
        self.calls.append((key, limit, window_seconds))
        return self.allowed


class FakeRevocationStore:
    """In-memory revocation store mirroring llamatrade_common.RevocationStore."""

    def __init__(self) -> None:
        self.revoked_jtis: dict[str, int] = {}
        self.user_cutoffs: dict[str, int] = {}

    async def revoke_token(self, jti: str, exp: int) -> None:
        self.revoked_jtis[jti] = exp

    async def revoke_all_for_user(self, user_id: str, now: int) -> None:
        self.user_cutoffs[user_id] = now

    async def is_revoked(self, claims: dict[str, object]) -> bool:
        if str(claims.get("jti", "")) in self.revoked_jtis:
            return True
        cutoff = self.user_cutoffs.get(str(claims.get("sub")))
        iat = claims.get("iat")
        return cutoff is not None and isinstance(iat, int | float) and iat < cutoff


# ===================
# Fixtures
# ===================


@pytest.fixture
def mock_db() -> MockAsyncSession:
    """Create mock database session."""
    return MockAsyncSession()


@pytest.fixture
def auth_servicer(mock_db: MockAsyncSession) -> AuthServicer:
    """Create AuthServicer with mocked database and Redis features off."""
    from src.grpc.servicer import AuthServicer

    servicer = AuthServicer()

    async def mock_get_db() -> MockAsyncSession:
        return mock_db

    servicer._get_db = mock_get_db
    servicer._rate_limiter = None
    servicer._revocation = None
    return servicer


@pytest.fixture
def context() -> MockRequestContext:
    """Create mock request context."""
    return MockRequestContext()


@pytest.fixture
def auth_context(context: MockRequestContext) -> MockRequestContext:
    """Create request context with valid auth token."""
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    token = create_test_token(user_id, tenant_id)
    return MockRequestContext(headers={"authorization": f"Bearer {token}"})


def create_test_token(
    user_id: str,
    tenant_id: str,
    token_type: str = "access",
    expired: bool = False,
    jti: str | None = None,
) -> str:
    """Create a test JWT token."""
    now = datetime.now(UTC)
    if expired:
        exp = now - timedelta(hours=1)
    else:
        exp = now + timedelta(hours=1)

    payload: dict[str, object] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": "test@example.com",
        "roles": ["admin"],
        "type": token_type,
        "iat": now,
        "exp": exp,
    }
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ===================
# Register Tests
# ===================


class TestRegister:
    """Tests for register RPC."""

    async def test_register_success(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test successful registration creates user and tenant."""
        from llamatrade_proto.generated import auth_pb2

        # Mock no existing user
        mock_db._query_result = None

        request = auth_pb2.RegisterRequest(
            tenant_name="Test Company",
            email="newuser@example.com",
            password="SecurePass123!",
            first_name="New",
            last_name="User",
        )

        response = await auth_servicer.register(request, context)

        assert response.user.email == "newuser@example.com"
        assert response.user.first_name == "New"
        assert response.user.last_name == "User"
        assert response.tenant.name == "Test Company"
        assert response.user.is_active is True

    async def test_register_duplicate_email(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test registration fails for existing email."""
        from llamatrade_proto.generated import auth_pb2

        # Mock existing user
        mock_db._query_result = MockUser(email="existing@example.com")

        request = auth_pb2.RegisterRequest(
            tenant_name="Test Company",
            email="existing@example.com",
            password="SecurePass123!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.register(request, context)

        assert "ALREADY_EXISTS" in str(exc_info.value.code)

    async def test_register_weak_password(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test registration rejects a weak password."""
        from llamatrade_proto.generated import auth_pb2

        mock_db._query_result = None

        request = auth_pb2.RegisterRequest(
            tenant_name="Test Company",
            email="weakpass@example.com",
            password="short",
            first_name="New",
            last_name="User",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.register(request, context)

        assert "INVALID_ARGUMENT" in str(exc_info.value.code)

    async def test_register_matches_oauth_signup_user_shape(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Register delegates to create_tenant_and_user: both paths produce
        equivalent user rows."""
        import bcrypt as bcrypt_mod

        from llamatrade_proto.generated import auth_pb2

        from src.session import create_tenant_and_user

        mock_db._query_result = None
        request = auth_pb2.RegisterRequest(
            tenant_name="Acme",
            email="rpc@example.com",
            password="SecurePass123",
            first_name="Ada",
            last_name="Lovelace",
        )
        await auth_servicer.register(request, context)
        rpc_user = mock_db._users["rpc@example.com"]

        oauth_db = MockAsyncSession()
        oauth_user, _ = await create_tenant_and_user(
            oauth_db,
            email="oauth@example.com",
            password="SecurePass123",
            tenant_name="Acme",
            first_name="Ada",
            last_name="Lovelace",
        )

        for field in ("role", "is_active", "first_name", "last_name"):
            assert getattr(rpc_user, field) == getattr(oauth_user, field)
        assert bcrypt_mod.checkpw(b"SecurePass123", rpc_user.password_hash.encode())
        assert bcrypt_mod.checkpw(b"SecurePass123", oauth_user.password_hash.encode())


# ===================
# Login Tests
# ===================


class TestLogin:
    """Tests for login RPC."""

    async def test_login_success(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test successful login returns tokens and user."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser(email="test@example.com", password="Test123!")
        mock_db._query_result = user

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="Test123!",
        )

        response = await auth_servicer.login(request, context)

        assert response.access_token
        assert response.refresh_token
        assert response.user.email == "test@example.com"
        assert response.user.id == str(user.id)

    async def test_login_invalid_email(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test login fails for non-existent user."""
        from llamatrade_proto.generated import auth_pb2

        mock_db._query_result = None

        request = auth_pb2.LoginRequest(
            email="nonexistent@example.com",
            password="Test123!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_login_wrong_password(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test login fails for wrong password."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser(email="test@example.com", password="CorrectPass123!")
        mock_db._query_result = user

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="WrongPassword!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_login_inactive_user(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test login fails for inactive user."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser(email="test@example.com", password="Test123!", is_active=False)
        mock_db._query_result = user

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="Test123!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(request, context)

        assert "PERMISSION_DENIED" in str(exc_info.value.code)


# ===================
# ValidateToken Tests
# ===================


class TestValidateToken:
    """Tests for validate_token RPC."""

    async def test_validate_valid_token(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test validation of valid token."""
        from llamatrade_proto.generated import auth_pb2

        user_id = str(uuid4())
        tenant_id = str(uuid4())
        token = create_test_token(user_id, tenant_id)

        request = auth_pb2.ValidateTokenRequest(token=token)
        response = await auth_servicer.validate_token(request, context)

        assert response.valid is True
        assert response.context.user_id == user_id
        assert response.context.tenant_id == tenant_id
        assert response.token_type == "access"

    async def test_validate_expired_token(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test validation of expired token."""
        from llamatrade_proto.generated import auth_pb2

        user_id = str(uuid4())
        tenant_id = str(uuid4())
        token = create_test_token(user_id, tenant_id, expired=True)

        request = auth_pb2.ValidateTokenRequest(token=token)
        response = await auth_servicer.validate_token(request, context)

        assert response.valid is False

    async def test_validate_invalid_token(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test validation of invalid token."""
        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.ValidateTokenRequest(token="invalid.token.here")
        response = await auth_servicer.validate_token(request, context)

        assert response.valid is False

    async def test_validate_refresh_token_rejected(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """A refresh token is not a valid access credential: the type gate rejects it."""
        from llamatrade_proto.generated import auth_pb2

        user_id = str(uuid4())
        tenant_id = str(uuid4())
        token = create_test_token(user_id, tenant_id, token_type="refresh")

        request = auth_pb2.ValidateTokenRequest(token=token)
        response = await auth_servicer.validate_token(request, context)

        assert response.valid is False


# ===================
# RefreshToken Tests
# ===================


class TestRefreshToken:
    """Tests for refresh_token RPC."""

    async def test_refresh_token_success(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test successful token refresh."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser()
        mock_db._query_result = user
        refresh_token = create_test_token(str(user.id), str(user.tenant_id), token_type="refresh")

        request = auth_pb2.RefreshTokenRequest(refresh_token=refresh_token)
        response = await auth_servicer.refresh_token(request, context)

        assert response.access_token
        assert response.refresh_token
        assert response.access_token != refresh_token

    async def test_refresh_with_access_token_fails(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test refresh fails when using access token."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser()
        access_token = create_test_token(str(user.id), str(user.tenant_id), token_type="access")

        request = auth_pb2.RefreshTokenRequest(refresh_token=access_token)

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.refresh_token(request, context)

        assert "INVALID_ARGUMENT" in str(exc_info.value.code)

    async def test_refresh_expired_token_fails(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test refresh fails for expired token."""
        from llamatrade_proto.generated import auth_pb2

        user_id = str(uuid4())
        tenant_id = str(uuid4())
        expired_token = create_test_token(user_id, tenant_id, token_type="refresh", expired=True)

        request = auth_pb2.RefreshTokenRequest(refresh_token=expired_token)

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.refresh_token(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)


# ===================
# GetCurrentUser Tests
# ===================


class TestGetCurrentUser:
    """Tests for get_current_user RPC."""

    async def test_get_current_user_success(
        self, auth_servicer: AuthServicer, mock_db: MockAsyncSession
    ) -> None:
        """Test getting current user from token."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser()
        tenant = MockTenant(id=user.tenant_id)
        token = create_test_token(str(user.id), str(user.tenant_id))
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})

        # Mock database to return user then tenant
        call_count = [0]
        original_user = user
        original_tenant = tenant

        async def mock_execute(query: object) -> MagicMock:
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = original_user
            else:
                result.scalar_one_or_none.return_value = original_tenant
            return result

        mock_db.execute = mock_execute

        request = auth_pb2.GetCurrentUserRequest()
        response = await auth_servicer.get_current_user(request, context)

        assert response.user.id == str(user.id)
        assert response.user.email == user.email
        assert response.user.avatar_url == ""  # None avatar maps to empty string
        assert response.tenant.id == str(tenant.id)

    async def test_get_current_user_includes_avatar_url(
        self, auth_servicer: AuthServicer, mock_db: MockAsyncSession
    ) -> None:
        """The account's avatar_url flows through to the User proto."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser(avatar_url="https://cdn.example.com/alex.jpg")
        tenant = MockTenant(id=user.tenant_id)
        token = create_test_token(str(user.id), str(user.tenant_id))
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})

        call_count = [0]

        async def mock_execute(query: object) -> MagicMock:
            call_count[0] += 1
            result = MagicMock()
            result.scalar_one_or_none.return_value = user if call_count[0] == 1 else tenant
            return result

        mock_db.execute = mock_execute

        request = auth_pb2.GetCurrentUserRequest()
        response = await auth_servicer.get_current_user(request, context)

        assert response.user.avatar_url == "https://cdn.example.com/alex.jpg"

    async def test_get_current_user_no_token(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test getting current user without token fails."""
        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.GetCurrentUserRequest()

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.get_current_user(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_get_current_user_invalid_token(self, auth_servicer: AuthServicer) -> None:
        """Test getting current user with invalid token fails."""
        from llamatrade_proto.generated import auth_pb2

        context = MockRequestContext(headers={"authorization": "Bearer invalid.token"})
        request = auth_pb2.GetCurrentUserRequest()

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.get_current_user(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)


# ===================
# ChangePassword Tests
# ===================


class TestChangePassword:
    """Tests for change_password RPC."""

    async def test_change_password_success(
        self, auth_servicer: AuthServicer, mock_db: MockAsyncSession
    ) -> None:
        """Test successful password change."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser(password="OldPass123!")
        token = create_test_token(str(user.id), str(user.tenant_id))
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})
        mock_db._query_result = user

        request = auth_pb2.ChangePasswordRequest(
            current_password="OldPass123!",
            new_password="NewPass456!",
        )

        response = await auth_servicer.change_password(request, context)

        assert response.success is True
        assert "successfully" in response.message.lower()

    async def test_change_password_wrong_current(
        self, auth_servicer: AuthServicer, mock_db: MockAsyncSession
    ) -> None:
        """Test password change fails with wrong current password."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser(password="CorrectPass123!")
        token = create_test_token(str(user.id), str(user.tenant_id))
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})
        mock_db._query_result = user

        request = auth_pb2.ChangePasswordRequest(
            current_password="WrongPass123!",
            new_password="NewPass456!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.change_password(request, context)

        assert "INVALID_ARGUMENT" in str(exc_info.value.code)

    async def test_change_password_no_auth(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test password change fails without authentication."""
        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.ChangePasswordRequest(
            current_password="OldPass123!",
            new_password="NewPass456!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.change_password(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)


# ===================
# GetUser Tests
# ===================


class TestGetUser:
    """Tests for get_user RPC."""

    async def test_get_user_success(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test getting user by ID."""
        from llamatrade_proto.generated import auth_pb2

        user = MockUser()
        mock_db._query_result = user

        request = auth_pb2.GetUserRequest(user_id=str(user.id))
        response = await auth_servicer.get_user(request, context)

        assert response.user.id == str(user.id)
        assert response.user.email == user.email
        assert response.user.first_name == user.first_name

    async def test_get_user_not_found(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test getting non-existent user."""
        from llamatrade_proto.generated import auth_pb2

        mock_db._query_result = None

        request = auth_pb2.GetUserRequest(user_id=str(uuid4()))

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.get_user(request, context)

        assert "NOT_FOUND" in str(exc_info.value.code)


# ===================
# GetTenant Tests
# ===================


class TestGetTenant:
    """Tests for get_tenant RPC."""

    async def test_get_tenant_success(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test getting tenant by ID."""
        from llamatrade_proto.generated import auth_pb2

        tenant = MockTenant()
        mock_db._query_result = tenant

        request = auth_pb2.GetTenantRequest(tenant_id=str(tenant.id))
        response = await auth_servicer.get_tenant(request, context)

        assert response.tenant.id == str(tenant.id)
        assert response.tenant.name == tenant.name
        assert response.tenant.is_active == tenant.is_active

    async def test_get_tenant_not_found(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test getting non-existent tenant."""
        from llamatrade_proto.generated import auth_pb2

        mock_db._query_result = None

        request = auth_pb2.GetTenantRequest(tenant_id=str(uuid4()))

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.get_tenant(request, context)

        assert "NOT_FOUND" in str(exc_info.value.code)


# ===================
# CheckPermission Tests
# ===================


class TestCheckPermission:
    """Tests for check_permission RPC."""

    async def test_admin_has_full_access(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test admin role has full access."""
        from llamatrade_proto.generated import auth_pb2, common_pb2

        request = auth_pb2.CheckPermissionRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(uuid4()),
                user_id=str(uuid4()),
                roles=["admin"],
            ),
            resource="strategies",
            action="delete",
        )

        response = await auth_servicer.check_permission(request, context)
        assert response.allowed is True

    async def test_trader_has_limited_access(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test trader role has limited access."""
        from llamatrade_proto.generated import auth_pb2, common_pb2

        # Trader can create strategies
        request = auth_pb2.CheckPermissionRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(uuid4()),
                user_id=str(uuid4()),
                roles=["trader"],
            ),
            resource="strategies",
            action="create",
        )

        response = await auth_servicer.check_permission(request, context)
        assert response.allowed is True

    async def test_viewer_cannot_create(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test viewer role cannot create resources."""
        from llamatrade_proto.generated import auth_pb2, common_pb2

        request = auth_pb2.CheckPermissionRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(uuid4()),
                user_id=str(uuid4()),
                roles=["viewer"],
            ),
            resource="strategies",
            action="create",
        )

        response = await auth_servicer.check_permission(request, context)
        assert response.allowed is False

    async def test_viewer_can_read(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        """Test viewer role can read resources."""
        from llamatrade_proto.generated import auth_pb2, common_pb2

        request = auth_pb2.CheckPermissionRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(uuid4()),
                user_id=str(uuid4()),
                roles=["viewer"],
            ),
            resource="strategies",
            action="read",
        )

        response = await auth_servicer.check_permission(request, context)
        assert response.allowed is True


# ===================
# ValidateAPIKey Tests
# ===================


class TestValidateAPIKey:
    """Tests for validate_a_p_i_key RPC."""

    async def test_validate_valid_api_key(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test validation of valid API key."""
        from llamatrade_proto.generated import auth_pb2

        api_key = MockAPIKey(key_prefix="testkey_", scopes=["read", "write"])
        mock_db._query_result = api_key

        request = auth_pb2.ValidateAPIKeyRequest(
            api_key="testkey_secretpart123",
            required_scopes=["read"],
        )

        response = await auth_servicer.validate_a_p_i_key(request, context)

        assert response.valid is True
        assert response.context.tenant_id == str(api_key.tenant_id)
        assert "read" in response.granted_scopes

    async def test_validate_api_key_missing_scope(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test API key validation fails for missing required scope."""
        from llamatrade_proto.generated import auth_pb2

        api_key = MockAPIKey(key_prefix="testkey_", scopes=["read"])
        mock_db._query_result = api_key

        request = auth_pb2.ValidateAPIKeyRequest(
            api_key="testkey_secretpart123",
            required_scopes=["write", "admin"],
        )

        response = await auth_servicer.validate_a_p_i_key(request, context)

        assert response.valid is False

    async def test_validate_api_key_not_found(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test validation of non-existent API key."""
        from llamatrade_proto.generated import auth_pb2

        mock_db._query_result = None

        request = auth_pb2.ValidateAPIKeyRequest(api_key="nonexistent_key")

        response = await auth_servicer.validate_a_p_i_key(request, context)
        assert response.valid is False

    async def test_validate_expired_api_key(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test validation of expired API key."""
        from llamatrade_proto.generated import auth_pb2

        api_key = MockAPIKey(
            key_prefix="testkey_",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        mock_db._query_result = api_key

        request = auth_pb2.ValidateAPIKeyRequest(api_key="testkey_secretpart123")

        response = await auth_servicer.validate_a_p_i_key(request, context)
        assert response.valid is False

    async def test_validate_inactive_api_key(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """Test validation of inactive API key."""
        from llamatrade_proto.generated import auth_pb2

        mock_db._query_result = None  # Inactive keys won't be found

        request = auth_pb2.ValidateAPIKeyRequest(api_key="inactive_key123")

        response = await auth_servicer.validate_a_p_i_key(request, context)
        assert response.valid is False

    async def test_validate_api_key_wrong_secret(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """A key sharing the prefix but not the full-key hash is rejected."""
        from llamatrade_proto.generated import auth_pb2

        # Stored key hashes the standard secret; the request presents a different one.
        api_key = MockAPIKey(key_prefix="testkey_")
        mock_db._query_result = api_key

        request = auth_pb2.ValidateAPIKeyRequest(api_key="testkey_wrongsecret999")

        response = await auth_servicer.validate_a_p_i_key(request, context)
        assert response.valid is False


# ===================
# Alpaca credential validation
# ===================


class _FakeAccount:
    """Minimal stand-in for llamatrade_alpaca Account."""

    def __init__(self, status: str = "ACTIVE", buying_power: float = 100000.0) -> None:
        self.status = status
        self.buying_power = buying_power


class _FakeClientCtx:
    """Async-context-manager stand-in for llamatrade_alpaca.TradingClient."""

    def __init__(self, action: Callable[[], object]) -> None:
        self._action = action

    async def __aenter__(self) -> _FakeClientCtx:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get_account(self) -> object:
        return self._action()


def _raiser(exc: Exception):
    def _run() -> object:
        raise exc

    return _run


def _fake_trading_client(behavior: dict[bool, Callable[[], object]]):
    """TradingClient replacement whose get_account behavior keys off the `paper` flag."""

    def factory(*, credentials: object, paper: bool, timeout: float) -> _FakeClientCtx:
        return _FakeClientCtx(behavior[paper])

    return factory


class TestValidateAlpacaCredentials:
    """Tests for AuthServicer.validate_alpaca_credentials."""

    async def test_valid_credentials(
        self, auth_servicer: AuthServicer, auth_context: MockRequestContext
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.ValidateAlpacaCredentialsRequest(
            api_key="PKTEST", api_secret="sk_test", is_paper=True
        )
        factory = _fake_trading_client({True: lambda: _FakeAccount("ACTIVE", 12345.0)})
        with patch("llamatrade_alpaca.TradingClient", factory):
            resp = await auth_servicer.validate_alpaca_credentials(request, auth_context)

        assert resp.valid is True
        assert resp.account_status == "ACTIVE"
        assert resp.buying_power == "12345.0"

    async def test_invalid_credentials(
        self, auth_servicer: AuthServicer, auth_context: MockRequestContext
    ) -> None:
        from llamatrade_alpaca.errors import AuthenticationError
        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.ValidateAlpacaCredentialsRequest(
            api_key="bad", api_secret="bad", is_paper=True
        )
        err = AuthenticationError("Invalid API credentials")
        factory = _fake_trading_client({True: _raiser(err), False: _raiser(err)})
        with patch("llamatrade_alpaca.TradingClient", factory):
            resp = await auth_servicer.validate_alpaca_credentials(request, auth_context)

        assert resp.valid is False
        assert "Invalid API key" in resp.message

    async def test_paper_live_mismatch(
        self, auth_servicer: AuthServicer, auth_context: MockRequestContext
    ) -> None:
        from llamatrade_alpaca.errors import AuthenticationError
        from llamatrade_proto.generated import auth_pb2

        # is_paper=True but the keys only authenticate on the live environment.
        request = auth_pb2.ValidateAlpacaCredentialsRequest(
            api_key="PKlive", api_secret="sk_live", is_paper=True
        )
        factory = _fake_trading_client(
            {True: _raiser(AuthenticationError("nope")), False: lambda: _FakeAccount()}
        )
        with patch("llamatrade_alpaca.TradingClient", factory):
            resp = await auth_servicer.validate_alpaca_credentials(request, auth_context)

        assert resp.valid is False
        assert "live" in resp.message

    async def test_missing_fields_short_circuit(
        self, auth_servicer: AuthServicer, auth_context: MockRequestContext
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.ValidateAlpacaCredentialsRequest(
            api_key="", api_secret="", is_paper=True
        )
        # No TradingClient patch: the method must short-circuit before reaching Alpaca.
        resp = await auth_servicer.validate_alpaca_credentials(request, auth_context)
        assert resp.valid is False
        assert "required" in resp.message.lower()

    async def test_network_error_raises_unavailable(
        self, auth_servicer: AuthServicer, auth_context: MockRequestContext
    ) -> None:
        from connectrpc.code import Code

        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.ValidateAlpacaCredentialsRequest(
            api_key="PK", api_secret="sk", is_paper=True
        )
        factory = _fake_trading_client({True: _raiser(RuntimeError("connection refused"))})
        with patch("llamatrade_alpaca.TradingClient", factory):
            with pytest.raises(ConnectError) as exc_info:
                await auth_servicer.validate_alpaca_credentials(request, auth_context)
        assert exc_info.value.code == Code.UNAVAILABLE

    async def test_unauthenticated_without_token(
        self, auth_servicer: AuthServicer, context: MockRequestContext
    ) -> None:
        from connectrpc.code import Code

        from llamatrade_proto.generated import auth_pb2

        request = auth_pb2.ValidateAlpacaCredentialsRequest(
            api_key="PK", api_secret="sk", is_paper=True
        )
        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.validate_alpaca_credentials(request, context)
        assert exc_info.value.code == Code.UNAUTHENTICATED


def test_mask_key_returns_only_a_prefix() -> None:
    """Broker-credential responses are write-only: masked key prefix, never the secret."""
    from src.grpc.servicer import _mask_key

    assert _mask_key("PKABCDEFGH123456") == "PKABCDEF…"
    assert _mask_key("") == ""


# ===================
# Rate Limiting Tests
# ===================


class TestRateLimiting:
    """RESOURCE_EXHAUSTED on limit; key selection per IP else per identifier."""

    async def test_login_blocked_returns_resource_exhausted(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        from connectrpc.code import Code

        from llamatrade_proto.generated import auth_pb2

        auth_servicer._rate_limiter = FakeRateLimiter(allowed=False)
        mock_db._query_result = MockUser()

        request = auth_pb2.LoginRequest(email="test@example.com", password="Test123!")

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(request, context)

        assert exc_info.value.code == Code.RESOURCE_EXHAUSTED

    async def test_login_email_bucket_applies_without_forwarded_ip(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        """With no trusted client IP, only the (case-folded) email bucket is enforced."""
        from llamatrade_proto.generated import auth_pb2

        limiter = FakeRateLimiter(allowed=True)
        auth_servicer._rate_limiter = limiter
        user = MockUser(email="test@example.com", password="Test123!")
        mock_db._query_result = user

        request = auth_pb2.LoginRequest(email="Test@Example.com", password="Test123!")
        await auth_servicer.login(request, context)

        assert [c[0] for c in limiter.calls] == [
            "login:email:test@example.com",
            "login:email:test@example.com",
        ]
        assert [(c[1], c[2]) for c in limiter.calls] == [(10, 60), (30, 900)]

    async def test_login_enforces_email_and_ip_buckets(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
    ) -> None:
        """Both the email bucket and the trusted-IP bucket are enforced."""
        from llamatrade_proto.generated import auth_pb2

        limiter = FakeRateLimiter(allowed=True)
        auth_servicer._rate_limiter = limiter
        user = MockUser(email="test@example.com", password="Test123!")
        mock_db._query_result = user

        # GCP topology: <real-client>, <lb>; the trusted client IP is 1.2.3.4.
        context = MockRequestContext(headers={"x-forwarded-for": "1.2.3.4, 10.0.0.1"})
        request = auth_pb2.LoginRequest(email="test@example.com", password="Test123!")
        await auth_servicer.login(request, context)

        keys = [c[0] for c in limiter.calls]
        assert keys.count("login:email:test@example.com") == 2
        assert keys.count("login:ip:1.2.3.4") == 2

    async def test_login_ip_bucket_ignores_spoofed_leftmost_xff(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
    ) -> None:
        """A client-supplied leftmost XFF hop cannot rotate the limiter key; the
        IP bucket reads the trusted (LB-appended) position instead."""
        from llamatrade_proto.generated import auth_pb2

        limiter = FakeRateLimiter(allowed=True)
        auth_servicer._rate_limiter = limiter
        user = MockUser(email="test@example.com", password="Test123!")
        mock_db._query_result = user

        # Attacker stuffs 9.9.9.9; LB appends the real client 1.2.3.4 then its own IP.
        context = MockRequestContext(headers={"x-forwarded-for": "9.9.9.9, 1.2.3.4, 10.0.0.1"})
        request = auth_pb2.LoginRequest(email="test@example.com", password="Test123!")
        await auth_servicer.login(request, context)

        ip_keys = [c[0] for c in limiter.calls if c[0].startswith("login:ip:")]
        assert ip_keys and all(k == "login:ip:1.2.3.4" for k in ip_keys)
        assert not any("9.9.9.9" in c[0] for c in limiter.calls)

    async def test_login_email_bucket_limits_regardless_of_ip(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
    ) -> None:
        """The email bucket blocks even when the (rotated) IP bucket would allow, so
        a spoofed/rotated source IP cannot escape the per-target-email limit."""
        from connectrpc.code import Code

        from llamatrade_proto.generated import auth_pb2

        class EmailBlockingLimiter(FakeRateLimiter):
            async def check_and_count(self, key: str, limit: int, window_seconds: int) -> bool:
                await super().check_and_count(key, limit, window_seconds)
                return not key.startswith("login:email:")

        auth_servicer._rate_limiter = EmailBlockingLimiter()
        mock_db._query_result = MockUser()

        context = MockRequestContext(headers={"x-forwarded-for": "5.5.5.5, 10.0.0.1"})
        request = auth_pb2.LoginRequest(email="victim@example.com", password="Test123!")

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(request, context)

        assert exc_info.value.code == Code.RESOURCE_EXHAUSTED

    async def test_login_escalating_window_blocks_after_burst(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        from connectrpc.code import Code

        from llamatrade_proto.generated import auth_pb2

        class BurstLimiter(FakeRateLimiter):
            async def check_and_count(self, key: str, limit: int, window_seconds: int) -> bool:
                await super().check_and_count(key, limit, window_seconds)
                return window_seconds != 900  # only the wide lockout window trips

        auth_servicer._rate_limiter = BurstLimiter()
        mock_db._query_result = MockUser()
        request = auth_pb2.LoginRequest(email="test@example.com", password="Test123!")

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(request, context)

        assert exc_info.value.code == Code.RESOURCE_EXHAUSTED

    async def test_register_blocked_returns_resource_exhausted(
        self,
        auth_servicer: AuthServicer,
        context: MockRequestContext,
    ) -> None:
        from connectrpc.code import Code

        from llamatrade_proto.generated import auth_pb2

        auth_servicer._rate_limiter = FakeRateLimiter(allowed=False)
        request = auth_pb2.RegisterRequest(
            tenant_name="T", email="new@example.com", password="SecurePass123"
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.register(request, context)

        assert exc_info.value.code == Code.RESOURCE_EXHAUSTED

    async def test_validate_alpaca_credentials_blocked(
        self,
        auth_servicer: AuthServicer,
        auth_context: MockRequestContext,
    ) -> None:
        from connectrpc.code import Code

        from llamatrade_proto.generated import auth_pb2

        limiter = FakeRateLimiter(allowed=False)
        auth_servicer._rate_limiter = limiter
        request = auth_pb2.ValidateAlpacaCredentialsRequest(
            api_key="PK", api_secret="sk", is_paper=True
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.validate_alpaca_credentials(request, auth_context)

        assert exc_info.value.code == Code.RESOURCE_EXHAUSTED
        assert limiter.calls[0][0].startswith("alpaca_validate:")

    async def test_no_limiter_configured_allows_login(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        assert auth_servicer._rate_limiter is None
        user = MockUser(email="test@example.com", password="Test123!")
        mock_db._query_result = user

        request = auth_pb2.LoginRequest(email="test@example.com", password="Test123!")
        response = await auth_servicer.login(request, context)
        assert response.access_token


# ===================
# Login Timing Oracle Tests
# ===================


class TestLoginTimingOracle:
    """A user-lookup miss burns a bcrypt check so timing matches wrong-password."""

    async def test_dummy_hash_checked_on_user_miss(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        mock_db._query_result = None
        request = auth_pb2.LoginRequest(email="ghost@example.com", password="Whatever1")

        with patch("src.grpc.servicer.bcrypt.checkpw", return_value=False) as checkpw:
            with pytest.raises(ConnectError) as exc_info:
                await auth_servicer.login(request, context)

        assert checkpw.call_count == 1
        from src.grpc.servicer import _DUMMY_PASSWORD_HASH

        assert checkpw.call_args.args == (b"Whatever1", _DUMMY_PASSWORD_HASH)
        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_wrong_password_checks_real_hash_once(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        user = MockUser(email="test@example.com", password="CorrectPass123!")
        mock_db._query_result = user
        request = auth_pb2.LoginRequest(email="test@example.com", password="WrongPass1")

        with patch("src.grpc.servicer.bcrypt.checkpw", return_value=False) as checkpw:
            with pytest.raises(ConnectError):
                await auth_servicer.login(request, context)

        assert checkpw.call_count == 1


# ===================
# Token Revocation Tests
# ===================


class TestRefreshRotation:
    """Refresh tokens are single-use: the presented jti is revoked on rotation."""

    async def test_refresh_revokes_used_jti(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        store = FakeRevocationStore()
        auth_servicer._revocation = store
        user = MockUser()
        mock_db._query_result = user
        token = create_test_token(
            str(user.id), str(user.tenant_id), token_type="refresh", jti="refresh-jti-1"
        )

        response = await auth_servicer.refresh_token(
            auth_pb2.RefreshTokenRequest(refresh_token=token), context
        )

        assert response.access_token
        assert "refresh-jti-1" in store.revoked_jtis
        new_refresh = jwt.decode(response.refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert new_refresh["jti"] and new_refresh["jti"] != "refresh-jti-1"

    async def test_double_refresh_rejected(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        store = FakeRevocationStore()
        auth_servicer._revocation = store
        user = MockUser()
        mock_db._query_result = user
        token = create_test_token(
            str(user.id), str(user.tenant_id), token_type="refresh", jti="refresh-jti-2"
        )
        request = auth_pb2.RefreshTokenRequest(refresh_token=token)

        await auth_servicer.refresh_token(request, context)

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.refresh_token(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_refresh_rejected_after_revoke_all(
        self,
        auth_servicer: AuthServicer,
        mock_db: MockAsyncSession,
        context: MockRequestContext,
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        store = FakeRevocationStore()
        auth_servicer._revocation = store
        user = MockUser()
        mock_db._query_result = user
        token = create_test_token(
            str(user.id), str(user.tenant_id), token_type="refresh", jti="refresh-jti-3"
        )
        await store.revoke_all_for_user(str(user.id), int(datetime.now(UTC).timestamp()) + 60)

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.refresh_token(
                auth_pb2.RefreshTokenRequest(refresh_token=token), context
            )

        assert "UNAUTHENTICATED" in str(exc_info.value.code)


class TestLogoutRevocation:
    """Logout denylists the presented access jti (and the refresh, if supplied)."""

    async def test_logout_revokes_access_jti(self, auth_servicer: AuthServicer) -> None:
        from llamatrade_proto.generated import auth_pb2

        store = FakeRevocationStore()
        auth_servicer._revocation = store
        user = MockUser()
        token = create_test_token(str(user.id), str(user.tenant_id), jti="access-jti-1")
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})

        response = await auth_servicer.logout(auth_pb2.LogoutRequest(), context)

        assert response.success is True
        assert "access-jti-1" in store.revoked_jtis

    async def test_logout_revokes_supplied_refresh_jti(self, auth_servicer: AuthServicer) -> None:
        from llamatrade_proto.generated import auth_pb2

        store = FakeRevocationStore()
        auth_servicer._revocation = store
        user = MockUser()
        access = create_test_token(str(user.id), str(user.tenant_id), jti="access-jti-2")
        refresh = create_test_token(
            str(user.id), str(user.tenant_id), token_type="refresh", jti="refresh-jti-4"
        )
        context = MockRequestContext(
            headers={"authorization": f"Bearer {access}", "x-refresh-token": refresh}
        )

        await auth_servicer.logout(auth_pb2.LogoutRequest(), context)

        assert "access-jti-2" in store.revoked_jtis
        assert "refresh-jti-4" in store.revoked_jtis

    async def test_logout_ignores_invalid_refresh_header(self, auth_servicer: AuthServicer) -> None:
        from llamatrade_proto.generated import auth_pb2

        store = FakeRevocationStore()
        auth_servicer._revocation = store
        user = MockUser()
        access = create_test_token(str(user.id), str(user.tenant_id), jti="access-jti-3")
        context = MockRequestContext(
            headers={"authorization": f"Bearer {access}", "x-refresh-token": "garbage"}
        )

        response = await auth_servicer.logout(auth_pb2.LogoutRequest(), context)

        assert response.success is True
        assert set(store.revoked_jtis) == {"access-jti-3"}

    async def test_logout_expired_token_still_succeeds(self, auth_servicer: AuthServicer) -> None:
        from llamatrade_proto.generated import auth_pb2

        store = FakeRevocationStore()
        auth_servicer._revocation = store
        user = MockUser()
        token = create_test_token(str(user.id), str(user.tenant_id), expired=True, jti="j")
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})

        response = await auth_servicer.logout(auth_pb2.LogoutRequest(), context)

        assert response.success is True
        assert store.revoked_jtis == {}


class TestChangePasswordRevocation:
    """A password change revokes every session issued before it."""

    async def test_change_password_revokes_all_user_tokens(
        self, auth_servicer: AuthServicer, mock_db: MockAsyncSession
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        store = FakeRevocationStore()
        auth_servicer._revocation = store
        user = MockUser(password="OldPass123!")
        token = create_test_token(str(user.id), str(user.tenant_id))
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})
        mock_db._query_result = user

        response = await auth_servicer.change_password(
            auth_pb2.ChangePasswordRequest(
                current_password="OldPass123!", new_password="NewPass456!"
            ),
            context,
        )

        assert response.success is True
        assert str(user.id) in store.user_cutoffs

    async def test_failed_change_does_not_revoke(
        self, auth_servicer: AuthServicer, mock_db: MockAsyncSession
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        store = FakeRevocationStore()
        auth_servicer._revocation = store
        user = MockUser(password="CorrectPass123!")
        token = create_test_token(str(user.id), str(user.tenant_id))
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})
        mock_db._query_result = user

        with pytest.raises(ConnectError):
            await auth_servicer.change_password(
                auth_pb2.ChangePasswordRequest(
                    current_password="WrongPass123!", new_password="NewPass456!"
                ),
                context,
            )

        assert store.user_cutoffs == {}


# ===================
# Asymmetric verification
# ===================


def _rsa_pair() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

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


class TestAsymmetricVerification:
    """Servicer token verification is pinned to the configured key material."""

    @pytest.fixture
    def rs256_keys(self, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
        import src.grpc.servicer as servicer_module

        private_pem, public_pem = _rsa_pair()
        monkeypatch.setattr(servicer_module, "VERIFY_KEY", public_pem)
        monkeypatch.setattr(servicer_module, "VERIFY_ALGORITHM", "RS256")
        return private_pem, public_pem

    async def test_validate_token_accepts_rs256_when_pinned(
        self, auth_servicer: AuthServicer, rs256_keys: tuple[str, str]
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        private_pem, _ = rs256_keys
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(uuid4()),
                "tenant_id": str(uuid4()),
                "type": "access",
                "roles": ["admin"],
                "iat": now,
                "exp": now + timedelta(hours=1),
            },
            private_pem,
            algorithm="RS256",
        )

        response = await auth_servicer.validate_token(
            auth_pb2.ValidateTokenRequest(token=token), MockRequestContext()
        )
        assert response.valid is True

    async def test_validate_token_rejects_hs256_when_rs256_pinned(
        self, auth_servicer: AuthServicer, rs256_keys: tuple[str, str]
    ) -> None:
        from llamatrade_proto.generated import auth_pb2

        token = create_test_token(str(uuid4()), str(uuid4()))
        response = await auth_servicer.validate_token(
            auth_pb2.ValidateTokenRequest(token=token), MockRequestContext()
        )
        assert response.valid is False

    async def test_validate_token_rejects_service_token(self, auth_servicer: AuthServicer) -> None:
        """A service token (aud=llamatrade-internal) can never pass as a user token."""
        from llamatrade_common import mint_service_token
        from llamatrade_proto.generated import auth_pb2

        token = mint_service_token(secret=JWT_SECRET)
        response = await auth_servicer.validate_token(
            auth_pb2.ValidateTokenRequest(token=token), MockRequestContext()
        )
        assert response.valid is False

    async def test_change_password_rejects_service_token(self, auth_servicer: AuthServicer) -> None:
        from llamatrade_common import mint_service_token
        from llamatrade_proto.generated import auth_pb2

        token = mint_service_token(secret=JWT_SECRET)
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})
        with pytest.raises(ConnectError):
            await auth_servicer.change_password(
                auth_pb2.ChangePasswordRequest(
                    current_password="OldPass123!", new_password="NewPass456!"
                ),
                context,
            )


# ===================
# DeleteAlpacaCredentials Tests
# ===================


class TestDeleteAlpacaCredentials:
    """Tests for the delete_alpaca_credentials RPC (dependency guard)."""

    @staticmethod
    def _request(credentials_id: UUID) -> object:
        from llamatrade_proto.generated import auth_pb2

        return auth_pb2.DeleteAlpacaCredentialsRequest(credentials_id=str(credentials_id))

    async def test_delete_success(
        self, auth_servicer: AuthServicer, auth_context: MockRequestContext
    ) -> None:
        with patch(
            "src.services.tenant_service.TenantService.delete_alpaca_credentials",
            new=AsyncMock(return_value=True),
        ):
            response = await auth_servicer.delete_alpaca_credentials(
                self._request(uuid4()), auth_context
            )

        assert response.success is True

    async def test_delete_missing_credentials_is_not_found(
        self, auth_servicer: AuthServicer, auth_context: MockRequestContext
    ) -> None:
        from connectrpc.code import Code

        with patch(
            "src.services.tenant_service.TenantService.delete_alpaca_credentials",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(ConnectError) as exc_info:
                await auth_servicer.delete_alpaca_credentials(self._request(uuid4()), auth_context)

        assert exc_info.value.code == Code.NOT_FOUND

    async def test_delete_with_dependents_is_failed_precondition(
        self, auth_servicer: AuthServicer, auth_context: MockRequestContext
    ) -> None:
        """Dependents map to FAILED_PRECONDITION with every blocking id in the message."""
        from connectrpc.code import Code

        from llamatrade_db.credential_dependents import CredentialDependents

        from src.services.tenant_service import CredentialsInUseError

        session_id, sleeve_id, execution_id = uuid4(), uuid4(), uuid4()
        error = CredentialsInUseError(
            CredentialDependents(
                session_ids=(session_id,),
                sleeve_ids=(sleeve_id,),
                strategy_execution_ids=(execution_id,),
            )
        )

        with patch(
            "src.services.tenant_service.TenantService.delete_alpaca_credentials",
            new=AsyncMock(side_effect=error),
        ):
            with pytest.raises(ConnectError) as exc_info:
                await auth_servicer.delete_alpaca_credentials(self._request(uuid4()), auth_context)

        assert exc_info.value.code == Code.FAILED_PRECONDITION
        message = str(exc_info.value)
        assert str(session_id) in message
        assert str(sleeve_id) in message
        assert str(execution_id) in message

    async def test_delete_requires_a_token(self, auth_servicer: AuthServicer) -> None:
        from connectrpc.code import Code

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.delete_alpaca_credentials(
                self._request(uuid4()), MockRequestContext()
            )

        assert exc_info.value.code == Code.UNAUTHENTICATED
