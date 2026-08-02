"""Transport construction — the single place a service's event backend is made.

Kafka is the sole backend: :func:`get_default_transport` builds a
:class:`KafkaTransport`. Every layer above (bus, catalog, consumer, fan-out) is
backend-neutral, so a future swap is one adapter away.
"""

from __future__ import annotations

from llamatrade_events.transport.base import EventTransport
from llamatrade_events.transport.kafka import KafkaTransport


def get_default_transport() -> EventTransport:
    """Construct the event transport (Kafka)."""
    return KafkaTransport()
