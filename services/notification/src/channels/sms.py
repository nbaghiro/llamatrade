"""SMS notification channel using Twilio."""

import logging
import os
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class SMSProvider(StrEnum):
    """Supported SMS providers."""

    TWILIO = "twilio"


@dataclass
class SMSResult:
    """Result of an SMS send operation."""

    success: bool
    message_sid: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class SMSChannel:
    """SMS notification sender.

    Supports multiple providers with Twilio as the default.
    Configuration is read from environment variables:

    For Twilio:
        - TWILIO_ACCOUNT_SID: Twilio account SID
        - TWILIO_AUTH_TOKEN: Twilio auth token
        - TWILIO_PHONE_NUMBER: Twilio phone number to send from
        - SMS_PROVIDER: Set to "twilio" (default)

    Usage:
        channel = SMSChannel()
        result = await channel.send(
            to="+1234567890",
            message="Your order has been filled!",
        )
        if result.success:
            print(f"Sent: {result.message_sid}")
        else:
            print(f"Failed: {result.error_message}")
    """

    def __init__(self) -> None:
        """Initialize the SMS channel with configuration from environment."""
        self.provider = SMSProvider(os.getenv("SMS_PROVIDER", "twilio"))

        # Twilio configuration
        self.twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER", "")

    @property
    def is_configured(self) -> bool:
        """Check if the SMS channel is properly configured."""
        if self.provider == SMSProvider.TWILIO:
            return bool(
                self.twilio_account_sid and self.twilio_auth_token and self.twilio_phone_number
            )
        return False

    async def send(
        self,
        to: str,
        message: str,
        from_number: str | None = None,
    ) -> SMSResult:
        """Send an SMS notification.

        Args:
            to: Recipient phone number in E.164 format (e.g., +1234567890).
            message: The message body (max 1600 characters for Twilio).
            from_number: Optional sender phone number. Uses default if not provided.

        Returns:
            SMSResult with success status and details.
        """
        if not self.is_configured:
            logger.warning("SMS channel not configured, cannot send")
            return SMSResult(
                success=False,
                error_code="NOT_CONFIGURED",
                error_message="SMS channel is not properly configured",
            )

        # Validate phone number format
        if not to.startswith("+"):
            logger.warning(f"Invalid phone number format: {to}")
            return SMSResult(
                success=False,
                error_code="INVALID_NUMBER",
                error_message="Phone number must be in E.164 format (e.g., +1234567890)",
            )

        # Truncate message if too long
        if len(message) > 1600:
            message = message[:1597] + "..."
            logger.warning("Message truncated to 1600 characters")

        if self.provider == SMSProvider.TWILIO:
            return await self._send_twilio(to, message, from_number)

        return SMSResult(
            success=False,
            error_code="UNKNOWN_PROVIDER",
            error_message=f"Unknown SMS provider: {self.provider}",
        )

    async def _send_twilio(
        self,
        to: str,
        message: str,
        from_number: str | None = None,
    ) -> SMSResult:
        """Send SMS via Twilio API.

        Uses the Twilio REST API directly with httpx for async support.
        """
        import httpx

        sender = from_number or self.twilio_phone_number

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    auth=(self.twilio_account_sid, self.twilio_auth_token),
                    data={
                        "To": to,
                        "From": sender,
                        "Body": message,
                    },
                    timeout=30.0,
                )

                if response.status_code == 201:
                    data = response.json()
                    logger.info(f"SMS sent successfully: {data.get('sid')}")
                    return SMSResult(
                        success=True,
                        message_sid=data.get("sid"),
                    )

                # Handle error response
                error_data = response.json() if response.content else {}
                error_code = str(error_data.get("code", response.status_code))
                error_message = error_data.get("message", f"HTTP {response.status_code}")

                logger.error(f"Twilio API error: {error_code} - {error_message}")
                return SMSResult(
                    success=False,
                    error_code=error_code,
                    error_message=error_message,
                )

        except httpx.TimeoutException:
            logger.error("Twilio API timeout")
            return SMSResult(
                success=False,
                error_code="TIMEOUT",
                error_message="Request to Twilio API timed out",
            )
        except httpx.RequestError as e:
            logger.error(f"Twilio API request error: {e}")
            return SMSResult(
                success=False,
                error_code="REQUEST_ERROR",
                error_message=str(e),
            )
        except Exception as e:
            logger.error(f"Unexpected error sending SMS: {e}")
            return SMSResult(
                success=False,
                error_code="UNKNOWN_ERROR",
                error_message=str(e),
            )

    async def send_verification_code(
        self,
        to: str,
        code: str,
    ) -> SMSResult:
        """Send a verification code via SMS.

        Args:
            to: Recipient phone number in E.164 format.
            code: The verification code to send.

        Returns:
            SMSResult with success status.
        """
        message = f"Your LlamaTrade verification code is: {code}. This code expires in 10 minutes."
        return await self.send(to, message)

    async def send_alert(
        self,
        to: str,
        alert_type: str,
        symbol: str | None = None,
        message: str | None = None,
    ) -> SMSResult:
        """Send a trading alert via SMS.

        Args:
            to: Recipient phone number in E.164 format.
            alert_type: Type of alert (e.g., "ORDER_FILLED", "PRICE_ALERT").
            symbol: Optional trading symbol.
            message: Optional custom message.

        Returns:
            SMSResult with success status.
        """
        if message:
            body = f"LlamaTrade Alert: {message}"
        elif symbol:
            body = f"LlamaTrade {alert_type}: {symbol}"
        else:
            body = f"LlamaTrade Alert: {alert_type}"

        return await self.send(to, body)
