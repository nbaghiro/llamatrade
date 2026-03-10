"""Workflow test configuration with service startup fixtures.

This module provides fixtures for starting and managing service processes
for multi-service integration tests.

It also provides fixtures for loading multiple gRPC servicers in the same test.
The key challenge is that each service has its own `src/` directory, causing module
name conflicts when loading multiple servicers.

Solution: Preload and cache servicer CLASSES at module import time, before any tests run.
The classes retain their internal module references even after sys.path changes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Service ports
SERVICE_PORTS = {
    "auth": 8810,
    "strategy": 8820,
    "backtest": 8830,
    "market-data": 8840,
    "trading": 8850,
    "portfolio": 8860,
    "notification": 8870,
    "billing": 8880,
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
) -> Generator[ServiceProcess]:
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

    raise TimeoutError(
        f"Service at {base_url} did not become healthy within {timeout}s: {last_error}"
    )


@asynccontextmanager
async def start_service_async(
    name: str,
    port: int | None = None,
    env_overrides: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> AsyncGenerator[ServiceProcess]:
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
) -> Generator[ServiceProcess]:
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
) -> Generator[ServiceProcess]:
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
) -> Generator[ServiceProcess]:
    """Start backtest service for the test module."""
    env = {
        "DATABASE_URL": database_url,
        "REDIS_URL": redis_url,
        "JWT_SECRET": "test-secret-for-integration-tests",
    }

    with start_service("backtest", env_overrides=env) as service:
        yield service


@pytest.fixture
async def workflow_client() -> AsyncGenerator[httpx.AsyncClient]:
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
                "indicators": [{"type": "sma", "params": {"period": 20}, "output_name": "sma_20"}],
                "entry_conditions": [{"type": "cross_above", "left": "close", "right": "sma_20"}],
                "exit_conditions": [],
                "risk": {"stop_loss_percent": 5},
            },
        },
    )

    if response.status_code not in (200, 201):
        raise RuntimeError(f"Strategy creation failed: {response.text}")

    return response.json()


# ==========================================
# Multi-Servicer Support (Direct gRPC)
# ==========================================
#
# These fixtures allow loading multiple servicers in the same test by
# preloading and caching the servicer classes at module import time.

# Cache for servicer classes - populated at module load time
_AUTH_SERVICER_CLASS: type | None = None
_STRATEGY_SERVICER_CLASS: type | None = None
_BACKTEST_SERVICER_CLASS: type | None = None


def _clear_src_modules() -> None:
    """Clear all src.* modules from sys.modules."""
    modules_to_remove = [k for k in list(sys.modules.keys()) if k == "src" or k.startswith("src.")]
    for mod in modules_to_remove:
        del sys.modules[mod]


def _remove_service_paths() -> None:
    """Remove all service paths from sys.path."""
    services = ["auth", "billing", "strategy", "backtest", "market-data", "trading", "portfolio"]
    for svc in services:
        svc_path = str(SERVICES_DIR / svc)
        if svc_path in sys.path:
            sys.path.remove(svc_path)


def _load_auth_servicer_class() -> type:
    """Load AuthServicer class."""
    global _AUTH_SERVICER_CLASS
    if _AUTH_SERVICER_CLASS is not None:
        return _AUTH_SERVICER_CLASS

    _remove_service_paths()
    _clear_src_modules()

    auth_path = str(SERVICES_DIR / "auth")
    sys.path.insert(0, auth_path)

    from src.grpc.servicer import AuthServicer

    _AUTH_SERVICER_CLASS = AuthServicer
    return AuthServicer


def _load_strategy_servicer_class() -> type:
    """Load StrategyServicer class."""
    global _STRATEGY_SERVICER_CLASS
    if _STRATEGY_SERVICER_CLASS is not None:
        return _STRATEGY_SERVICER_CLASS

    _remove_service_paths()
    _clear_src_modules()

    strategy_path = str(SERVICES_DIR / "strategy")
    sys.path.insert(0, strategy_path)

    from src.grpc.servicer import StrategyServicer

    _STRATEGY_SERVICER_CLASS = StrategyServicer
    return StrategyServicer


def _load_backtest_servicer_class() -> type:
    """Load BacktestServicer class."""
    global _BACKTEST_SERVICER_CLASS
    if _BACKTEST_SERVICER_CLASS is not None:
        return _BACKTEST_SERVICER_CLASS

    _remove_service_paths()
    _clear_src_modules()

    backtest_path = str(SERVICES_DIR / "backtest")
    sys.path.insert(0, backtest_path)

    from src.grpc.servicer import BacktestServicer

    _BACKTEST_SERVICER_CLASS = BacktestServicer
    return BacktestServicer


def _preload_all_servicers() -> None:
    """Preload all servicer classes at module import time.

    Order matters! Each load clears previous src modules, but the cached
    class retains its internal references to those modules.

    We load in reverse dependency order so the most-used modules are loaded last
    and remain in sys.modules for any runtime imports.
    """
    # Load auth first (foundational service)
    _load_auth_servicer_class()

    # Load strategy (depends on auth for context validation)
    _load_strategy_servicer_class()

    # Load backtest last (depends on strategy)
    _load_backtest_servicer_class()


# Preload at module import time
_preload_all_servicers()


class MockServicerContext:
    """Mock ConnectRPC servicer context for testing.

    Supports setting authorization headers for authenticated requests.
    """

    def __init__(self, auth_token: str | None = None) -> None:
        self.headers: dict[str, str] = {}
        self._cancelled = False
        if auth_token:
            self.headers["authorization"] = f"Bearer {auth_token}"

    def cancelled(self) -> bool:
        return self._cancelled

    def invocation_metadata(self) -> list[tuple[str, str]]:
        """Return headers as metadata tuples (gRPC style)."""
        return list(self.headers.items())

    def request_headers(self) -> dict[str, str]:
        """Return headers dict (ConnectRPC style)."""
        return self.headers

    async def abort(self, code: str, message: str) -> None:
        """Abort the RPC with an error code and message.

        In production, this raises a ConnectError. For testing, we raise
        a ConnectError to match the expected behavior.
        """
        from connectrpc.code import Code
        from connectrpc.errors import ConnectError

        # Map string codes to Code enum
        code_map = {
            "INVALID_ARGUMENT": Code.INVALID_ARGUMENT,
            "NOT_FOUND": Code.NOT_FOUND,
            "UNAUTHENTICATED": Code.UNAUTHENTICATED,
            "PERMISSION_DENIED": Code.PERMISSION_DENIED,
            "INTERNAL": Code.INTERNAL,
        }
        error_code = code_map.get(code, Code.INTERNAL)
        raise ConnectError(error_code, message)


@pytest.fixture
def mock_context() -> MockServicerContext:
    """Create a mock gRPC context."""
    return MockServicerContext()


@pytest.fixture
def multi_auth_servicer(db_session: "AsyncSession") -> Any:
    """Create an AuthServicer instance for multi-servicer tests.

    Uses the preloaded class to avoid module conflicts.
    """
    assert _AUTH_SERVICER_CLASS is not None, "AuthServicer not loaded"
    servicer = _AUTH_SERVICER_CLASS()

    async def mock_get_db() -> "AsyncSession":
        return db_session

    servicer._get_db = mock_get_db
    return servicer


@pytest.fixture
def multi_strategy_servicer(db_session: "AsyncSession") -> Any:
    """Create a StrategyServicer instance for multi-servicer tests.

    Uses the preloaded class to avoid module conflicts.
    """
    assert _STRATEGY_SERVICER_CLASS is not None, "StrategyServicer not loaded"
    servicer = _STRATEGY_SERVICER_CLASS()

    async def mock_get_db() -> "AsyncSession":
        return db_session

    servicer._get_db = mock_get_db
    return servicer


@pytest.fixture
def multi_backtest_servicer(db_session: "AsyncSession") -> Any:
    """Create a BacktestServicer instance for multi-servicer tests.

    Uses the preloaded class to avoid module conflicts.
    """
    assert _BACKTEST_SERVICER_CLASS is not None, "BacktestServicer not loaded"
    servicer = _BACKTEST_SERVICER_CLASS()

    @asynccontextmanager
    async def mock_get_db():
        yield db_session

    servicer._get_db = mock_get_db
    return servicer
