"""Authentication fixtures for integration tests.

Provides fixtures for creating test tenants, users, and JWT tokens
for authenticated API requests.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Tenant, User

# Default JWT secret for tests (matches set_test_environment)
TEST_JWT_SECRET = "test-secret-for-integration-tests"
TEST_JWT_ALGORITHM = "HS256"


def create_jwt_token(
    user_id: UUID,
    tenant_id: UUID,
    email: str,
    roles: list[str] | None = None,
    expires_in: timedelta | None = None,
    token_type: str = "access",
) -> str:
    """Create a JWT token for testing.

    Args:
        user_id: User's UUID
        tenant_id: Tenant's UUID
        email: User's email
        roles: List of role names (default: ["user"])
        expires_in: Token expiration (default: 1 hour)
        token_type: Token type (access or refresh)

    Returns:
        Encoded JWT token string
    """
    if roles is None:
        roles = ["user"]
    if expires_in is None:
        expires_in = timedelta(hours=1)

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "email": email,
        "roles": roles,
        "type": token_type,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + expires_in,
    }

    return jwt.encode(payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)


def create_auth_headers(token: str) -> dict[str, str]:
    """Create Authorization headers from a token."""
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_tenant(db_session: AsyncSession) -> Tenant:
    """Create a test tenant in the database.

    Returns:
        Tenant model instance with ID persisted to database
    """
    tenant = Tenant(
        id=uuid4(),
        name="Test Organization",
        slug=f"test-org-{uuid4().hex[:8]}",
        is_active=True,
        settings={"timezone": "UTC"},
    )
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def test_user(db_session: AsyncSession, test_tenant: Tenant) -> User:
    """Create a test user in the database.

    Returns:
        User model instance with ID persisted to database
    """
    # bcrypt hash for "password123" - pre-computed for speed
    password_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.s1X5GmXBiLNjNW"

    user = User(
        id=uuid4(),
        tenant_id=test_tenant.id,
        email=f"test-{uuid4().hex[:8]}@example.com",
        password_hash=password_hash,
        first_name="Test",
        last_name="User",
        role="user",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user: User, test_tenant: Tenant) -> str:
    """Create a JWT token for the test user.

    Returns:
        Valid JWT token string
    """
    return create_jwt_token(
        user_id=test_user.id,
        tenant_id=test_tenant.id,
        email=test_user.email,
        roles=[test_user.role],
    )


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    """Create Authorization headers for the test user.

    Returns:
        Dict with Authorization header
    """
    return create_auth_headers(auth_token)


@pytest.fixture
async def admin_user(db_session: AsyncSession, test_tenant: Tenant) -> User:
    """Create an admin user in the database.

    Returns:
        User model instance with admin role
    """
    password_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.s1X5GmXBiLNjNW"

    user = User(
        id=uuid4(),
        tenant_id=test_tenant.id,
        email=f"admin-{uuid4().hex[:8]}@example.com",
        password_hash=password_hash,
        first_name="Admin",
        last_name="User",
        role="admin",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user: User, test_tenant: Tenant) -> str:
    """Create a JWT token for the admin user."""
    return create_jwt_token(
        user_id=admin_user.id,
        tenant_id=test_tenant.id,
        email=admin_user.email,
        roles=["admin"],
    )


@pytest.fixture
def admin_headers(admin_token: str) -> dict[str, str]:
    """Create Authorization headers for the admin user."""
    return create_auth_headers(admin_token)


# ==========================================
# Second tenant fixtures for isolation tests
# ==========================================


@pytest.fixture
async def second_tenant(db_session: AsyncSession) -> Tenant:
    """Create a second tenant for cross-tenant isolation tests.

    Returns:
        Tenant model instance for the second tenant
    """
    tenant = Tenant(
        id=uuid4(),
        name="Second Organization",
        slug=f"second-org-{uuid4().hex[:8]}",
        is_active=True,
        settings={"timezone": "UTC"},
    )
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def second_tenant_user(db_session: AsyncSession, second_tenant: Tenant) -> User:
    """Create a user for the second tenant.

    Returns:
        User model instance belonging to second tenant
    """
    password_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.s1X5GmXBiLNjNW"

    user = User(
        id=uuid4(),
        tenant_id=second_tenant.id,
        email=f"other-{uuid4().hex[:8]}@example.com",
        password_hash=password_hash,
        first_name="Other",
        last_name="User",
        role="user",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def second_tenant_token(second_tenant_user: User, second_tenant: Tenant) -> str:
    """Create a JWT token for the second tenant's user."""
    return create_jwt_token(
        user_id=second_tenant_user.id,
        tenant_id=second_tenant.id,
        email=second_tenant_user.email,
        roles=[second_tenant_user.role],
    )


@pytest.fixture
def second_tenant_headers(second_tenant_token: str) -> dict[str, str]:
    """Create Authorization headers for the second tenant's user."""
    return create_auth_headers(second_tenant_token)


# ==========================================
# Expired/invalid token fixtures
# ==========================================


@pytest.fixture
def expired_token(test_user: User, test_tenant: Tenant) -> str:
    """Create an expired JWT token for testing auth failures."""
    return create_jwt_token(
        user_id=test_user.id,
        tenant_id=test_tenant.id,
        email=test_user.email,
        roles=[test_user.role],
        expires_in=timedelta(seconds=-1),  # Already expired
    )


@pytest.fixture
def expired_headers(expired_token: str) -> dict[str, str]:
    """Create Authorization headers with expired token."""
    return create_auth_headers(expired_token)


@pytest.fixture
def invalid_token() -> str:
    """Create an invalid JWT token."""
    return "invalid.jwt.token"


@pytest.fixture
def invalid_headers(invalid_token: str) -> dict[str, str]:
    """Create Authorization headers with invalid token."""
    return create_auth_headers(invalid_token)
