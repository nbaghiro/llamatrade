"""Forming period bars — fold an intraday bar stream into the strategy's evaluation grid.

The strategy language is daily-or-coarser and a backtest evaluates exactly one bar per period,
so a live session fed one-minute bars would fill its indicator windows with minute bars and
compute different values than a backtest of the same strategy over the same days.

:class:`FormingBarAggregator` keeps one *forming* bar per symbol for the period in progress:
open from the period's first bar, running high/low extrema, close from the latest bar, summed
volume. Live bar feeds hand the forming bar to the session on every update; the evaluation core
replaces a same-timestamp bar in place, so a period occupies exactly one slot in history and
equals the completed period bar once the period ends.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo

from llamatrade_runtime.types import Bar

MARKET_TIMEZONE_NAME = "America/New_York"

# Maps a bar timestamp to the start of the period it belongs to.
PeriodStart = Callable[[datetime], datetime]


@lru_cache(maxsize=1)
def market_timezone() -> ZoneInfo:
    """The exchange timezone period boundaries are keyed on, resolved on first use."""
    return ZoneInfo(MARKET_TIMEZONE_NAME)


def daily_period_start(timestamp: datetime, tz: tzinfo | None = None) -> datetime:
    """Midnight of ``timestamp``'s exchange-local calendar day, as an aware datetime.

    Keying on the exchange calendar day rather than the UTC day keeps one trading session in one
    period across daylight-saving shifts and across the UTC midnight that after-hours bars cross.
    Naive timestamps are read as UTC, matching the bar streams.
    """
    zone = tz or market_timezone()
    aware = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=UTC)
    local = aware.astimezone(zone)
    return datetime(local.year, local.month, local.day, tzinfo=zone)


class FormingBarAggregator:
    """Folds per-symbol intraday bars into the forming bar of the period they belong to.

    A seed lets a session that starts mid-period adopt the partial bar its warm-up preload
    already covers (daily reads include the currently forming bar), so the morning's open,
    extremes and volume are not lost. Live bars whose coverage overlaps the seed's add their
    volume twice; open/high/low/close stay correct.
    """

    def __init__(
        self,
        *,
        period_start: PeriodStart | None = None,
        seed: Mapping[str, Bar] | None = None,
    ) -> None:
        self._period_start: PeriodStart = period_start or daily_period_start
        self._forming: dict[str, Bar] = dict(seed) if seed else {}

    def update(self, symbol: str, bar: Bar) -> Bar:
        """Fold ``bar`` into ``symbol``'s forming bar and return the forming bar.

        A bar in a new period starts a fresh forming bar stamped at the period start; a bar in
        the period already in progress extends it and keeps that bar's timestamp, so the series
        a consumer has already published stays addressable.
        """
        period = self._period_start(bar.timestamp)
        current = self._forming.get(symbol)

        if current is None or self._period_start(current.timestamp) != period:
            forming = Bar(
                timestamp=period,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        else:
            forming = Bar(
                timestamp=current.timestamp,
                open=current.open,
                high=max(current.high, bar.high),
                low=min(current.low, bar.low),
                close=bar.close,
                volume=current.volume + bar.volume,
            )

        self._forming[symbol] = forming
        return forming

    def current(self, symbol: str) -> Bar | None:
        """``symbol``'s forming bar, or None if it has not reported in any period yet."""
        return self._forming.get(symbol)

    def reset(self) -> None:
        """Drop every symbol's forming bar."""
        self._forming.clear()
