"""Test alert service."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_STATUS_FILLED,
    ORDER_TYPE_MARKET,
)

from src.models import OrderResponse
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
        side=ORDER_SIDE_BUY,
        qty=10.0,
        order_type=ORDER_TYPE_MARKET,
        status=ORDER_STATUS_FILLED,
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


class TestWebhookSecurity:
    """Tests for webhook HMAC signature and security."""

    async def test_hmac_signature_computed_correctly(
        self, alert_service_no_db, mock_webhook, tenant_id
    ):
        """Test HMAC signature is computed correctly."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        alert_service_no_db._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        await alert_service_no_db._send_webhook(mock_webhook, alert)

        # Verify signature header was added
        call_kwargs = mock_client.post.call_args[1]
        headers = call_kwargs["headers"]
        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")

        # Verify signature is correct
        payload = call_kwargs["json"]
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        expected_sig = hmac.new(
            mock_webhook.secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        assert headers["X-Webhook-Signature"] == f"sha256={expected_sig}"

    async def test_no_signature_when_no_secret(self, alert_service_no_db, mock_webhook, tenant_id):
        """Test no signature header when webhook has no secret."""
        mock_webhook.secret = None
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        alert_service_no_db._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        await alert_service_no_db._send_webhook(mock_webhook, alert)

        call_kwargs = mock_client.post.call_args[1]
        headers = call_kwargs["headers"]
        assert "X-Webhook-Signature" not in headers

    async def test_custom_headers_included(self, alert_service_no_db, mock_webhook, tenant_id):
        """Test custom headers from webhook config are included."""
        mock_webhook.headers = {"X-Custom-Header": "custom-value", "Authorization": "Bearer token"}
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        alert_service_no_db._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        await alert_service_no_db._send_webhook(mock_webhook, alert)

        call_kwargs = mock_client.post.call_args[1]
        headers = call_kwargs["headers"]
        assert headers["X-Custom-Header"] == "custom-value"
        assert headers["Authorization"] == "Bearer token"


class TestWebhookRetryLogic:
    """Tests for webhook retry logic."""

    async def test_retry_on_connection_error(self, alert_service_no_db, mock_webhook, tenant_id):
        """Test webhook retries on connection error."""
        mock_client = AsyncMock()
        # Fail twice, then succeed
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.post.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.ConnectError("Connection refused"),
            mock_response,
        ]
        alert_service_no_db._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        await alert_service_no_db._send_webhook(mock_webhook, alert)

        # Should have been called 3 times (2 retries + 1 success)
        assert mock_client.post.call_count == 3

    async def test_retry_exhausted_raises_error(self, alert_service_no_db, mock_webhook, tenant_id):
        """Test webhook raises error after retries exhausted."""
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        alert_service_no_db._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        # With reraise=True, the original exception is raised after retries exhausted
        with pytest.raises(httpx.ConnectError):
            await alert_service_no_db._send_webhook(mock_webhook, alert)

        # Should have been called 3 times (max attempts)
        assert mock_client.post.call_count == 3

    async def test_retry_on_5xx_error(self, alert_service_no_db, mock_webhook, tenant_id):
        """Test webhook retries on 5xx HTTP errors."""
        mock_client = AsyncMock()
        mock_error_response = MagicMock()
        mock_error_response.status_code = 503
        mock_error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Service Unavailable",
            request=MagicMock(),
            response=mock_error_response,
        )

        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.raise_for_status = MagicMock()

        mock_client.post.side_effect = [
            mock_error_response,
            mock_success_response,
        ]
        alert_service_no_db._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        await alert_service_no_db._send_webhook(mock_webhook, alert)

        assert mock_client.post.call_count == 2


class TestWebhookDeliveryTracking:
    """Tests for webhook delivery tracking."""

    async def test_success_resets_failure_count(
        self, alert_service, mock_db, mock_webhook, tenant_id
    ):
        """Test successful delivery resets failure count."""
        mock_webhook.failure_count = 3
        mock_webhook.last_triggered_at = None
        mock_webhook.last_status_code = 500

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        alert_service._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        await alert_service._send_webhook(mock_webhook, alert)

        # Verify failure count was reset
        assert mock_webhook.failure_count == 0
        assert mock_webhook.last_status_code == 200
        assert mock_webhook.last_triggered_at is not None
        mock_db.commit.assert_called()

    async def test_failure_increments_failure_count(
        self, alert_service, mock_db, mock_webhook, tenant_id
    ):
        """Test failed delivery increments failure count."""
        mock_webhook.failure_count = 2
        mock_webhook.last_triggered_at = None
        mock_webhook.last_status_code = None

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        alert_service._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        # With reraise=True, the original exception is raised after retries exhausted
        with pytest.raises(httpx.ConnectError):
            await alert_service._send_webhook(mock_webhook, alert)

        # Verify failure count was incremented
        assert mock_webhook.failure_count == 3
        assert mock_webhook.last_triggered_at is not None
        mock_db.commit.assert_called()

    async def test_http_status_code_tracked_on_failure(
        self, alert_service, mock_db, mock_webhook, tenant_id
    ):
        """Test HTTP status code is tracked on HTTP error failure."""
        mock_webhook.failure_count = 0
        mock_webhook.last_status_code = None

        mock_client = AsyncMock()
        mock_error_response = MagicMock()
        mock_error_response.status_code = 403
        mock_error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=mock_error_response,
        )
        mock_client.post.return_value = mock_error_response
        alert_service._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        # With reraise=True, the original exception is raised after retries exhausted
        with pytest.raises(httpx.HTTPStatusError):
            await alert_service._send_webhook(mock_webhook, alert)

        # Verify status code was tracked
        assert mock_webhook.last_status_code == 403
        assert mock_webhook.failure_count == 1

    async def test_delivery_tracking_handles_db_error(
        self, alert_service, mock_db, mock_webhook, tenant_id
    ):
        """Test delivery tracking gracefully handles database errors."""
        mock_webhook.failure_count = 0
        mock_db.commit.side_effect = Exception("Database error")

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        alert_service._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        # Should not raise despite database error
        await alert_service._send_webhook(mock_webhook, alert)

        mock_db.rollback.assert_called()


class TestWebhookErrorIsolation:
    """Tests for error isolation between webhooks."""

    async def test_single_webhook_failure_does_not_break_others(
        self, alert_service, mock_db, tenant_id
    ):
        """Test that one webhook failure doesn't prevent others from sending."""
        webhook1 = MagicMock()
        webhook1.url = "https://example1.com/webhook"
        webhook1.secret = "secret1"
        webhook1.events = []
        webhook1.headers = None
        webhook1.failure_count = 0
        webhook1.last_triggered_at = None
        webhook1.last_status_code = None

        webhook2 = MagicMock()
        webhook2.url = "https://example2.com/webhook"
        webhook2.secret = "secret2"
        webhook2.events = []
        webhook2.headers = None
        webhook2.failure_count = 0
        webhook2.last_triggered_at = None
        webhook2.last_status_code = None

        # Mock _get_webhooks to return both webhooks
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [webhook1, webhook2]
        mock_db.execute.return_value = mock_result

        # Mock HTTP client - first webhook fails, second succeeds
        mock_client = AsyncMock()

        async def mock_post(url, **kwargs):
            if url == "https://example1.com/webhook":
                raise httpx.ConnectError("Connection refused")
            response = MagicMock()
            response.status_code = 200
            response.raise_for_status = MagicMock()
            return response

        mock_client.post.side_effect = mock_post
        alert_service._http_client = mock_client

        alert = Alert(
            tenant_id=tenant_id,
            alert_type=AlertType.ORDER_FILLED,
            priority=AlertPriority.LOW,
            title="Test",
            message="Test message",
        )

        # Should return False (partial failure) but not raise
        result = await alert_service.send(alert)

        assert result is False  # One webhook failed
        # Verify both webhooks were attempted (with retries for first)
        assert mock_client.post.call_count >= 2
