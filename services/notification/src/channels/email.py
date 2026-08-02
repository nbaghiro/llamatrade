"""Email notification channel — SMTP via aiosmtplib.

STARTTLS + login run only when credentials are configured, so the mailpit
dev/CI catcher (plain SMTP, no auth) and a real provider share one code path.
An unconfigured host means email is off: send() reports failure rather than
pretending delivery happened.
"""

from __future__ import annotations

import logging
import os
import time
from email.message import EmailMessage

import aiosmtplib

from llamatrade_telemetry import metrics
from llamatrade_telemetry.instrumentation.dependency import time_dependency

logger = logging.getLogger(__name__)

_CHANNEL = "email"
_TIMEOUT = 10.0


class EmailChannel:
    """Email sender over SMTP."""

    def __init__(self) -> None:
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@llamatrade.com")

    @property
    def is_configured(self) -> bool:
        return bool(self.smtp_host)

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> bool:
        if not self.is_configured:
            metrics.notification.delivery_failed(channel=_CHANNEL, reason="not_configured")
            return False

        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        start = time.perf_counter()
        try:
            with time_dependency("smtp", "send"):
                await aiosmtplib.send(
                    message,
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    username=self.smtp_user or None,
                    password=self.smtp_password or None,
                    start_tls=bool(self.smtp_user) or None,
                    timeout=_TIMEOUT,
                )
        except (aiosmtplib.SMTPException, OSError) as e:
            logger.warning("email delivery to %s failed: %s", to, e)
            metrics.notification.delivery_failed(channel=_CHANNEL, reason=type(e).__name__)
            return False
        finally:
            metrics.notification.delivery_latency.labels(channel=_CHANNEL).observe(
                time.perf_counter() - start
            )
        metrics.notification.delivered(channel=_CHANNEL)
        return True
