"""LlamaTrade Protocol Buffers and gRPC library.

This package provides:
- Generated protobuf messages and gRPC stubs (in `generated/`)
- Typed client wrappers for service-to-service calls (in `clients/`)
- Interceptors for auth and logging (in `interceptors/`)
- Server utilities (in `server/`)

Usage:
    # Generated proto messages
    from llamatrade_proto.generated import auth_pb2, market_data_pb2

    # High-level client wrappers
    from llamatrade_proto.clients import MarketDataClient, AuthClient

    # Or import clients directly from package root
    from llamatrade_proto import MarketDataClient, AuthInterceptor
"""

# Re-export clients for convenience
from llamatrade_proto.clients import (
    AuthClient,
    BacktestClient,
    MarketDataClient,
    TradingClient,
)

# Re-export interceptors
from llamatrade_proto.interceptors import (
    AuthInterceptor,
    LoggingInterceptor,
)

# Re-export server utilities
from llamatrade_proto.server import GRPCServer

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
