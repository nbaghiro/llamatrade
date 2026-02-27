"""Kong gateway authentication propagation tests.

These tests verify that:
1. gRPC services have proper authentication via grpc-web plugin
2. Webhook routes are publicly accessible (use signature verification)
3. JWT claims are properly validated
4. CORS headers are configured

NOTE: Most API calls now use gRPC. Only webhooks and WebSockets use HTTP.
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

    def test_stripe_webhook_is_public(self, kong_services: list[dict]):
        """Test Stripe webhook endpoint is publicly accessible.

        Stripe webhooks use signature verification, not JWT.
        """
        routes = get_routes_for_service(kong_services, "billing-webhook-service")

        assert len(routes) >= 1, "Billing webhook service should have routes"
        webhook_route = routes[0]
        assert "webhook" in webhook_route.get("tags", [])


class TestGRPCServices:
    """Tests for gRPC service configuration."""

    def test_grpc_auth_service_has_grpc_web_plugin(self, kong_services: list[dict]):
        """Test gRPC auth service has grpc-web plugin for browser communication."""
        plugins = get_service_plugins(kong_services, "grpc-auth-service")
        grpc_web = next((p for p in plugins if p.get("name") == "grpc-web"), None)

        assert grpc_web is not None, "gRPC auth service should have grpc-web plugin"

    def test_grpc_market_data_service_exists(self, kong_services: list[dict]):
        """Test gRPC market data service is configured."""
        service = next((s for s in kong_services if s["name"] == "grpc-market-data-service"), None)
        assert service is not None, "gRPC market data service should exist"
        assert service.get("protocol") == "grpc"

    def test_grpc_strategy_service_exists(self, kong_services: list[dict]):
        """Test gRPC strategy service is configured."""
        service = next((s for s in kong_services if s["name"] == "grpc-strategy-service"), None)
        assert service is not None, "gRPC strategy service should exist"
        assert service.get("protocol") == "grpc"

    def test_grpc_backtest_service_exists(self, kong_services: list[dict]):
        """Test gRPC backtest service is configured."""
        service = next((s for s in kong_services if s["name"] == "grpc-backtest-service"), None)
        assert service is not None, "gRPC backtest service should exist"
        assert service.get("protocol") == "grpc"

    def test_grpc_trading_service_exists(self, kong_services: list[dict]):
        """Test gRPC trading service is configured."""
        service = next((s for s in kong_services if s["name"] == "grpc-trading-service"), None)
        assert service is not None, "gRPC trading service should exist"
        assert service.get("protocol") == "grpc"

    def test_grpc_billing_service_exists(self, kong_services: list[dict]):
        """Test gRPC billing service is configured."""
        service = next((s for s in kong_services if s["name"] == "grpc-billing-service"), None)
        assert service is not None, "gRPC billing service should exist"
        assert service.get("protocol") == "grpc"


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

    def test_grpc_routes_tagged(self, kong_services: list[dict]):
        """Test gRPC routes are tagged as 'grpc'."""
        grpc_services = [s for s in kong_services if s["name"].startswith("grpc-")]

        for service in grpc_services:
            routes = service.get("routes", [])
            for route in routes:
                tags = route.get("tags", [])
                assert "grpc" in tags, (
                    f"Route {route.get('name')} should be tagged 'grpc'"
                )

    def test_public_routes_tagged_appropriately(self, kong_services: list[dict]):
        """Test public routes (auth, webhooks) are tagged as 'public' or 'webhook'."""
        # Auth public routes
        auth_routes = get_routes_for_service(kong_services, "auth-service")
        if auth_routes:
            public_route = next((r for r in auth_routes if "public" in r.get("name", "").lower()), None)
            if public_route:
                tags = public_route.get("tags", [])
                assert "public" in tags

    def test_webhook_routes_tagged_webhook(self, kong_services: list[dict]):
        """Test webhook routes are tagged as 'webhook'."""
        billing_routes = get_routes_for_service(kong_services, "billing-webhook-service")

        if billing_routes:
            webhook_route = billing_routes[0]
            tags = webhook_route.get("tags", [])
            assert "webhook" in tags
