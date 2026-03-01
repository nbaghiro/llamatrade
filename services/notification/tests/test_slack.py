"""Tests for Slack notification channel."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from src.channels.slack import (
    SlackAttachment,
    SlackBlock,
    SlackChannel,
    SlackMessageColor,
    SlackResult,
)


class TestSlackMessageColor:
    """Tests for SlackMessageColor enum."""

    def test_color_values(self):
        """Test color enum values."""
        assert SlackMessageColor.GOOD == "good"
        assert SlackMessageColor.WARNING == "warning"
        assert SlackMessageColor.DANGER == "danger"
        assert SlackMessageColor.INFO == "#2196F3"


class TestSlackBlock:
    """Tests for SlackBlock dataclass."""

    def test_basic_block(self):
        """Test creating a basic block."""
        block = SlackBlock(type="section")
        result = block.to_dict()
        assert result == {"type": "section"}

    def test_block_with_text(self):
        """Test block with text."""
        block = SlackBlock(
            type="section",
            text={"type": "mrkdwn", "text": "Hello"},
        )
        result = block.to_dict()
        assert result["text"] == {"type": "mrkdwn", "text": "Hello"}

    def test_block_with_fields(self):
        """Test block with fields."""
        block = SlackBlock(
            type="section",
            fields=[
                {"type": "mrkdwn", "text": "*Field 1*"},
                {"type": "mrkdwn", "text": "*Field 2*"},
            ],
        )
        result = block.to_dict()
        assert len(result["fields"]) == 2


class TestSlackAttachment:
    """Tests for SlackAttachment dataclass."""

    def test_basic_attachment(self):
        """Test creating a basic attachment."""
        attachment = SlackAttachment(color=SlackMessageColor.GOOD)
        result = attachment.to_dict()
        assert result == {"color": "good"}

    def test_full_attachment(self):
        """Test attachment with all fields."""
        attachment = SlackAttachment(
            color=SlackMessageColor.DANGER,
            title="Alert",
            text="Something happened",
            fields=[{"title": "Field", "value": "Value", "short": True}],
            footer="LlamaTrade",
            ts=1234567890,
        )
        result = attachment.to_dict()

        assert result["color"] == "danger"
        assert result["title"] == "Alert"
        assert result["text"] == "Something happened"
        assert len(result["fields"]) == 1
        assert result["footer"] == "LlamaTrade"
        assert result["ts"] == 1234567890


class TestSlackResult:
    """Tests for SlackResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful result."""
        result = SlackResult(success=True)
        assert result.success is True
        assert result.error_message is None

    def test_failed_result(self):
        """Test creating a failed result."""
        result = SlackResult(success=False, error_message="API error")
        assert result.success is False
        assert result.error_message == "API error"


class TestSlackChannelInit:
    """Tests for SlackChannel initialization."""

    def test_basic_init(self):
        """Test basic initialization."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")
        assert channel.webhook_url == "https://hooks.slack.com/test"
        assert channel.default_channel is None
        assert channel.default_username == "LlamaTrade"

    def test_full_init(self):
        """Test initialization with all options."""
        channel = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            default_channel="#alerts",
            default_username="TradingBot",
            default_icon_emoji=":robot_face:",
        )
        assert channel.default_channel == "#alerts"
        assert channel.default_username == "TradingBot"
        assert channel.default_icon_emoji == ":robot_face:"


class TestSlackChannelSend:
    """Tests for SlackChannel send method."""

    @pytest.mark.asyncio
    async def test_send_simple_message(self):
        """Test sending a simple message."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await channel.send("Hello, Slack!")

            assert result.success is True

    @pytest.mark.asyncio
    async def test_send_with_channel_override(self):
        """Test sending with channel override."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await channel.send("Hello!", channel="#general")

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["channel"] == "#general"

    @pytest.mark.asyncio
    async def test_send_with_blocks(self):
        """Test sending with Block Kit blocks."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        blocks = [
            SlackBlock(
                type="section",
                text={"type": "mrkdwn", "text": "Block text"},
            )
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await channel.send("Fallback", blocks=blocks)

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "blocks" in payload
            assert len(payload["blocks"]) == 1

    @pytest.mark.asyncio
    async def test_send_with_attachments(self):
        """Test sending with attachments."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        attachments = [
            SlackAttachment(
                color=SlackMessageColor.GOOD,
                title="Success",
                text="Everything worked!",
            )
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await channel.send("Fallback", attachments=attachments)

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "attachments" in payload
            assert payload["attachments"][0]["color"] == "good"

    @pytest.mark.asyncio
    async def test_send_api_error(self):
        """Test handling API error response."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_payload"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await channel.send("Hello!")

            assert result.success is False
            assert "invalid_payload" in result.error_message

    @pytest.mark.asyncio
    async def test_send_timeout(self):
        """Test handling timeout."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("Timeout")
            )

            result = await channel.send("Hello!")

            assert result.success is False
            assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_send_request_error(self):
        """Test handling request error."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection failed")
            )

            result = await channel.send("Hello!")

            assert result.success is False
            assert result.error_message is not None


class TestSlackChannelTradingAlerts:
    """Tests for SlackChannel trading alert methods."""

    @pytest.mark.asyncio
    async def test_send_trading_alert(self):
        """Test sending a trading alert."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await channel.send_trading_alert(
                alert_type="ORDER_FILLED",
                message="Order completed",
                symbol="AAPL",
                price=150.00,
                quantity=100,
            )

            assert result.success is True
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "AAPL" in payload["text"]

    @pytest.mark.asyncio
    async def test_send_order_filled_buy(self):
        """Test sending order filled notification for buy."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await channel.send_order_filled(
                symbol="TSLA",
                side="buy",
                quantity=50,
                price=200.00,
            )

            assert result.success is True
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            # Check attachment color is good (green) for buy
            assert payload["attachments"][0]["color"] == "good"

    @pytest.mark.asyncio
    async def test_send_order_filled_sell(self):
        """Test sending order filled notification for sell."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await channel.send_order_filled(
                symbol="TSLA",
                side="sell",
                quantity=50,
                price=220.00,
            )

            assert result.success is True
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            # Check attachment color is warning (yellow) for sell
            assert payload["attachments"][0]["color"] == "warning"

    @pytest.mark.asyncio
    async def test_send_position_closed_profit(self):
        """Test sending position closed notification with profit."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await channel.send_position_closed(
                symbol="AAPL",
                quantity=100,
                pnl=500.00,
                pnl_percent=5.0,
            )

            assert result.success is True
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["attachments"][0]["color"] == "good"

    @pytest.mark.asyncio
    async def test_send_position_closed_loss(self):
        """Test sending position closed notification with loss."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await channel.send_position_closed(
                symbol="AAPL",
                quantity=100,
                pnl=-200.00,
            )

            assert result.success is True
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["attachments"][0]["color"] == "danger"

    @pytest.mark.asyncio
    async def test_send_price_alert(self):
        """Test sending price alert."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await channel.send_price_alert(
                symbol="NVDA",
                current_price=450.00,
                condition="above",
                threshold=440.00,
            )

            assert result.success is True
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "NVDA" in payload["text"]
            assert "above" in payload["text"]

    @pytest.mark.asyncio
    async def test_send_session_started(self):
        """Test sending session started notification."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await channel.send_session_status(
                status="started",
                strategy_name="Moving Average Crossover",
                mode="paper",
            )

            assert result.success is True
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["attachments"][0]["color"] == "good"

    @pytest.mark.asyncio
    async def test_send_session_error(self):
        """Test sending session error notification."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await channel.send_session_status(
                status="error",
                strategy_name="My Strategy",
                error="Connection lost to broker",
            )

            assert result.success is True
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["attachments"][0]["color"] == "danger"

    @pytest.mark.asyncio
    async def test_send_risk_alert(self):
        """Test sending risk alert."""
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await channel.send_risk_alert(
                alert_type="DAILY_LOSS_LIMIT",
                message="Daily loss limit exceeded. Trading paused.",
                current_value=5.5,
                limit_value=5.0,
            )

            assert result.success is True
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["attachments"][0]["color"] == "danger"
            assert len(payload["attachments"][0]["fields"]) == 2
