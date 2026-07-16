"""Pure read-model: aggregate ledger projections into the portfolio read views.

Turns one-or-more ``AccountProjection``s (a tenant may own several accounts, one
per broker credential set) plus a price map into the summary / positions /
transaction views the read API serves. The legacy float/JSONB path computed
these from a per-tenant summary row; here they derive from the event-sourced
projection, so they are consistent with sleeves/funds by construction.

Pure (no DB/IO): the DB-backed ``PortfolioReadService`` supplies projections,
prices, and prior-equity, and maps these views onto the response schemas.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger import analytics
from src.ledger.postings import Bucket, build_postings
from src.ledger.projection import AccountProjection, LedgerEventLike

ZERO = Decimal("0")


@dataclass(frozen=True)
class PositionView:
    """Aggregate holding in one symbol across all sleeves/accounts."""

    symbol: str
    qty: float
    side: str
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    current_price: float
    avg_entry_price: float


@dataclass(frozen=True)
class SummaryView:
    """Account-wide portfolio summary."""

    total_equity: float
    cash: float
    market_value: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    day_pnl: float
    day_pnl_percent: float
    total_pnl_percent: float
    positions_count: int


@dataclass(frozen=True)
class TransactionView:
    """One economic ledger event rendered as a transaction-history row."""

    event_id: str
    type: str  # buy/sell/deposit/withdrawal/dividend/fee/transfer_in/transfer_out
    symbol: str | None
    qty: float | None
    price: float | None
    amount: float
    fees: float
    occurred_at: object  # datetime | None
    sleeve_id: str | None = None  # target sleeve for allocations/transfers (name resolved by caller)


def _price(prices: dict[str, Decimal], symbol: str, fallback: Decimal) -> Decimal:
    """Live price, treating 0/absent as a miss (fall back to avg entry)."""
    p = prices.get(symbol)
    return p if p else fallback


def aggregate_positions(
    projections: Iterable[AccountProjection], prices: dict[str, Decimal]
) -> list[PositionView]:
    """Sum lots per symbol across every sleeve/account, marked to market."""
    qty_by: dict[str, Decimal] = {}
    cost_by: dict[str, Decimal] = {}
    for proj in projections:
        for sleeve in proj.sleeves.values():
            for symbol, pos in sleeve.positions.items():
                if pos.qty == ZERO:
                    continue
                qty_by[symbol] = qty_by.get(symbol, ZERO) + pos.qty
                cost_by[symbol] = cost_by.get(symbol, ZERO) + pos.cost_basis

    views: list[PositionView] = []
    for symbol in sorted(qty_by):
        qty = qty_by[symbol]
        if qty == ZERO:
            continue
        cost_basis = cost_by[symbol]
        avg_entry = cost_basis / qty  # sign-stable: long→+, short→+
        side = "long" if qty > ZERO else "short"
        magnitude = abs(qty)
        current = _price(prices, symbol, avg_entry)
        mkt_value = magnitude * current
        upnl = analytics.unrealized_pnl(side, float(magnitude), float(avg_entry), float(current))
        views.append(
            PositionView(
                symbol=symbol,
                qty=float(magnitude),
                side=side,
                cost_basis=float(abs(cost_basis)),
                market_value=float(mkt_value),
                unrealized_pnl=upnl,
                unrealized_pnl_percent=analytics.pnl_percent(upnl, float(abs(cost_basis))),
                current_price=float(current),
                avg_entry_price=float(abs(avg_entry)),
            )
        )
    return views


def portfolio_summary(
    projections: Iterable[AccountProjection],
    prices: dict[str, Decimal],
    *,
    prior_equity: float | None = None,
) -> SummaryView:
    """Aggregate cash + marked positions + realized P&L into a summary view."""
    projections = list(projections)
    positions = aggregate_positions(projections, prices)

    cash = sum((p.total_cash() for p in projections), ZERO)
    realized = ZERO
    for proj in projections:
        for sleeve in proj.sleeves.values():
            realized += sleeve.realized_pnl

    market_value = sum(p.market_value for p in positions)
    unrealized = sum(p.unrealized_pnl for p in positions)
    total_equity = float(cash) + market_value

    cost_total = sum(p.cost_basis for p in positions)
    total_pnl_percent = ((unrealized + float(realized)) / cost_total * 100) if cost_total else 0.0

    day_pnl = 0.0
    day_pnl_percent = 0.0
    if prior_equity:
        day_pnl = total_equity - prior_equity
        day_pnl_percent = (day_pnl / prior_equity * 100) if prior_equity else 0.0

    return SummaryView(
        total_equity=total_equity,
        cash=float(cash),
        market_value=market_value,
        total_unrealized_pnl=unrealized,
        total_realized_pnl=float(realized),
        day_pnl=day_pnl,
        day_pnl_percent=day_pnl_percent,
        total_pnl_percent=total_pnl_percent,
        positions_count=len(positions),
    )


# event_type -> transaction-view type label
_TXN_TYPE: dict[LedgerEventType, str] = {
    LedgerEventType.FUNDS_DEPOSITED: "deposit",
    LedgerEventType.FUNDS_WITHDRAWN: "withdrawal",
    LedgerEventType.DIVIDEND_RECEIVED: "dividend",
    LedgerEventType.INTEREST_ACCRUED: "interest",
    LedgerEventType.FEE_CHARGED: "fee",
    LedgerEventType.CAPITAL_ALLOCATED: "transfer_in",
    LedgerEventType.CAPITAL_TRANSFERRED: "transfer_in",
}


def _f(data: dict[str, object], key: str) -> float | None:
    val = data.get(key)
    return float(str(val)) if val is not None else None


def transactions_view(events: Iterable[LedgerEventLike]) -> list[TransactionView]:
    """Render economic ledger events as transaction-history rows (newest-first).

    Order fills become buy/sell with qty/price; cash events carry an amount.
    Non-economic lifecycle events (submit/cancel/sleeve) are skipped. Amount is
    the absolute cash movement (sum of negative CASH/EXTERNAL legs' magnitude).
    """
    out: list[TransactionView] = []
    for ev in events:
        etype = (
            ev.event_type
            if isinstance(ev.event_type, LedgerEventType)
            else LedgerEventType(ev.event_type)
        )
        data = ev.data
        postings = build_postings(etype, data)
        if not postings:
            continue
        occurred = getattr(ev, "occurred_at", None)
        event_id = str(getattr(ev, "event_id", ""))

        if etype is LedgerEventType.ORDER_FILLED:
            side = str(data.get("side", "")).lower()
            qty = _f(data, "qty")
            price = _f(data, "price")
            amount = abs((qty or 0.0) * (price or 0.0))
            out.append(
                TransactionView(
                    event_id=event_id,
                    type=side or "buy",
                    symbol=str(data.get("symbol")) if data.get("symbol") else None,
                    qty=qty,
                    price=price,
                    amount=amount,
                    fees=_f(data, "fees") or 0.0,
                    occurred_at=occurred,
                )
            )
            continue

        label = _TXN_TYPE.get(etype)
        if label is None:
            continue
        amount = _f(data, "amount") or abs(
            float(
                sum((p.amount for p in postings if p.bucket is Bucket.CASH and p.amount < 0), ZERO)
            )
        )
        out.append(
            TransactionView(
                event_id=event_id,
                type=label,
                symbol=str(data.get("symbol")) if data.get("symbol") else None,
                qty=None,
                price=None,
                amount=abs(amount),
                fees=0.0,
                occurred_at=occurred,
                sleeve_id=str(data["to_sleeve_id"]) if data.get("to_sleeve_id") else None,
            )
        )
    out.reverse()  # events arrive oldest-first; history is newest-first
    return out


@dataclass(frozen=True)
class TradeStats:
    """Realized-trade statistics for a sleeve (from closed sells)."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # percent
    profit_factor: float
    average_win: float
    average_loss: float
    realized_pnl: float


def sleeve_trade_stats(events: Iterable[LedgerEventLike], sleeve_id: str) -> TradeStats:
    """Tally realized P&L per closing sell for one sleeve.

    A "trade" is a sell fill; its realized P&L comes from the (FIFO-enriched)
    ``realized_pnl`` on the event. Buys open exposure and aren't counted as
    realized trades. Win rate / profit factor / averages follow standard defs.
    """
    wins: list[float] = []
    losses: list[float] = []
    for ev in events:
        etype = (
            ev.event_type
            if isinstance(ev.event_type, LedgerEventType)
            else LedgerEventType(ev.event_type)
        )
        if etype is not LedgerEventType.ORDER_FILLED:
            continue
        data = ev.data
        if str(data.get("sleeve_id")) != sleeve_id or str(data.get("side", "")).lower() != "sell":
            continue
        raw = data.get("realized_pnl")
        realized = float(str(raw)) if raw is not None else 0.0
        (wins if realized > 0 else losses).append(realized)

    total = len(wins) + len(losses)
    total_wins = sum(wins)
    total_losses = abs(sum(losses))
    return TradeStats(
        total_trades=total,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=(len(wins) / total * 100) if total else 0.0,
        profit_factor=(total_wins / total_losses) if total_losses > 0 else 0.0,
        average_win=(total_wins / len(wins)) if wins else 0.0,
        average_loss=(sum(losses) / len(losses)) if losses else 0.0,
        realized_pnl=total_wins - total_losses,
    )
