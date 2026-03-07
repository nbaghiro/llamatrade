"""Pytest configuration for alpaca library tests."""

import pytest


@pytest.fixture
def api_key() -> str:
    """Test API key."""
    return "test_api_key"


@pytest.fixture
def api_secret() -> str:
    """Test API secret."""
    return "test_api_secret"
