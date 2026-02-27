"""Shared test fixtures for strategy service tests."""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app

# ===================
# Sample S-expressions
# ===================

VALID_RSI_STRATEGY = """(strategy
  :name "RSI Mean Reversion"
  :type mean_reversion
  :symbols ["AAPL" "MSFT"]
  :timeframe "1D"
  :entry (< (rsi close 14) 30)
  :exit (> (rsi close 14) 70)
  :stop-loss-pct 2.0
  :take-profit-pct 6.0)"""

VALID_MA_CROSSOVER = """(strategy
  :name "MA Crossover"
  :type trend_following
  :symbols ["SPY"]
  :timeframe "4H"
  :entry (cross-above (sma close 20) (sma close 50))
  :exit (cross-below (sma close 20) (sma close 50))
  :position-size-pct 5.0)"""

VALID_MOMENTUM_STRATEGY = """(strategy
  :name "Momentum Strategy"
  :type momentum
  :symbols ["QQQ" "IWM"]
  :timeframe "1H"
  :entry (and (> (rsi close 14) 50) (> close (sma close 20)))
  :exit (or (< (rsi close 14) 40) (< close (sma close 20))))"""

INVALID_SYNTAX = '(strategy :name "broken'  # Missing closing quotes and paren

INVALID_MISSING_ENTRY = """(strategy
  :name "No Entry"
  :symbols ["AAPL"]
  :timeframe "1D"
  :exit true)"""


# ===================
# Test IDs
# ===================


@pytest.fixture
def tenant_id():
    """Generate a test tenant ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Generate a test user ID."""
    return uuid4()


@pytest.fixture
def strategy_id():
    """Generate a test strategy ID."""
    return uuid4()


# ===================
# Mock Database Session
# ===================


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.delete = AsyncMock()
    return db


# ===================
# Mock Strategy Data
# ===================


def make_mock_strategy(
    id: Any = None,
    tenant_id: Any = None,
    name: str = "Test Strategy",
    description: str | None = None,
    strategy_type: str = "mean_reversion",
    status: str = "draft",
    current_version: int = 1,
    created_by: Any = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
):
    """Create a mock Strategy object."""
    from llamatrade_db.models.strategy import (
        StrategyStatus as DBStrategyStatus,
    )
    from llamatrade_db.models.strategy import (
        StrategyType as DBStrategyType,
    )

    strategy = MagicMock()
    strategy.id = id or uuid4()
    strategy.tenant_id = tenant_id or uuid4()
    strategy.name = name
    strategy.description = description
    strategy.strategy_type = DBStrategyType(strategy_type)
    strategy.status = DBStrategyStatus(status)
    strategy.current_version = current_version
    strategy.created_by = created_by or uuid4()
    strategy.created_at = created_at or datetime.utcnow()
    strategy.updated_at = updated_at or datetime.utcnow()
    return strategy


def make_mock_version(
    id: Any = None,
    strategy_id: Any = None,
    version: int = 1,
    config_sexpr: str = VALID_RSI_STRATEGY,
    config_json: dict | None = None,
    symbols: list[str] | None = None,
    timeframe: str = "1D",
    changelog: str | None = None,
    created_by: Any = None,
    created_at: datetime | None = None,
):
    """Create a mock StrategyVersion object."""
    ver = MagicMock()
    ver.id = id or uuid4()
    ver.strategy_id = strategy_id or uuid4()
    ver.version = version
    ver.config_sexpr = config_sexpr
    ver.config_json = config_json or {"name": "Test Strategy"}
    ver.symbols = symbols or ["AAPL", "MSFT"]
    ver.timeframe = timeframe
    ver.changelog = changelog
    ver.created_by = created_by or uuid4()
    ver.created_at = created_at or datetime.utcnow()
    return ver


@pytest.fixture
def mock_strategy(tenant_id, user_id, strategy_id):
    """Create a mock strategy."""
    return make_mock_strategy(
        id=strategy_id,
        tenant_id=tenant_id,
        created_by=user_id,
    )


@pytest.fixture
def mock_version(strategy_id, user_id):
    """Create a mock version."""
    return make_mock_version(
        strategy_id=strategy_id,
        created_by=user_id,
    )


# ===================
# HTTP Client
# ===================


@pytest.fixture
async def client():
    """Create async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ===================
# Auth Override Helper
# ===================


def make_auth_context(tenant_id, user_id):
    """Create a mock TenantContext for auth override."""
    from llamatrade_common.models import TenantContext

    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        email="test@example.com",
        roles=["admin"],
    )
