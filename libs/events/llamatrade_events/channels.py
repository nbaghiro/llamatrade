"""The channel registry — every stream the system uses, defined once.

Each channel declares its key template, delivery shape, whether it carries the
full envelope or a raw payload (high-volume bars skip the envelope), and its
Kafka topic. Retention is topic config, provisioned in Terraform — not declared
here.

A logical per-entity stream (``trading:orders:{session_id}``) maps to one shared
topic keyed by the entity — ``trading.orders`` partitioned by ``session_id``.
:func:`resolve_topic` maps a resolved stream name back to
``(topic, routing_key)`` so the transport can pick the topic and, for per-entity
fan-out, filter to the one entity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Delivery(Enum):
    TAIL = "tail"  # independent fan-out (UI streams, bars)
    CONSUME = "consume"  # durable consumer group (ledger fills)


@dataclass(frozen=True)
class Channel:
    """A logical stream + its wire policy."""

    key_template: str  # e.g. "trading:orders:{session_id}" or "ledger:fills"
    kafka_topic: str  # static Kafka topic base (the transport namespaces it)
    delivery: Delivery = Delivery.TAIL
    enveloped: bool = True  # False → raw payload bytes (no EventEnvelope)

    def key(self, **params: object) -> str:
        """Resolve the concrete stream key (fills any ``{placeholder}``).

        Accepts non-str params (e.g. a ``UUID`` session id) — ``str.format``
        stringifies them, so callers needn't coerce.
        """
        return self.key_template.format(**params)


# --- Trading UI (per-session, tail fan-out) ---
ORDERS = Channel("trading:orders:{session_id}", kafka_topic="trading.orders")
POSITIONS = Channel("trading:positions:{session_id}", kafka_topic="trading.positions")

# --- Ledger fills (one global stream, durable consumer group, keyed by account) ---
LEDGER_FILLS = Channel("ledger:fills", kafka_topic="ledger.fills", delivery=Delivery.CONSUME)

# --- Backtest progress (per-backtest, short, tail-replay) ---
BACKTEST_PROGRESS = Channel("backtest:progress:{backtest_id}", kafka_topic="backtest.progress")

# --- Market data live bars (one global stream, high-volume, raw payload, keyed by symbol) ---
BARS = Channel("market:bars:1m", kafka_topic="market.bars.1m", enveloped=False)

# --- Notifications (one global stream, durable consumer group, keyed by tenant) ---
NOTIFICATIONS = Channel("notifications", kafka_topic="notifications", delivery=Delivery.CONSUME)


_CHANNELS: tuple[Channel, ...] = (
    ORDERS,
    POSITIONS,
    LEDGER_FILLS,
    BACKTEST_PROGRESS,
    BARS,
    NOTIFICATIONS,
)


def _matcher(template: str) -> re.Pattern[str]:
    """A regex for a key template, capturing the ``{placeholder}`` value (if any)."""
    escaped = re.escape(template)
    pattern = re.sub(r"\\\{[a-zA-Z_][a-zA-Z0-9_]*\\\}", "(?P<key>.+)", escaped)
    return re.compile(f"^{pattern}$")


_MATCHERS: tuple[tuple[Channel, re.Pattern[str]], ...] = tuple(
    (ch, _matcher(ch.key_template)) for ch in _CHANNELS
)


def resolve_topic(stream: str) -> tuple[str, str | None]:
    """Map a resolved logical stream name to ``(kafka_topic_base, routing_key)``.

    - Static channels (``ledger:fills``, ``market:bars:1m``) → ``(topic, None)``.
    - Per-entity channels (``trading:orders:abc``) → ``(topic, "abc")``; the routing
      key is what a per-entity fan-out tail filters on.
    - Unknown streams (e.g. a ``…:dlq`` side-topic or a test stream) fall back to a
      dotted form of the name so ad-hoc publishes still resolve to a topic.
    """
    for ch, rx in _MATCHERS:
        m = rx.match(stream)
        if m:
            return ch.kafka_topic, m.groupdict().get("key")
    return stream.replace(":", "."), None
