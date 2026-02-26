"""Workflow test configuration with service startup fixtures.

This module provides fixtures for starting and managing service processes
for multi-service integration tests.
"""

import asyncio
import os
import signal
import subprocess
import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

# Service ports (from CLAUDE.md)
SERVICE_PORTS = {
    "auth": 47810,
    "strategy": 47820,
    "backtest": 47830,
    "market-data": 47840,
    "trading": 47850,
    "portfolio": 47860,
    "notification": 47870,
    "billing": 47880,
}

# Base path for services
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SERVICES_DIR = PROJECT_ROOT / "services"


@dataclass
class ServiceProcess:
    """Represents a running service process."""

    name: str
    process: subprocess.Popen
    port: int
    base_url: str

    def is_alive(self) -> bool:
        """Check if the process is still running."""
        return self.process.poll() is None

    def stop(self) -> None:
        """Stop the service process."""
        if self.is_alive():
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


@contextmanager
def start_service(
    name: str,
    port: int | None = None,
    env_overrides: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> Generator[ServiceProcess, None, None]:
    """Start a service as a subprocess.

    Args:
        name: Service name (e.g., "auth", "strategy")
        port: Port to run on (default: from SERVICE_PORTS)
        env_overrides: Additional environment variables
        timeout: Seconds to wait for health check

    Yields:
        ServiceProcess with process handle and connection info
    """
    if port is None:
        port = SERVICE_PORTS.get(name, 8000)

    service_dir = SERVICES_DIR / name
    if not service_dir.exists():
        raise ValueError(f"Service directory not found: {service_dir}")

    # Build environment
    env = os.environ.copy()
    env["PORT"] = str(port)
    if env_overrides:
        env.update(env_overrides)

    # Start the service
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", str(port)],
        cwd=str(service_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://localhost:{port}"
    service = ServiceProcess(name=name, process=process, port=port, base_url=base_url)

    try:
        # Wait for health check
        _wait_for_health(base_url, timeout)
        yield service
    finally:
        service.stop()


def _wait_for_health(base_url: str, timeout: float) -> None:
    """Wait for a service to become healthy."""
    import time

    deadline = time.time() + timeout
    last_error = None

    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=2.0)
            if response.status_code == 200:
                return
        except (httpx.RequestError, httpx.HTTPError) as e:
            last_error = e

        time.sleep(0.5)

    raise TimeoutError(f"Service at {base_url} did not become healthy within {timeout}s: {last_error}")


@asynccontextmanager
async def start_service_async(
    name: str,
    port: int | None = None,
    env_overrides: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> AsyncGenerator[ServiceProcess, None]:
    """Async version of start_service."""
    # Use sync context manager in async context
    with start_service(name, port, env_overrides, timeout) as service:
        yield service


# ==========================================
# Pytest fixtures for common service setups
# ==========================================


@pytest.fixture(scope="module")
def auth_service(
    database_url: str,
    redis_url: str,
) -> Generator[ServiceProcess, None, None]:
    """Start auth service for the test module."""
    env = {
        "DATABASE_URL": database_url,
        "REDIS_URL": redis_url,
        "JWT_SECRET": "test-secret-for-integration-tests",
    }

    with start_service("auth", env_overrides=env) as service:
        yield service


@pytest.fixture(scope="module")
def strategy_service(
    database_url: str,
    redis_url: str,
) -> Generator[ServiceProcess, None, None]:
    """Start strategy service for the test module."""
    env = {
        "DATABASE_URL": database_url,
        "REDIS_URL": redis_url,
        "JWT_SECRET": "test-secret-for-integration-tests",
    }

    with start_service("strategy", env_overrides=env) as service:
        yield service


@pytest.fixture(scope="module")
def backtest_service(
    database_url: str,
    redis_url: str,
) -> Generator[ServiceProcess, None, None]:
    """Start backtest service for the test module."""
    env = {
        "DATABASE_URL": database_url,
        "REDIS_URL": redis_url,
        "JWT_SECRET": "test-secret-for-integration-tests",
    }

    with start_service("backtest", env_overrides=env) as service:
        yield service


@pytest.fixture
async def workflow_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create an async HTTP client for workflow tests."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


# ==========================================
# Helper functions for workflow tests
# ==========================================


async def register_and_login(
    client: httpx.AsyncClient,
    auth_url: str,
    email: str = "workflow@example.com",
    password: str = "WorkflowPassword123!",
    tenant_name: str = "Workflow Test Co",
) -> dict[str, str]:
    """Register a user and return auth headers.

    Returns:
        Dict with Authorization header for authenticated requests
    """
    # Register
    response = await client.post(
        f"{auth_url}/auth/register",
        json={
            "tenant_name": tenant_name,
            "email": email,
            "password": password,
        },
    )

    # If already exists, try login
    if response.status_code == 400:
        pass
    elif response.status_code != 201:
        raise RuntimeError(f"Registration failed: {response.text}")

    # Login
    response = await client.post(
        f"{auth_url}/auth/login",
        json={"email": email, "password": password},
    )

    if response.status_code != 200:
        raise RuntimeError(f"Login failed: {response.text}")

    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def create_strategy(
    client: httpx.AsyncClient,
    strategy_url: str,
    headers: dict[str, str],
    name: str = "Workflow Test Strategy",
) -> dict:
    """Create a test strategy and return the response data."""
    response = await client.post(
        f"{strategy_url}/strategies",
        headers=headers,
        json={
            "name": name,
            "description": "Strategy for workflow testing",
            "strategy_type": "momentum",
            "config": {
                "symbols": ["AAPL"],
                "timeframe": "1D",
                "indicators": [
                    {"type": "sma", "params": {"period": 20}, "output_name": "sma_20"}
                ],
                "entry_conditions": [
                    {"type": "cross_above", "left": "close", "right": "sma_20"}
                ],
                "exit_conditions": [],
                "risk": {"stop_loss_percent": 5},
            },
        },
    )

    if response.status_code not in (200, 201):
        raise RuntimeError(f"Strategy creation failed: {response.text}")

    return response.json()
