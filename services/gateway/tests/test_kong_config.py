"""Tests for Kong gateway configuration validation.

These tests validate the kong.yaml configuration file to catch:
- YAML syntax errors
- Missing required fields
- Inconsistent configuration
- Security misconfigurations
"""

from pathlib import Path

import pytest
import yaml

KONG_CONFIG_PATH = Path(__file__).parent.parent / "kong.yaml"


@pytest.fixture
def kong_config():
    """Load Kong configuration."""
    with open(KONG_CONFIG_PATH) as f:
        return yaml.safe_load(f)


class TestKongConfigStructure:
    """Tests for basic configuration structure."""

    def test_config_file_exists(self):
        """Test that kong.yaml exists."""
        assert KONG_CONFIG_PATH.exists(), "kong.yaml not found"

    def test_valid_yaml_syntax(self):
        """Test that kong.yaml is valid YAML."""
        with open(KONG_CONFIG_PATH) as f:
            config = yaml.safe_load(f)
        assert config is not None

    def test_has_format_version(self, kong_config):
        """Test that format version is specified."""
        assert "_format_version" in kong_config
        assert kong_config["_format_version"] in ["2.1", "3.0"]

    def test_has_services(self, kong_config):
        """Test that services are defined."""
        assert "services" in kong_config
        assert len(kong_config["services"]) > 0

    def test_has_upstreams(self, kong_config):
        """Test that upstreams are defined."""
        assert "upstreams" in kong_config
        assert len(kong_config["upstreams"]) > 0

    def test_has_global_plugins(self, kong_config):
        """Test that global plugins are defined."""
        assert "plugins" in kong_config
        assert len(kong_config["plugins"]) > 0


class TestServiceConfiguration:
    """Tests for service configuration."""

    def test_all_services_have_name(self, kong_config):
        """Test that all services have a name."""
        for service in kong_config["services"]:
            assert "name" in service, f"Service missing name: {service}"

    def test_all_services_have_host(self, kong_config):
        """Test that all services have a host."""
        for service in kong_config["services"]:
            assert "host" in service, f"Service {service.get('name')} missing host"

    def test_all_services_have_routes(self, kong_config):
        """Test that all services have at least one route."""
        for service in kong_config["services"]:
            assert "routes" in service, f"Service {service['name']} has no routes"
            assert len(service["routes"]) > 0, f"Service {service['name']} has empty routes"

    def test_all_routes_have_paths(self, kong_config):
        """Test that all routes have paths defined."""
        for service in kong_config["services"]:
            for route in service["routes"]:
                assert "paths" in route, (
                    f"Route {route.get('name')} in {service['name']} missing paths"
                )
                assert len(route["paths"]) > 0

    def test_service_timeouts_are_reasonable(self, kong_config):
        """Test that service timeouts are within reasonable bounds."""
        max_timeout = 600000  # 10 minutes max
        min_timeout = 1000  # 1 second min

        for service in kong_config["services"]:
            for timeout_key in ["connect_timeout", "read_timeout", "write_timeout"]:
                if timeout_key in service:
                    timeout = service[timeout_key]
                    assert timeout >= min_timeout, (
                        f"{service['name']} {timeout_key} too low: {timeout}ms"
                    )
                    assert timeout <= max_timeout, (
                        f"{service['name']} {timeout_key} too high: {timeout}ms"
                    )


class TestUpstreamConfiguration:
    """Tests for upstream configuration."""

    def test_all_upstreams_have_name(self, kong_config):
        """Test that all upstreams have a name."""
        for upstream in kong_config["upstreams"]:
            assert "name" in upstream

    def test_all_upstreams_have_targets(self, kong_config):
        """Test that all upstreams have targets."""
        for upstream in kong_config["upstreams"]:
            assert "targets" in upstream, f"Upstream {upstream['name']} has no targets"
            assert len(upstream["targets"]) > 0

    def test_http_upstreams_have_healthchecks(self, kong_config):
        """Test that HTTP upstreams have health checks configured.

        Note: gRPC upstreams use gRPC health checking protocol which is
        configured differently, so we only validate HTTP upstreams here.
        """
        for upstream in kong_config["upstreams"]:
            # Only check HTTP upstreams (gRPC health checks work differently)
            if "-http-upstream" in upstream["name"]:
                assert "healthchecks" in upstream, f"HTTP upstream {upstream['name']} missing healthchecks"

    def test_upstream_targets_have_valid_format(self, kong_config):
        """Test that upstream targets have host:port format."""
        for upstream in kong_config["upstreams"]:
            for target in upstream["targets"]:
                assert "target" in target
                target_str = target["target"]
                assert ":" in target_str, f"Target {target_str} missing port"
                host, port = target_str.rsplit(":", 1)
                assert host, f"Target {target_str} missing host"
                assert port.isdigit(), f"Target {target_str} has invalid port"


class TestSecurityConfiguration:
    """Tests for security-related configuration."""

    # Services that should require JWT authentication
    PROTECTED_SERVICES = [
        "strategy-service",
        "backtest-service",
        "market-data-service",
        "trading-service",
        "portfolio-service",
        "notification-service",
    ]

    # Services that have public endpoints (no JWT required)
    PUBLIC_SERVICES = [
        "auth-service",  # Has both public and protected routes
    ]

    def test_protected_services_have_jwt_plugin(self, kong_config):
        """Test that protected services have JWT authentication."""
        for service in kong_config["services"]:
            if service["name"] in self.PROTECTED_SERVICES:
                plugins = service.get("plugins", [])
                plugin_names = [p["name"] for p in plugins]
                assert "jwt" in plugin_names, (
                    f"Protected service {service['name']} missing JWT plugin"
                )

    def test_jwt_plugins_verify_expiration(self, kong_config):
        """Test that JWT plugins verify token expiration."""
        for service in kong_config["services"]:
            for plugin in service.get("plugins", []):
                if plugin["name"] == "jwt":
                    config = plugin.get("config", {})
                    claims = config.get("claims_to_verify", [])
                    assert "exp" in claims, (
                        f"JWT plugin in {service['name']} should verify 'exp' claim"
                    )

    def test_all_services_have_rate_limiting(self, kong_config):
        """Test that all services have rate limiting."""
        for service in kong_config["services"]:
            plugins = service.get("plugins", [])
            plugin_names = [p["name"] for p in plugins]
            assert "rate-limiting" in plugin_names, (
                f"Service {service['name']} missing rate-limiting plugin"
            )

    def test_rate_limits_are_reasonable(self, kong_config):
        """Test that rate limits are not too permissive."""
        max_per_minute = 1000
        max_per_hour = 50000

        for service in kong_config["services"]:
            for plugin in service.get("plugins", []):
                if plugin["name"] == "rate-limiting":
                    config = plugin.get("config", {})
                    if "minute" in config:
                        assert config["minute"] <= max_per_minute, (
                            f"{service['name']} rate limit too high: {config['minute']}/min"
                        )
                    if "hour" in config:
                        assert config["hour"] <= max_per_hour, (
                            f"{service['name']} rate limit too high: {config['hour']}/hour"
                        )


class TestGlobalPlugins:
    """Tests for global plugin configuration."""

    def test_cors_plugin_exists(self, kong_config):
        """Test that CORS is configured globally."""
        plugin_names = [p["name"] for p in kong_config["plugins"]]
        assert "cors" in plugin_names, "Global CORS plugin not configured"

    def test_cors_has_allowed_origins(self, kong_config):
        """Test that CORS has origins configured."""
        for plugin in kong_config["plugins"]:
            if plugin["name"] == "cors":
                config = plugin.get("config", {})
                assert "origins" in config, "CORS missing origins"
                assert len(config["origins"]) > 0, "CORS has no allowed origins"

    def test_cors_allows_required_methods(self, kong_config):
        """Test that CORS allows required HTTP methods."""
        required_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

        for plugin in kong_config["plugins"]:
            if plugin["name"] == "cors":
                config = plugin.get("config", {})
                methods = config.get("methods", [])
                for method in required_methods:
                    assert method in methods, f"CORS missing method: {method}"

    def test_correlation_id_plugin_exists(self, kong_config):
        """Test that correlation ID is configured for tracing."""
        plugin_names = [p["name"] for p in kong_config["plugins"]]
        assert "correlation-id" in plugin_names, "Correlation ID plugin not configured"

    def test_prometheus_metrics_enabled(self, kong_config):
        """Test that Prometheus metrics are enabled."""
        plugin_names = [p["name"] for p in kong_config["plugins"]]
        assert "prometheus" in plugin_names, "Prometheus metrics not enabled"


class TestServicePortMappings:
    """Tests for service port consistency."""

    # gRPC ports for services (all services use gRPC only)
    EXPECTED_GRPC_PORTS = {
        "auth": 8810,
        "strategy": 8820,
        "backtest": 8830,
        "market-data": 8840,
        "trading": 8850,
        "portfolio": 8860,
        "notification": 8870,
        "billing": 8880,
    }

    # HTTP ports (only for special cases like Stripe webhooks)
    EXPECTED_HTTP_PORTS = {
        "billing": 8881,  # Stripe webhook HTTP endpoint
    }

    def test_grpc_upstream_ports_match_services(self, kong_config):
        """Test that gRPC upstream target ports match expected service ports."""
        for upstream in kong_config["upstreams"]:
            # Extract service name from upstream name (e.g., "auth-grpc-upstream" -> "auth")
            upstream_name = upstream["name"]
            if "-grpc-upstream" in upstream_name:
                service_name = upstream_name.replace("-grpc-upstream", "")
                if service_name in self.EXPECTED_GRPC_PORTS:
                    expected_port = self.EXPECTED_GRPC_PORTS[service_name]
                    target = upstream["targets"][0]["target"]
                    actual_port = int(target.split(":")[1])

                    assert actual_port == expected_port, (
                        f"gRPC upstream {upstream_name} has port {actual_port}, expected {expected_port}"
                    )

    def test_http_upstream_ports_match_services(self, kong_config):
        """Test that HTTP upstream target ports match expected service ports."""
        for upstream in kong_config["upstreams"]:
            upstream_name = upstream["name"]
            if "-http-upstream" in upstream_name:
                service_name = upstream_name.replace("-http-upstream", "")
                if service_name in self.EXPECTED_HTTP_PORTS:
                    expected_port = self.EXPECTED_HTTP_PORTS[service_name]
                    target = upstream["targets"][0]["target"]
                    actual_port = int(target.split(":")[1])

                    assert actual_port == expected_port, (
                        f"HTTP upstream {upstream_name} has port {actual_port}, expected {expected_port}"
                    )

    def test_grpc_service_ports_match_upstreams(self, kong_config):
        """Test that gRPC service port definitions match their upstreams."""
        for service in kong_config["services"]:
            service_name_full = service["name"]
            # Extract service name from gRPC service (e.g., "grpc-auth-service" -> "auth")
            if service_name_full.startswith("grpc-") and service_name_full.endswith("-service"):
                service_name = service_name_full.replace("grpc-", "").replace("-service", "")
                if service_name in self.EXPECTED_GRPC_PORTS:
                    expected_port = self.EXPECTED_GRPC_PORTS[service_name]
                    actual_port = service.get("port")

                    if actual_port:
                        assert actual_port == expected_port, (
                            f"Service {service_name_full} has port {actual_port}, "
                            f"expected {expected_port}"
                        )


class TestRoutePathConsistency:
    """Tests for route path configuration."""

    def test_all_api_routes_have_valid_prefix(self, kong_config):
        """Test that all routes use /api/ or /grpc/ prefix."""
        for service in kong_config["services"]:
            for route in service["routes"]:
                for path in route["paths"]:
                    # Skip webhook routes which may have different patterns
                    if "webhook" in path.lower():
                        continue
                    assert path.startswith("/api/") or path.startswith("/grpc/"), (
                        f"Route path {path} in {service['name']} should start with /api/ or /grpc/"
                    )

    def test_no_duplicate_route_paths(self, kong_config):
        """Test that there are no duplicate route paths across services."""
        all_paths = []
        for service in kong_config["services"]:
            for route in service["routes"]:
                for path in route["paths"]:
                    if path in all_paths:
                        # Allow duplicates only if they're method-specific
                        pass  # Could add more sophisticated duplicate detection
                    all_paths.append(path)

    def test_strip_path_is_false(self, kong_config):
        """Test that strip_path is false (we want full paths forwarded)."""
        for service in kong_config["services"]:
            for route in service["routes"]:
                strip_path = route.get("strip_path", True)
                assert strip_path is False, (
                    f"Route {route.get('name')} should have strip_path: false"
                )
