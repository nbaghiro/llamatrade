"""Slack notification channel using incoming webhooks."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

import httpx

logger = logging.getLogger(__name__)


class SlackMessageColor(StrEnum):
    """Colors for Slack message attachments."""

    GOOD = "good"  # Green
    WARNING = "warning"  # Yellow
    DANGER = "danger"  # Red
    INFO = "#2196F3"  # Blue


@dataclass
class SlackBlock:
    """A Slack Block Kit block."""

    type: str
    text: dict | None = None
    elements: list[dict] | None = None
    fields: list[dict] | None = None

    def to_dict(self) -> dict:
        """Convert to Slack API format."""
        result: dict = {"type": self.type}
        if self.text:
            result["text"] = self.text
        if self.elements:
            result["elements"] = self.elements
        if self.fields:
            result["fields"] = self.fields
        return result


@dataclass
class SlackAttachment:
    """A Slack message attachment for rich formatting."""

    color: str = SlackMessageColor.INFO
    title: str | None = None
    text: str | None = None
    fields: list[dict] = field(default_factory=list)
    footer: str | None = None
    ts: int | None = None

    def to_dict(self) -> dict:
        """Convert to Slack API format."""
        result: dict = {"color": self.color}
        if self.title:
            result["title"] = self.title
        if self.text:
            result["text"] = self.text
        if self.fields:
            result["fields"] = self.fields
        if self.footer:
            result["footer"] = self.footer
        if self.ts:
            result["ts"] = self.ts
        return result


@dataclass
class SlackResult:
    """Result of a Slack send operation."""

    success: bool
    error_message: str | None = None


class SlackChannel:
    """Slack notification sender using incoming webhooks.

    Sends messages to Slack via incoming webhook URLs. Supports:
    - Plain text messages
    - Rich formatting with Block Kit
    - Attachments with colors
    - Channel overrides

    Usage:
        channel = SlackChannel(webhook_url="https://hooks.slack.com/services/...")

        # Simple message
        result = await channel.send("Hello from LlamaTrade!")

        # Rich trading alert
        result = await channel.send_trading_alert(
            alert_type="ORDER_FILLED",
            symbol="AAPL",
            message="Bought 100 shares at $150.00",
            color=SlackMessageColor.GOOD,
        )
    """

    def __init__(
        self,
        webhook_url: str,
        default_channel: str | None = None,
        default_username: str = "LlamaTrade",
        default_icon_emoji: str = ":chart_with_upwards_trend:",
    ) -> None:
        """Initialize the Slack channel.

        Args:
            webhook_url: Slack incoming webhook URL.
            default_channel: Optional default channel override (e.g., "#trading-alerts").
            default_username: Bot username shown in Slack.
            default_icon_emoji: Bot icon emoji.
        """
        self.webhook_url = webhook_url
        self.default_channel = default_channel
        self.default_username = default_username
        self.default_icon_emoji = default_icon_emoji

    async def send(
        self,
        text: str,
        channel: str | None = None,
        blocks: list[SlackBlock] | None = None,
        attachments: list[SlackAttachment] | None = None,
        username: str | None = None,
        icon_emoji: str | None = None,
    ) -> SlackResult:
        """Send a message to Slack.

        Args:
            text: The message text (used as fallback for notifications).
            channel: Optional channel override.
            blocks: Optional Block Kit blocks for rich formatting.
            attachments: Optional attachments with colors/fields.
            username: Optional username override.
            icon_emoji: Optional icon emoji override.

        Returns:
            SlackResult with success status.
        """
        payload: dict = {
            "text": text,
            "username": username or self.default_username,
            "icon_emoji": icon_emoji or self.default_icon_emoji,
        }

        # Add channel if specified
        target_channel = channel or self.default_channel
        if target_channel:
            payload["channel"] = target_channel

        # Add blocks for rich formatting
        if blocks:
            payload["blocks"] = [b.to_dict() for b in blocks]

        # Add attachments
        if attachments:
            payload["attachments"] = [a.to_dict() for a in attachments]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=30.0,
                )

                if response.status_code == 200 and response.text == "ok":
                    logger.info("Slack message sent successfully")
                    return SlackResult(success=True)

                # Handle error
                error_msg = response.text or f"HTTP {response.status_code}"
                logger.error(f"Slack API error: {error_msg}")
                return SlackResult(success=False, error_message=error_msg)

        except httpx.TimeoutException:
            logger.error("Slack API timeout")
            return SlackResult(success=False, error_message="Request timed out")
        except httpx.RequestError as e:
            logger.error(f"Slack API request error: {e}")
            return SlackResult(success=False, error_message=str(e))
        except Exception as e:
            logger.error(f"Unexpected error sending to Slack: {e}")
            return SlackResult(success=False, error_message=str(e))

    async def send_trading_alert(
        self,
        alert_type: str,
        message: str,
        symbol: str | None = None,
        price: float | None = None,
        quantity: float | None = None,
        pnl: float | None = None,
        color: str = SlackMessageColor.INFO,
        channel: str | None = None,
    ) -> SlackResult:
        """Send a formatted trading alert.

        Args:
            alert_type: Type of alert (e.g., "ORDER_FILLED", "PRICE_ALERT").
            message: Main alert message.
            symbol: Trading symbol.
            price: Price value.
            quantity: Quantity value.
            pnl: Profit/loss value.
            color: Attachment color.
            channel: Optional channel override.

        Returns:
            SlackResult with success status.
        """
        # Build fields for the attachment
        fields: list[dict] = []

        if symbol:
            fields.append(
                {
                    "title": "Symbol",
                    "value": symbol,
                    "short": True,
                }
            )

        if price is not None:
            fields.append(
                {
                    "title": "Price",
                    "value": f"${price:,.2f}",
                    "short": True,
                }
            )

        if quantity is not None:
            fields.append(
                {
                    "title": "Quantity",
                    "value": f"{quantity:,.0f}",
                    "short": True,
                }
            )

        if pnl is not None:
            pnl_str = f"${pnl:+,.2f}" if pnl != 0 else "$0.00"
            fields.append(
                {
                    "title": "P&L",
                    "value": pnl_str,
                    "short": True,
                }
            )

        attachment = SlackAttachment(
            color=color,
            title=f":bell: {alert_type}",
            text=message,
            fields=fields,
            footer="LlamaTrade",
            ts=int(datetime.now(UTC).timestamp()),
        )

        fallback_text = f"{alert_type}: {message}"
        if symbol:
            fallback_text = f"{alert_type} - {symbol}: {message}"

        return await self.send(
            text=fallback_text,
            attachments=[attachment],
            channel=channel,
        )

    async def send_order_filled(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        channel: str | None = None,
    ) -> SlackResult:
        """Send an order filled notification.

        Args:
            symbol: Trading symbol.
            side: Order side ("buy" or "sell").
            quantity: Filled quantity.
            price: Fill price.
            channel: Optional channel override.

        Returns:
            SlackResult with success status.
        """
        is_buy = side.lower() == "buy"
        emoji = ":chart_with_upwards_trend:" if is_buy else ":chart_with_downwards_trend:"
        color = SlackMessageColor.GOOD if is_buy else SlackMessageColor.WARNING

        message = f"{emoji} {side.upper()} {quantity:,.0f} {symbol} @ ${price:,.2f}"

        return await self.send_trading_alert(
            alert_type="ORDER_FILLED",
            message=message,
            symbol=symbol,
            price=price,
            quantity=quantity,
            color=color,
            channel=channel,
        )

    async def send_position_closed(
        self,
        symbol: str,
        quantity: float,
        pnl: float,
        pnl_percent: float | None = None,
        channel: str | None = None,
    ) -> SlackResult:
        """Send a position closed notification.

        Args:
            symbol: Trading symbol.
            quantity: Position size.
            pnl: Realized P&L.
            pnl_percent: P&L percentage.
            channel: Optional channel override.

        Returns:
            SlackResult with success status.
        """
        if pnl >= 0:
            emoji = ":moneybag:"
            color = SlackMessageColor.GOOD
        else:
            emoji = ":money_with_wings:"
            color = SlackMessageColor.DANGER

        pnl_str = f"${pnl:+,.2f}"
        if pnl_percent is not None:
            pnl_str += f" ({pnl_percent:+.2f}%)"

        message = f"{emoji} Closed {quantity:,.0f} {symbol} | P&L: {pnl_str}"

        return await self.send_trading_alert(
            alert_type="POSITION_CLOSED",
            message=message,
            symbol=symbol,
            quantity=quantity,
            pnl=pnl,
            color=color,
            channel=channel,
        )

    async def send_price_alert(
        self,
        symbol: str,
        current_price: float,
        condition: str,
        threshold: float,
        channel: str | None = None,
    ) -> SlackResult:
        """Send a price alert notification.

        Args:
            symbol: Trading symbol.
            current_price: Current price.
            condition: Alert condition ("above" or "below").
            threshold: Price threshold.
            channel: Optional channel override.

        Returns:
            SlackResult with success status.
        """
        emoji = ":arrow_up:" if condition == "above" else ":arrow_down:"
        message = f"{emoji} {symbol} is now ${current_price:,.2f} ({condition} ${threshold:,.2f})"

        return await self.send_trading_alert(
            alert_type="PRICE_ALERT",
            message=message,
            symbol=symbol,
            price=current_price,
            color=SlackMessageColor.WARNING,
            channel=channel,
        )

    async def send_session_status(
        self,
        status: str,
        strategy_name: str,
        mode: str = "paper",
        error: str | None = None,
        channel: str | None = None,
    ) -> SlackResult:
        """Send a trading session status notification.

        Args:
            status: Session status ("started", "stopped", "error").
            strategy_name: Name of the strategy.
            mode: Trading mode ("live" or "paper").
            error: Error message if status is "error".
            channel: Optional channel override.

        Returns:
            SlackResult with success status.
        """
        if status == "started":
            emoji = ":rocket:"
            color = SlackMessageColor.GOOD
            message = f"{emoji} Trading session started: {strategy_name} ({mode} mode)"
        elif status == "stopped":
            emoji = ":stop_sign:"
            color = SlackMessageColor.WARNING
            message = f"{emoji} Trading session stopped: {strategy_name}"
        else:  # error
            emoji = ":x:"
            color = SlackMessageColor.DANGER
            message = f"{emoji} Trading session error: {strategy_name}"
            if error:
                message += f"\nError: {error}"

        return await self.send_trading_alert(
            alert_type=f"SESSION_{status.upper()}",
            message=message,
            color=color,
            channel=channel,
        )

    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        current_value: float | None = None,
        limit_value: float | None = None,
        channel: str | None = None,
    ) -> SlackResult:
        """Send a risk management alert.

        Args:
            alert_type: Type of risk alert (e.g., "DAILY_LOSS_LIMIT", "DRAWDOWN_LIMIT").
            message: Alert message.
            current_value: Current value that triggered the alert.
            limit_value: Limit that was breached.
            channel: Optional channel override.

        Returns:
            SlackResult with success status.
        """
        fields: list[dict] = []

        if current_value is not None:
            fields.append(
                {
                    "title": "Current",
                    "value": f"{current_value:.2f}%",
                    "short": True,
                }
            )

        if limit_value is not None:
            fields.append(
                {
                    "title": "Limit",
                    "value": f"{limit_value:.2f}%",
                    "short": True,
                }
            )

        attachment = SlackAttachment(
            color=SlackMessageColor.DANGER,
            title=f":warning: {alert_type}",
            text=message,
            fields=fields,
            footer="LlamaTrade Risk Management",
            ts=int(datetime.now(UTC).timestamp()),
        )

        return await self.send(
            text=f"Risk Alert: {message}",
            attachments=[attachment],
            channel=channel,
        )
