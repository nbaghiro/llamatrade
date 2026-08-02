"""Shared fixtures for the common-library test suite."""

from collections.abc import Generator

import pytest

from llamatrade_common import utils


@pytest.fixture(autouse=True)
def reset_cipher_cache() -> Generator[None]:
    """Ciphers are built once per process; env-driven tests need a clean registry."""
    utils._CIPHERS.clear()
    yield
    utils._CIPHERS.clear()
