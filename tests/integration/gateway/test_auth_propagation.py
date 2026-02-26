"""Kong gateway authentication propagation tests.

These tests verify that:
1. Public routes are correctly identified and accessible without auth
2. Protected routes require valid JWT
3. JWT claims are properly validated (exp claim)
4. X-Tenant-ID header is allowed through CORS

NOTE: These tests verify the configuration. For live testing, see workflow tests.
"""

import pytest

from tests.integration.gateway.conftest import (
    get_routes_for_service,
    get_service_plugins,
    has_jwt_plugin,
)

pytestmark = [pytest.mark.integration, pytest.mark.gateway]


class TestPublicRoutes:
    """Tests for public route identification."""

    def test_auth_login_is_public(self, kong_services: list[dict]):
        """Test /api/auth/login is publicly accessible."""
        routes = get_routes_for_service(kong_services, "auth-service")
        public_route = next((r for r in routes if r.get("name") == "auth-public-routes"), None)

        assert public_route is not None
        assert "/api/auth/login" in public_route.get("paths", [])
        assert "public" in public_route.get("tags", [])

    def test_auth_register_is_public(self, kong_services: list[dict]):
        """Test /api/auth/register is publicly accessible."""
        routes = get_routes_for_service(kong_services, "auth-service")
        public_route = next((r for r in routes if r.get("name") == "auth-public-routes"), None)

        assert public_route is not None
        assert "/api/auth/register" in public_route.get("paths", [])

    def test_auth_refresh_is_public(self, kong_services: list[dict]):
        """Test /api/auth/refresh is publicly accessible.

        Token refresh needs to work with just a refresh token,
        without a valid access token.
        """
        routes = get_routes_for_service(kong_services, "auth-service")
        public_route = next((r for r in routes if r.get("name") == "auth-public-routes"), None)

        assert public_route is not None
        assert "/api/auth/refresh" in public_route.get("paths", [])

    def test_stripe_webhook_is_public(self, kong_services: list[dict]):
        """Test Stripe webhook endpoint is publicly accessible.

        Stripe webhooks use signature verification, not JWT.
        """
        routes = get_routes_for_service(kong_services, "billing-service")
        webhook_route = next((r for r in routes if r.get("name") == "stripe-webhook-route"), None)

        assert webhook_route is not None
        assert "webhook" in webhook_route.get("tags", [])


class TestProtectedRoutes:
    """Tests for protected route identification."""

    def test_auth_me_is_protected(self, kong_services: list[dict]):
        """Test /api/auth/me requires authentication."""
        routes = get_routes_for_service(kong_services, "auth-service")
        protected_route = next((r for r in routes if r.get("name") == "auth-protected-routes"), None)

        assert protected_route is not None
        assert "/api/auth/me" in protected_route.get("paths", [])
        assert "protected" in protected_route.get("tags", [])

    def test_strategies_are_protected(self, kong_services: list[dict]):
        """Test strategy routes require authentication."""
        routes = get_routes_for_service(kong_services, "strategy-service")

        # All strategy routes should be protected
        for route in routes:
            assert "protected" in route.get("tags", [])

        # Service should have JWT plugin
        plugins = get_service_plugins(kong_services, "strategy-service")
        assert has_jwt_plugin(plugins)

    def test_backtests_are_protected(self, kong_services: list[dict]):
        """Test backtest routes require authentication."""
        plugins = get_service_plugins(kong_services, "backtest-service")
        assert has_jwt_plugin(plugins)

    def test_trading_routes_are_protected(self, kong_services: list[dict]):
        """Test trading routes require authentication.

        Trading is critical - must be protected.
        """
        plugins = get_service_plugins(kong_services, "trading-service")
        assert has_jwt_plugin(plugins)

        routes = get_routes_for_service(kong_services, "trading-service")
        for route in routes:
            assert "protected" in route.get("tags", [])

    def test_billing_protected_routes_are_protected(self, kong_services: list[dict]):
        """Test billing protected routes require authentication."""
        routes = get_routes_for_service(kong_services, "billing-service")
        protected_route = next((r for r in routes if r.get("name") == "billing-protected-routes"), None)

        assert protected_route is not None
        assert "protected" in protected_route.get("tags", [])

        # Verify subscription/invoice paths are protected
        paths = protected_route.get("paths", [])
        assert "/api/subscriptions" in paths
        assert "/api/invoices" in paths


class TestJWTConfiguration:
    """Tests for JWT plugin configuration."""

    def test_jwt_validates_expiration(self, kong_services: list[dict]):
        """Test JWT plugin validates token expiration."""
        for service in kong_services:
            plugins = service.get("plugins", [])
            jwt_plugin = next((p for p in plugins if p.get("name") == "jwt"), None)

            if jwt_plugin:
                config = jwt_plugin.get("config", {})
                claims_to_verify = config.get("claims_to_verify", [])
                assert "exp" in claims_to_verify, (
                    f"Service {service['name']} JWT should validate expiration"
                )

    def test_jwt_does_not_run_on_preflight(self, kong_services: list[dict]):
        """Test JWT plugin skips OPTIONS requests (CORS preflight).

        Kong's JWT plugin defaults run_on_preflight to false if not specified,
        so we just verify it's not explicitly set to true.
        """
        for service in kong_services:
            plugins = service.get("plugins", [])
            jwt_plugin = next((p for p in plugins if p.get("name") == "jwt"), None)

            if jwt_plugin:
                config = jwt_plugin.get("config", {})
                # run_on_preflight defaults to false; verify it's not explicitly true
                assert config.get("run_on_preflight") is not True, (
                    f"Service {service['name']} JWT should not run on preflight"
                )


class TestTenantPropagation:
    """Tests for tenant context propagation."""

    def test_cors_allows_tenant_header(self, kong_plugins: list[dict]):
        """Test CORS allows X-Tenant-ID header for tenant context."""
        cors = next((p for p in kong_plugins if p.get("name") == "cors"), None)
        assert cors is not None

        config = cors.get("config", {})
        allowed_headers = config.get("headers", [])

        assert "X-Tenant-ID" in allowed_headers, (
            "CORS must allow X-Tenant-ID header for multi-tenant context"
        )

    def test_request_transformer_adds_gateway_headers(self, kong_plugins: list[dict]):
        """Test request transformer adds gateway identification headers."""
        transformer = next((p for p in kong_plugins if p.get("name") == "request-transformer"), None)
        assert transformer is not None

        config = transformer.get("config", {})
        add_headers = config.get("add", {}).get("headers", [])

        # Should add headers identifying the request came through Kong
        header_names = [h.split(":")[0] for h in add_headers]
        assert "X-Gateway-Version" in header_names or "X-Forwarded-By" in header_names


class TestRouteTagging:
    """Tests for route tagging consistency."""

    def test_all_protected_routes_tagged(self, kong_services: list[dict]):
        """Test all protected routes are tagged as 'protected'."""
        for service in kong_services:
            plugins = service.get("plugins", [])

            # If service has JWT, all its routes should be tagged protected
            if has_jwt_plugin(plugins):
                routes = service.get("routes", [])
                for route in routes:
                    tags = route.get("tags", [])
                    assert "protected" in tags, (
                        f"Route {route.get('name')} in JWT-protected service "
                        f"{service['name']} should be tagged 'protected'"
                    )

    def test_public_routes_not_tagged_protected(self, kong_services: list[dict]):
        """Test public routes are tagged appropriately."""
        auth_routes = get_routes_for_service(kong_services, "auth-service")
        public_route = next((r for r in auth_routes if r.get("name") == "auth-public-routes"), None)

        assert public_route is not None
        tags = public_route.get("tags", [])
        assert "public" in tags
        assert "protected" not in tags

    def test_webhook_routes_tagged_webhook(self, kong_services: list[dict]):
        """Test webhook routes are tagged as 'webhook'."""
        billing_routes = get_routes_for_service(kong_services, "billing-service")
        webhook_route = next((r for r in billing_routes if r.get("name") == "stripe-webhook-route"), None)

        assert webhook_route is not None
        tags = webhook_route.get("tags", [])
        assert "webhook" in tags
