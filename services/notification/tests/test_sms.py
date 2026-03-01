"""Tests for SMS notification channel."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.channels.sms import SMSChannel, SMSProvider, SMSResult


class TestSMSChannelConfiguration:
    """Tests for SMS channel configuration."""

    def test_default_provider(self):
        """Test default provider is Twilio."""
        channel = SMSChannel()
        assert channel.provider == SMSProvider.TWILIO

    def test_is_configured_false_when_missing_credentials(self):
        """Test is_configured returns False when credentials missing."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "",
                "TWILIO_AUTH_TOKEN": "",
                "TWILIO_PHONE_NUMBER": "",
            },
            clear=True,
        ):
            channel = SMSChannel()
            assert channel.is_configured is False

    def test_is_configured_true_with_credentials(self):
        """Test is_configured returns True with all credentials."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token123",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()
            assert channel.is_configured is True

    def test_is_configured_false_with_partial_credentials(self):
        """Test is_configured returns False with partial credentials."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()
            assert channel.is_configured is False


class TestSMSResult:
    """Tests for SMSResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful result."""
        result = SMSResult(success=True, message_sid="SM123")
        assert result.success is True
        assert result.message_sid == "SM123"
        assert result.error_code is None
        assert result.error_message is None

    def test_failed_result(self):
        """Test creating a failed result."""
        result = SMSResult(
            success=False,
            error_code="21211",
            error_message="Invalid phone number",
        )
        assert result.success is False
        assert result.error_code == "21211"
        assert result.error_message == "Invalid phone number"


class TestSMSChannelSend:
    """Tests for SMS channel send method."""

    @pytest.mark.asyncio
    async def test_send_not_configured(self):
        """Test send fails gracefully when not configured."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "",
                "TWILIO_AUTH_TOKEN": "",
                "TWILIO_PHONE_NUMBER": "",
            },
            clear=True,
        ):
            channel = SMSChannel()
            result = await channel.send("+1234567890", "Test message")

            assert result.success is False
            assert result.error_code == "NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_send_invalid_phone_format(self):
        """Test send fails with invalid phone number format."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()
            result = await channel.send("1234567890", "Test message")  # Missing +

            assert result.success is False
            assert result.error_code == "INVALID_NUMBER"

    @pytest.mark.asyncio
    async def test_send_success(self):
        """Test successful SMS send."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()

            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"sid": "SM123456"}

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                result = await channel.send("+1234567890", "Test message")

                assert result.success is True
                assert result.message_sid == "SM123456"

    @pytest.mark.asyncio
    async def test_send_api_error(self):
        """Test SMS send handles API errors."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()

            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_response.content = b'{"code": 21211, "message": "Invalid phone number"}'
                mock_response.json.return_value = {
                    "code": 21211,
                    "message": "Invalid phone number",
                }

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                result = await channel.send("+1234567890", "Test message")

                assert result.success is False
                assert result.error_code == "21211"
                assert "Invalid phone number" in result.error_message

    @pytest.mark.asyncio
    async def test_send_timeout(self):
        """Test SMS send handles timeout."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=httpx.TimeoutException("Timeout")
                )

                result = await channel.send("+1234567890", "Test message")

                assert result.success is False
                assert result.error_code == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_send_request_error(self):
        """Test SMS send handles request errors."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()

            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=httpx.ConnectError("Connection failed")
                )

                result = await channel.send("+1234567890", "Test message")

                assert result.success is False
                assert result.error_code == "REQUEST_ERROR"

    @pytest.mark.asyncio
    async def test_send_truncates_long_message(self):
        """Test that long messages are truncated."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()
            long_message = "x" * 2000  # Longer than 1600 char limit

            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"sid": "SM123456"}

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                await channel.send("+1234567890", long_message)

                # Verify the message was truncated
                call_args = mock_client_instance.post.call_args
                sent_message = call_args.kwargs["data"]["Body"]
                assert len(sent_message) == 1600
                assert sent_message.endswith("...")

    @pytest.mark.asyncio
    async def test_send_custom_from_number(self):
        """Test sending with custom from number."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()

            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"sid": "SM123456"}

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                await channel.send(
                    "+1234567890",
                    "Test",
                    from_number="+19998887777",
                )

                call_args = mock_client_instance.post.call_args
                assert call_args.kwargs["data"]["From"] == "+19998887777"


class TestSMSChannelHelpers:
    """Tests for SMS channel helper methods."""

    @pytest.mark.asyncio
    async def test_send_verification_code(self):
        """Test sending verification code."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()

            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"sid": "SM123456"}

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                result = await channel.send_verification_code("+1234567890", "123456")

                assert result.success is True
                call_args = mock_client_instance.post.call_args
                body = call_args.kwargs["data"]["Body"]
                assert "123456" in body
                assert "verification code" in body.lower()

    @pytest.mark.asyncio
    async def test_send_alert_with_message(self):
        """Test sending alert with custom message."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()

            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"sid": "SM123456"}

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                result = await channel.send_alert(
                    "+1234567890",
                    "ORDER_FILLED",
                    message="Your AAPL order was filled at $150.00",
                )

                assert result.success is True
                call_args = mock_client_instance.post.call_args
                body = call_args.kwargs["data"]["Body"]
                assert "AAPL" in body
                assert "$150.00" in body

    @pytest.mark.asyncio
    async def test_send_alert_with_symbol(self):
        """Test sending alert with symbol."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()

            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"sid": "SM123456"}

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                result = await channel.send_alert(
                    "+1234567890",
                    "PRICE_ALERT",
                    symbol="TSLA",
                )

                assert result.success is True
                call_args = mock_client_instance.post.call_args
                body = call_args.kwargs["data"]["Body"]
                assert "PRICE_ALERT" in body
                assert "TSLA" in body

    @pytest.mark.asyncio
    async def test_send_alert_basic(self):
        """Test sending basic alert."""
        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "AC123",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_PHONE_NUMBER": "+15551234567",
            },
        ):
            channel = SMSChannel()

            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {"sid": "SM123456"}

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance

                result = await channel.send_alert("+1234567890", "SESSION_STARTED")

                assert result.success is True
                call_args = mock_client_instance.post.call_args
                body = call_args.kwargs["data"]["Body"]
                assert "SESSION_STARTED" in body
                assert "LlamaTrade" in body
