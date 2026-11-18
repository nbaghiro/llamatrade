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

from . import _scaffold
from .client import (
    MeshClient,
    MeshError,
    find_mailpit_message,
    login,
    mailpit_available,
    mailpit_message_html,
    mailpit_message_text,
    publish_bar,
    publish_notification_event,
)

pytestmark = pytest.mark.e2e

# NotificationCategory values (events.proto)
CATEGORY_SLEEVE_FROZEN = 1
CATEGORY_PAYMENT_FAILED = 61

# AlertConditionType / ChannelType values (notification.proto)
CONDITION_PRICE_ABOVE = 1
CONDITION_PRICE_BELOW = 2
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

    def test_mark_all_clears_the_bell(self, throwaway_tenant: Callable[[str], MeshClient]) -> None:
        """The bell's "mark all read": two unread rows, one call, count back to zero."""
        client = throwaway_tenant("notif-markall")
        tenant_id = client.ctx["tenantId"]
        for n in range(2):
            publish_notification_event(
                tenant_id,
                CATEGORY_SLEEVE_FROZEN,
                reason=f"e2e markall {n}",
                dedup=f"e2e-markall-{tenant_id}-{n}",
            )

        assert _poll(
            lambda: sum(n.get("title") == "Sleeve frozen" for n in _notifications(client)) >= 2
        ), "both events never landed"
        before = client.call("notification", "ListNotifications", {"unreadOnly": True})
        assert before.get("unreadCount", 0) >= 2

        marked = client.call("notification", "MarkAsRead", {"markAll": True})
        assert marked.get("markedCount", 0) >= 2

        after = client.call("notification", "ListNotifications", {"unreadOnly": True})
        assert after.get("notifications", []) == []
        assert after.get("unreadCount", 0) == 0

    def test_mark_as_read_requires_a_target(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        """Neither an id nor markAll is a client bug, refused rather than a silent no-op."""
        client = throwaway_tenant("notif-noop")

        with pytest.raises(MeshError) as exc:
            client.call("notification", "MarkAsRead", {})
        assert "invalid_argument" in str(exc.value).lower()

    def test_redelivered_event_stays_single(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        client = throwaway_tenant("notif-dup")
        tenant_id = client.ctx["tenantId"]

        def frozen_rows() -> list[dict[str, object]]:
            return [n for n in _notifications(client) if n.get("title") == "Sleeve frozen"]

        # Two identical events, then a marker on a different category. The
        # tenant key routes all three to one partition, so the marker's row
        # proves both duplicates were consumed — no fixed sleep needed.
        for _ in range(2):
            publish_notification_event(
                tenant_id, CATEGORY_SLEEVE_FROZEN, reason="dup", dedup="same-episode"
            )
        publish_notification_event(
            tenant_id, CATEGORY_PAYMENT_FAILED, reason="marker", dedup="flush-marker"
        )
        assert _poll(
            lambda: any(n.get("title") == "Payment failed" for n in _notifications(client))
        ), "the marker event never surfaced; the consumer is not draining this tenant"
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
        assert _poll(
            lambda: find_mailpit_message(email, "Payment failed") is not None, timeout=30.0
        ), "no payment-failed email captured by mailpit"


@pytest.mark.skipif(not mailpit_available(), reason="mailpit not running")
class TestPasswordResetFlow:
    def test_full_round_trip(self, throwaway_tenant: Callable[[str], MeshClient]) -> None:
        client = throwaway_tenant("reset")
        email = client.call("auth", "GetCurrentUser", {})["user"]["email"]

        anon = MeshClient()
        response = anon.call("auth", "RequestPasswordReset", {"email": email}, context=False)
        assert response["success"] is True

        assert _poll(
            lambda: find_mailpit_message(email, "Reset your password") is not None, timeout=30.0
        ), "reset email never arrived"
        message = find_mailpit_message(email, "Reset your password")
        assert message is not None
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

    def test_price_below_condition_fires(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        client = throwaway_tenant("alert-below")
        client.call(
            "notification",
            "CreateAlert",
            {
                "name": "e2e floor watch",
                "condition": {
                    "type": CONDITION_PRICE_BELOW,
                    "symbol": "E2EBLW",
                    "threshold": {"value": "100"},
                },
                "cooldownMinutes": 60,
            },
        )

        def _triggered() -> bool:
            publish_bar("E2EBLW", "5")
            return any(n.get("title") == "Price alert triggered" for n in _notifications(client))

        assert _poll(_triggered, timeout=60.0, interval=3.0), "PRICE_BELOW alert never fired"
        row = next(n for n in _notifications(client) if n["title"] == "Price alert triggered")
        assert "e2e floor watch" in row["message"]

    def test_toggle_cooldown_and_delete_lifecycle(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        """One journey over two alerts on the same symbol.

        A stays active and fires exactly once (cooldown 60m suppresses every
        later bar). B is toggled OFF before any bar, stays silent while A
        fires (proof the bars were evaluated), then is toggled ON and fires —
        B's row doubles as the flush marker showing post-trigger bars were
        evaluated while A stayed suppressed. Ends with DeleteAlert for both.
        """
        client = throwaway_tenant("alert-tgl")
        symbol = "E2ETGL"

        def _create(name: str) -> dict[str, object]:
            return client.call(
                "notification",
                "CreateAlert",
                {
                    "name": name,
                    "condition": {
                        "type": CONDITION_PRICE_ABOVE,
                        "symbol": symbol,
                        "threshold": {"value": "10"},
                    },
                    "cooldownMinutes": 60,
                },
            )["alert"]

        alert_a = _create("e2e-tgl-armed")
        alert_b = _create("e2e-tgl-muted")

        toggled = client.call(
            "notification", "ToggleAlert", {"alertId": alert_b["id"], "isActive": False}
        )
        assert toggled["alert"].get("isActive", False) is False

        def _rows_for(name: str) -> list[dict[str, object]]:
            return [
                n
                for n in _notifications(client)
                if n.get("title") == "Price alert triggered" and name in str(n.get("message"))
            ]

        def _a_fired() -> bool:
            publish_bar(symbol, "500")
            return len(_rows_for("e2e-tgl-armed")) >= 1

        assert _poll(_a_fired, timeout=60.0, interval=3.0), "active alert never fired"
        # The bars that fired A were evaluated against B too; disabled means silent.
        assert _rows_for("e2e-tgl-muted") == [], "a toggled-off alert must not fire"

        toggled_on = client.call(
            "notification", "ToggleAlert", {"alertId": alert_b["id"], "isActive": True}
        )
        assert toggled_on["alert"].get("isActive") is True

        def _b_fired() -> bool:
            publish_bar(symbol, "500")
            return len(_rows_for("e2e-tgl-muted")) >= 1

        # B re-enters the watch set on the next 30s sweep, then fires.
        assert _poll(_b_fired, timeout=90.0, interval=3.0), "re-enabled alert never fired"

        # Cooldown: every bar since A's trigger (including all that fired B)
        # was suppressed for A — exactly one row, one recorded trigger.
        assert len(_rows_for("e2e-tgl-armed")) == 1, "cooldown must suppress repeat triggers"
        listed = client.call("notification", "ListAlerts", {}).get("alerts", [])
        row_a = next(a for a in listed if a["id"] == alert_a["id"])
        assert int(row_a.get("timesTriggered", 0)) == 1

        for alert_id in (alert_a["id"], alert_b["id"]):
            deleted = client.call("notification", "DeleteAlert", {"alertId": alert_id})
            assert deleted.get("success") is True
        assert client.call("notification", "ListAlerts", {}).get("alerts", []) == []

    @pytest.mark.slow
    def test_cooldown_expiry_re_arms_the_alert(
        self, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        """The other half of the cooldown contract: it must end, not mute forever.

        Every other cooldown assertion in this suite proves suppression, which a
        permanently broken alert would also satisfy. One minute is the shortest
        cooldown the API accepts (0 falls back to the 60-minute default), so this
        spends that minute and is opt-in behind E2E_SLOW.
        """
        client = throwaway_tenant("alert-cool")
        symbol = "E2ECOOL"
        created = client.call(
            "notification",
            "CreateAlert",
            {
                "name": "e2e-cooldown-expiry",
                "condition": {
                    "type": CONDITION_PRICE_ABOVE,
                    "symbol": symbol,
                    "threshold": {"value": "10"},
                },
                "cooldownMinutes": 1,
            },
        )["alert"]

        def _rows() -> list[dict[str, object]]:
            return [
                n
                for n in _notifications(client)
                if n.get("title") == "Price alert triggered"
                and "e2e-cooldown-expiry" in str(n.get("message"))
            ]

        def _fired_once() -> bool:
            publish_bar(symbol, "500")
            return len(_rows()) >= 1

        assert _poll(_fired_once, timeout=60.0, interval=3.0), "alert never fired the first time"

        # Inside the window, further bars stay suppressed.
        for _ in range(3):
            publish_bar(symbol, "500")
            time.sleep(1)
        assert len(_rows()) == 1, "a bar inside the cooldown window must not re-fire"

        # Past the window, the same bar must fire again.
        time.sleep(60)

        def _fired_again() -> bool:
            publish_bar(symbol, "500")
            return len(_rows()) >= 2

        assert _poll(_fired_again, timeout=90.0, interval=3.0), (
            "the alert never re-armed after its cooldown expired"
        )

        listed = client.call("notification", "ListAlerts", {}).get("alerts", [])
        row = next(a for a in listed if a["id"] == created["id"])
        assert int(row.get("timesTriggered", 0)) >= 2


class TestProducerEmissions:
    def test_execution_start_emits_the_strategy_deployed_row(
        self, demo: MeshClient, throwaway_tenant: Callable[[str], MeshClient]
    ) -> None:
        """A REAL producer (the strategy service) emits EXECUTION_STARTED end to
        end — no topic injection: StartExecution publishes to Kafka and the
        notification pipeline lands the in-app row."""
        client = throwaway_tenant("notif-producer")
        funded = _scaffold.fund_tenant_execution(client, demo, "E2E deploy notification")
        try:

            def _deployed() -> dict[str, object] | None:
                return next(
                    (n for n in _notifications(client) if n.get("title") == "Strategy deployed"),
                    None,
                )

            assert _poll(lambda: _deployed() is not None, timeout=30.0), (
                "EXECUTION_STARTED never surfaced as an in-app row"
            )
            row = _deployed()
            assert row is not None
            assert row.get("message") == "Your strategy is funded and running."
            metadata = row.get("metadata", {})
            assert isinstance(metadata, dict)
            assert metadata.get("execution_id") == funded.execution_id
            assert metadata.get("strategy_id") == funded.strategy_id
            assert metadata.get("category") == "40"
        finally:
            client.try_call(
                "strategy",
                "StopExecution",
                {"executionId": funded.execution_id, "reason": "e2e cleanup"},
            )
            client.try_call(
                "auth", "DeleteAlpacaCredentials", {"credentialsId": funded.credentials_id}
            )
