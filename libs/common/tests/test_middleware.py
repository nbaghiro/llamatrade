"""Tests for FastAPI middleware."""

from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from llamatrade_common.middleware import (
    ServiceClient,
    TenantMiddleware,
    get_tenant_context,
    require_auth,
    require_roles,
    set_tenant_context,
)
from llamatrade_common.models import TenantContext


class TestTenantContext:
    """Tests for TenantContext management."""

    def teardown_method(self):
        """Clear context after each test."""
        set_tenant_context(None)

    def test_set_and_get_tenant_context(self):
        """Test setting and getting tenant context."""
        ctx = TenantContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            email="user@example.com",
            roles=["user"],
        )
        set_tenant_context(ctx)

        retrieved = get_tenant_context()
        assert retrieved.email == "user@example.com"

    def test_get_tenant_context_not_set(self):
        """Test getting context when not set raises error."""
        from fastapi import HTTPException

        set_tenant_context(None)

        with pytest.raises(HTTPException) as exc_info:
            get_tenant_context()

        assert exc_info.value.status_code == 401


class TestTenantMiddleware:
    """Tests for TenantMiddleware."""

    @pytest.fixture
    def app(self):
        """Create a FastAPI app with tenant middleware."""
        app = FastAPI()

        @app.middleware("http")
        async def tenant_middleware(request, call_next):
            middleware = TenantMiddleware(jwt_secret="test-secret")
            return await middleware(request, call_next)

        @app.get("/public/health")
        async def health():
            return {"status": "ok"}

        @app.get("/protected")
        async def protected():
            ctx = get_tenant_context()
            return {"tenant_id": str(ctx.tenant_id)}

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_public_path_allowed(self, client):
        """Test public paths are allowed without token."""
        # Configure middleware with /public as public path
        response = client.get("/public/health")
        assert response.status_code == 200

    def test_protected_without_token(self, client):
        """Test protected endpoint without token."""
        response = client.get("/protected")
        # Should fail because no context is set
        assert response.status_code == 401

    def test_protected_with_invalid_token(self, client):
        """Test protected endpoint with invalid token."""
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer invalid-token"},
        )
        # Should fail because token is invalid
        assert response.status_code == 401


class TestRequireAuth:
    """Tests for require_auth dependency."""

    @pytest.fixture
    def app(self):
        """Create a FastAPI app with auth dependency."""
        app = FastAPI()

        @app.get("/secured")
        async def secured_endpoint(ctx: TenantContext = Depends(require_auth)):
            return {"user_id": str(ctx.user_id)}

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_require_auth_no_context(self, client):
        """Test require_auth when no context is set."""
        response = client.get("/secured")
        assert response.status_code == 401


class TestRequireRoles:
    """Tests for require_roles dependency factory."""

    def test_require_roles_creates_dependency(self):
        """Test that require_roles creates a dependency function."""
        dep = require_roles("admin", "superuser")
        assert callable(dep)


class TestServiceClient:
    """Tests for ServiceClient."""

    def test_service_client_init(self):
        """Test ServiceClient initialization."""
        client = ServiceClient(
            base_url="http://localhost:8000/",
            timeout=60.0,
        )

        assert client.base_url == "http://localhost:8000"  # Trailing slash removed
        assert client.timeout == 60.0

    def test_service_client_headers_no_context(self):
        """Test headers when no tenant context is set."""
        set_tenant_context(None)
        client = ServiceClient(base_url="http://localhost:8000")

        headers = client._get_headers()

        assert headers["Content-Type"] == "application/json"
        assert "X-Tenant-ID" not in headers

    def test_service_client_headers_with_context(self):
        """Test headers when tenant context is set."""
        ctx = TenantContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            email="test@example.com",
            roles=["user"],
        )
        set_tenant_context(ctx)

        client = ServiceClient(base_url="http://localhost:8000")
        headers = client._get_headers()

        assert headers["X-Tenant-ID"] == str(ctx.tenant_id)
        assert headers["X-User-ID"] == str(ctx.user_id)

        set_tenant_context(None)
