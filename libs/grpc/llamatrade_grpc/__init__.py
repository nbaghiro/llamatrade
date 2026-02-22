"""LlamaTrade gRPC client library.

This package provides typed gRPC client wrappers and interceptors for
inter-service communication in the LlamaTrade platform.

Usage:
    from llamatrade_grpc.clients import MarketDataClient, AuthClient, TradingClient

    # Create a client
    market_data = MarketDataClient("market-data:50051")

    # Use the client
    async for bar in market_data.stream_bars(["AAPL", "GOOGL"]):
        print(bar)
"""

from llamatrade_grpc.clients.auth import AuthClient
from llamatrade_grpc.clients.market_data import MarketDataClient
from llamatrade_grpc.clients.trading import TradingClient
from llamatrade_grpc.interceptors.auth import AuthInterceptor
from llamatrade_grpc.interceptors.logging import LoggingInterceptor

__all__ = [
    "AuthClient",
    "MarketDataClient",
    "TradingClient",
    "AuthInterceptor",
    "LoggingInterceptor",
]

__version__ = "0.1.0"
