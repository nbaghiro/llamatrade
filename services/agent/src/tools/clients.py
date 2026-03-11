"""Service clients for inter-service communication.

This module provides async clients for calling other LlamaTrade services
via Connect protocol. Clients are lazily initialized and cached.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llamatrade_proto.generated.backtest_connect import BacktestServiceClient
    from llamatrade_proto.generated.portfolio_connect import PortfolioServiceClient
    from llamatrade_proto.generated.strategy_connect import StrategyServiceClient

# Service URLs from environment
STRATEGY_SERVICE_URL = os.getenv("STRATEGY_GRPC_TARGET", "http://localhost:8820")
PORTFOLIO_SERVICE_URL = os.getenv("PORTFOLIO_GRPC_TARGET", "http://localhost:8830")
BACKTEST_SERVICE_URL = os.getenv("BACKTEST_GRPC_TARGET", "http://localhost:8850")
MARKET_DATA_SERVICE_URL = os.getenv("MARKET_DATA_GRPC_TARGET", "http://localhost:8840")

# Cached clients
_strategy_client: StrategyServiceClient | None = None
_portfolio_client: PortfolioServiceClient | None = None
_backtest_client: BacktestServiceClient | None = None


def get_strategy_client() -> StrategyServiceClient:
    """Get or create the strategy service client."""
    global _strategy_client
    if _strategy_client is None:
        from llamatrade_proto.generated.strategy_connect import StrategyServiceClient

        _strategy_client = StrategyServiceClient(STRATEGY_SERVICE_URL)
    return _strategy_client


def get_portfolio_client() -> PortfolioServiceClient:
    """Get or create the portfolio service client."""
    global _portfolio_client
    if _portfolio_client is None:
        from llamatrade_proto.generated.portfolio_connect import PortfolioServiceClient

        _portfolio_client = PortfolioServiceClient(PORTFOLIO_SERVICE_URL)
    return _portfolio_client


def get_backtest_client() -> BacktestServiceClient:
    """Get or create the backtest service client."""
    global _backtest_client
    if _backtest_client is None:
        from llamatrade_proto.generated.backtest_connect import BacktestServiceClient

        _backtest_client = BacktestServiceClient(BACKTEST_SERVICE_URL)
    return _backtest_client


def tenant_headers(tenant_id: str, user_id: str) -> dict[str, str]:
    """Create headers with tenant context for inter-service calls."""
    return {
        "X-Tenant-ID": tenant_id,
        "X-User-ID": user_id,
    }
