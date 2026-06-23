"""Tests for OrderCreate type<->price validation (trading-hardening 6A)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    ORDER_TYPE_STOP,
    ORDER_TYPE_STOP_LIMIT,
    ORDER_TYPE_TRAILING_STOP,
)

from src.models import OrderCreate


def _base(**overrides):
    kwargs = dict(symbol="AAPL", side=ORDER_SIDE_BUY, qty=10.0)
    kwargs.update(overrides)
    return kwargs


def test_market_order_needs_no_price() -> None:
    order = OrderCreate(**_base(order_type=ORDER_TYPE_MARKET))
    assert order.order_type == ORDER_TYPE_MARKET


def test_limit_order_requires_limit_price() -> None:
    with pytest.raises(ValidationError, match="limit_price"):
        OrderCreate(**_base(order_type=ORDER_TYPE_LIMIT))
    # With a valid price it passes.
    OrderCreate(**_base(order_type=ORDER_TYPE_LIMIT, limit_price=150.0))


def test_limit_order_rejects_nonpositive_price() -> None:
    with pytest.raises(ValidationError, match="limit_price"):
        OrderCreate(**_base(order_type=ORDER_TYPE_LIMIT, limit_price=0.0))


def test_stop_order_requires_stop_price() -> None:
    with pytest.raises(ValidationError, match="stop_price"):
        OrderCreate(**_base(order_type=ORDER_TYPE_STOP))
    OrderCreate(**_base(order_type=ORDER_TYPE_STOP, stop_price=140.0))


def test_stop_limit_requires_both_prices() -> None:
    with pytest.raises(ValidationError):
        OrderCreate(**_base(order_type=ORDER_TYPE_STOP_LIMIT, stop_price=140.0))
    with pytest.raises(ValidationError):
        OrderCreate(**_base(order_type=ORDER_TYPE_STOP_LIMIT, limit_price=141.0))
    OrderCreate(**_base(order_type=ORDER_TYPE_STOP_LIMIT, stop_price=140.0, limit_price=141.0))


def test_trailing_stop_requires_trail_percent() -> None:
    with pytest.raises(ValidationError, match="trail_percent"):
        OrderCreate(**_base(order_type=ORDER_TYPE_TRAILING_STOP))
    OrderCreate(**_base(order_type=ORDER_TYPE_TRAILING_STOP, trail_percent=2.5))
