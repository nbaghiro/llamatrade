"""Tests for Auth Connect servicer.

Tests the AuthServicer directly without HTTP layer.
"""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import bcrypt
import jwt
import pytest
from connectrpc.errors import ConnectError

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
        id=None,
        tenant_id=None,
        email="test@example.com",
        password="Test123!",
        first_name="Test",
        last_name="User",
        role="admin",
        is_active=True,
    ):
        self.id = id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.email = email
        self.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.is_active = is_active
        self.created_at = datetime.now(UTC)
        self.last_login = None


class MockTenant:
    """Mock Tenant database model."""

    def __init__(self, id=None, name="Test Tenant", slug="test-tenant", is_active=True):
        self.id = id or uuid4()
        self.name = name
        self.slug = slug
        self.is_active = is_active
        self.created_at = datetime.now(UTC)
        self.settings = {}


class MockAPIKey:
    """Mock APIKey database model."""

    def __init__(
        self,
        id=None,
        tenant_id=None,
        user_id=None,
        name="Test Key",
        key_prefix="testkey_",
        scopes=None,
        is_active=True,
        expires_at=None,
    ):
        self.id = id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.user_id = user_id
        self.name = name
        self.key_prefix = key_prefix
        self.scopes = scopes or ["read", "write"]
        self.is_active = is_active
        self.expires_at = expires_at
        self.last_used_at = None
        self.created_at = datetime.now(UTC)


class MockRequestContext:
    """Mock ConnectRPC RequestContext."""

    def __init__(self, headers=None):
        self.headers = headers or {}


class MockAsyncSession:
    """Mock async database session."""

    def __init__(self):
        self._users = {}
        self._tenants = {}
        self._api_keys = {}
        self._query_result = None

    def set_user(self, user):
        self._users[str(user.id)] = user
        self._users[user.email] = user

    def set_tenant(self, tenant):
        self._tenants[str(tenant.id)] = tenant

    def set_api_key(self, api_key):
        self._api_keys[api_key.prefix] = api_key

    async def execute(self, query):
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._query_result
        return result

    async def flush(self):
        pass

    async def commit(self):
        pass

    def add(self, obj):
        # Ensure created_at is set
        if hasattr(obj, "created_at") and obj.created_at is None:
            obj.created_at = datetime.now(UTC)
        if hasattr(obj, "email"):
            self.set_user(obj)
        elif hasattr(obj, "slug"):
            self.set_tenant(obj)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# ===================
# Fixtures
# ===================


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return MockAsyncSession()


@pytest.fixture
def auth_servicer(mock_db):
    """Create AuthServicer with mocked database."""
    from src.grpc.servicer import AuthServicer

    servicer = AuthServicer()

    async def mock_get_db():
        return mock_db

    servicer._get_db = mock_get_db
    return servicer


@pytest.fixture
def context():
    """Create mock request context."""
    return MockRequestContext()


@pytest.fixture
def auth_context(context):
    """Create request context with valid auth token."""
    user_id = str(uuid4())
    tenant_id = str(uuid4())
    token = create_test_token(user_id, tenant_id)
    return MockRequestContext(headers={"authorization": f"Bearer {token}"})


def create_test_token(
    user_id: str, tenant_id: str, token_type: str = "access", expired: bool = False
):
    """Create a test JWT token."""
    now = datetime.now(UTC)
    if expired:
        exp = now - timedelta(hours=1)
    else:
        exp = now + timedelta(hours=1)

    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": "test@example.com",
        "roles": ["admin"],
        "type": token_type,
        "iat": now,
        "exp": exp,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ===================
# Register Tests
# ===================


class TestRegister:
    """Tests for register RPC."""

    async def test_register_success(self, auth_servicer, mock_db, context):
        """Test successful registration creates user and tenant."""
        from llamatrade.v1 import auth_pb2

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

    async def test_register_duplicate_email(self, auth_servicer, mock_db, context):
        """Test registration fails for existing email."""
        from llamatrade.v1 import auth_pb2

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


# ===================
# Login Tests
# ===================


class TestLogin:
    """Tests for login RPC."""

    async def test_login_success(self, auth_servicer, mock_db, context):
        """Test successful login returns tokens and user."""
        from llamatrade.v1 import auth_pb2

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

    async def test_login_invalid_email(self, auth_servicer, mock_db, context):
        """Test login fails for non-existent user."""
        from llamatrade.v1 import auth_pb2

        mock_db._query_result = None

        request = auth_pb2.LoginRequest(
            email="nonexistent@example.com",
            password="Test123!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_login_wrong_password(self, auth_servicer, mock_db, context):
        """Test login fails for wrong password."""
        from llamatrade.v1 import auth_pb2

        user = MockUser(email="test@example.com", password="CorrectPass123!")
        mock_db._query_result = user

        request = auth_pb2.LoginRequest(
            email="test@example.com",
            password="WrongPassword!",
        )

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.login(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_login_inactive_user(self, auth_servicer, mock_db, context):
        """Test login fails for inactive user."""
        from llamatrade.v1 import auth_pb2

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

    async def test_validate_valid_token(self, auth_servicer, context):
        """Test validation of valid token."""
        from llamatrade.v1 import auth_pb2

        user_id = str(uuid4())
        tenant_id = str(uuid4())
        token = create_test_token(user_id, tenant_id)

        request = auth_pb2.ValidateTokenRequest(token=token)
        response = await auth_servicer.validate_token(request, context)

        assert response.valid is True
        assert response.context.user_id == user_id
        assert response.context.tenant_id == tenant_id
        assert response.token_type == "access"

    async def test_validate_expired_token(self, auth_servicer, context):
        """Test validation of expired token."""
        from llamatrade.v1 import auth_pb2

        user_id = str(uuid4())
        tenant_id = str(uuid4())
        token = create_test_token(user_id, tenant_id, expired=True)

        request = auth_pb2.ValidateTokenRequest(token=token)
        response = await auth_servicer.validate_token(request, context)

        assert response.valid is False

    async def test_validate_invalid_token(self, auth_servicer, context):
        """Test validation of invalid token."""
        from llamatrade.v1 import auth_pb2

        request = auth_pb2.ValidateTokenRequest(token="invalid.token.here")
        response = await auth_servicer.validate_token(request, context)

        assert response.valid is False

    async def test_validate_refresh_token(self, auth_servicer, context):
        """Test validation of refresh token."""
        from llamatrade.v1 import auth_pb2

        user_id = str(uuid4())
        tenant_id = str(uuid4())
        token = create_test_token(user_id, tenant_id, token_type="refresh")

        request = auth_pb2.ValidateTokenRequest(token=token)
        response = await auth_servicer.validate_token(request, context)

        assert response.valid is True
        assert response.token_type == "refresh"


# ===================
# RefreshToken Tests
# ===================


class TestRefreshToken:
    """Tests for refresh_token RPC."""

    async def test_refresh_token_success(self, auth_servicer, mock_db, context):
        """Test successful token refresh."""
        from llamatrade.v1 import auth_pb2

        user = MockUser()
        mock_db._query_result = user
        refresh_token = create_test_token(str(user.id), str(user.tenant_id), token_type="refresh")

        request = auth_pb2.RefreshTokenRequest(refresh_token=refresh_token)
        response = await auth_servicer.refresh_token(request, context)

        assert response.access_token
        assert response.refresh_token
        assert response.access_token != refresh_token

    async def test_refresh_with_access_token_fails(self, auth_servicer, mock_db, context):
        """Test refresh fails when using access token."""
        from llamatrade.v1 import auth_pb2

        user = MockUser()
        access_token = create_test_token(str(user.id), str(user.tenant_id), token_type="access")

        request = auth_pb2.RefreshTokenRequest(refresh_token=access_token)

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.refresh_token(request, context)

        assert "INVALID_ARGUMENT" in str(exc_info.value.code)

    async def test_refresh_expired_token_fails(self, auth_servicer, context):
        """Test refresh fails for expired token."""
        from llamatrade.v1 import auth_pb2

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

    async def test_get_current_user_success(self, auth_servicer, mock_db):
        """Test getting current user from token."""
        from llamatrade.v1 import auth_pb2

        user = MockUser()
        tenant = MockTenant(id=user.tenant_id)
        token = create_test_token(str(user.id), str(user.tenant_id))
        context = MockRequestContext(headers={"authorization": f"Bearer {token}"})

        # Mock database to return user then tenant
        call_count = [0]
        original_user = user
        original_tenant = tenant

        async def mock_execute(query):
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
        assert response.tenant.id == str(tenant.id)

    async def test_get_current_user_no_token(self, auth_servicer, context):
        """Test getting current user without token fails."""
        from llamatrade.v1 import auth_pb2

        request = auth_pb2.GetCurrentUserRequest()

        with pytest.raises(ConnectError) as exc_info:
            await auth_servicer.get_current_user(request, context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_get_current_user_invalid_token(self, auth_servicer):
        """Test getting current user with invalid token fails."""
        from llamatrade.v1 import auth_pb2

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

    async def test_change_password_success(self, auth_servicer, mock_db):
        """Test successful password change."""
        from llamatrade.v1 import auth_pb2

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

    async def test_change_password_wrong_current(self, auth_servicer, mock_db):
        """Test password change fails with wrong current password."""
        from llamatrade.v1 import auth_pb2

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

    async def test_change_password_no_auth(self, auth_servicer, context):
        """Test password change fails without authentication."""
        from llamatrade.v1 import auth_pb2

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

    async def test_get_user_success(self, auth_servicer, mock_db, context):
        """Test getting user by ID."""
        from llamatrade.v1 import auth_pb2

        user = MockUser()
        mock_db._query_result = user

        request = auth_pb2.GetUserRequest(user_id=str(user.id))
        response = await auth_servicer.get_user(request, context)

        assert response.user.id == str(user.id)
        assert response.user.email == user.email
        assert response.user.first_name == user.first_name

    async def test_get_user_not_found(self, auth_servicer, mock_db, context):
        """Test getting non-existent user."""
        from llamatrade.v1 import auth_pb2

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

    async def test_get_tenant_success(self, auth_servicer, mock_db, context):
        """Test getting tenant by ID."""
        from llamatrade.v1 import auth_pb2

        tenant = MockTenant()
        mock_db._query_result = tenant

        request = auth_pb2.GetTenantRequest(tenant_id=str(tenant.id))
        response = await auth_servicer.get_tenant(request, context)

        assert response.tenant.id == str(tenant.id)
        assert response.tenant.name == tenant.name
        assert response.tenant.is_active == tenant.is_active

    async def test_get_tenant_not_found(self, auth_servicer, mock_db, context):
        """Test getting non-existent tenant."""
        from llamatrade.v1 import auth_pb2

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

    async def test_admin_has_full_access(self, auth_servicer, context):
        """Test admin role has full access."""
        from llamatrade.v1 import auth_pb2, common_pb2

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

    async def test_trader_has_limited_access(self, auth_servicer, context):
        """Test trader role has limited access."""
        from llamatrade.v1 import auth_pb2, common_pb2

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

    async def test_viewer_cannot_create(self, auth_servicer, context):
        """Test viewer role cannot create resources."""
        from llamatrade.v1 import auth_pb2, common_pb2

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

    async def test_viewer_can_read(self, auth_servicer, context):
        """Test viewer role can read resources."""
        from llamatrade.v1 import auth_pb2, common_pb2

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

    async def test_validate_valid_api_key(self, auth_servicer, mock_db, context):
        """Test validation of valid API key."""
        from llamatrade.v1 import auth_pb2

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

    async def test_validate_api_key_missing_scope(self, auth_servicer, mock_db, context):
        """Test API key validation fails for missing required scope."""
        from llamatrade.v1 import auth_pb2

        api_key = MockAPIKey(key_prefix="testkey_", scopes=["read"])
        mock_db._query_result = api_key

        request = auth_pb2.ValidateAPIKeyRequest(
            api_key="testkey_secretpart123",
            required_scopes=["write", "admin"],
        )

        response = await auth_servicer.validate_a_p_i_key(request, context)

        assert response.valid is False

    async def test_validate_api_key_not_found(self, auth_servicer, mock_db, context):
        """Test validation of non-existent API key."""
        from llamatrade.v1 import auth_pb2

        mock_db._query_result = None

        request = auth_pb2.ValidateAPIKeyRequest(api_key="nonexistent_key")

        response = await auth_servicer.validate_a_p_i_key(request, context)
        assert response.valid is False

    async def test_validate_expired_api_key(self, auth_servicer, mock_db, context):
        """Test validation of expired API key."""
        from llamatrade.v1 import auth_pb2

        api_key = MockAPIKey(
            key_prefix="testkey_",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        mock_db._query_result = api_key

        request = auth_pb2.ValidateAPIKeyRequest(api_key="testkey_secretpart123")

        response = await auth_servicer.validate_a_p_i_key(request, context)
        assert response.valid is False

    async def test_validate_inactive_api_key(self, auth_servicer, mock_db, context):
        """Test validation of inactive API key."""
        from llamatrade.v1 import auth_pb2

        mock_db._query_result = None  # Inactive keys won't be found

        request = auth_pb2.ValidateAPIKeyRequest(api_key="inactive_key123")

        response = await auth_servicer.validate_a_p_i_key(request, context)
        assert response.valid is False
