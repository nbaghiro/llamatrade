"""Tests for notification gRPC servicer methods."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from conftest import TEST_TENANT_ID, TEST_USER_ID, MockServicerContext

from src.grpc.servicer import NotificationServicer

pytestmark = pytest.mark.asyncio


class TestListNotifications:
    """Tests for ListNotifications gRPC method."""

    async def test_list_notifications_empty(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test listing notifications returns empty list when none exist."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.ListNotificationsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
        )

        response = await notification_servicer.ListNotifications(request, grpc_context)

        assert len(response.notifications) == 0
        assert response.pagination.total_items == 0
        assert response.unread_count == 0

    async def test_list_notifications_with_data(
        self,
        notification_servicer: NotificationServicer,
        grpc_context: MockServicerContext,
        sample_notification: dict[str, Any],
    ) -> None:
        """Test listing notifications returns stored notifications."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        # Add notification to servicer's in-memory storage
        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._notifications[key] = [sample_notification]

        request = notification_pb2.ListNotificationsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
        )

        response = await notification_servicer.ListNotifications(request, grpc_context)

        assert len(response.notifications) == 1
        assert response.notifications[0].title == "Test Notification"
        assert response.pagination.total_items == 1
        assert response.unread_count == 1

    async def test_list_notifications_unread_only(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test filtering notifications by unread_only."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._notifications[key] = [
            {
                "id": str(uuid4()),
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": 1,
                "title": "Read Notification",
                "message": "Already read",
                "is_read": True,
                "metadata": {},
                "created_at": datetime.now(UTC).isoformat(),
                "read_at": datetime.now(UTC).isoformat(),
            },
            {
                "id": str(uuid4()),
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": 1,
                "title": "Unread Notification",
                "message": "Not read yet",
                "is_read": False,
                "metadata": {},
                "created_at": datetime.now(UTC).isoformat(),
                "read_at": None,
            },
        ]

        request = notification_pb2.ListNotificationsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            unread_only=True,
        )

        response = await notification_servicer.ListNotifications(request, grpc_context)

        assert len(response.notifications) == 1
        assert response.notifications[0].title == "Unread Notification"
        assert response.unread_count == 1

    async def test_list_notifications_pagination(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test pagination of notifications."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._notifications[key] = [
            {
                "id": str(uuid4()),
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": 1,
                "title": f"Notification {i}",
                "message": f"Message {i}",
                "is_read": False,
                "metadata": {},
                "created_at": datetime.now(UTC).isoformat(),
                "read_at": None,
            }
            for i in range(5)
        ]

        request = notification_pb2.ListNotificationsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            pagination=common_pb2.PaginationRequest(page=1, page_size=2),
        )

        response = await notification_servicer.ListNotifications(request, grpc_context)

        assert len(response.notifications) == 2
        assert response.pagination.total_items == 5
        assert response.pagination.total_pages == 3
        assert response.pagination.has_next is True
        assert response.pagination.has_previous is False

    async def test_list_notifications_tenant_isolation(
        self,
        notification_servicer: NotificationServicer,
        grpc_context: MockServicerContext,
        sample_notification: dict[str, Any],
    ) -> None:
        """Test that notifications are isolated by tenant."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        # Add notification for different tenant
        other_tenant = str(uuid4())
        key = f"{other_tenant}:{TEST_USER_ID}"
        notification_servicer._notifications[key] = [sample_notification]

        # Request for our tenant should return empty
        request = notification_pb2.ListNotificationsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
        )

        response = await notification_servicer.ListNotifications(request, grpc_context)

        assert len(response.notifications) == 0


class TestMarkAsRead:
    """Tests for MarkAsRead gRPC method."""

    async def test_mark_single_notification_as_read(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test marking a single notification as read."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        notification_id = str(uuid4())
        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._notifications[key] = [
            {
                "id": notification_id,
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": 1,
                "title": "Test",
                "message": "Test",
                "is_read": False,
                "metadata": {},
                "created_at": datetime.now(UTC).isoformat(),
                "read_at": None,
            }
        ]

        request = notification_pb2.MarkAsReadRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            notification_id=notification_id,
        )

        response = await notification_servicer.MarkAsRead(request, grpc_context)

        assert response.marked_count == 1
        assert notification_servicer._notifications[key][0]["is_read"] is True
        assert notification_servicer._notifications[key][0]["read_at"] is not None

    async def test_mark_all_notifications_as_read(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test marking all notifications as read."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._notifications[key] = [
            {
                "id": str(uuid4()),
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": 1,
                "title": f"Notification {i}",
                "message": f"Message {i}",
                "is_read": False,
                "metadata": {},
                "created_at": datetime.now(UTC).isoformat(),
                "read_at": None,
            }
            for i in range(3)
        ]

        request = notification_pb2.MarkAsReadRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            mark_all=True,
        )

        response = await notification_servicer.MarkAsRead(request, grpc_context)

        assert response.marked_count == 3
        for n in notification_servicer._notifications[key]:
            assert n["is_read"] is True

    async def test_mark_already_read_notification(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test marking an already-read notification is idempotent."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        notification_id = str(uuid4())
        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._notifications[key] = [
            {
                "id": notification_id,
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": 1,
                "title": "Test",
                "message": "Test",
                "is_read": True,
                "metadata": {},
                "created_at": datetime.now(UTC).isoformat(),
                "read_at": datetime.now(UTC).isoformat(),
            }
        ]

        request = notification_pb2.MarkAsReadRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            notification_id=notification_id,
        )

        response = await notification_servicer.MarkAsRead(request, grpc_context)

        assert response.marked_count == 0

    async def test_mark_nonexistent_notification(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test marking a nonexistent notification returns 0."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.MarkAsReadRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            notification_id=str(uuid4()),
        )

        response = await notification_servicer.MarkAsRead(request, grpc_context)

        assert response.marked_count == 0
