"""E2E: outbound webhook delivery — signed POSTs to a real in-test HTTP listener.

The test runs a real HTTP server on the host and registers it via CreateWebhook,
so the notification service's delivery worker POSTs to it across the Docker
bridge. The listener is an external actor (like mailpit), not a mock: the full
pipeline — Kafka consume, persist, channel planning, HTTP dispatch, HMAC signing,
failure tracking — runs in the real service.

Reachability: with the compose mesh the services run in containers, so the
listener is addressed as ``host.docker.internal`` (Docker Desktop resolves it
natively); a host-local mesh (honcho) reaches it as ``localhost``. Override with
``E2E_WEBHOOK_CALLBACK_HOST`` when neither default applies (e.g. Linux CI needs
an ``extra_hosts: host-gateway`` mapping or the bridge gateway IP).

Auto-disable: the threshold is the service's module constant
``WEBHOOK_DISABLE_THRESHOLD = 25`` (services/notification/src/delivery.py) — not
env-tunable — so the disable test drives 25 real failed deliveries. The listener
answers 404 (a non-retried failure), keeping each delivery to a single POST.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from .client import MeshClient, publish_notification_event

pytestmark = pytest.mark.e2e

# NotificationCategory (events.proto): ORDER_REJECTED delivers to webhooks by
# default and to no other channel, so these flows stay out of mailpit.
_CATEGORY_ORDER_REJECTED = 11

# services/notification/src/delivery.py: WEBHOOK_DISABLE_THRESHOLD (module constant).
_DISABLE_THRESHOLD = 25

_CALLBACK_HOST = os.getenv("E2E_WEBHOOK_CALLBACK_HOST", "host.docker.internal")


@dataclass
class _Received:
    path: str
    body: bytes
    signature: str


@dataclass
class _Listener:
    """In-test HTTP listener: 200 on /ok, 404 on /fail; records every POST."""

    server: ThreadingHTTPServer
    thread: threading.Thread
    received: list[_Received] = field(default_factory=list)

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def url(self, path: str) -> str:
        return f"http://{_CALLBACK_HOST}:{self.port}{path}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def listener() -> Generator[_Listener]:
    received: list[_Received] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length)
            received.append(
                _Received(
                    path=self.path,
                    body=body,
                    signature=self.headers.get("X-Webhook-Signature", ""),
                )
            )
            status = 404 if self.path.startswith("/fail") else 200
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            """Silence per-request stderr logging."""

    server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    box = _Listener(server=server, thread=thread, received=received)
    yield box
    box.close()


def _poll(check: Callable[[], bool], *, timeout: float, interval: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(interval)
    return False


def test_notification_delivers_a_signed_post(
    throwaway_tenant: Callable[[str], MeshClient], listener: _Listener
) -> None:
    client = throwaway_tenant("hook-live")
    created = client.call(
        "notification",
        "CreateWebhook",
        {"name": "e2e-live", "url": listener.url("/ok")},
    )
    secret = created["secret"]
    assert secret

    reason = f"e2e delivery {int(time.time() * 1000)}"
    publish_notification_event(
        client.ctx["tenantId"],
        _CATEGORY_ORDER_REJECTED,
        symbol="E2EHOOK",
        reason=reason,
        dedup=reason,
    )

    assert _poll(lambda: len(listener.received) >= 1, timeout=60.0), (
        "no webhook delivery arrived at the in-test listener — if the mesh cannot "
        f"reach {_CALLBACK_HOST}, set E2E_WEBHOOK_CALLBACK_HOST"
    )
    hit = listener.received[0]
    assert hit.path == "/ok"

    # The signature is HMAC-SHA256 over the exact transmitted bytes.
    expected = hmac.new(secret.encode(), hit.body, hashlib.sha256).hexdigest()
    assert hit.signature == f"sha256={expected}", "X-Webhook-Signature does not verify"

    payload = json.loads(hit.body)
    assert payload["category"] == _CATEGORY_ORDER_REJECTED
    assert payload["title"] == "Order rejected"
    assert payload["message"]
    assert payload["timestamp"]


def test_failing_endpoint_disables_after_threshold_with_self_notification(
    throwaway_tenant: Callable[[str], MeshClient], listener: _Listener
) -> None:
    client = throwaway_tenant("hook-dead")
    created = client.call(
        "notification",
        "CreateWebhook",
        {"name": "e2e-dead", "url": listener.url("/fail")},
    )
    webhook_id = created["webhook"]["id"]

    # Each distinct event is one delivery -> one 404 -> one failure count.
    run = f"{int(time.time() * 1000)}"
    for i in range(_DISABLE_THRESHOLD):
        publish_notification_event(
            client.ctx["tenantId"],
            _CATEGORY_ORDER_REJECTED,
            symbol="E2EDEAD",
            reason=f"e2e fail {run}-{i}",
            dedup=f"e2e-fail-{run}-{i}",
        )

    def _disabled() -> bool:
        rows = client.call("notification", "ListWebhooks", {}).get("webhooks", [])
        row = next((w for w in rows if w.get("id") == webhook_id), None)
        return row is not None and not row.get("isActive", False)

    assert _poll(_disabled, timeout=120.0, interval=3.0), (
        f"webhook was not auto-disabled after {_DISABLE_THRESHOLD} failed deliveries "
        f"({len(listener.received)} POSTs observed)"
    )
    assert len(listener.received) >= _DISABLE_THRESHOLD

    def _notice() -> bool:
        rows = client.call("notification", "ListNotifications", {}).get("notifications", [])
        return any(r.get("title") == "Webhook disabled" for r in rows)

    assert _poll(_notice, timeout=30.0), "WEBHOOK_DISABLED self-notification never surfaced"
