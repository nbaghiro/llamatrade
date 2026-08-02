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
    from llamatrade_proto import MarketDataClient
"""

# Re-export clients for convenience
from llamatrade_proto.clients import (
    AuthClient,
    MarketDataClient,
)

# Re-export interceptors
from llamatrade_proto.interceptors import (
    LoggingInterceptor,
)

# Re-export timestamp helpers
from llamatrade_proto.timestamps import (
    date_from_proto_timestamp,
    date_to_proto_timestamp,
    from_proto_timestamp,
    to_proto_timestamp,
)

__all__ = [
    # Clients
    "AuthClient",
    "MarketDataClient",
    # Interceptors
    "LoggingInterceptor",
    # Timestamp helpers
    "date_from_proto_timestamp",
    "date_to_proto_timestamp",
    "from_proto_timestamp",
    "to_proto_timestamp",
]

__version__ = "0.1.0"
