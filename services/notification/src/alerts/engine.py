"""Condition evaluation and the trigger write path.

Market-driven conditions evaluate against a per-symbol rolling window of live
bars; RSI reuses the runtime indicator library so alert semantics match the
strategy engine exactly. Triggering is transactional: the alert row is locked,
the cooldown re-checked, and the notification persisted with a deterministic
id derived from (alert, minute bucket), so a torn leader or a concurrent
event-matcher cannot double-notify.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.notification import Alert
from llamatrade_dsl.analysis import IndicatorSpec
from llamatrade_events.idempotency import derive_event_id
from llamatrade_proto.generated import events_pb2, notification_pb2
from llamatrade_runtime.indicators.library import PriceData, compute_indicator
from llamatrade_telemetry import metrics

from src.pipeline import Dispatcher, persist_and_plan

logger = logging.getLogger(__name__)

_C = notification_pb2

RSI_PERIOD = 14
WINDOW_BARS = 120  # rolling minutes retained per symbol

MARKET_CONDITION_TYPES: frozenset[int] = frozenset(
    {
        _C.ALERT_CONDITION_TYPE_PRICE_ABOVE,
        _C.ALERT_CONDITION_TYPE_PRICE_BELOW,
        _C.ALERT_CONDITION_TYPE_PRICE_CHANGE_PERCENT,
        _C.ALERT_CONDITION_TYPE_VOLUME_ABOVE,
        _C.ALERT_CONDITION_TYPE_RSI_ABOVE,
        _C.ALERT_CONDITION_TYPE_RSI_BELOW,
    }
)


@dataclass
class SymbolWindow:
    """Rolling per-symbol bar state for market-condition evaluation."""

    closes: deque[float] = field(default_factory=lambda: deque(maxlen=WINDOW_BARS))
    volumes: deque[int] = field(default_factory=lambda: deque(maxlen=WINDOW_BARS))

    def push(self, close: float, volume: int) -> None:
        self.closes.append(close)
        self.volumes.append(volume)

    def rsi(self, period: int = RSI_PERIOD) -> float | None:
        if len(self.closes) < period + 1:
            return None
        closes = np.asarray(self.closes, dtype=np.float64)
        spec = IndicatorSpec(
            indicator_type="rsi",
            symbol="",
            source="close",
            params=(period,),
            output_key="rsi",
            output_field=None,
            required_bars=period + 1,
        )
        prices = PriceData(
            open=closes, high=closes, low=closes, close=closes, volume=np.asarray(self.volumes)
        )
        value = compute_indicator(spec, prices)["rsi"][-1]
        return None if np.isnan(value) else float(value)

    def percent_change(self) -> float | None:
        """Change of the latest close vs the oldest retained close (~2h window)."""
        if len(self.closes) < 2 or self.closes[0] == 0:
            return None
        return (self.closes[-1] - self.closes[0]) / self.closes[0] * 100.0


def threshold_of(alert: Alert) -> Decimal:
    raw = (alert.condition or {}).get("threshold", "0")
    try:
        return Decimal(str(raw))
    except ArithmeticError:
        return Decimal(0)


def alert_is_live(alert: Alert, now: datetime) -> bool:
    if alert.status != _C.ALERT_STATUS_ACTIVE:
        return False
    if alert.expires_at is not None and _aware(alert.expires_at) < now:
        return False
    if alert.last_triggered_at is not None:
        cooldown_until = _aware(alert.last_triggered_at) + timedelta(minutes=alert.cooldown_minutes)
        if cooldown_until > now:
            metrics.notification.cooldown_skipped()
            return False
    return True


def evaluate_market(alert: Alert, window: SymbolWindow) -> tuple[bool, str]:
    """One market condition against the symbol window; returns (hit, detail)."""
    threshold = float(threshold_of(alert))
    close = window.closes[-1] if window.closes else None
    if close is None:
        return False, ""
    kind = int(alert.alert_type)
    if kind == _C.ALERT_CONDITION_TYPE_PRICE_ABOVE:
        return close > threshold, f"price {close:.2f} above {threshold:.2f}"
    if kind == _C.ALERT_CONDITION_TYPE_PRICE_BELOW:
        return close < threshold, f"price {close:.2f} below {threshold:.2f}"
    if kind == _C.ALERT_CONDITION_TYPE_VOLUME_ABOVE:
        volume = window.volumes[-1] if window.volumes else 0
        return volume > threshold, f"volume {volume} above {threshold:.0f}"
    if kind == _C.ALERT_CONDITION_TYPE_PRICE_CHANGE_PERCENT:
        change = window.percent_change()
        if change is None:
            return False, ""
        return abs(change) >= abs(threshold), f"moved {change:+.2f}% (threshold {threshold}%)"
    if kind in (_C.ALERT_CONDITION_TYPE_RSI_ABOVE, _C.ALERT_CONDITION_TYPE_RSI_BELOW):
        rsi = window.rsi()
        if rsi is None:
            return False, ""
        if kind == _C.ALERT_CONDITION_TYPE_RSI_ABOVE:
            return rsi > threshold, f"RSI {rsi:.1f} above {threshold:.0f}"
        return rsi < threshold, f"RSI {rsi:.1f} below {threshold:.0f}"
    return False, ""


async def trigger_alert(
    session_factory: async_sessionmaker[AsyncSession],
    dispatcher: Dispatcher,
    *,
    alert_id: UUID,
    tenant_id: UUID,
    reason: str,
    bucket: str,
) -> bool:
    """Fire one alert: lock, re-check, count, persist, deliver.

    ``bucket`` (typically the bar's minute timestamp) seeds the deterministic
    notification id, so concurrent evaluators collapse to one notification.
    """
    now = datetime.now(UTC)
    async with tenant_session(tenant_id, session_factory) as db:
        alert = await db.scalar(select(Alert).where(Alert.id == alert_id).with_for_update())
        if alert is None or not alert_is_live(alert, now):
            return False
        event = events_pb2.NotificationEvent(
            category=events_pb2.NOTIFICATION_CATEGORY_PRICE_ALERT_TRIGGERED,
            symbol=alert.symbol or "",
            reason=f"{alert.name}: {reason}",
            extra={"alert_id": str(alert.id)},
        )
        result = await persist_and_plan(
            db,
            tenant_id=tenant_id,
            user_id=alert.created_by,
            event_id=derive_event_id(str(alert.id), bucket),
            event=event,
            channel_override=frozenset(int(c) for c in (alert.channels or [])),
        )
        if result.notification_id is None:
            return False
        alert.last_triggered_at = now
        alert.trigger_count += 1
        await db.commit()
    metrics.notification.alert_triggered(type=_C.AlertConditionType.Name(alert.alert_type).lower())
    if result.deliveries:
        await dispatcher.dispatch(result.deliveries)
    return True


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
