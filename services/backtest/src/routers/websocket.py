"""WebSocket router for real-time backtest progress updates."""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.progress import ProgressSubscriber

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/backtests/{backtest_id}/progress")
async def backtest_progress(websocket: WebSocket, backtest_id: str) -> None:
    """WebSocket endpoint for real-time backtest progress updates.

    Connect to this endpoint to receive progress updates as the backtest runs.
    Messages are JSON objects with the following structure:
    {
        "backtest_id": "uuid",
        "progress": 0-100,
        "message": "Status message",
        "eta_seconds": null or seconds remaining,
        "timestamp": "ISO timestamp"
    }

    The connection closes automatically when progress reaches 100%.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for backtest {backtest_id}")

    subscriber = ProgressSubscriber()

    try:
        # Send initial connected message
        await websocket.send_json(
            {
                "type": "connected",
                "backtest_id": backtest_id,
                "message": "Connected to progress stream",
            }
        )

        # Subscribe to progress updates
        async for update in subscriber.subscribe(backtest_id):
            await websocket.send_json(
                {
                    "type": "progress",
                    **update.to_dict(),
                }
            )

        # Send completion message
        await websocket.send_json(
            {
                "type": "completed",
                "backtest_id": backtest_id,
                "message": "Backtest completed",
            }
        )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for backtest {backtest_id}")
    except Exception as e:
        logger.error(f"WebSocket error for backtest {backtest_id}: {e}")
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(e),
                }
            )
        except Exception:
            pass
    finally:
        await subscriber.close()


@router.websocket("/backtests/batch/progress")
async def batch_progress(websocket: WebSocket) -> None:
    """WebSocket endpoint for monitoring multiple backtest progress streams.

    Send a JSON message to subscribe to backtests:
    {"action": "subscribe", "backtest_ids": ["uuid1", "uuid2"]}

    Or unsubscribe:
    {"action": "unsubscribe", "backtest_ids": ["uuid1"]}

    Receive progress updates for all subscribed backtests.
    """
    await websocket.accept()
    logger.info("Batch WebSocket connected")

    subscribers: dict[str, ProgressSubscriber] = {}
    tasks: dict[str, asyncio.Task] = {}

    async def listen_for_progress(backtest_id: str) -> None:
        """Listen for progress updates for a specific backtest."""
        subscriber = ProgressSubscriber()
        subscribers[backtest_id] = subscriber
        try:
            async for update in subscriber.subscribe(backtest_id):
                await websocket.send_json(
                    {
                        "type": "progress",
                        **update.to_dict(),
                    }
                )
        except Exception as e:
            logger.error(f"Error listening to {backtest_id}: {e}")
        finally:
            await subscriber.close()
            if backtest_id in subscribers:
                del subscribers[backtest_id]

    try:
        while True:
            # Receive commands from client
            data = await websocket.receive_json()
            action = data.get("action")
            backtest_ids = data.get("backtest_ids", [])

            if action == "subscribe":
                for bid in backtest_ids:
                    if bid not in tasks:
                        task = asyncio.create_task(listen_for_progress(bid))
                        tasks[bid] = task
                        await websocket.send_json(
                            {
                                "type": "subscribed",
                                "backtest_id": bid,
                            }
                        )

            elif action == "unsubscribe":
                for bid in backtest_ids:
                    if bid in tasks:
                        tasks[bid].cancel()
                        del tasks[bid]
                    if bid in subscribers:
                        await subscribers[bid].close()
                        del subscribers[bid]
                    await websocket.send_json(
                        {
                            "type": "unsubscribed",
                            "backtest_id": bid,
                        }
                    )

    except WebSocketDisconnect:
        logger.info("Batch WebSocket disconnected")
    except Exception as e:
        logger.error(f"Batch WebSocket error: {e}")
    finally:
        # Clean up all subscriptions
        for task in tasks.values():
            task.cancel()
        for subscriber in subscribers.values():
            await subscriber.close()
