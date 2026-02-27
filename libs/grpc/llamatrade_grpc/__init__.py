"""LlamaTrade gRPC client library.

This package provides typed gRPC client wrappers, interceptors, and server
utilities for inter-service communication in the LlamaTrade platform.

Usage:
    from llamatrade_grpc import MarketDataClient, AuthClient, TradingClient

    # Create a client
    market_data = MarketDataClient("market-data:8840")

    # Use the client
    async for bar in market_data.stream_bars(["AAPL", "GOOGL"]):
        print(bar)

Server Usage:
    from llamatrade_grpc import GRPCServer, LoggingInterceptor

    server = GRPCServer(port=8840, interceptors=[LoggingInterceptor()])
    server.add_servicer(lambda s: add_MyServiceServicer_to_server(MyServicer(), s))
    await server.start()
"""

from llamatrade_grpc.clients.auth import AuthClient
from llamatrade_grpc.clients.backtest import BacktestClient
from llamatrade_grpc.clients.market_data import MarketDataClient
from llamatrade_grpc.clients.trading import TradingClient
from llamatrade_grpc.interceptors.auth import AuthInterceptor
from llamatrade_grpc.interceptors.logging import LoggingInterceptor
from llamatrade_grpc.server.base import GRPCServer

__all__ = [
    # Clients
    "AuthClient",
    "BacktestClient",
    "MarketDataClient",
    "TradingClient",
    # Interceptors
    "AuthInterceptor",
    "LoggingInterceptor",
    # Server
    "GRPCServer",
]

__version__ = "0.1.0"
