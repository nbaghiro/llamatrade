"""Tests for alert gRPC servicer methods."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import grpc.aio
import pytest
from conftest import TEST_TENANT_ID, TEST_USER_ID, MockServicerContext

from src.grpc.servicer import NotificationServicer

pytestmark = pytest.mark.asyncio


class TestListAlerts:
    """Tests for ListAlerts gRPC method."""

    async def test_list_alerts_empty(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test listing alerts returns empty list when none exist."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.ListAlertsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
        )

        response = await notification_servicer.ListAlerts(request, grpc_context)

        assert len(response.alerts) == 0

    async def test_list_alerts_with_data(
        self,
        notification_servicer: NotificationServicer,
        grpc_context: MockServicerContext,
        sample_alert: dict[str, Any],
    ) -> None:
        """Test listing alerts returns stored alerts."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._alerts[key] = [sample_alert]

        request = notification_pb2.ListAlertsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
        )

        response = await notification_servicer.ListAlerts(request, grpc_context)

        assert len(response.alerts) == 1
        assert response.alerts[0].name == "Price Alert"

    async def test_list_alerts_active_only(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test filtering alerts by active_only."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._alerts[key] = [
            {
                "id": str(uuid4()),
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "name": "Active Alert",
                "description": "",
                "is_active": True,
                "condition": {"type": 1, "symbol": "AAPL", "threshold": "200"},
                "channels": [1],
                "cooldown_minutes": 60,
                "times_triggered": 0,
                "last_triggered_at": None,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            {
                "id": str(uuid4()),
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "name": "Inactive Alert",
                "description": "",
                "is_active": False,
                "condition": {"type": 1, "symbol": "GOOGL", "threshold": "150"},
                "channels": [1],
                "cooldown_minutes": 60,
                "times_triggered": 0,
                "last_triggered_at": None,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ]

        request = notification_pb2.ListAlertsRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            active_only=True,
        )

        response = await notification_servicer.ListAlerts(request, grpc_context)

        assert len(response.alerts) == 1
        assert response.alerts[0].name == "Active Alert"


class TestCreateAlert:
    """Tests for CreateAlert gRPC method."""

    async def test_create_alert_success(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test creating an alert successfully."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.CreateAlertRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            name="New Price Alert",
            description="Alert when AAPL hits $200",
            condition=notification_pb2.AlertCondition(
                type=notification_pb2.ALERT_CONDITION_TYPE_PRICE_ABOVE,
                symbol="AAPL",
                threshold=common_pb2.Decimal(value="200.0"),
            ),
            channels=[notification_pb2.CHANNEL_TYPE_EMAIL],
            cooldown_minutes=30,
        )

        response = await notification_servicer.CreateAlert(request, grpc_context)

        assert response.alert.name == "New Price Alert"
        assert response.alert.description == "Alert when AAPL hits $200"
        assert response.alert.is_active is True
        assert response.alert.times_triggered == 0
        assert response.alert.id  # Should have an ID

        # Verify stored in memory
        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        assert len(notification_servicer._alerts[key]) == 1

    async def test_create_alert_with_strategy_condition(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test creating an alert with strategy-based condition."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        strategy_id = str(uuid4())
        request = notification_pb2.CreateAlertRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            name="Strategy Alert",
            description="Alert on strategy signal",
            condition=notification_pb2.AlertCondition(
                type=notification_pb2.ALERT_CONDITION_TYPE_STRATEGY_SIGNAL,
                strategy_id=strategy_id,
            ),
            channels=[notification_pb2.CHANNEL_TYPE_EMAIL, notification_pb2.CHANNEL_TYPE_WEBHOOK],
        )

        response = await notification_servicer.CreateAlert(request, grpc_context)

        assert response.alert.name == "Strategy Alert"
        assert response.alert.condition.strategy_id == strategy_id

    async def test_create_multiple_alerts(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test creating multiple alerts for same user."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        for i in range(3):
            request = notification_pb2.CreateAlertRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                name=f"Alert {i}",
                condition=notification_pb2.AlertCondition(
                    type=notification_pb2.ALERT_CONDITION_TYPE_PRICE_ABOVE,
                    symbol="AAPL",
                    threshold=common_pb2.Decimal(value=str(100 + i * 10)),
                ),
                channels=[notification_pb2.CHANNEL_TYPE_EMAIL],
            )
            await notification_servicer.CreateAlert(request, grpc_context)

        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        assert len(notification_servicer._alerts[key]) == 3


class TestDeleteAlert:
    """Tests for DeleteAlert gRPC method."""

    async def test_delete_alert_success(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test deleting an alert successfully."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        alert_id = str(uuid4())
        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._alerts[key] = [
            {
                "id": alert_id,
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "name": "Alert to Delete",
                "description": "",
                "is_active": True,
                "condition": {"type": 1, "symbol": "AAPL", "threshold": "200"},
                "channels": [1],
                "cooldown_minutes": 60,
                "times_triggered": 0,
                "last_triggered_at": None,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ]

        request = notification_pb2.DeleteAlertRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            alert_id=alert_id,
        )

        response = await notification_servicer.DeleteAlert(request, grpc_context)

        assert response.success is True
        assert len(notification_servicer._alerts[key]) == 0

    async def test_delete_alert_not_found(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test deleting a nonexistent alert returns NOT_FOUND."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.DeleteAlertRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            alert_id=str(uuid4()),
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await notification_servicer.DeleteAlert(request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND


class TestToggleAlert:
    """Tests for ToggleAlert gRPC method."""

    async def test_toggle_alert_deactivate(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test deactivating an alert."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        alert_id = str(uuid4())
        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._alerts[key] = [
            {
                "id": alert_id,
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "name": "Active Alert",
                "description": "",
                "is_active": True,
                "condition": {"type": 1, "symbol": "AAPL", "threshold": "200"},
                "channels": [1],
                "cooldown_minutes": 60,
                "times_triggered": 0,
                "last_triggered_at": None,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ]

        request = notification_pb2.ToggleAlertRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            alert_id=alert_id,
            is_active=False,
        )

        response = await notification_servicer.ToggleAlert(request, grpc_context)

        assert response.alert.is_active is False
        assert notification_servicer._alerts[key][0]["is_active"] is False

    async def test_toggle_alert_activate(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test activating an alert."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        alert_id = str(uuid4())
        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._alerts[key] = [
            {
                "id": alert_id,
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "name": "Inactive Alert",
                "description": "",
                "is_active": False,
                "condition": {"type": 1, "symbol": "AAPL", "threshold": "200"},
                "channels": [1],
                "cooldown_minutes": 60,
                "times_triggered": 0,
                "last_triggered_at": None,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ]

        request = notification_pb2.ToggleAlertRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            alert_id=alert_id,
            is_active=True,
        )

        response = await notification_servicer.ToggleAlert(request, grpc_context)

        assert response.alert.is_active is True

    async def test_toggle_alert_not_found(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test toggling a nonexistent alert returns NOT_FOUND."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        request = notification_pb2.ToggleAlertRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            alert_id=str(uuid4()),
            is_active=False,
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await notification_servicer.ToggleAlert(request, grpc_context)

        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND

    async def test_toggle_alert_updates_timestamp(
        self, notification_servicer: NotificationServicer, grpc_context: MockServicerContext
    ) -> None:
        """Test that toggling updates the updated_at timestamp."""
        from llamatrade_proto.generated import common_pb2, notification_pb2

        alert_id = str(uuid4())
        original_time = "2024-01-01T00:00:00+00:00"
        key = f"{TEST_TENANT_ID}:{TEST_USER_ID}"
        notification_servicer._alerts[key] = [
            {
                "id": alert_id,
                "tenant_id": str(TEST_TENANT_ID),
                "user_id": str(TEST_USER_ID),
                "name": "Alert",
                "description": "",
                "is_active": True,
                "condition": {"type": 1, "symbol": "AAPL", "threshold": "200"},
                "channels": [1],
                "cooldown_minutes": 60,
                "times_triggered": 0,
                "last_triggered_at": None,
                "created_at": original_time,
                "updated_at": original_time,
            }
        ]

        request = notification_pb2.ToggleAlertRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            alert_id=alert_id,
            is_active=False,
        )

        await notification_servicer.ToggleAlert(request, grpc_context)

        # updated_at should be different from original
        assert notification_servicer._alerts[key][0]["updated_at"] != original_time
