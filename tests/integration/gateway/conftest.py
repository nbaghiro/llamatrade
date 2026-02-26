"""Gateway test fixtures.

Provides fixtures for testing Kong gateway configuration and routing.
"""

from pathlib import Path

import pytest
import yaml


@pytest.fixture(scope="module")
def kong_config() -> dict:
    """Load Kong configuration from kong.yaml."""
    # Path: tests/integration/gateway/conftest.py -> project root (3 parents up)
    config_path = Path(__file__).parents[3] / "services" / "gateway" / "kong.yaml"
    if not config_path.exists():
        pytest.skip(f"Kong configuration not found at {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def kong_local_config() -> dict:
    """Load Kong local development configuration."""
    config_path = Path(__file__).parents[3] / "services" / "gateway" / "kong.local.yaml"
    if not config_path.exists():
        pytest.skip(f"Kong local configuration not found at {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def kong_services(kong_config: dict) -> list[dict]:
    """Extract services from Kong config."""
    return kong_config.get("services", [])


@pytest.fixture(scope="module")
def kong_plugins(kong_config: dict) -> list[dict]:
    """Extract global plugins from Kong config."""
    return kong_config.get("plugins", [])


@pytest.fixture(scope="module")
def kong_upstreams(kong_config: dict) -> list[dict]:
    """Extract upstreams from Kong config."""
    return kong_config.get("upstreams", [])


def get_routes_for_service(services: list[dict], service_name: str) -> list[dict]:
    """Helper to get routes for a specific service."""
    for service in services:
        if service.get("name") == service_name:
            return service.get("routes", [])
    return []


def get_service_plugins(services: list[dict], service_name: str) -> list[dict]:
    """Helper to get plugins for a specific service."""
    for service in services:
        if service.get("name") == service_name:
            return service.get("plugins", [])
    return []


def has_jwt_plugin(plugins: list[dict]) -> bool:
    """Check if JWT plugin is configured."""
    return any(p.get("name") == "jwt" for p in plugins)


def get_rate_limit_config(plugins: list[dict]) -> dict | None:
    """Get rate limiting configuration from plugins."""
    for plugin in plugins:
        if plugin.get("name") == "rate-limiting":
            return plugin.get("config", {})
    return None
