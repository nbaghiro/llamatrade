"""Inter-service HTTP clients for portfolio service."""

from src.clients.market_data import MarketDataClient, get_market_data_client

__all__ = ["MarketDataClient", "get_market_data_client"]
