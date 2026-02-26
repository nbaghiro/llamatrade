"""Test alert service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.models import OrderResponse, OrderStatus
from src.services.alert_service import (
    Alert,
    AlertPriority,
    AlertService,
    AlertType,
)


@pytest.fixture
def alert_service(mock_db):
    """Create alert service with mocked database."""
    return AlertService(mock_db)


@pytest.fixture
def alert_service_no_db():
    """Create alert service without database."""
    return AlertService()


@pytest.fixture
def sample_order_response(order_id):
    """Create a sample order response."""
    return OrderResponse(
        id=order_id,
        alpaca_order_id="alpaca-123",
        symbol="AAPL",
        side="buy",
        qty=10.0,
        order_type="market",
        status=OrderStatus.FILLED,
        filled_qty=10.0,
        filled_avg_price=150.50,
        submitted_at=datetime.now(UTC),
        filled_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_webhook():
    """Create a mock webhook."""
    webhook = MagicMock()
    webhook.url = "https://example.com/webhook"
    webhook.secret = "test-secret"
    webhook.events = []  # Accept all events
    return webhook


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation(self, tenant_id, session_id):
        """Test creating an Alert instance."""
        alert = Alert(
            tenant_id=tenant_id,
            session_id=session_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test Alert",
            message="This is a test",
        )

        assert alert.tenant_id == tenant_id
        assert alert.session_id == session_id
        assert alert.alert_type == AlertType.ORDER_FILLED
        assert alert.priority == AlertPriority.LOW
        assert alert.timestamp is not None

    def test_alert_with_metadata(self, tenant_id):
        """Test creating Alert with metadata."""
        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.RISK_BREACH,
            priority=AlertPriority.HIGH,
            title="Risk Breach",
            message="Daily loss limit exceeded",
            metadata={"current_loss": -1500.0, "limit": 1000.0},
        )

        assert alert.metadata["current_loss"] == -1500.0
        assert alert.metadata["limit"] == 1000.0


class TestAlertService:
    """Tests for AlertService."""

    async def test_send_no_webhooks(self, alert_service, mock_db, tenant_id):
        """Test sending alert when no webhooks configured."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        result = await alert_service.send(alert)

        assert result is True  # No failures if no webhooks

    async def test_should_send_all_events(self, alert_service, mock_webhook, tenant_id):
        """Test webhook with no event filter accepts all."""
        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test",
        )

        result = alert_service._should_send(alert, mock_webhook)

        assert result is True

    async def test_should_send_filtered_events(self, alert_service, mock_webhook, tenant_id):
        """Test webhook with event filter."""
        mock_webhook.events = ["risk_breach", "session_error"]

        # Order filled not in events list
        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test",
        )

        result = alert_service._should_send(alert, mock_webhook)
        assert result is False

        # Risk breach is in events list
        alert.alert_type = AlertType.RISK_BREACH
        result = alert_service._should_send(alert, mock_webhook)
        assert result is True


class TestAlertServiceEvents:
    """Tests for alert service event handlers."""

    async def test_on_order_filled(
        self, alert_service_no_db, tenant_id, session_id, sample_order_response
    ):
        """Test on_order_filled creates correct alert."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_order_filled(
                tenant_id=tenant_id,
                session_id=session_id,
                order=sample_order_response,
            )

            mock_send.assert_called_once()
            alert = mock_send.call_args[0][0]
            assert alert.alert_type == AlertType.ORDER_FILLED
            assert alert.priority == AlertPriority.LOW
            assert "AAPL" in alert.title

    async def test_on_order_rejected(self, alert_service_no_db, tenant_id, session_id):
        """Test on_order_rejected creates correct alert."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_order_rejected(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol="AAPL",
                side="buy",
                qty=100.0,
                reason="Insufficient funds",
            )

            alert = mock_send.call_args[0][0]
            assert alert.alert_type == AlertType.ORDER_REJECTED
            assert alert.priority == AlertPriority.MEDIUM

    async def test_on_position_opened(self, alert_service_no_db, tenant_id, session_id):
        """Test on_position_opened creates correct alert."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_position_opened(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol="AAPL",
                side="long",
                qty=10.0,
                price=150.0,
            )

            alert = mock_send.call_args[0][0]
            assert alert.alert_type == AlertType.POSITION_OPENED
            assert alert.symbol == "AAPL"

    async def test_on_position_closed_profit(self, alert_service_no_db, tenant_id, session_id):
        """Test on_position_closed with profit uses LOW priority."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_position_closed(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol="AAPL",
                qty=10.0,
                pnl=100.0,  # Profit
            )

            alert = mock_send.call_args[0][0]
            assert alert.priority == AlertPriority.LOW

    async def test_on_position_closed_loss(self, alert_service_no_db, tenant_id, session_id):
        """Test on_position_closed with loss uses MEDIUM priority."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_position_closed(
                tenant_id=tenant_id,
                session_id=session_id,
                symbol="AAPL",
                qty=10.0,
                pnl=-100.0,  # Loss
            )

            alert = mock_send.call_args[0][0]
            assert alert.priority == AlertPriority.MEDIUM

    async def test_on_risk_breach(self, alert_service_no_db, tenant_id, session_id):
        """Test on_risk_breach creates HIGH priority alert."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_risk_breach(
                tenant_id=tenant_id,
                session_id=session_id,
                breach_type="position_size",
                details={"current": 15000, "limit": 10000},
            )

            alert = mock_send.call_args[0][0]
            assert alert.alert_type == AlertType.RISK_BREACH
            assert alert.priority == AlertPriority.HIGH

    async def test_on_daily_loss_limit(self, alert_service_no_db, tenant_id, session_id):
        """Test on_daily_loss_limit creates CRITICAL alert."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_daily_loss_limit(
                tenant_id=tenant_id,
                session_id=session_id,
                current_loss=-1500.0,
                limit=1000.0,
            )

            alert = mock_send.call_args[0][0]
            assert alert.alert_type == AlertType.DAILY_LOSS_LIMIT
            assert alert.priority == AlertPriority.CRITICAL

    async def test_on_strategy_error(self, alert_service_no_db, tenant_id, session_id):
        """Test on_strategy_error creates CRITICAL alert."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_strategy_error(
                tenant_id=tenant_id,
                session_id=session_id,
                error="Unexpected exception in strategy",
            )

            alert = mock_send.call_args[0][0]
            assert alert.alert_type == AlertType.STRATEGY_ERROR
            assert alert.priority == AlertPriority.CRITICAL

    async def test_on_session_started(self, alert_service_no_db, tenant_id, session_id):
        """Test on_session_started creates alert."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_session_started(
                tenant_id=tenant_id,
                session_id=session_id,
                strategy_name="Moving Average Crossover",
                mode="paper",
            )

            alert = mock_send.call_args[0][0]
            assert alert.alert_type == AlertType.SESSION_STARTED
            assert "Moving Average Crossover" in alert.message

    async def test_on_session_error(self, alert_service_no_db, tenant_id, session_id):
        """Test on_session_error creates CRITICAL alert."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_session_error(
                tenant_id=tenant_id,
                session_id=session_id,
                error="Database connection failed",
            )

            alert = mock_send.call_args[0][0]
            assert alert.alert_type == AlertType.SESSION_ERROR
            assert alert.priority == AlertPriority.CRITICAL

    async def test_on_connection_lost(self, alert_service_no_db, tenant_id, session_id):
        """Test on_connection_lost creates HIGH priority alert."""
        with patch.object(alert_service_no_db, "send", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            await alert_service_no_db.on_connection_lost(
                tenant_id=tenant_id,
                session_id=session_id,
                service="Alpaca WebSocket",
            )

            alert = mock_send.call_args[0][0]
            assert alert.alert_type == AlertType.CONNECTION_LOST
            assert alert.priority == AlertPriority.HIGH


class TestAlertServiceClose:
    """Tests for alert service cleanup."""

    async def test_close_with_client(self, alert_service_no_db):
        """Test closing service with HTTP client."""
        mock_client = AsyncMock()
        alert_service_no_db._http_client = mock_client

        await alert_service_no_db.close()

        mock_client.aclose.assert_called_once()
        assert alert_service_no_db._http_client is None

    async def test_close_without_client(self, alert_service_no_db):
        """Test closing service without HTTP client."""
        # Should not raise
        await alert_service_no_db.close()
