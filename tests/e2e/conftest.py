"""E2E suite fixtures — drives the live service mesh (see client.py).

Unlike the per-service integration suites (testcontainers), this suite targets a
*running* deployment (real services + backtest worker + seeded demo tenant) over
HTTP, so it SKIPS itself when the mesh is unreachable. It is not in the default
``testpaths``; run it with ``pytest tests/e2e`` (or ``make test-e2e``).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Generator

import pytest

from .client import MeshClient, MeshError, login, mesh_up, register_and_login


def _enabled(var: str) -> bool:
    return os.getenv(var, "").strip().lower() in {"1", "true", "yes", "on"}


_LIVE_LLM = _enabled("E2E_LIVE_LLM")
_LIVE_ALPACA = _enabled("E2E_LIVE_ALPACA")


def pytest_configure(config: pytest.Config) -> None:
    """Register suite-local markers (shared markers live in the root pyproject)."""
    config.addinivalue_line("markers", "e2e: end-to-end test against the live service mesh.")
    config.addinivalue_line(
        "markers", "e2e_smoke: fast PR subset — auth + strategy lifecycle + funding."
    )
    config.addinivalue_line(
        "markers", "live_llm: exercises the real LLM; opt-in via E2E_LIVE_LLM=1."
    )
    config.addinivalue_line(
        "markers",
        "live_alpaca: needs real Alpaca paper keys on the account; opt-in via E2E_LIVE_ALPACA=1.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip tests that need an external third party unless explicitly enabled."""
    gates = (
        ("live_llm", _LIVE_LLM, "set E2E_LIVE_LLM=1 to run"),
        ("live_alpaca", _LIVE_ALPACA, "set E2E_LIVE_ALPACA=1 (needs real paper keys)"),
    )
    for keyword, enabled, hint in gates:
        if enabled:
            continue
        skip = pytest.mark.skip(reason=f"{keyword} disabled ({hint})")
        for item in items:
            if keyword in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def _require_mesh() -> Generator[None]:
    """Skip the whole suite when the mesh isn't reachable (keeps plain CI green)."""
    if not mesh_up():
        pytest.skip(
            "e2e mesh not running — start the stack (make dev-up) + the backtest worker "
            "+ `make seed-demo`, then re-run."
        )
    yield


@pytest.fixture(scope="session")
def demo() -> MeshClient:
    """Logged-in demo tenant (seeded data): the shared read identity."""
    try:
        return login()
    except MeshError as e:
        pytest.skip(f"demo login failed — is the demo account seeded (make seed-demo)? ({e})")


@pytest.fixture
def throwaway_tenant() -> Callable[[str], MeshClient]:
    """Factory: register a fresh isolated tenant and return a MeshClient for it.

    Each mutating flow runs on its own tenant so the suite stays order-independent
    and safe to run in parallel against a single mesh. Emails/tenant names are
    unique per call (millisecond clock + counter), so re-runs never collide.
    """
    counter = {"n": 0}

    def _make(label: str = "e2e") -> MeshClient:
        counter["n"] += 1
        uniq = f"{int(time.time() * 1000)}{counter['n']}"
        email = f"{label}-{uniq}@e2e.llamatrade.test"
        return register_and_login(f"{label} {uniq}", email)

    return _make
