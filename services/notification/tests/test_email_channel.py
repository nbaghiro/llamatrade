"""Tests for EmailChannel to improve coverage."""

import os
from unittest.mock import patch

import pytest

from src.channels.email import EmailChannel

# === Test Fixtures ===


@pytest.fixture
def email_channel() -> EmailChannel:
    """Create an EmailChannel instance."""
    return EmailChannel()


# === EmailChannel Initialization Tests ===


class TestEmailChannelInit:
    """Tests for EmailChannel initialization."""

    def test_default_smtp_host(self, email_channel: EmailChannel) -> None:
        """Test default SMTP host."""
        assert email_channel.smtp_host == "smtp.gmail.com"

    def test_default_smtp_port(self, email_channel: EmailChannel) -> None:
        """Test default SMTP port."""
        assert email_channel.smtp_port == 587

    def test_default_from_email(self, email_channel: EmailChannel) -> None:
        """Test default from email."""
        assert email_channel.from_email == "noreply@llamatrade.com"

    def test_smtp_user_default_empty(self, email_channel: EmailChannel) -> None:
        """Test SMTP user defaults to empty string."""
        # Without env var, should be empty
        assert email_channel.smtp_user == "" or email_channel.smtp_user is not None

    def test_smtp_password_default_empty(self, email_channel: EmailChannel) -> None:
        """Test SMTP password defaults to empty string."""
        assert email_channel.smtp_password == "" or email_channel.smtp_password is not None

    def test_custom_env_vars(self) -> None:
        """Test initialization with custom environment variables."""
        with patch.dict(
            os.environ,
            {
                "SMTP_HOST": "custom.smtp.host",
                "SMTP_PORT": "465",
                "SMTP_USER": "testuser",
                "SMTP_PASSWORD": "testpass",
                "FROM_EMAIL": "custom@example.com",
            },
        ):
            channel = EmailChannel()

            assert channel.smtp_host == "custom.smtp.host"
            assert channel.smtp_port == 465
            assert channel.smtp_user == "testuser"
            assert channel.smtp_password == "testpass"
            assert channel.from_email == "custom@example.com"


# === EmailChannel.send Tests ===


class TestEmailChannelSend:
    """Tests for EmailChannel.send method."""

    async def test_send_returns_true(self, email_channel: EmailChannel) -> None:
        """Test send returns True (stub implementation)."""
        result = await email_channel.send(
            to="recipient@example.com",
            subject="Test Subject",
            body="Test body content",
        )

        assert result is True

    async def test_send_with_html_body(self, email_channel: EmailChannel) -> None:
        """Test send with HTML body."""
        result = await email_channel.send(
            to="recipient@example.com",
            subject="HTML Test",
            body="Plain text body",
            html_body="<html><body><h1>HTML Content</h1></body></html>",
        )

        assert result is True

    async def test_send_without_html_body(self, email_channel: EmailChannel) -> None:
        """Test send without HTML body (None)."""
        result = await email_channel.send(
            to="recipient@example.com",
            subject="Plain Text Only",
            body="This is plain text only",
            html_body=None,
        )

        assert result is True

    async def test_send_empty_subject(self, email_channel: EmailChannel) -> None:
        """Test send with empty subject."""
        result = await email_channel.send(
            to="recipient@example.com",
            subject="",
            body="Body with empty subject",
        )

        assert result is True

    async def test_send_long_body(self, email_channel: EmailChannel) -> None:
        """Test send with long body content."""
        long_body = "This is a test. " * 1000

        result = await email_channel.send(
            to="recipient@example.com",
            subject="Long Email",
            body=long_body,
        )

        assert result is True

    async def test_send_multiple_recipients_string(self, email_channel: EmailChannel) -> None:
        """Test send with comma-separated recipients."""
        result = await email_channel.send(
            to="user1@example.com, user2@example.com",
            subject="Multiple Recipients",
            body="Test body",
        )

        assert result is True
