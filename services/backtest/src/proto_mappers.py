"""Canonical DB-row → proto mappers for backtest reads.

Proto is the single source of truth for the read/wire shape (decision 1A): these
functions map the persisted ``Backtest``/``BacktestResult`` rows straight to the
generated proto messages in one pass, with no intermediate Pydantic layer (13A)
and money kept as ``Decimal`` end-to-end (5A). Proto field names are authoritative
(7A) — e.g. DB ``annual_return`` → proto ``annualized_return``.

JSONB blobs (``equity_curve``, ``trades``) are parsed directly into proto here;
they are trusted (written by this service on completion), so they are not
re-validated through Pydantic on read.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from llamatrade_db.models.backtest import Backtest, BacktestResult
from llamatrade_proto.generated import backtest_pb2, common_pb2
from llamatrade_proto.generated.trading_pb2 import ORDER_SIDE_BUY

# Scale for computed (divided) statistics, to keep Decimal strings bounded.
_COMPUTED_SCALE = Decimal("0.00000001")
_ZERO = Decimal("0")


def _dec(value: Decimal | int | str) -> common_pb2.Decimal:
    """Proto Decimal from a Decimal/int (DB-sourced values preserve their scale)."""
    return common_pb2.Decimal(value=str(value))


def _dec_json(value: object, default: str = "0") -> common_pb2.Decimal:
    """Proto Decimal from a JSON scalar (float/int/str), via str to avoid float drift."""
    if value is None:
        return common_pb2.Decimal(value=default)
    return common_pb2.Decimal(value=str(value))


def _to_decimal(value: object) -> Decimal:
    """Parse a JSON scalar to Decimal without float rounding."""
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _ts(value: datetime) -> common_pb2.Timestamp:
    return common_pb2.Timestamp(seconds=int(value.timestamp()))


def backtest_run_to_proto(b: Backtest) -> backtest_pb2.BacktestRun:
    """Map a persisted Backtest row to a proto BacktestRun (run-level; results attached separately)."""
    run = backtest_pb2.BacktestRun(
        id=str(b.id),
        tenant_id=str(b.tenant_id),
        strategy_id=str(b.strategy_id),
        strategy_version=b.strategy_version,
        status=b.status,
        status_message=b.error_message or "",
        progress_percent=100 if b.status == backtest_pb2.BACKTEST_STATUS_COMPLETED else 0,
        created_at=_ts(b.created_at),
    )
    run.config.CopyFrom(
        backtest_pb2.BacktestConfig(
            strategy_id=str(b.strategy_id),
            strategy_version=b.strategy_version,
            start_date=_ts(datetime.combine(b.start_date, datetime.min.time())),
            end_date=_ts(datetime.combine(b.end_date, datetime.min.time())),
            initial_capital=_dec(b.initial_capital),
        )
    )
    if b.started_at:
        run.started_at.CopyFrom(_ts(b.started_at))
    if b.completed_at:
        run.completed_at.CopyFrom(_ts(b.completed_at))
    return run


def backtest_trade_to_proto(raw: dict[str, Any]) -> backtest_pb2.BacktestTrade:
    """Map one persisted trade dict (JSONB) to a proto BacktestTrade."""
    exit_date = raw.get("exit_date")
    exit_price = raw.get("exit_price")
    return backtest_pb2.BacktestTrade(
        symbol=str(raw["symbol"]),
        side=ORDER_SIDE_BUY,  # engine is long-only
        quantity=_dec_json(raw.get("quantity")),
        entry_price=_dec_json(raw.get("entry_price")),
        exit_price=_dec_json(exit_price)
        if exit_price is not None
        else common_pb2.Decimal(value="0"),
        entry_time=_ts(datetime.fromisoformat(str(raw["entry_date"]))),
        exit_time=_ts(datetime.fromisoformat(str(exit_date))) if exit_date else None,
        pnl=_dec_json(raw.get("pnl")),
        pnl_percent=_dec_json(raw.get("pnl_percent")),
        commission=_dec_json(raw.get("commission")),
    )


def backtest_metrics_to_proto(
    b: Backtest,
    r: BacktestResult,
    trades_raw: list[dict[str, Any]],
    *,
    peak_equity: Decimal,
    benchmark_curve_available: bool,
) -> backtest_pb2.BacktestMetrics:
    """Map DB metric columns + persisted trades to a proto BacktestMetrics.

    Trade-derived stats (avg/largest win-loss, holding period, expectancy,
    commission) are computed here from the trade log; the rest read straight off
    the ``BacktestResult`` columns.
    """
    pnls = [_to_decimal(t.get("pnl")) for t in trades_raw]
    commissions = [_to_decimal(t.get("commission")) for t in trades_raw]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    def _avg(values: list[Decimal]) -> Decimal:
        return (sum(values, _ZERO) / len(values)).quantize(_COMPUTED_SCALE) if values else _ZERO

    avg_win = _avg(wins)
    avg_loss = abs(_avg(losses))
    total_commission = sum(commissions, _ZERO)
    expectancy = _avg(pnls)

    holding_days = [
        (
            datetime.fromisoformat(str(t["exit_date"]))
            - datetime.fromisoformat(str(t["entry_date"]))
        ).days
        for t in trades_raw
        if t.get("exit_date")
    ]
    avg_holding = (
        (Decimal(sum(holding_days)) / len(holding_days)).quantize(_COMPUTED_SCALE)
        if holding_days
        else _ZERO
    )

    metrics = backtest_pb2.BacktestMetrics(
        total_return=_dec(r.total_return),
        annualized_return=_dec(r.annual_return),
        sharpe_ratio=_dec(r.sharpe_ratio),
        sortino_ratio=_dec(r.sortino_ratio if r.sortino_ratio is not None else _ZERO),
        max_drawdown=_dec(r.max_drawdown),
        max_drawdown_duration_days=_dec(r.max_drawdown_duration or 0),
        total_trades=r.total_trades,
        winning_trades=r.winning_trades,
        losing_trades=r.losing_trades,
        win_rate=_dec(r.win_rate),
        average_win=_dec(avg_win),
        average_loss=_dec(avg_loss),
        expectancy=_dec(expectancy),
        average_holding_period_days=_dec(avg_holding),
        starting_capital=_dec(b.initial_capital),
        ending_capital=_dec(r.final_equity),
        peak_capital=_dec(peak_equity),
        total_commission=_dec(total_commission),
    )

    # Undefined (no trades / no losses): leave unset rather than writing a fake 0.
    if r.profit_factor is not None:
        metrics.profit_factor.CopyFrom(_dec(r.profit_factor))

    # Benchmark metrics only when the comparison was actually computed.
    benchmark_available = r.benchmark_return is not None or benchmark_curve_available
    if benchmark_available:
        benchmark_return = r.benchmark_return if r.benchmark_return is not None else _ZERO
        metrics.benchmark_return.CopyFrom(_dec(benchmark_return))
        metrics.alpha.CopyFrom(_dec(r.alpha if r.alpha is not None else _ZERO))
        metrics.beta.CopyFrom(_dec(r.beta if r.beta is not None else _ZERO))
        metrics.information_ratio.CopyFrom(
            _dec(r.information_ratio if r.information_ratio is not None else _ZERO)
        )
        metrics.excess_return.CopyFrom(_dec(r.total_return - benchmark_return))
        metrics.benchmark_symbol = r.benchmark_symbol or "SPY"

    return metrics


def _equity_points(
    raw_curve: list[dict[str, Any]] | None, initial_capital: Decimal
) -> tuple[list[backtest_pb2.EquityPoint], Decimal]:
    """Build proto equity points (recomputing drawdown) and return the peak equity."""
    if not raw_curve:
        return [], initial_capital

    points: list[backtest_pb2.EquityPoint] = []
    peak = initial_capital
    for point in raw_curve:
        equity = _to_decimal(point.get("equity"))
        peak = max(peak, equity)
        drawdown_pct = ((peak - equity) / peak * 100) if peak > 0 else _ZERO
        points.append(
            backtest_pb2.EquityPoint(
                timestamp=_ts(datetime.fromisoformat(str(point["date"]))),
                equity=_dec(equity),
                drawdown=_dec(drawdown_pct.quantize(_COMPUTED_SCALE)),
            )
        )
    return points, peak


def backtest_results_to_proto(
    b: Backtest,
    r: BacktestResult,
    *,
    trades_preview: int,
) -> backtest_pb2.BacktestResults:
    """Map the persisted Backtest + BacktestResult rows to a proto BacktestResults.

    Trades are capped at ``trades_preview``; the full log is paged via
    GetBacktestTrades (14B).
    """
    initial_capital = b.initial_capital
    raw_trades: list[dict[str, Any]] = r.trades or []
    raw_benchmark_curve: list[dict[str, Any]] | None = r.benchmark_equity_curve

    equity_curve, peak_equity = _equity_points(r.equity_curve, initial_capital)
    metrics = backtest_metrics_to_proto(
        b,
        r,
        raw_trades,
        peak_equity=peak_equity,
        benchmark_curve_available=bool(raw_benchmark_curve),
    )

    proto = backtest_pb2.BacktestResults(
        metrics=metrics,
        equity_curve=equity_curve,
        trades=[backtest_trade_to_proto(t) for t in raw_trades[:trades_preview]],
        benchmark_equity_curve=[
            backtest_pb2.EquityPoint(
                timestamp=_ts(datetime.fromisoformat(str(point["date"]))),
                equity=_dec_json(point.get("equity")),
            )
            for point in (raw_benchmark_curve or [])
        ],
        benchmark_symbol=metrics.benchmark_symbol,
    )
    proto.monthly_returns.update(r.monthly_returns or {})
    return proto
