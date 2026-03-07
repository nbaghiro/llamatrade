"""Tests for channel gRPC servicer methods."""

# pyright: reportPrivateUsage=false
# pyright: reportArgumentType=false

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from conftest import TEST_TENANT_ID, TEST_USER_ID, MockServicerContext

from src.grpc.servicer import NotificationServicer

pytestmark = pytest.mark.asyncio


class TestListChannels:
    """Tests for ListChannels gRPC method."""

    async def test_list_channels_returns_default_email(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test listing channels returns default email channel if none configured."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.ListChannelsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
        )

        response = await notification_servicer.ListChannels(request, grpc_context)

        assert len(response.channels) == 1
        assert response.channels[0].type == notification_pb2.CHANNEL_TYPE_EMAIL
        assert response.channels[0].is_enabled is False
        assert response.channels[0].is_verified is False

    async def test_list_channels_with_configured_channels(
        self,
        notification_servicer: NotificationServicer,
        grpc_context: MockServicerContext,
        sample_channel: dict[str, Any],
    ) -> None:
        """Test listing configured channels."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._channels[key] = [sample_channel]

        request = notification_pb2.ListChannelsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
        )

        response = await notification_servicer.ListChannels(request, grpc_context)

        assert len(response.channels) == 1
        assert response.channels[0].is_enabled is True
        assert response.channels[0].is_verified is True

    async def test_list_channels_multiple_types(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test listing multiple channel types."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._channels[key] = [
            {
                "id": str(uuid4()),
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": notification_pb2.CHANNEL_TYPE_EMAIL,
                "is_enabled": True,
                "is_verified": True,
                "config": {"email": "test@example.com"},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            {
                "id": str(uuid4()),
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": notification_pb2.CHANNEL_TYPE_WEBHOOK,
                "is_enabled": True,
                "is_verified": False,
                "config": {"url": "https://example.com/webhook"},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ]

        request = notification_pb2.ListChannelsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
        )

        response = await notification_servicer.ListChannels(request, grpc_context)

        assert len(response.channels) == 2


class TestUpdateChannel:
    """Tests for UpdateChannel gRPC method."""

    async def test_update_channel_create_new(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test creating a new channel via update."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.UpdateChannelRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            type=notification_pb2.CHANNEL_TYPE_EMAIL,
            is_enabled=True,
            config={"email": "new@example.com"},
        )

        response = await notification_servicer.UpdateChannel(request, grpc_context)

        assert response.channel.type == notification_pb2.CHANNEL_TYPE_EMAIL
        assert response.channel.is_enabled is True
        assert response.channel.is_verified is False  # New channels are not verified
        assert response.channel.id  # Should have an ID

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        assert len(notification_servicer._channels[key]) == 1

    async def test_update_channel_modify_existing(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test updating an existing channel."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        channel_id = str(uuid4())
        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._channels[key] = [
            {
                "id": channel_id,
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": notification_pb2.CHANNEL_TYPE_EMAIL,
                "is_enabled": False,
                "is_verified": True,
                "config": {"email": "old@example.com"},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ]

        request = notification_pb2.UpdateChannelRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            type=notification_pb2.CHANNEL_TYPE_EMAIL,
            is_enabled=True,
            config={"email": "new@example.com"},
        )

        response = await notification_servicer.UpdateChannel(request, grpc_context)

        assert response.channel.is_enabled is True
        # Should preserve the original channel ID
        assert response.channel.id == channel_id
        # Should still have only one email channel
        assert len(notification_servicer._channels[key]) == 1

    async def test_update_channel_add_webhook(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test adding a webhook channel."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.UpdateChannelRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            type=notification_pb2.CHANNEL_TYPE_WEBHOOK,
            is_enabled=True,
            config={
                "url": "https://example.com/webhook",
                "secret": "mysecret",
            },
        )

        response = await notification_servicer.UpdateChannel(request, grpc_context)

        assert response.channel.type == notification_pb2.CHANNEL_TYPE_WEBHOOK
        assert response.channel.is_enabled is True
        assert "url" in response.channel.config

    async def test_update_channel_disable(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test disabling a channel."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._channels[key] = [
            {
                "id": str(uuid4()),
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "type": notification_pb2.CHANNEL_TYPE_EMAIL,
                "is_enabled": True,
                "is_verified": True,
                "config": {"email": "test@example.com"},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ]

        request = notification_pb2.UpdateChannelRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            type=notification_pb2.CHANNEL_TYPE_EMAIL,
            is_enabled=False,
            config={"email": "test@example.com"},
        )

        response = await notification_servicer.UpdateChannel(request, grpc_context)

        assert response.channel.is_enabled is False


class TestTestChannel:
    """Tests for TestChannel gRPC method."""

    async def test_test_channel_success(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test testing a channel (stub always succeeds)."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.TestChannelRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            type=notification_pb2.CHANNEL_TYPE_EMAIL,
        )

        response = await notification_servicer.TestChannel(request, grpc_context)

        assert response.success is True
        assert "stub" in response.message.lower()

    async def test_test_channel_webhook(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test testing a webhook channel."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.TestChannelRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            type=notification_pb2.CHANNEL_TYPE_WEBHOOK,
        )

        response = await notification_servicer.TestChannel(request, grpc_context)

        assert response.success is True


class TestTenantIsolation:
    """Tests for tenant isolation in channel operations."""

    async def test_channels_isolated_by_tenant(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test that channels are isolated by tenant."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        other_tenant = str(uuid4())
        other_key = f"{other_tenant}:{TEST_USER_ID}"
        notification_servicer._channels[other_key] = [
            {
                "id": str(uuid4()),
                "tenant_id": other_tenant,
                "user_id": str(TEST_USER_ID),
                "type": notification_pb2.CHANNEL_TYPE_EMAIL,
                "is_enabled": True,
                "is_verified": True,
                "config": {"email": "other@example.com"},
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ]

        # Request for our tenant should return default channel, not other tenant's
        request = notification_pb2.ListChannelsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
        )

        response = await notification_servicer.ListChannels(request, grpc_context)

        # Should get default email channel, not the one from other tenant
        assert len(response.channels) == 1
        assert response.channels[0].is_enabled is False  # Default is disabled
