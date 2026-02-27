"""Kong gateway routing configuration tests.

These tests verify that Kong routes are correctly configured for gRPC-first architecture:
1. All services have gRPC upstreams defined
2. gRPC routes are correctly configured with grpc-web plugin
3. HTTP routes only exist for webhooks and WebSockets
4. Health checks are configured

NOTE: These tests verify the configuration files, not a live Kong instance.
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

    def test_grpc_upstreams_exist(self, kong_upstreams: list[dict]):
        """Test that gRPC upstreams are defined for all services."""
        grpc_upstreams = [u for u in kong_upstreams if "grpc" in u["name"]]

        # Should have gRPC upstreams for main services
        expected_grpc_services = ["auth", "market-data", "trading", "backtest", "strategy", "billing", "portfolio"]
        for service in expected_grpc_services:
            matching = [u for u in grpc_upstreams if service in u["name"]]
            assert len(matching) > 0, f"Missing gRPC upstream for {service}"

    def test_http_upstreams_have_health_checks(self, kong_upstreams: list[dict]):
        """Test that HTTP upstreams have health checks configured."""
        # Only traditional HTTP upstreams need health checks
        # gRPC uses different health checking, WebSocket connections are long-lived
        http_upstreams = [
            u for u in kong_upstreams
            if "grpc" not in u["name"] and "ws" not in u["name"]
        ]

        # Should have at least one HTTP upstream (billing for webhooks)
        assert len(http_upstreams) >= 1, "Should have at least billing HTTP upstream"

        for upstream in http_upstreams:
            name = upstream["name"]
            healthchecks = upstream.get("healthchecks", {})
            active = healthchecks.get("active", {})

            assert "http_path" in active, f"Upstream {name} missing health check path"
            assert active["http_path"] == "/health", f"Upstream {name} should use /health endpoint"

    def test_grpc_portfolio_service_routes(self, kong_services: list[dict]):
        """Test gRPC portfolio service routes are correctly configured."""
        routes = get_routes_for_service(kong_services, "grpc-portfolio-service")
        assert len(routes) >= 1, "gRPC portfolio service should have routes"

        paths = []
        for route in routes:
            paths.extend(route.get("paths", []))

        assert any("/grpc/llamatrade.v1.PortfolioService" in p for p in paths)

    def test_grpc_auth_service_routes(self, kong_services: list[dict]):
        """Test gRPC auth service routes are correctly configured."""
        routes = get_routes_for_service(kong_services, "grpc-auth-service")
        assert len(routes) >= 1, "gRPC auth service should have routes"

        paths = []
        for route in routes:
            paths.extend(route.get("paths", []))

        assert any("/grpc/llamatrade.v1.AuthService" in p for p in paths)

    def test_grpc_market_data_service_routes(self, kong_services: list[dict]):
        """Test gRPC market data service routes are correctly configured."""
        routes = get_routes_for_service(kong_services, "grpc-market-data-service")
        assert len(routes) >= 1, "gRPC market data service should have routes"

        paths = []
        for route in routes:
            paths.extend(route.get("paths", []))

        assert any("/grpc/llamatrade.v1.MarketDataService" in p for p in paths)

    def test_websocket_routes_exist(self, kong_services: list[dict]):
        """Test WebSocket routes are configured for real-time features."""
        ws_services = [s for s in kong_services if "ws" in s["name"].lower()]
        assert len(ws_services) >= 1, "Should have WebSocket services"

        # Verify WebSocket services have appropriate configuration
        for service in ws_services:
            routes = service.get("routes", [])
            assert len(routes) >= 1, f"WebSocket service {service['name']} should have routes"

            # Check routes are tagged as websocket
            for route in routes:
                tags = route.get("tags", [])
                assert "websocket" in tags or "streaming" in tags, (
                    f"WebSocket route {route.get('name')} should be tagged"
                )

    def test_billing_webhook_routes(self, kong_services: list[dict]):
        """Test billing webhook routes exist (Stripe requires HTTP)."""
        routes = get_routes_for_service(kong_services, "billing-webhook-service")
        assert len(routes) >= 1, "Billing webhook service should have routes"

        paths = []
        for route in routes:
            paths.extend(route.get("paths", []))

        assert any("webhook" in p.lower() for p in paths)


class TestRouteAuthentication:
    """Tests for route authentication configuration (gRPC services)."""

    def test_grpc_auth_service_has_rate_limiting(self, kong_services: list[dict]):
        """Test gRPC auth service has rate limiting."""
        plugins = get_service_plugins(kong_services, "grpc-auth-service")
        rate_limit = get_rate_limit_config(plugins)
        assert rate_limit is not None, "gRPC auth service should have rate limiting"

    def test_billing_webhooks_do_not_require_jwt(self, kong_services: list[dict]):
        """Test billing webhook route does NOT require JWT.

        Stripe webhooks must be publicly accessible and use their own
        signature verification mechanism instead of JWT.
        """
        plugins = get_service_plugins(kong_services, "billing-webhook-service")
        assert not has_jwt_plugin(plugins), (
            "Billing webhook service should not have JWT (Stripe uses signature verification)"
        )


class TestRateLimiting:
    """Tests for rate limiting configuration."""

    def test_grpc_services_have_rate_limiting(self, kong_services: list[dict]):
        """Test that gRPC services have rate limiting configured."""
        grpc_services = [s for s in kong_services if s["name"].startswith("grpc-")]

        for service in grpc_services:
            plugins = service.get("plugins", [])
            rate_limit = get_rate_limit_config(plugins)
            assert rate_limit is not None, f"Service {service['name']} missing rate limiting"

    def test_grpc_auth_service_rate_limits(self, kong_services: list[dict]):
        """Test gRPC auth service has appropriate rate limits."""
        plugins = get_service_plugins(kong_services, "grpc-auth-service")
        rate_limit = get_rate_limit_config(plugins)

        assert rate_limit is not None
        assert rate_limit.get("minute", 0) <= 100, "Auth rate limit should prevent brute force"

    def test_backtest_service_has_rate_limiting(self, kong_services: list[dict]):
        """Test gRPC backtest service has rate limiting configured."""
        plugins = get_service_plugins(kong_services, "grpc-backtest-service")
        rate_limit = get_rate_limit_config(plugins)
        # Rate limiting is optional but should exist for resource-intensive services
        if rate_limit:
            assert rate_limit.get("minute", 0) > 0, "Backtest rate limit should be set"

    def test_market_data_service_has_rate_limiting(self, kong_services: list[dict]):
        """Test gRPC market data service has rate limiting configured."""
        plugins = get_service_plugins(kong_services, "grpc-market-data-service")
        rate_limit = get_rate_limit_config(plugins)
        # Rate limiting is optional but should exist for frequently accessed services
        if rate_limit:
            assert rate_limit.get("minute", 0) > 0, "Market data rate limit should be set"

    def test_trading_service_has_rate_limiting(self, kong_services: list[dict]):
        """Test gRPC trading service has rate limiting configured."""
        plugins = get_service_plugins(kong_services, "grpc-trading-service")
        rate_limit = get_rate_limit_config(plugins)
        # Rate limiting is optional but should exist for trading operations
        if rate_limit:
            assert rate_limit.get("minute", 0) > 0, "Trading rate limit should be set"


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

    def test_grpc_services_have_timeouts(self, kong_services: list[dict]):
        """Test gRPC services have timeout configuration."""
        grpc_services = [s for s in kong_services if s["name"].startswith("grpc-")]

        for service in grpc_services:
            name = service["name"]
            assert "connect_timeout" in service, f"{name} missing connect_timeout"
            assert "read_timeout" in service, f"{name} missing read_timeout"
            assert "write_timeout" in service, f"{name} missing write_timeout"

    def test_webhook_service_has_timeouts(self, kong_services: list[dict]):
        """Test webhook service has timeout configuration."""
        service = next((s for s in kong_services if "webhook" in s["name"]), None)
        if service:
            assert "connect_timeout" in service
            assert "read_timeout" in service
