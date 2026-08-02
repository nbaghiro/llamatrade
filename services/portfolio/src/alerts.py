"""Ledger incident alerts — published onto the notification stream.

A thin producer over ``NotificationEvents``: the notification service owns
delivery (in-app row, email, webhooks). Dispatch is best-effort: every failure
is logged and swallowed — an alerting outage must never break a ledger
operation. Deterministic ids collapse re-reports of the same incident (a
sleeve freeze re-detected on every pass, a quarantined fill redelivered).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from llamatrade_events.catalog.notifications import (
    NotificationEvent,
    NotificationEvents,
    shared_notification_events,
)
from llamatrade_proto.generated import events_pb2

logger = logging.getLogger(__name__)

_E = events_pb2

IncidentKind = Literal[
    "sleeve_frozen",
    "fill_quarantined",
    "dlq_backlog",
    "external_trade_adopted",
    "corporate_action_proposed",
    "corporate_action_applied",
]

_CATEGORIES: dict[IncidentKind, events_pb2.NotificationCategory.ValueType] = {
    "sleeve_frozen": _E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN,
    "fill_quarantined": _E.NOTIFICATION_CATEGORY_FILL_QUARANTINED,
    # Aggregate backlog is operator-scoped (Prometheus); kept for a future tenant-attributable backlog signal.
    "dlq_backlog": _E.NOTIFICATION_CATEGORY_FILL_QUARANTINED,
    "external_trade_adopted": _E.NOTIFICATION_CATEGORY_EXTERNAL_TRADE_ADOPTED,
    "corporate_action_proposed": _E.NOTIFICATION_CATEGORY_CORPORATE_ACTION_PROPOSED,
    "corporate_action_applied": _E.NOTIFICATION_CATEGORY_CORPORATE_ACTION_APPLIED,
}

_SEVERITIES: dict[IncidentKind, events_pb2.NotificationSeverity.ValueType] = {
    "sleeve_frozen": _E.NOTIFICATION_SEVERITY_CRITICAL,
    "fill_quarantined": _E.NOTIFICATION_SEVERITY_CRITICAL,
    "dlq_backlog": _E.NOTIFICATION_SEVERITY_CRITICAL,
    "external_trade_adopted": _E.NOTIFICATION_SEVERITY_ACTIONABLE,
    "corporate_action_proposed": _E.NOTIFICATION_SEVERITY_ACTIONABLE,
    "corporate_action_applied": _E.NOTIFICATION_SEVERITY_INFO,
}


@dataclass(frozen=True)
class LedgerIncident:
    """One alert-worthy ledger event, with bounded string context for the payload."""

    kind: IncidentKind
    message: str
    context: dict[str, str] = field(default_factory=dict)


class LedgerAlertDispatcher:
    """Publishes ledger incidents onto the notification stream (best-effort)."""

    def __init__(self, events: NotificationEvents | None = None) -> None:
        self._events = events or shared_notification_events()

    async def dispatch(self, tenant_id: UUID, incident: LedgerIncident) -> None:
        """Publish the incident. Never raises."""
        event = NotificationEvent(
            category=_CATEGORIES[incident.kind],
            severity=_SEVERITIES[incident.kind],
            sleeve_id=incident.context.get("sleeve_id", ""),
            account_id=incident.context.get("account_id", ""),
            symbol=incident.context.get("symbol", ""),
            reason=incident.message,
            extra={k: str(v) for k, v in incident.context.items()},
        )
        await self._events.publish_safe(
            event,
            tenant_id=str(tenant_id),
            dedup_parts=_dedup_parts(incident),
        )


def _dedup_parts(incident: LedgerIncident) -> tuple[str, ...]:
    parts = [incident.kind]
    for key in (
        "sleeve_id",
        "client_order_id",
        "proposal_id",
        "external_id",
        "account_id",
        "symbol",
    ):
        if value := incident.context.get(key):
            parts.append(value)
    if len(parts) == 1:
        parts.append(incident.message)
    return tuple(parts)


_dispatcher: LedgerAlertDispatcher | None = None


def get_ledger_alert_dispatcher() -> LedgerAlertDispatcher:
    """Process-wide dispatcher on the shared notification stream (lazily built)."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = LedgerAlertDispatcher()
    return _dispatcher
