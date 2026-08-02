"""Tests for llamatrade_db.models.notification module."""

from llamatrade_db.models.notification import (
    Alert,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    Webhook,
)


class TestAlert:
    """Tests for Alert model."""

    def test_alert_tablename(self) -> None:
        """Test Alert has correct tablename."""
        assert Alert.__tablename__ == "alerts"

    def test_alert_has_required_columns(self) -> None:
        """Test Alert has all required columns."""
        columns = Alert.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "name" in columns
        assert "alert_type" in columns
        assert "symbol" in columns
        assert "condition" in columns
        assert "status" in columns
        assert "channels" in columns
        assert "cooldown_minutes" in columns
        assert "last_triggered_at" in columns
        assert "trigger_count" in columns
        assert "expires_at" in columns
        assert "created_by" in columns

    def test_alert_name_not_nullable(self) -> None:
        """Test name column is not nullable."""
        col = Alert.__table__.columns["name"]
        assert col.nullable is False

    def test_alert_type_not_nullable(self) -> None:
        """Test alert_type column is not nullable."""
        col = Alert.__table__.columns["alert_type"]
        assert col.nullable is False

    def test_alert_condition_not_nullable(self) -> None:
        """Test condition column is not nullable."""
        col = Alert.__table__.columns["condition"]
        assert col.nullable is False

    def test_alert_has_indexes(self) -> None:
        """Test Alert has expected indexes."""
        table_args = Alert.__table_args__
        assert table_args is not None


class TestNotification:
    """Tests for Notification model."""

    def test_notification_tablename(self) -> None:
        """Test Notification has correct tablename."""
        assert Notification.__tablename__ == "notifications"

    def test_notification_has_required_columns(self) -> None:
        """Test Notification has all required columns."""
        columns = Notification.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "user_id" in columns
        assert "alert_id" in columns
        assert "notification_type" in columns
        assert "event_id" in columns
        assert "category" in columns
        assert "severity" in columns
        assert "title" in columns
        assert "message" in columns
        assert "data" in columns
        assert "read_at" in columns

    def test_notification_title_not_nullable(self) -> None:
        """Test title column is not nullable."""
        col = Notification.__table__.columns["title"]
        assert col.nullable is False

    def test_notification_message_not_nullable(self) -> None:
        """Test message column is not nullable."""
        col = Notification.__table__.columns["message"]
        assert col.nullable is False

    def test_notification_event_id_unique(self) -> None:
        """Test event_id has a unique index (redelivery dedup)."""
        idx = {i.name: i for i in Notification.__table__.indexes}
        assert idx["ix_notifications_event_id"].unique is True

    def test_notification_user_id_nullable(self) -> None:
        """Test user_id is nullable (tenant-scoped rows leave it null)."""
        assert Notification.__table__.columns["user_id"].nullable is True


class TestNotificationChannel:
    """Tests for NotificationChannel model."""

    def test_notification_channel_tablename(self) -> None:
        """Test NotificationChannel has correct tablename."""
        assert NotificationChannel.__tablename__ == "notification_channels"

    def test_notification_channel_has_required_columns(self) -> None:
        """Test NotificationChannel has all required columns."""
        columns = NotificationChannel.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "user_id" in columns
        assert "channel_type" in columns
        assert "destination" in columns
        assert "is_verified" in columns
        assert "is_enabled" in columns
        assert "preferences" in columns

    def test_notification_channel_type_not_nullable(self) -> None:
        """Test channel_type column is not nullable."""
        col = NotificationChannel.__table__.columns["channel_type"]
        assert col.nullable is False

    def test_notification_channel_destination_not_nullable(self) -> None:
        """Test destination column is not nullable."""
        col = NotificationChannel.__table__.columns["destination"]
        assert col.nullable is False


class TestWebhook:
    """Tests for Webhook model."""

    def test_webhook_tablename(self) -> None:
        """Test Webhook has correct tablename."""
        assert Webhook.__tablename__ == "webhooks"

    def test_webhook_has_required_columns(self) -> None:
        """Test Webhook has all required columns."""
        columns = Webhook.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "name" in columns
        assert "url" in columns
        assert "secret" in columns
        assert "events" in columns
        assert "headers" in columns
        assert "is_active" in columns
        assert "last_triggered_at" in columns
        assert "last_status_code" in columns
        assert "failure_count" in columns
        assert "created_by" in columns

    def test_webhook_name_not_nullable(self) -> None:
        """Test name column is not nullable."""
        col = Webhook.__table__.columns["name"]
        assert col.nullable is False

    def test_webhook_url_not_nullable(self) -> None:
        """Test url column is not nullable."""
        col = Webhook.__table__.columns["url"]
        assert col.nullable is False

    def test_webhook_is_active_has_default(self) -> None:
        """Test is_active has default value."""
        col = Webhook.__table__.columns["is_active"]
        assert col.default is not None

    def test_webhook_failure_count_has_default(self) -> None:
        """Test failure_count has default value."""
        col = Webhook.__table__.columns["failure_count"]
        assert col.default is not None


class TestNotificationDelivery:
    """Tests for NotificationDelivery model."""

    def test_delivery_tablename(self) -> None:
        assert NotificationDelivery.__tablename__ == "notification_deliveries"

    def test_delivery_has_required_columns(self) -> None:
        columns = NotificationDelivery.__table__.columns
        for name in (
            "id",
            "tenant_id",
            "notification_id",
            "channel",
            "destination",
            "status",
            "attempts",
            "last_error",
            "delivered_at",
        ):
            assert name in columns

    def test_delivery_status_defaults_pending(self) -> None:
        col = NotificationDelivery.__table__.columns["status"]
        assert col.default is not None and col.default.arg == 1
