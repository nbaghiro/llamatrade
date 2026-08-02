"""The channel registry."""

from __future__ import annotations

from llamatrade_events.channels import (
    BACKTEST_PROGRESS,
    BARS,
    LEDGER_FILLS,
    NOTIFICATIONS,
    ORDERS,
    POSITIONS,
    Channel,
    Delivery,
    resolve_topic,
)


def test_key_fills_placeholders() -> None:
    assert ORDERS.key(session_id="s1") == "trading:orders:s1"
    assert POSITIONS.key(session_id="s1") == "trading:positions:s1"
    assert BACKTEST_PROGRESS.key(backtest_id="bt-1") == "backtest:progress:bt-1"


def test_key_accepts_non_str_params() -> None:
    from uuid import UUID

    uid = UUID("11111111-1111-1111-1111-111111111111")
    assert ORDERS.key(session_id=uid) == f"trading:orders:{uid}"


def test_static_keys_need_no_params() -> None:
    assert LEDGER_FILLS.key() == "ledger:fills"
    assert BARS.key() == "market:bars:1m"


def test_delivery_and_envelope_policy() -> None:
    # UI streams + bars are tail; the ledger is a durable consumer group.
    assert ORDERS.delivery is Delivery.TAIL
    assert LEDGER_FILLS.delivery is Delivery.CONSUME
    # Only the high-volume bar stream skips the envelope.
    assert BARS.enveloped is False
    assert ORDERS.enveloped is True
    assert LEDGER_FILLS.enveloped is True


def test_kafka_topics() -> None:
    # Retention/partitions live in Terraform; code declares only the topic base.
    assert LEDGER_FILLS.kafka_topic == "ledger.fills"
    assert BARS.kafka_topic == "market.bars.1m"
    assert BACKTEST_PROGRESS.kafka_topic == "backtest.progress"


def test_channel_is_frozen() -> None:
    import dataclasses

    import pytest

    c = Channel("x:{a}", kafka_topic="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(c, "kafka_topic", "y")


def test_notifications_channel_facts() -> None:
    assert NOTIFICATIONS.key() == "notifications"
    assert NOTIFICATIONS.kafka_topic == "notifications"
    assert NOTIFICATIONS.delivery is Delivery.CONSUME
    assert NOTIFICATIONS.enveloped is True
    assert resolve_topic("notifications") == ("notifications", None)
    assert resolve_topic("notifications:dlq") == ("notifications.dlq", None)
