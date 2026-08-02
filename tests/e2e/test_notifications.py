"""Notification flows over the live mesh: the durable floor, channels, alerts.

The producer seam is the real Kafka topic (publish_notification_event), so
the durable consumer, persistence, preference resolution, and delivery run
exactly as in production. Email assertions go through the mailpit catcher and
skip when it is not part of the stack.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from .client import (
    MeshClient,
    MeshError,
    login,
    mailpit_available,
    mailpit_message_html,
    mailpit_message_text,
    mailpit_messages,
    publish_bar,
    publish_notification_event,
)

pytestmark = pytest.mark.e2e

# NotificationCategory values (events.proto)
CATEGORY_SLEEVE_FROZEN = 1
CATEGORY_PAYMENT_FAILED = 61

# AlertConditionType / ChannelType values (notification.proto)
CONDITION_PRICE_ABOVE = 1
CHANNEL_EMAIL = 1


def _poll(check: Callable[[], bool], *, timeout: float = 30.0, interval: float = 1.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(interval)
    return False


def _notifications(client: MeshClient, **body: object) -> list[dict[str, object]]:
    response = client.call("notification", "ListNotifications", dict(body))
    items = response.get("notifications", [])
    return items if isinstance(items, list) else []


class TestInAppFlow:
    def test_event_becomes_inbox_row_and_reads(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        client = throwaway_tenant("notif")
        tenant_id = client.ctx["tenantId"]
        publish_notification_event(
            tenant_id,
            CATEGORY_SLEEVE_FROZEN,
            reason="e2e drift",
            dedup=f"e2e-{tenant_id}",
        )

        assert _poll(
            lambda: any(n.get("title") == "Sleeve frozen" for n in _notifications(client))
        ), "published event never surfaced in ListNotifications"

        listed = client.call("notification", "ListNotifications", {"unreadOnly": True})
        row = next(n for n in listed["notifications"] if n["title"] == "Sleeve frozen")
        assert listed.get("unreadCount", 0) >= 1
        assert "e2e drift" in row["message"]

        marked = client.call("notification", "MarkAsRead", {"notificationId": row["id"]})
        assert marked.get("markedCount") == 1
        after = client.call("notification", "ListNotifications", {"unreadOnly": True})
        assert all(n["id"] != row["id"] for n in after.get("notifications", []))

    def test_redelivered_event_stays_single(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        client = throwaway_tenant("notif-dup")
        tenant_id = client.ctx["tenantId"]

        def frozen_rows() -> list[dict[str, object]]:
            return [n for n in _notifications(client) if n.get("title") == "Sleeve frozen"]

        for _ in range(2):
            publish_notification_event(
                tenant_id, CATEGORY_SLEEVE_FROZEN, reason="dup", dedup="same-episode"
            )
        assert _poll(lambda: len(frozen_rows()) >= 1)
        time.sleep(3)
        assert len(frozen_rows()) == 1


class TestWebhookSurface:
    def test_crud_cycle_and_one_time_secret(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        client = throwaway_tenant("hook")
        created = client.call(
            "notification",
            "CreateWebhook",
            {"name": "e2e", "url": "https://example.invalid/hook"},
        )
        assert created["secret"]
        webhook = created["webhook"]
        assert webhook["isActive"] is True

        listed = client.call("notification", "ListWebhooks", {})
        assert [w["id"] for w in listed["webhooks"]] == [webhook["id"]]
        # The secret is never returned on reads.
        assert "secret" not in listed["webhooks"][0]

        updated = client.call(
            "notification",
            "UpdateWebhook",
            {
                "webhookId": webhook["id"],
                "name": "e2e-off",
                "url": webhook["url"],
                "isActive": False,
            },
        )
        assert updated["webhook"].get("isActive", False) is False

        deleted = client.call("notification", "DeleteWebhook", {"webhookId": webhook["id"]})
        assert deleted["success"] is True

    def test_bad_url_rejected(self, throwaway_tenant: Callable[[str], MeshClient]) -> None:
        client = throwaway_tenant("hook-bad")
        with pytest.raises(MeshError) as exc:
            client.call("notification", "CreateWebhook", {"name": "x", "url": "ftp://nope"})
        assert exc.value.code == "invalid_argument"


class TestPreferences:
    def test_matrix_round_trip(self, throwaway_tenant: Callable[[str], MeshClient]) -> None:
        client = throwaway_tenant("prefs")
        initial = client.call("notification", "GetPreferences", {})
        assert {p["channel"] for p in initial["preferences"]} >= {"CHANNEL_TYPE_EMAIL"} or len(
            initial["preferences"]
        ) == 2

        updated = client.call(
            "notification",
            "UpdatePreferences",
            {
                "preferences": [
                    {
                        "channel": CHANNEL_EMAIL,
                        "enabled": True,
                        "categories": [CATEGORY_PAYMENT_FAILED],
                    }
                ]
            },
        )
        email_pref = next(
            p
            for p in updated["preferences"]
            if p["channel"] in (CHANNEL_EMAIL, "CHANNEL_TYPE_EMAIL")
        )
        assert email_pref["categories"] in (
            [CATEGORY_PAYMENT_FAILED],
            ["NOTIFICATION_CATEGORY_PAYMENT_FAILED"],
        )


@pytest.mark.skipif(not mailpit_available(), reason="mailpit not running")
class TestEmailDelivery:
    def test_critical_event_lands_in_mailpit(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        client = throwaway_tenant("mail")
        tenant_id = client.ctx["tenantId"]
        email = client.call("auth", "GetCurrentUser", {})["user"]["email"]
        publish_notification_event(
            tenant_id, CATEGORY_PAYMENT_FAILED, reason="e2e invoice", dedup="pay-1"
        )
        assert _poll(lambda: len(mailpit_messages(f"to:{email}")) >= 1, timeout=30.0), (
            "no email captured by mailpit"
        )
        message = mailpit_messages(f"to:{email}")[0]
        assert "Payment failed" in str(message.get("Subject", ""))


@pytest.mark.skipif(not mailpit_available(), reason="mailpit not running")
class TestPasswordResetFlow:
    def test_full_round_trip(self, throwaway_tenant: Callable[[str], MeshClient]) -> None:
        client = throwaway_tenant("reset")
        email = client.call("auth", "GetCurrentUser", {})["user"]["email"]

        anon = MeshClient()
        response = anon.call("auth", "RequestPasswordReset", {"email": email}, context=False)
        assert response["success"] is True

        def _find_reset() -> bool:
            for msg in mailpit_messages(f"to:{email}"):
                if "Reset your password" in str(msg.get("Subject", "")):
                    return True
            return False

        assert _poll(_find_reset, timeout=30.0), "reset email never arrived"
        message = next(
            m
            for m in mailpit_messages(f"to:{email}")
            if "Reset your password" in str(m.get("Subject", ""))
        )
        message_id = str(message.get("ID", ""))
        text = mailpit_message_text(message_id)
        token = text.split("token=")[1].split()[0].strip()

        # Design + delivery together: the captured HTML carries the transactional
        # shell (rendered title copy and the hosted brand logo <img>).
        html = mailpit_message_html(message_id)
        assert "Reset your password" in html
        assert "<img" in html and "logo-monolith.png" in html

        new_password = "e2e-NewPassw0rd!"
        reset = anon.call(
            "auth",
            "ResetPassword",
            {"token": token, "newPassword": new_password},
            context=False,
        )
        assert reset["success"] is True

        # Token is single-use.
        with pytest.raises(MeshError):
            anon.call(
                "auth",
                "ResetPassword",
                {"token": token, "newPassword": "e2e-Another1!"},
                context=False,
            )

        relogged = login(email, new_password)
        assert relogged.ctx["tenantId"] == client.ctx["tenantId"]

        # A nonexistent email gets the identical uniform answer.
        uniform = anon.call(
            "auth",
            "RequestPasswordReset",
            {"email": "nobody@e2e.llamatrade.test"},
            context=False,
        )
        assert uniform == response


class TestPriceAlerts:
    def test_alert_triggers_from_live_bar(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        client = throwaway_tenant("alert")
        created = client.call(
            "notification",
            "CreateAlert",
            {
                "name": "e2e price watch",
                "condition": {
                    "type": CONDITION_PRICE_ABOVE,
                    "symbol": "E2EALRT",
                    "threshold": {"value": "10"},
                },
                "cooldownMinutes": 60,
            },
        )
        assert created["alert"]["isActive"] is True

        def _triggered() -> bool:
            publish_bar("E2EALRT", "500")
            return any(n.get("title") == "Price alert triggered" for n in _notifications(client))

        # The market loop refreshes its symbol set every 30s; keep feeding bars.
        assert _poll(_triggered, timeout=60.0, interval=3.0), (
            "price alert never fired (is the notification market loop running?)"
        )
        row = next(n for n in _notifications(client) if n["title"] == "Price alert triggered")
        assert "e2e price watch" in row["message"]
