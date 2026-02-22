"""Email notification channel."""

import os


class EmailChannel:
    """Email notification sender."""

    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@llamatrade.com")

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> bool:
        """Send an email notification."""
        # In production, use aiosmtplib or similar
        # import aiosmtplib
        # async with aiosmtplib.SMTP(self.smtp_host, self.smtp_port) as smtp:
        #     await smtp.starttls()
        #     await smtp.login(self.smtp_user, self.smtp_password)
        #     await smtp.send_message(message)
        return True
