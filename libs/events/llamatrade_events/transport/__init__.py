"""Transport seam: the backend-neutral interface plus its adapters.

The backend is chosen by :func:`get_default_transport` from config; add a backend
by writing one more adapter that satisfies :class:`EventTransport`. Nothing above
this package changes.
"""

from __future__ import annotations

from llamatrade_events.transport.base import (
    CURSOR_BEGIN,
    CURSOR_NEW,
    Cursor,
    EventTransport,
    OutgoingRecord,
)
from llamatrade_events.transport.factory import get_default_transport
from llamatrade_events.transport.kafka import TRANSPORT_ERRORS, KafkaTransport

__all__ = [
    "CURSOR_BEGIN",
    "CURSOR_NEW",
    "TRANSPORT_ERRORS",
    "Cursor",
    "EventTransport",
    "KafkaTransport",
    "OutgoingRecord",
    "get_default_transport",
]
