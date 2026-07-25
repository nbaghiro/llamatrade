"""Golden round-trip tests for the DB-row -> proto backtest mappers (10A).

Validates the canonical mapper in isolation: DB row in, proto out, with
(1) Decimal precision preserved (no float hop, 5A), (2) proto field names /
computed stats correct (7A), and (3) no proto Decimal field left unset outside
an explicit allowlist of metrics the engine does not compute.
"""

from decimal import Decimal

from google.protobuf.message import Message

from llamatrade_db.models.backtest import Backtest, BacktestResult
from llamatrade_proto.generated import common_pb2

from src.proto_mappers import backtest_results_to_proto, backtest_trade_to_proto

# Metrics the engine does not currently compute (proto fields intentionally unset).
_METRICS_UNSET_ALLOWLIST = {"volatility", "downside_deviation"}


def _decimal_field_names(message: Message) -> list[str]:
    """Names of message-typed Decimal fields on a proto message."""
    return [
        f.name
        for f in message.DESCRIPTOR.fields
        if f.message_type is not None and f.message_type.name == "Decimal"
    ]


def _make_rows(
    *, with_benchmark: bool = True, with_trades: bool = True
) -> tuple[Backtest, BacktestResult]:
    b = Backtest(initial_capital=Decimal("100000.00"))
    trades = (
        [
            {
                "entry_date": "2024-01-01T00:00:00",
                "exit_date": "2024-01-02T00:00:00",
                "symbol": "AAPL",
                "side": "buy",
                "entry_price": 100,
                "exit_price": 110,
                "quantity": 10,
                "pnl": 100,
                "pnl_percent": 10,
                "commission": 1,
            },
            {
                "entry_date": "2024-01-02T00:00:00",
                "exit_date": "2024-01-03T00:00:00",
                "symbol": "AAPL",
                "side": "buy",
                "entry_price": 110,
                "exit_price": 105,
                "quantity": 10,
                "pnl": -50,
                "pnl_percent": -4.5,
                "commission": 1,
            },
        ]
        if with_trades
        else []
    )
    r = BacktestResult(
        total_return=Decimal("0.150000"),
        annual_return=Decimal("0.120000"),
        sharpe_ratio=Decimal("1.5000"),
        sortino_ratio=Decimal("2.0000"),
        max_drawdown=Decimal("0.080000"),
        max_drawdown_duration=12,
        win_rate=Decimal("0.6000"),
        profit_factor=Decimal("1.8000") if with_trades else None,
        exposure_time=Decimal("50.00"),
        total_trades=len(trades),
        winning_trades=1 if with_trades else 0,
        losing_trades=1 if with_trades else 0,
        avg_trade_return=Decimal("0.030000"),
        final_equity=Decimal("115000.00"),
        equity_curve=[
            {"date": "2024-01-01T00:00:00", "equity": 100000},
            {"date": "2024-01-02T00:00:00", "equity": 110000},
            {"date": "2024-01-03T00:00:00", "equity": 115000},
        ],
        trades=trades,
        monthly_returns={"2024-01": 0.15},
        benchmark_return=Decimal("0.100000") if with_benchmark else None,
        benchmark_symbol="SPY" if with_benchmark else None,
        alpha=Decimal("0.020000") if with_benchmark else None,
        beta=Decimal("1.100000") if with_benchmark else None,
        information_ratio=Decimal("0.500000") if with_benchmark else None,
        benchmark_equity_curve=(
            [{"date": "2024-01-01T00:00:00", "equity": 100000}] if with_benchmark else None
        ),
    )
    return b, r


def test_metrics_precision_and_names_preserved() -> None:
    b, r = _make_rows()
    proto = backtest_results_to_proto(b, r, trades_preview=500)
    m = proto.metrics

    # 5A: DB Decimal mapped straight through — scale preserved, no float hop.
    assert m.total_return.value == "0.150000"
    assert Decimal(m.total_return.value) == Decimal("0.15")
    # 7A: proto names carry the DB values.
    assert Decimal(m.annualized_return.value) == Decimal("0.12")
    assert Decimal(m.sharpe_ratio.value) == Decimal("1.5")

    # Trade-derived stats computed from the trade log.
    assert Decimal(m.average_win.value) == Decimal("100")
    assert Decimal(m.average_loss.value) == Decimal("50")
    assert Decimal(m.expectancy.value) == Decimal("25")  # (100 - 50) / 2
    assert Decimal(m.total_commission.value) == Decimal("2")
    assert Decimal(m.average_holding_period_days.value) == Decimal("1")

    # Capital fields now populated (previously left unset).
    assert Decimal(m.starting_capital.value) == Decimal("100000")
    assert Decimal(m.ending_capital.value) == Decimal("115000")
    assert Decimal(m.peak_capital.value) == Decimal("115000")

    assert m.total_trades == 2 and m.winning_trades == 1 and m.losing_trades == 1


def test_metrics_completeness_no_unexpected_default() -> None:
    """No proto Decimal metric is left unset except the documented allowlist."""
    b, r = _make_rows()
    m = backtest_results_to_proto(b, r, trades_preview=500).metrics

    for name in _decimal_field_names(m):
        if name in _METRICS_UNSET_ALLOWLIST:
            assert not m.HasField(name), f"{name} should be unset (uncomputed)"
        else:
            assert m.HasField(name), f"{name} unexpectedly left at default"


def test_benchmark_gate_and_excess_return() -> None:
    b, r = _make_rows(with_benchmark=True)
    m = backtest_results_to_proto(b, r, trades_preview=500).metrics
    assert m.HasField("benchmark_return")
    assert Decimal(m.excess_return.value) == Decimal("0.05")  # 0.15 - 0.10
    assert m.benchmark_symbol == "SPY"


def test_no_benchmark_leaves_benchmark_fields_unset() -> None:
    b, r = _make_rows(with_benchmark=False)
    m = backtest_results_to_proto(b, r, trades_preview=500).metrics
    for name in ("benchmark_return", "alpha", "beta", "information_ratio", "excess_return"):
        assert not m.HasField(name)
    assert m.benchmark_symbol == ""


def test_profit_factor_none_left_unset() -> None:
    b, r = _make_rows(with_trades=False)
    m = backtest_results_to_proto(b, r, trades_preview=500).metrics
    assert not m.HasField("profit_factor")
    assert Decimal(m.average_win.value) == Decimal("0")


def test_equity_curve_drawdown_and_unset_fields() -> None:
    b, r = _make_rows()
    proto = backtest_results_to_proto(b, r, trades_preview=500)
    assert len(proto.equity_curve) == 3
    # Last point is the peak -> zero drawdown.
    assert Decimal(proto.equity_curve[-1].drawdown.value) == Decimal("0")
    # cash / positions_value / daily_return are not produced by the engine.
    for pt in proto.equity_curve:
        assert not pt.HasField("cash")
        assert not pt.HasField("positions_value")
        assert not pt.HasField("daily_return")


def test_trades_preview_cap() -> None:
    b, r = _make_rows()
    proto = backtest_results_to_proto(b, r, trades_preview=1)
    assert len(proto.trades) == 1  # capped; full log paged via GetBacktestTrades


def test_trade_mapper_maps_fields() -> None:
    trade = backtest_trade_to_proto(
        {
            "entry_date": "2024-01-01T00:00:00",
            "exit_date": "2024-01-02T00:00:00",
            "symbol": "MSFT",
            "side": "buy",
            "entry_price": 200,
            "exit_price": 210,
            "quantity": 5,
            "pnl": 50,
            "pnl_percent": 5,
            "commission": 1,
        }
    )
    assert trade.symbol == "MSFT"
    assert Decimal(trade.pnl.value) == Decimal("50")
    assert isinstance(trade.exit_time, common_pb2.Timestamp)
