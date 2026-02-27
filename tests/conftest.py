"""Root-level test configuration with container fixtures.

This module provides session-scoped fixtures for PostgreSQL and Redis
test containers. These containers are shared across all integration tests
for efficiency.
"""

import os

# Register fixture plugins for integration tests
# Only loaded when running from root directory (tests.integration is in path)
try:
    import tests.integration.fixtures.auth  # noqa: F401
    import tests.integration.fixtures.strategies  # noqa: F401

    pytest_plugins = [
        "tests.integration.fixtures.auth",
        "tests.integration.fixtures.strategies",
    ]
except ImportError:
    # Running service tests independently - fixtures not needed
    pytest_plugins = []
from collections.abc import AsyncGenerator, Generator

import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Start PostgreSQL container for the test session.

    Uses testcontainers to automatically manage container lifecycle.
    Container is started once per test session and cleaned up automatically.
    """
    with PostgresContainer(
        image="postgres:16-alpine",
        username="postgres",
        password="postgres",
        dbname="llamatrade_test",
        driver="asyncpg",
    ) as postgres:
        yield postgres


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer, None, None]:
    """Start Redis container for the test session."""
    with RedisContainer(image="redis:7-alpine") as redis:
        yield redis


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """Get the database URL for the test PostgreSQL container.

    Returns URL in asyncpg format: postgresql+asyncpg://user:pass@host:port/db
    """
    # testcontainers returns psycopg format, convert to asyncpg
    url = postgres_container.get_connection_url()
    # Convert from psycopg2 to asyncpg format
    return url.replace("psycopg2", "asyncpg")


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    """Get the Redis URL for the test container."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}"


@pytest.fixture(scope="session", autouse=True)
def set_test_environment(database_url: str, redis_url: str) -> Generator[None, None, None]:
    """Set environment variables for test containers.

    This fixture is autouse=True so it runs automatically for all tests.
    Sets DATABASE_URL and REDIS_URL to point to test containers.
    """
    original_db_url = os.environ.get("DATABASE_URL")
    original_redis_url = os.environ.get("REDIS_URL")
    original_jwt_secret = os.environ.get("JWT_SECRET")

    # Set test environment variables
    os.environ["DATABASE_URL"] = database_url
    os.environ["REDIS_URL"] = redis_url
    os.environ["JWT_SECRET"] = "test-secret-for-integration-tests"
    os.environ["TESTING"] = "true"

    yield

    # Restore original environment
    if original_db_url is not None:
        os.environ["DATABASE_URL"] = original_db_url
    else:
        os.environ.pop("DATABASE_URL", None)

    if original_redis_url is not None:
        os.environ["REDIS_URL"] = original_redis_url
    else:
        os.environ.pop("REDIS_URL", None)

    if original_jwt_secret is not None:
        os.environ["JWT_SECRET"] = original_jwt_secret
    else:
        os.environ.pop("JWT_SECRET", None)

    os.environ.pop("TESTING", None)
