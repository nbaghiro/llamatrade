"""Notification gRPC servicer implementation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import grpc.aio

logger = logging.getLogger(__name__)


class NotificationServicer:
    """gRPC servicer for the Notification service.

    Implements the NotificationService defined in notification.proto.

    Note: This is a stub implementation. The notification service
    is currently in early development with stubbed functionality.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        # In-memory storage for stubs
        self._notifications: dict[str, list[dict]] = {}
        self._alerts: dict[str, list[dict]] = {}
        self._channels: dict[str, list[dict]] = {}

    async def ListNotifications(
        self,
        request: notification_pb2.ListNotificationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> notification_pb2.ListNotificationsResponse:
        """List notifications for a user."""
        from llamatrade.v1 import common_pb2, notification_pb2

        try:
            tenant_id = request.context.tenant_id
            user_id = request.context.user_id

            # Get notifications from stub storage
            key = f"{tenant_id}:{user_id}"
            notifications = self._notifications.get(key, [])

            # Filter by unread_only
            if request.unread_only:
                notifications = [n for n in notifications if not n.get("is_read", False)]

            # Count unread
            unread_count = sum(1 for n in self._notifications.get(key, []) if not n.get("is_read", False))

            # Paginate
            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 20
            start = (page - 1) * page_size
            end = start + page_size
            paginated = notifications[start:end]

            total = len(notifications)
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return notification_pb2.ListNotificationsResponse(
                notifications=[self._to_proto_notification(n) for n in paginated],
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=page,
                    page_size=page_size,
                    has_next=page < total_pages,
                    has_previous=page > 1,
                ),
                unread_count=unread_count,
            )

        except Exception as e:
            logger.error("ListNotifications error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to list notifications: {e}",
            )

    async def MarkAsRead(
        self,
        request: notification_pb2.MarkAsReadRequest,
        context: grpc.aio.ServicerContext,
    ) -> notification_pb2.MarkAsReadResponse:
        """Mark notification(s) as read."""
        from llamatrade.v1 import notification_pb2

        try:
            tenant_id = request.context.tenant_id
            user_id = request.context.user_id
            key = f"{tenant_id}:{user_id}"

            marked_count = 0
            notifications = self._notifications.get(key, [])

            if request.mark_all:
                # Mark all as read
                for n in notifications:
                    if not n.get("is_read", False):
                        n["is_read"] = True
                        n["read_at"] = datetime.now(UTC).isoformat()
                        marked_count += 1
            else:
                # Mark specific notification
                for n in notifications:
                    if n.get("id") == request.notification_id:
                        if not n.get("is_read", False):
                            n["is_read"] = True
                            n["read_at"] = datetime.now(UTC).isoformat()
                            marked_count = 1
                        break

            return notification_pb2.MarkAsReadResponse(marked_count=marked_count)

        except Exception as e:
            logger.error("MarkAsRead error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to mark as read: {e}",
            )

    async def ListAlerts(
        self,
        request: notification_pb2.ListAlertsRequest,
        context: grpc.aio.ServicerContext,
    ) -> notification_pb2.ListAlertsResponse:
        """List alerts for a user."""
        from llamatrade.v1 import notification_pb2

        try:
            tenant_id = request.context.tenant_id
            user_id = request.context.user_id
            key = f"{tenant_id}:{user_id}"

            alerts = self._alerts.get(key, [])

            # Filter by active_only
            if request.active_only:
                alerts = [a for a in alerts if a.get("is_active", True)]

            return notification_pb2.ListAlertsResponse(
                alerts=[self._to_proto_alert(a) for a in alerts],
            )

        except Exception as e:
            logger.error("ListAlerts error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to list alerts: {e}",
            )

    async def CreateAlert(
        self,
        request: notification_pb2.CreateAlertRequest,
        context: grpc.aio.ServicerContext,
    ) -> notification_pb2.CreateAlertResponse:
        """Create a new alert."""
        from llamatrade.v1 import notification_pb2

        try:
            tenant_id = request.context.tenant_id
            user_id = request.context.user_id
            key = f"{tenant_id}:{user_id}"

            # Create alert
            alert_id = str(uuid4())
            now = datetime.now(UTC)

            alert = {
                "id": alert_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "name": request.name,
                "description": request.description,
                "is_active": True,
                "condition": {
                    "type": request.condition.type,
                    "symbol": request.condition.symbol,
                    "threshold": request.condition.threshold.value if request.condition.HasField("threshold") else None,
                    "strategy_id": request.condition.strategy_id,
                },
                "channels": list(request.channels),
                "cooldown_minutes": request.cooldown_minutes,
                "times_triggered": 0,
                "last_triggered_at": None,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            # Store alert
            if key not in self._alerts:
                self._alerts[key] = []
            self._alerts[key].append(alert)

            return notification_pb2.CreateAlertResponse(
                alert=self._to_proto_alert(alert),
            )

        except Exception as e:
            logger.error("CreateAlert error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to create alert: {e}",
            )

    async def DeleteAlert(
        self,
        request: notification_pb2.DeleteAlertRequest,
        context: grpc.aio.ServicerContext,
    ) -> notification_pb2.DeleteAlertResponse:
        """Delete an alert."""
        from llamatrade.v1 import notification_pb2

        try:
            tenant_id = request.context.tenant_id
            user_id = request.context.user_id
            key = f"{tenant_id}:{user_id}"

            alerts = self._alerts.get(key, [])
            original_count = len(alerts)
            self._alerts[key] = [a for a in alerts if a.get("id") != request.alert_id]

            success = len(self._alerts[key]) < original_count

            if not success:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Alert not found: {request.alert_id}",
                )

            return notification_pb2.DeleteAlertResponse(success=True)

        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("DeleteAlert error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to delete alert: {e}",
            )

    async def ToggleAlert(
        self,
        request: notification_pb2.ToggleAlertRequest,
        context: grpc.aio.ServicerContext,
    ) -> notification_pb2.ToggleAlertResponse:
        """Toggle alert active status."""
        from llamatrade.v1 import notification_pb2

        try:
            tenant_id = request.context.tenant_id
            user_id = request.context.user_id
            key = f"{tenant_id}:{user_id}"

            alerts = self._alerts.get(key, [])
            alert = None

            for a in alerts:
                if a.get("id") == request.alert_id:
                    a["is_active"] = request.is_active
                    a["updated_at"] = datetime.now(UTC).isoformat()
                    alert = a
                    break

            if not alert:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Alert not found: {request.alert_id}",
                )

            return notification_pb2.ToggleAlertResponse(
                alert=self._to_proto_alert(alert),
            )

        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("ToggleAlert error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to toggle alert: {e}",
            )

    async def ListChannels(
        self,
        request: notification_pb2.ListChannelsRequest,
        context: grpc.aio.ServicerContext,
    ) -> notification_pb2.ListChannelsResponse:
        """List notification channels for a user."""
        from llamatrade.v1 import notification_pb2

        try:
            tenant_id = request.context.tenant_id
            user_id = request.context.user_id
            key = f"{tenant_id}:{user_id}"

            channels = self._channels.get(key, [])

            # Return default channels if none configured
            if not channels:
                channels = [
                    {
                        "id": str(uuid4()),
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "type": notification_pb2.CHANNEL_TYPE_EMAIL,
                        "is_enabled": False,
                        "is_verified": False,
                        "config": {},
                        "created_at": datetime.now(UTC).isoformat(),
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                ]

            return notification_pb2.ListChannelsResponse(
                channels=[self._to_proto_channel(c) for c in channels],
            )

        except Exception as e:
            logger.error("ListChannels error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to list channels: {e}",
            )

    async def UpdateChannel(
        self,
        request: notification_pb2.UpdateChannelRequest,
        context: grpc.aio.ServicerContext,
    ) -> notification_pb2.UpdateChannelResponse:
        """Update a notification channel."""
        from llamatrade.v1 import notification_pb2

        try:
            tenant_id = request.context.tenant_id
            user_id = request.context.user_id
            key = f"{tenant_id}:{user_id}"

            channels = self._channels.get(key, [])
            channel = None

            # Find existing channel of this type
            for c in channels:
                if c.get("type") == request.type:
                    c["is_enabled"] = request.is_enabled
                    c["config"] = dict(request.config)
                    c["updated_at"] = datetime.now(UTC).isoformat()
                    channel = c
                    break

            # Create new channel if not found
            if not channel:
                channel = {
                    "id": str(uuid4()),
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "type": request.type,
                    "is_enabled": request.is_enabled,
                    "is_verified": False,
                    "config": dict(request.config),
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
                if key not in self._channels:
                    self._channels[key] = []
                self._channels[key].append(channel)

            return notification_pb2.UpdateChannelResponse(
                channel=self._to_proto_channel(channel),
            )

        except Exception as e:
            logger.error("UpdateChannel error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to update channel: {e}",
            )

    async def TestChannel(
        self,
        request: notification_pb2.TestChannelRequest,
        context: grpc.aio.ServicerContext,
    ) -> notification_pb2.TestChannelResponse:
        """Test a notification channel."""
        from llamatrade.v1 import notification_pb2

        try:
            # Stub implementation - always succeeds
            return notification_pb2.TestChannelResponse(
                success=True,
                message="Test notification sent successfully (stub)",
            )

        except Exception as e:
            logger.error("TestChannel error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to test channel: {e}",
            )

    # ===================
    # Helper methods
    # ===================

    def _to_proto_notification(self, n: dict) -> notification_pb2.Notification:
        """Convert notification dict to proto Notification."""
        from llamatrade.v1 import common_pb2, notification_pb2

        created_at = n.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        read_at = n.get("read_at")
        if isinstance(read_at, str):
            read_at = datetime.fromisoformat(read_at.replace("Z", "+00:00"))

        return notification_pb2.Notification(
            id=n.get("id", ""),
            tenant_id=n.get("tenant_id", ""),
            user_id=n.get("user_id", ""),
            type=n.get("type", notification_pb2.NOTIFICATION_TYPE_INFO),
            title=n.get("title", ""),
            message=n.get("message", ""),
            is_read=n.get("is_read", False),
            metadata=n.get("metadata", {}),
            created_at=common_pb2.Timestamp(seconds=int(created_at.timestamp())) if created_at else None,
            read_at=common_pb2.Timestamp(seconds=int(read_at.timestamp())) if read_at else None,
        )

    def _to_proto_alert(self, a: dict) -> notification_pb2.Alert:
        """Convert alert dict to proto Alert."""
        from llamatrade.v1 import common_pb2, notification_pb2

        condition = a.get("condition", {})

        created_at = a.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        updated_at = a.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))

        last_triggered = a.get("last_triggered_at")
        if isinstance(last_triggered, str):
            last_triggered = datetime.fromisoformat(last_triggered.replace("Z", "+00:00"))

        return notification_pb2.Alert(
            id=a.get("id", ""),
            tenant_id=a.get("tenant_id", ""),
            user_id=a.get("user_id", ""),
            name=a.get("name", ""),
            description=a.get("description", ""),
            is_active=a.get("is_active", True),
            condition=notification_pb2.AlertCondition(
                type=condition.get("type", notification_pb2.ALERT_CONDITION_TYPE_UNSPECIFIED),
                symbol=condition.get("symbol", ""),
                threshold=common_pb2.Decimal(value=str(condition.get("threshold", 0))) if condition.get("threshold") else None,
                strategy_id=condition.get("strategy_id", ""),
            ),
            channels=a.get("channels", []),
            cooldown_minutes=a.get("cooldown_minutes", 0),
            times_triggered=a.get("times_triggered", 0),
            last_triggered_at=common_pb2.Timestamp(seconds=int(last_triggered.timestamp())) if last_triggered else None,
            created_at=common_pb2.Timestamp(seconds=int(created_at.timestamp())) if created_at else None,
            updated_at=common_pb2.Timestamp(seconds=int(updated_at.timestamp())) if updated_at else None,
        )

    def _to_proto_channel(self, c: dict) -> notification_pb2.Channel:
        """Convert channel dict to proto Channel."""
        from llamatrade.v1 import common_pb2, notification_pb2

        created_at = c.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        updated_at = c.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))

        return notification_pb2.Channel(
            id=c.get("id", ""),
            tenant_id=c.get("tenant_id", ""),
            user_id=c.get("user_id", ""),
            type=c.get("type", notification_pb2.CHANNEL_TYPE_EMAIL),
            is_enabled=c.get("is_enabled", False),
            is_verified=c.get("is_verified", False),
            config=c.get("config", {}),
            created_at=common_pb2.Timestamp(seconds=int(created_at.timestamp())) if created_at else None,
            updated_at=common_pb2.Timestamp(seconds=int(updated_at.timestamp())) if updated_at else None,
        )


# Type aliases for method signatures (imported lazily)
from llamatrade.v1 import notification_pb2
