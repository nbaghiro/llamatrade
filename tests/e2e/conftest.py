"""E2E suite fixtures.

Unlike ``tests/integration`` (self-contained, testcontainers-backed), the e2e
suite drives a *running* deployment — real service processes, the backtest
Celery worker, and a seeded demo tenant — over HTTP. It therefore SKIPS itself
when the mesh isn't reachable, so a plain ``pytest`` run (e.g. in unit CI, with
no live stack) never fails on it.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from . import harness


@pytest.fixture(scope="session", autouse=True)
def set_test_environment() -> Generator[None]:
    """Neutralize the root testcontainer env-swap for the e2e suite.

    ``tests/conftest.py`` provides an autouse fixture of the same name that spins
    up throwaway Postgres/Redis containers and rebinds ``REDIS_URL``/
    ``DATABASE_URL`` to them. E2E targets the *live* mesh, so overriding it here
    keeps the real environment (and skips the container start entirely).
    """
    yield


@pytest.fixture(scope="session")
def session() -> harness.JSON:
    """Authenticated demo session; skips the whole suite if the mesh isn't up."""
    try:
        return harness.login()
    except harness.E2EError as e:  # unreachable mesh -> skip; anything else -> real failure
        if "unreachable" in str(e):
            pytest.skip(
                "e2e mesh not running — start the stack + backtest worker + `make seed-demo`, "
                f"then re-run. ({e})"
            )
        raise
