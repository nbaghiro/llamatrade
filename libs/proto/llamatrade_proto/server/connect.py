"""Connect protocol server middleware for FastAPI/ASGI.

This module provides utilities for mounting Connect protocol services
directly in FastAPI applications, enabling browser-to-service communication
without a proxy.

Example:
    from llamatrade_proto.server import create_connect_routes
    from llamatrade_proto.generated.auth_connect import AuthServiceASGIApplication
    from src.grpc.servicer import AuthServicer

    servicer = AuthServicer()
    connect_app = AuthServiceASGIApplication(servicer)
    app.mount("/", connect_app)
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ASGIApplication(Protocol):
    """Protocol for ASGI applications."""

    async def __call__(
        self,
        scope: dict,
        receive: object,
        send: object,
    ) -> None:
        """Handle ASGI request."""
        ...


def create_connect_routes(app: ASGIApplication) -> ASGIApplication:
    """Create a Connect ASGI application ready for mounting.

    This is a simple passthrough function that validates the ASGI app
    and returns it for mounting. The actual ASGI application is created
    by the generated *ASGIApplication classes.

    Args:
        app: A Connect ASGI application (e.g., AuthServiceASGIApplication)

    Returns:
        The ASGI application ready for mounting

    Example:
        from llamatrade_proto.auth_connect import (
            AuthServiceASGIApplication,
        )
        from src.grpc.servicer import AuthServicer

        servicer = AuthServicer()
        connect_app = create_connect_routes(AuthServiceASGIApplication(servicer))
        app.mount("/", connect_app)
    """
    if not isinstance(app, ASGIApplication):
        raise TypeError(f"Expected ASGI application, got {type(app)}")

    return app


class CombinedConnectApp:
    """Combines multiple Connect ASGI applications into one.

    Routes requests to the appropriate service based on the request path.
    Each Connect service handles paths like /servicename.v1.ServiceName/Method.

    Example:
        from llamatrade_proto.auth_connect import (
            AuthServiceASGIApplication,
        )
        from llamatrade_proto.billing_connect import (
            BillingServiceASGIApplication,
        )

        combined = CombinedConnectApp([
            AuthServiceASGIApplication(auth_servicer),
            BillingServiceASGIApplication(billing_servicer),
        ])
        app.mount("/", combined)
    """

    def __init__(self, apps: Iterable[ASGIApplication]) -> None:
        """Initialize with multiple Connect ASGI applications.

        Args:
            apps: Iterable of Connect ASGI applications
        """
        self._apps = list(apps)

    async def __call__(
        self,
        scope: dict,
        receive: object,
        send: object,
    ) -> None:
        """Route request to appropriate service.

        Tries each app in order until one handles the request (returns
        without raising). If no app handles it, returns 404.
        """
        if scope["type"] != "http":
            # Only handle HTTP requests
            return

        # Try each app - Connect apps will handle their routes
        # and return 404 for routes they don't handle
        for app in self._apps:
            try:
                await app(scope, receive, send)
                return
            except Exception:
                # App didn't handle this route, try next
                continue

        # No app handled the request - return 404
        await self._send_404(scope, send)

    async def _send_404(self, scope: dict, send: object) -> None:
        """Send 404 Not Found response."""
        await send(
            {  # type: ignore[operator]
                "type": "http.response.start",
                "status": 404,
                "headers": [[b"content-type", b"text/plain"]],
            }
        )
        await send(
            {  # type: ignore[operator]
                "type": "http.response.body",
                "body": b"Not Found",
            }
        )
