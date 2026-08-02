"""Email channel: SMTP send, auth gating, unconfigured behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiosmtplib
import pytest


@pytest.fixture
def smtp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "mail.test")
    monkeypatch.setenv("SMTP_PORT", "1025")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    monkeypatch.setenv("FROM_EMAIL", "noreply@test")


def _channel() -> object:
    from src.channels.email import EmailChannel

    return EmailChannel()


async def test_unconfigured_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    channel = _channel()
    assert not channel.is_configured
    assert await channel.send("a@b.test", "s", "b") is False


async def test_send_success(smtp_env: None) -> None:
    with patch("aiosmtplib.send", new_callable=AsyncMock) as send:
        channel = _channel()
        ok = await channel.send("user@test", "Subject", "Body")
    assert ok
    message = send.call_args.args[0]
    assert message["To"] == "user@test"
    assert message["From"] == "noreply@test"
    assert message["Subject"] == "Subject"
    assert send.call_args.kwargs["hostname"] == "mail.test"
    assert send.call_args.kwargs["port"] == 1025
    # No credentials -> no auth, no forced STARTTLS (mailpit-compatible).
    assert send.call_args.kwargs["username"] is None
    assert send.call_args.kwargs["start_tls"] is None


async def test_send_with_credentials_uses_tls(
    smtp_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASSWORD", "p")
    with patch("aiosmtplib.send", new_callable=AsyncMock) as send:
        ok = await _channel().send("user@test", "S", "B")
    assert ok
    assert send.call_args.kwargs["username"] == "u"
    assert send.call_args.kwargs["start_tls"] is True


async def test_smtp_error_reports_failure(smtp_env: None) -> None:
    with patch(
        "aiosmtplib.send",
        new_callable=AsyncMock,
        side_effect=aiosmtplib.SMTPException("boom"),
    ):
        ok = await _channel().send("user@test", "S", "B")
    assert ok is False


async def test_html_alternative_attached(smtp_env: None) -> None:
    with patch("aiosmtplib.send", new_callable=AsyncMock) as send:
        await _channel().send("user@test", "S", "plain", html_body="<b>rich</b>")
    message = send.call_args.args[0]
    assert message.get_content_type() == "multipart/alternative"
