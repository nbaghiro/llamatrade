"""Market-condition evaluation: windows, thresholds, RSI, cooldown, expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from llamatrade_db.models.notification import Alert
from llamatrade_proto.generated import notification_pb2

from src.alerts.engine import (
    RSI_PERIOD,
    SymbolWindow,
    alert_is_live,
    evaluate_market,
    threshold_of,
)

_C = notification_pb2


def _alert(
    condition_type: int,
    threshold: str,
    *,
    status: int = _C.ALERT_STATUS_ACTIVE,
    cooldown_minutes: int = 60,
    last_triggered_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> Alert:
    return Alert(
        id=uuid4(),
        tenant_id=uuid4(),
        name="a",
        alert_type=condition_type,
        symbol="SPY",
        condition={"threshold": threshold},
        status=status,
        channels=[],
        cooldown_minutes=cooldown_minutes,
        last_triggered_at=last_triggered_at,
        trigger_count=0,
        expires_at=expires_at,
        created_by=uuid4(),
    )


def _window(closes: list[float], volumes: list[int] | None = None) -> SymbolWindow:
    window = SymbolWindow()
    volumes = volumes or [1000] * len(closes)
    for close, volume in zip(closes, volumes, strict=True):
        window.push(close, volume)
    return window


class TestPriceConditions:
    def test_price_above_hit(self) -> None:
        hit, detail = evaluate_market(
            _alert(_C.ALERT_CONDITION_TYPE_PRICE_ABOVE, "500"), _window([501.0])
        )
        assert hit
        assert "above" in detail

    def test_price_above_miss(self) -> None:
        hit, _ = evaluate_market(
            _alert(_C.ALERT_CONDITION_TYPE_PRICE_ABOVE, "500"), _window([499.0])
        )
        assert not hit

    def test_price_below(self) -> None:
        hit, _ = evaluate_market(
            _alert(_C.ALERT_CONDITION_TYPE_PRICE_BELOW, "500"), _window([499.0])
        )
        assert hit

    def test_volume_above(self) -> None:
        hit, detail = evaluate_market(
            _alert(_C.ALERT_CONDITION_TYPE_VOLUME_ABOVE, "5000"),
            _window([500.0], [6000]),
        )
        assert hit
        assert "volume" in detail

    def test_percent_change_both_directions(self) -> None:
        up = _window([100.0, 101.0, 103.0])
        down = _window([100.0, 99.0, 96.5])
        alert = _alert(_C.ALERT_CONDITION_TYPE_PRICE_CHANGE_PERCENT, "3")
        assert evaluate_market(alert, up)[0]
        assert evaluate_market(alert, down)[0]
        flat = _window([100.0, 100.5])
        assert not evaluate_market(alert, flat)[0]

    def test_empty_window_never_hits(self) -> None:
        hit, _ = evaluate_market(_alert(_C.ALERT_CONDITION_TYPE_PRICE_ABOVE, "1"), SymbolWindow())
        assert not hit


class TestRsi:
    def test_needs_warmup(self) -> None:
        window = _window([100.0] * RSI_PERIOD)
        assert window.rsi() is None

    def test_all_gains_is_100(self) -> None:
        closes = [100.0 + i for i in range(RSI_PERIOD + 2)]
        assert _window(closes).rsi() == 100.0

    def test_known_wilder_vector(self) -> None:
        # Classic Wilder worked example: 14-period RSI over these closes ≈ 70.53.
        closes = [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
        ]
        rsi = _window(closes).rsi()
        assert rsi is not None
        assert abs(rsi - 70.53) < 0.5

    def test_rsi_above_condition(self) -> None:
        closes = [100.0 + i for i in range(RSI_PERIOD + 2)]
        hit, detail = evaluate_market(
            _alert(_C.ALERT_CONDITION_TYPE_RSI_ABOVE, "70"), _window(closes)
        )
        assert hit
        assert "RSI" in detail

    def test_rsi_below_condition(self) -> None:
        closes = [100.0 - i * 0.5 for i in range(RSI_PERIOD + 2)]
        hit, _ = evaluate_market(_alert(_C.ALERT_CONDITION_TYPE_RSI_BELOW, "30"), _window(closes))
        assert hit


class TestLiveness:
    def test_active_no_history_is_live(self) -> None:
        assert alert_is_live(_alert(_C.ALERT_CONDITION_TYPE_PRICE_ABOVE, "1"), datetime.now(UTC))

    def test_disabled_is_not_live(self) -> None:
        alert = _alert(_C.ALERT_CONDITION_TYPE_PRICE_ABOVE, "1", status=_C.ALERT_STATUS_DISABLED)
        assert not alert_is_live(alert, datetime.now(UTC))

    def test_cooldown_suppresses(self) -> None:
        now = datetime.now(UTC)
        alert = _alert(
            _C.ALERT_CONDITION_TYPE_PRICE_ABOVE,
            "1",
            cooldown_minutes=60,
            last_triggered_at=now - timedelta(minutes=10),
        )
        assert not alert_is_live(alert, now)

    def test_cooldown_expires(self) -> None:
        now = datetime.now(UTC)
        alert = _alert(
            _C.ALERT_CONDITION_TYPE_PRICE_ABOVE,
            "1",
            cooldown_minutes=60,
            last_triggered_at=now - timedelta(minutes=61),
        )
        assert alert_is_live(alert, now)

    def test_expired_is_not_live(self) -> None:
        now = datetime.now(UTC)
        alert = _alert(_C.ALERT_CONDITION_TYPE_PRICE_ABOVE, "1", expires_at=now - timedelta(days=1))
        assert not alert_is_live(alert, now)


def test_threshold_parsing() -> None:
    assert threshold_of(_alert(_C.ALERT_CONDITION_TYPE_PRICE_ABOVE, "70.5")) == Decimal("70.5")
    alert = _alert(_C.ALERT_CONDITION_TYPE_PRICE_ABOVE, "not-a-number")
    assert threshold_of(alert) == Decimal(0)


def test_window_is_bounded() -> None:
    window = _window([float(i) for i in range(500)])
    assert len(window.closes) == 120
