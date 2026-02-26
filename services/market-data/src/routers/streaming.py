"""Streaming router - WebSocket real-time data endpoints."""

import json
import logging
import os
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from pydantic import ValidationError

from src.models import StreamSubscription
from src.streaming.manager import StreamManager, get_stream_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# JWT settings - should match auth service
# In production, these would come from environment/config
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"


async def authenticate_websocket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
) -> tuple[UUID | None, UUID | None]:
    """Authenticate WebSocket connection via token query parameter.

    Args:
        websocket: WebSocket connection
        token: JWT token from query parameter

    Returns:
        Tuple of (tenant_id, user_id) if authenticated, (None, None) otherwise
    """
    if not token:
        return None, None

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        tenant_id = UUID(payload.get("tenant_id", ""))
        user_id = UUID(payload.get("sub", ""))
        return tenant_id, user_id
    except (JWTError, ValueError, ValidationError) as e:
        logger.warning(f"WebSocket auth failed: {e}")
        return None, None


@router.websocket("/ws")
async def websocket_stream(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    stream_manager: StreamManager = Depends(get_stream_manager),
) -> None:
    """WebSocket endpoint for real-time market data streaming.

    Authentication:
    - Pass JWT token as query parameter: `/stream/ws?token=<jwt>`
    - Anonymous connections are allowed but may be rate-limited

    Message format:
    {
        "action": "subscribe" | "unsubscribe",
        "trades": ["AAPL", "GOOGL"],
        "quotes": ["AAPL"],
        "bars": ["SPY"]
    }
    """
    # Authenticate if token provided
    tenant_id, user_id = await authenticate_websocket(websocket, token)

    # Accept connection (even anonymous - market data is public)
    await websocket.accept()

    client_id = id(websocket)
    await stream_manager.connect(client_id, websocket)

    # Log connection with tenant info
    logger.info(
        f"WebSocket connected: client={client_id}",
        extra={
            "client_id": client_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "user_id": str(user_id) if user_id else None,
            "authenticated": tenant_id is not None,
        },
    )

    try:
        while True:
            # Receive subscription messages
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                subscription = StreamSubscription(**message)

                if subscription.action == "subscribe":
                    await stream_manager.subscribe(
                        client_id=client_id,
                        trades=subscription.trades or [],
                        quotes=subscription.quotes or [],
                        bars=subscription.bars or [],
                    )

                    # Log subscription with tenant context
                    logger.info(
                        "Client subscribed",
                        extra={
                            "client_id": client_id,
                            "tenant_id": str(tenant_id) if tenant_id else None,
                            "trades": subscription.trades or [],
                            "quotes": subscription.quotes or [],
                            "bars": subscription.bars or [],
                        },
                    )

                    await websocket.send_json(
                        {
                            "type": "subscribed",
                            "trades": subscription.trades or [],
                            "quotes": subscription.quotes or [],
                            "bars": subscription.bars or [],
                        }
                    )

                elif subscription.action == "unsubscribe":
                    await stream_manager.unsubscribe(
                        client_id=client_id,
                        trades=subscription.trades or [],
                        quotes=subscription.quotes or [],
                        bars=subscription.bars or [],
                    )
                    await websocket.send_json(
                        {
                            "type": "unsubscribed",
                            "trades": subscription.trades or [],
                            "quotes": subscription.quotes or [],
                            "bars": subscription.bars or [],
                        }
                    )

            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON",
                    }
                )
            except Exception as e:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": str(e),
                    }
                )

    except WebSocketDisconnect:
        logger.info(
            f"WebSocket disconnected: client={client_id}",
            extra={
                "client_id": client_id,
                "tenant_id": str(tenant_id) if tenant_id else None,
            },
        )
        await stream_manager.disconnect(client_id)


@router.get("/status")
async def stream_status(
    stream_manager: StreamManager = Depends(get_stream_manager),
) -> dict[str, str | int | dict[str, int]]:
    """Get streaming service status."""
    return {
        "status": "running",
        "active_connections": stream_manager.connection_count,
        "subscriptions": stream_manager.subscription_count,
    }
