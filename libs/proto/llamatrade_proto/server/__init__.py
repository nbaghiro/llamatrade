"""Server utilities for gRPC and Connect protocols."""

from typing import TYPE_CHECKING

from llamatrade_proto.server.base import GRPCServer

# Connect imports with fallback for when connectrpc is not installed
_connect_available: bool
CombinedConnectApp: type | None
create_connect_routes: object | None

try:
    from llamatrade_proto.server.connect import (
        CombinedConnectApp as _CombinedConnectApp,
    )
    from llamatrade_proto.server.connect import (
        create_connect_routes as _create_connect_routes,
    )

    CombinedConnectApp = _CombinedConnectApp
    create_connect_routes = _create_connect_routes
    _connect_available = True
except ImportError:
    CombinedConnectApp = None
    create_connect_routes = None
    _connect_available = False

if TYPE_CHECKING:
    from llamatrade_proto.server.connect import (
        CombinedConnectApp as CombinedConnectApp,
    )
    from llamatrade_proto.server.connect import (
        create_connect_routes as create_connect_routes,
    )

__all__ = [
    "GRPCServer",
    "CombinedConnectApp",
    "create_connect_routes",
]
