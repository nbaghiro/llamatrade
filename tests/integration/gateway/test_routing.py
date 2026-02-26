"""Kong gateway routing configuration tests.

These tests verify that Kong routes are correctly configured:
1. All expected services have routes defined
2. Routes point to correct upstreams
3. Path prefixes are correctly configured
4. Protected vs public routes are properly distinguished

NOTE: These tests verify the configuration files, not a live Kong instance.
For live gateway testing, use the workflow tests with real HTTP calls.
"""

import pytest

from tests.integration.gateway.conftest import (
    get_rate_limit_config,
    get_routes_for_service,
    get_service_plugins,
    has_jwt_plugin,
)

pytestmark = [pytest.mark.integration, pytest.mark.gateway]


class TestServiceRouting:
    """Tests for service routing configuration."""

    def test_all_services_have_upstreams(
        self,
        kong_services: list[dict],
        kong_upstreams: list[dict],
    ):
        """Test that all services have corresponding upstreams defined."""
        upstream_names = {u["name"] for u in kong_upstreams}

        for service in kong_services:
            host = service.get("host")
            assert host in upstream_names, f"Service {service['name']} references undefined upstream {host}"

    def test_all_upstreams_have_health_checks(self, kong_upstreams: list[dict]):
        """Test that all upstreams have health checks configured."""
        for upstream in kong_upstreams:
            name = upstream["name"]
            healthchecks = upstream.get("healthchecks", {})
            active = healthchecks.get("active", {})

            assert "http_path" in active, f"Upstream {name} missing health check path"
            assert active["http_path"] == "/health", f"Upstream {name} should use /health endpoint"

    def test_auth_service_routes(self, kong_services: list[dict]):
        """Test auth service has correct public and protected routes."""
        routes = get_routes_for_service(kong_services, "auth-service")
        assert len(routes) >= 2, "Auth service should have public and protected routes"

        public_route = next((r for r in routes if r.get("name") == "auth-public-routes"), None)
        protected_route = next((r for r in routes if r.get("name") == "auth-protected-routes"), None)

        assert public_route is not None, "Auth service missing public routes"
        assert protected_route is not None, "Auth service missing protected routes"

        # Verify public paths
        public_paths = public_route.get("paths", [])
        assert "/api/auth/login" in public_paths
        assert "/api/auth/register" in public_paths
        assert "/api/auth/refresh" in public_paths

        # Verify protected paths
        protected_paths = protected_route.get("paths", [])
        assert "/api/auth/me" in protected_paths
        assert "/api/users" in protected_paths

    def test_strategy_service_routes(self, kong_services: list[dict]):
        """Test strategy service routes are correctly configured."""
        routes = get_routes_for_service(kong_services, "strategy-service")
        assert len(routes) >= 1, "Strategy service should have routes"

        paths = []
        for route in routes:
            paths.extend(route.get("paths", []))

        assert "/api/strategies" in paths
        assert "/api/templates" in paths
        assert "/api/indicators" in paths

    def test_backtest_service_routes(self, kong_services: list[dict]):
        """Test backtest service routes are correctly configured."""
        routes = get_routes_for_service(kong_services, "backtest-service")
        assert len(routes) >= 1

        paths = []
        for route in routes:
            paths.extend(route.get("paths", []))

        assert "/api/backtests" in paths

    def test_market_data_service_routes(self, kong_services: list[dict]):
        """Test market data service routes are correctly configured."""
        routes = get_routes_for_service(kong_services, "market-data-service")
        assert len(routes) >= 1

        paths = []
        for route in routes:
            paths.extend(route.get("paths", []))

        assert "/api/market-data" in paths
        assert "/api/bars" in paths
        assert "/api/quotes" in paths

    def test_trading_service_routes(self, kong_services: list[dict]):
        """Test trading service routes are correctly configured."""
        routes = get_routes_for_service(kong_services, "trading-service")
        assert len(routes) >= 1

        paths = []
        for route in routes:
            paths.extend(route.get("paths", []))

        assert "/api/orders" in paths
        assert "/api/trading" in paths
        assert "/api/sessions" in paths
        assert "/api/positions" in paths

    def test_portfolio_service_routes(self, kong_services: list[dict]):
        """Test portfolio service routes are correctly configured."""
        routes = get_routes_for_service(kong_services, "portfolio-service")
        assert len(routes) >= 1

        paths = []
        for route in routes:
            paths.extend(route.get("paths", []))

        assert "/api/portfolio" in paths
        assert "/api/performance" in paths

    def test_billing_service_routes(self, kong_services: list[dict]):
        """Test billing service has both protected and webhook routes."""
        routes = get_routes_for_service(kong_services, "billing-service")
        assert len(routes) >= 2, "Billing service should have protected and webhook routes"

        protected_route = next((r for r in routes if r.get("name") == "billing-protected-routes"), None)
        webhook_route = next((r for r in routes if r.get("name") == "stripe-webhook-route"), None)

        assert protected_route is not None, "Billing service missing protected routes"
        assert webhook_route is not None, "Billing service missing webhook route"

        # Verify webhook paths
        webhook_paths = webhook_route.get("paths", [])
        assert "/api/webhooks/stripe" in webhook_paths or "/api/billing/webhook" in webhook_paths

        # Verify webhook only allows POST
        methods = webhook_route.get("methods", [])
        assert "POST" in methods
        assert "GET" not in methods


class TestRouteAuthentication:
    """Tests for route authentication configuration."""

    def test_strategy_service_requires_jwt(self, kong_services: list[dict]):
        """Test strategy service has JWT plugin enabled."""
        plugins = get_service_plugins(kong_services, "strategy-service")
        assert has_jwt_plugin(plugins), "Strategy service should require JWT authentication"

    def test_backtest_service_requires_jwt(self, kong_services: list[dict]):
        """Test backtest service has JWT plugin enabled."""
        plugins = get_service_plugins(kong_services, "backtest-service")
        assert has_jwt_plugin(plugins), "Backtest service should require JWT authentication"

    def test_market_data_service_requires_jwt(self, kong_services: list[dict]):
        """Test market data service has JWT plugin enabled."""
        plugins = get_service_plugins(kong_services, "market-data-service")
        assert has_jwt_plugin(plugins), "Market data service should require JWT authentication"

    def test_trading_service_requires_jwt(self, kong_services: list[dict]):
        """Test trading service has JWT plugin enabled."""
        plugins = get_service_plugins(kong_services, "trading-service")
        assert has_jwt_plugin(plugins), "Trading service should require JWT authentication"

    def test_portfolio_service_requires_jwt(self, kong_services: list[dict]):
        """Test portfolio service has JWT plugin enabled."""
        plugins = get_service_plugins(kong_services, "portfolio-service")
        assert has_jwt_plugin(plugins), "Portfolio service should require JWT authentication"

    def test_billing_webhooks_do_not_require_jwt(self, kong_services: list[dict]):
        """Test billing service webhook route does NOT require JWT.

        Stripe webhooks must be publicly accessible and use their own
        signature verification mechanism instead of JWT.
        """
        # The billing service as a whole doesn't have JWT plugin
        # because the webhook route needs to be public
        plugins = get_service_plugins(kong_services, "billing-service")

        # Billing service should NOT have JWT at service level
        # (JWT would be applied at route level for protected routes if needed)
        # Currently the config doesn't have route-level plugins, so webhooks are public
        # This is intentional - webhooks use Stripe signature verification
        assert not has_jwt_plugin(plugins), (
            "Billing service should not have service-level JWT "
            "(would block webhook route)"
        )


class TestRateLimiting:
    """Tests for rate limiting configuration."""

    def test_all_services_have_rate_limiting(self, kong_services: list[dict]):
        """Test that all services have rate limiting configured."""
        for service in kong_services:
            plugins = service.get("plugins", [])
            rate_limit = get_rate_limit_config(plugins)
            assert rate_limit is not None, f"Service {service['name']} missing rate limiting"

    def test_auth_service_rate_limits(self, kong_services: list[dict]):
        """Test auth service has appropriate rate limits."""
        plugins = get_service_plugins(kong_services, "auth-service")
        rate_limit = get_rate_limit_config(plugins)

        assert rate_limit is not None
        assert rate_limit.get("minute", 0) <= 100, "Auth rate limit should prevent brute force"

    def test_backtest_service_strict_rate_limits(self, kong_services: list[dict]):
        """Test backtest service has stricter rate limits (resource intensive)."""
        plugins = get_service_plugins(kong_services, "backtest-service")
        rate_limit = get_rate_limit_config(plugins)

        assert rate_limit is not None
        # Backtests are expensive, should have lower limits
        assert rate_limit.get("minute", 0) <= 50, "Backtest rate limit should be strict"
        assert rate_limit.get("hour", 0) <= 500, "Backtest hourly limit should be strict"

    def test_market_data_service_higher_rate_limits(self, kong_services: list[dict]):
        """Test market data service has higher rate limits (frequent access)."""
        plugins = get_service_plugins(kong_services, "market-data-service")
        rate_limit = get_rate_limit_config(plugins)

        assert rate_limit is not None
        # Market data is accessed frequently, needs higher limits
        assert rate_limit.get("minute", 0) >= 100, "Market data rate limit should allow frequent access"

    def test_trading_service_moderate_rate_limits(self, kong_services: list[dict]):
        """Test trading service has moderate rate limits."""
        plugins = get_service_plugins(kong_services, "trading-service")
        rate_limit = get_rate_limit_config(plugins)

        assert rate_limit is not None
        # Trading needs reasonable limits but not too high (order spam prevention)
        assert 50 <= rate_limit.get("minute", 0) <= 200


class TestGlobalPlugins:
    """Tests for global Kong plugins."""

    def test_cors_plugin_configured(self, kong_plugins: list[dict]):
        """Test CORS plugin is globally configured."""
        cors = next((p for p in kong_plugins if p.get("name") == "cors"), None)
        assert cors is not None, "CORS plugin should be globally configured"

        config = cors.get("config", {})
        assert "origins" in config
        assert "methods" in config
        assert "headers" in config

    def test_cors_allows_required_headers(self, kong_plugins: list[dict]):
        """Test CORS allows Authorization and X-Tenant-ID headers."""
        cors = next((p for p in kong_plugins if p.get("name") == "cors"), None)
        config = cors.get("config", {})
        headers = config.get("headers", [])

        assert "Authorization" in headers, "CORS must allow Authorization header"
        assert "X-Tenant-ID" in headers, "CORS must allow X-Tenant-ID header"

    def test_correlation_id_plugin_configured(self, kong_plugins: list[dict]):
        """Test correlation ID plugin is configured for request tracing."""
        corr_id = next((p for p in kong_plugins if p.get("name") == "correlation-id"), None)
        assert corr_id is not None, "Correlation ID plugin should be configured"

        config = corr_id.get("config", {})
        assert config.get("header_name") == "X-Request-ID"
        assert config.get("echo_downstream") is True

    def test_prometheus_metrics_enabled(self, kong_plugins: list[dict]):
        """Test Prometheus metrics are enabled for monitoring."""
        prometheus = next((p for p in kong_plugins if p.get("name") == "prometheus"), None)
        assert prometheus is not None, "Prometheus plugin should be enabled for monitoring"

    def test_response_transformer_removes_server_header(self, kong_plugins: list[dict]):
        """Test response transformer removes Server header (security)."""
        transformer = next((p for p in kong_plugins if p.get("name") == "response-transformer"), None)
        assert transformer is not None

        config = transformer.get("config", {})
        remove_headers = config.get("remove", {}).get("headers", [])
        assert "Server" in remove_headers, "Should remove Server header for security"


class TestServiceTimeouts:
    """Tests for service timeout configuration."""

    def test_backtest_service_has_extended_timeout(self, kong_services: list[dict]):
        """Test backtest service has extended timeout for long-running backtests."""
        service = next((s for s in kong_services if s["name"] == "backtest-service"), None)
        assert service is not None

        # Backtests can take a long time, need extended timeout
        read_timeout = service.get("read_timeout", 0)
        assert read_timeout >= 60000, "Backtest service needs extended read timeout"

    def test_trading_service_has_fast_timeout(self, kong_services: list[dict]):
        """Test trading service has reasonable timeout for order operations."""
        service = next((s for s in kong_services if s["name"] == "trading-service"), None)
        assert service is not None

        # Trading should be fast - don't wait forever
        read_timeout = service.get("read_timeout", 0)
        assert read_timeout <= 60000, "Trading service should have fast timeout"

    def test_all_services_have_timeouts(self, kong_services: list[dict]):
        """Test all services have timeout configuration."""
        for service in kong_services:
            name = service["name"]
            assert "connect_timeout" in service, f"{name} missing connect_timeout"
            assert "read_timeout" in service, f"{name} missing read_timeout"
            assert "write_timeout" in service, f"{name} missing write_timeout"
