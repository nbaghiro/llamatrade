"""The channel registry."""

from __future__ import annotations

from llamatrade_events.channels import (
    BACKTEST_PROGRESS,
    BARS,
    LEDGER_FILLS,
    ORDERS,
    POSITIONS,
    Channel,
    Delivery,
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


def test_retention_bounds() -> None:
    assert LEDGER_FILLS.maxlen == 10_000
    assert BARS.maxlen == 50_000
    assert BACKTEST_PROGRESS.maxlen == 256


def test_channel_is_frozen() -> None:
    import dataclasses

    import pytest

    c = Channel("x:{a}", maxlen=10)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(c, "maxlen", 20)
