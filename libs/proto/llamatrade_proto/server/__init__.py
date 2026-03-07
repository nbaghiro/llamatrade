"""Server utilities for gRPC and Connect protocols."""

from llamatrade_proto.server.base import GRPCServer

# Connect imports with fallback for when connectrpc is not installed
try:
    from llamatrade_proto.server.connect import (
        CombinedConnectApp,
        create_connect_routes,
    )

    _connect_available = True
except ImportError:
    CombinedConnectApp = None  # type: ignore[assignment, misc]
    create_connect_routes = None  # type: ignore[assignment]
    _connect_available = False

__all__ = [
    "GRPCServer",
    "CombinedConnectApp",
    "create_connect_routes",
]
