"""Streaming router - WebSocket real-time data endpoints."""

import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.models import StreamSubscription
from src.streaming.manager import StreamManager, get_stream_manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_stream(
    websocket: WebSocket,
    stream_manager: StreamManager = Depends(get_stream_manager),
):
    """WebSocket endpoint for real-time market data streaming.

    Clients can subscribe/unsubscribe to trades, quotes, and bars
    for specific symbols.

    Message format:
    {
        "action": "subscribe" | "unsubscribe",
        "trades": ["AAPL", "GOOGL"],
        "quotes": ["AAPL"],
        "bars": ["SPY"]
    }
    """
    await websocket.accept()

    client_id = id(websocket)
    await stream_manager.connect(client_id, websocket)

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
        await stream_manager.disconnect(client_id)


@router.get("/status")
async def stream_status(
    stream_manager: StreamManager = Depends(get_stream_manager),
):
    """Get streaming service status."""
    return {
        "status": "running",
        "active_connections": stream_manager.connection_count,
        "subscriptions": stream_manager.subscription_count,
    }
