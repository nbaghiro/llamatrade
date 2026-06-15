"""Transport seam: the backend-neutral interface plus its Redis Streams adapter.

Swap backends by writing one more adapter (e.g. ``KafkaTransport``) that satisfies
:class:`EventTransport`; nothing above this package changes.
"""

from __future__ import annotations

from llamatrade_events.transport.base import (
    CURSOR_BEGIN,
    CURSOR_NEW,
    Cursor,
    EventTransport,
)
from llamatrade_events.transport.redis_streams import RedisStreamsTransport

__all__ = [
    "CURSOR_BEGIN",
    "CURSOR_NEW",
    "Cursor",
    "EventTransport",
    "RedisStreamsTransport",
]
