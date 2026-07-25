"""Golden round-trip tests for the internal-object -> proto portfolio mappers (1A).

Validates the canonical mappers in isolation: read-model view / compute result
in, proto out, with (1) Decimal precision preserved (no float hop, 5A),
(2) proto field names authoritative (7A: ``qty``->``quantity``, ``occurred_at``
->``timestamp``), (3) the STRING transaction taxonomy mapped to the int
``TransactionType`` enum (never int-vs-string), and (4) no proto Decimal field
left unset outside an explicit allowlist.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from google.protobuf.message import Message

from llamatrade_proto.generated import portfolio_pb2, trading_pb2
from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_PAPER, EXECUTION_STATUS_RUNNING

from src.ledger.analytics import EquityMetrics
from src.ledger.read_model import PositionView, TradeStats, TransactionView
from src.proto_mappers import (
    benchmark_series_to_proto,
    equity_point_to_proto,
    live_metrics_to_proto,
    period_returns_to_proto,
    position_view_to_proto,
    strategy_summary_to_proto,
    transaction_view_to_proto,
)

_TENANT = UUID("11111111-1111-1111-1111-111111111111")
_EVENT = UUID("22222222-2222-2222-2222-222222222222")

# Aggregated positions carry no per-lot realized P&L or broker available-qty.
_POSITION_UNSET_ALLOWLIST = {"realized_pnl", "available_quantity"}
# Not computed on the live metrics path.
_LIVE_METRICS_UNSET_ALLOWLIST = {"calmar_ratio", "alpha", "beta", "correlation"}


def _decimal_field_names(message: Message) -> list[str]:
    return [
        f.name
        for f in message.DESCRIPTOR.fields
        if f.message_type is not None and f.message_type.name == "Decimal"
    ]


def _position_view() -> PositionView:
    return PositionView(
        symbol="AAPL",
        qty=Decimal("100.00000000"),
        side="long",
        cost_basis=Decimal("15000.00"),
        market_value=Decimal("15500.00"),
        unrealized_pnl=Decimal("500.00"),
        unrealized_pnl_percent=Decimal("3.3333"),
        current_price=Decimal("155.00000000"),
        avg_entry_price=Decimal("150.00000000"),
    )


def test_position_precision_and_side() -> None:
    proto = position_view_to_proto(_position_view())
    assert proto.symbol == "AAPL"
    assert proto.side == trading_pb2.POSITION_SIDE_LONG
    # 5A: DB Decimal preserved through str, no float hop.
    assert proto.quantity.value == "100.00000000"
    assert Decimal(proto.quantity.value) == Decimal("100")
    assert Decimal(proto.cost_basis.value) == Decimal("15000")
    assert Decimal(proto.average_entry_price.value) == Decimal("150")
    # unrealized_pnl_percent is populated (the old hand-mapper dropped it).
    assert Decimal(proto.unrealized_pnl_percent.value) == Decimal("3.3333")


def test_position_short_side() -> None:
    view = _position_view()
    object.__setattr__(view, "side", "short")
    assert position_view_to_proto(view).side == trading_pb2.POSITION_SIDE_SHORT


def test_position_completeness_no_unexpected_default() -> None:
    proto = position_view_to_proto(_position_view())
    for name in _decimal_field_names(proto):
        if name in _POSITION_UNSET_ALLOWLIST:
            assert not proto.HasField(name), f"{name} should be unset"
        else:
            assert proto.HasField(name), f"{name} unexpectedly left at default"


def _txn_view(txn_type: str = "buy") -> TransactionView:
    return TransactionView(
        event_id=str(_EVENT),
        type=txn_type,
        symbol="AAPL",
        qty=Decimal("2.5"),
        price=Decimal("100.25"),
        amount=Decimal("250.625"),
        fees=Decimal("1.00"),
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def test_transaction_proto_names_and_precision() -> None:
    proto = transaction_view_to_proto(_txn_view(), tenant_id=_TENANT, description="Momentum")
    assert proto.id == str(_EVENT)
    assert proto.portfolio_id == str(_TENANT)
    # 7A: read-model `qty`/`occurred_at` map to proto `quantity`/`timestamp`.
    assert Decimal(proto.quantity.value) == Decimal("2.5")
    assert proto.timestamp.seconds == int(datetime(2026, 1, 2, tzinfo=UTC).timestamp())
    # 5A: money kept as Decimal.
    assert proto.amount.value == "250.625"
    assert Decimal(proto.fees.value) == Decimal("1")
    assert proto.description == "Momentum"


def test_transaction_type_string_maps_to_enum() -> None:
    """Enum caveat: string taxonomy -> int enum; transfers stay distinct from deposit."""
    assert transaction_view_to_proto(_txn_view("buy"), tenant_id=_TENANT).type == (
        portfolio_pb2.TRANSACTION_TYPE_BUY
    )
    transfer = transaction_view_to_proto(_txn_view("transfer_in"), tenant_id=_TENANT)
    assert transfer.type == portfolio_pb2.TRANSACTION_TYPE_TRANSFER_IN
    assert transfer.type != portfolio_pb2.TRANSACTION_TYPE_DEPOSIT


def test_transaction_null_qty_price_default_zero() -> None:
    view = TransactionView(
        event_id=str(_EVENT),
        type="deposit",
        symbol=None,
        qty=None,
        price=None,
        amount=Decimal("1000"),
        fees=Decimal("0"),
        occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    proto = transaction_view_to_proto(view, tenant_id=_TENANT)
    assert proto.symbol == ""
    assert Decimal(proto.quantity.value) == Decimal("0")
    assert Decimal(proto.price.value) == Decimal("0")


def test_transaction_bad_event_id_falls_back_to_zero_uuid() -> None:
    view = _txn_view()
    object.__setattr__(view, "event_id", "not-a-uuid")
    assert transaction_view_to_proto(view, tenant_id=_TENANT).id == str(UUID(int=0))


def test_transaction_completeness_no_unexpected_default() -> None:
    proto = transaction_view_to_proto(_txn_view(), tenant_id=_TENANT)
    for name in _decimal_field_names(proto):
        assert proto.HasField(name), f"{name} unexpectedly left at default"


def test_period_returns_present_keys_and_missing_zero() -> None:
    proto = period_returns_to_proto({"return_1d": Decimal("1.5"), "return_all": Decimal("42.0")})
    assert Decimal(proto.return_1d.value) == Decimal("1.5")
    assert Decimal(proto.return_all.value) == Decimal("42")
    # Missing keys collapse to "0" (not left unset) so aggregation stays numeric.
    assert proto.return_1m.value == "0"
    for name in _decimal_field_names(proto):
        assert proto.HasField(name)


def test_equity_point_sets_only_computed_fields() -> None:
    bare = equity_point_to_proto(timestamp=datetime(2026, 1, 1, tzinfo=UTC), equity=Decimal("100"))
    assert Decimal(bare.equity.value) == Decimal("100")
    for name in ("return_percent", "drawdown", "benchmark_value"):
        assert not bare.HasField(name)

    full = equity_point_to_proto(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        equity=Decimal("100"),
        return_percent=Decimal("5.5"),
        drawdown=Decimal("2.0"),
        benchmark_value=Decimal("101"),
    )
    assert Decimal(full.return_percent.value) == Decimal("5.5")
    assert Decimal(full.drawdown.value) == Decimal("2")
    assert Decimal(full.benchmark_value.value) == Decimal("101")


def test_benchmark_series_maps_points_and_return() -> None:
    points = [
        equity_point_to_proto(timestamp=datetime(2026, 1, 1, tzinfo=UTC), equity=Decimal("100")),
        equity_point_to_proto(timestamp=datetime(2026, 1, 2, tzinfo=UTC), equity=Decimal("110")),
    ]
    proto = benchmark_series_to_proto(symbol="SPY", points=points, total_return=Decimal("10.0"))
    assert proto.symbol == "SPY"
    assert proto.name == "SPY"
    assert len(proto.equity_curve) == 2
    assert Decimal(proto.total_return.value) == Decimal("10")


def test_benchmark_series_null_return_defaults_zero() -> None:
    proto = benchmark_series_to_proto(symbol="SPY", points=[], total_return=None)
    assert proto.total_return.value == "0"


def _summary_proto(
    *,
    allocated_capital: Decimal | None = Decimal("10000.00"),
    current_value: Decimal | None = Decimal("10500.00"),
    started_at: datetime | None = datetime(2026, 1, 1, tzinfo=UTC),
) -> portfolio_pb2.StrategyPerformanceSummary:
    return strategy_summary_to_proto(
        execution_id=UUID("33333333-3333-3333-3333-333333333333"),
        strategy_id=UUID("44444444-4444-4444-4444-444444444444"),
        strategy_name="Trend",
        mode=EXECUTION_MODE_PAPER,
        status=EXECUTION_STATUS_RUNNING,
        color="#fff",
        allocated_capital=allocated_capital,
        current_value=current_value,
        positions_count=2,
        returns=period_returns_to_proto({}),
        started_at=started_at,
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def test_strategy_summary_enum_and_precision() -> None:
    proto = _summary_proto()
    # Enum ints straight off the execution row — no string round-trip.
    assert proto.mode == EXECUTION_MODE_PAPER
    assert proto.status == EXECUTION_STATUS_RUNNING
    assert Decimal(proto.allocated_capital.value) == Decimal("10000")
    assert Decimal(proto.current_value.value) == Decimal("10500")
    assert proto.started_at.seconds == int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
    # All Decimal fields populated (aggregate reads stay numeric).
    for name in _decimal_field_names(proto):
        assert proto.HasField(name)


def test_strategy_summary_unfunded_defaults_zero_and_no_start() -> None:
    proto = _summary_proto(allocated_capital=None, current_value=None, started_at=None)
    assert proto.allocated_capital.value == "0"
    assert proto.current_value.value == "0"
    assert not proto.HasField("started_at")


def _equity_metrics() -> EquityMetrics:
    return EquityMetrics(
        total_return=250.0,
        total_return_percent=2.5,
        annualized_return=30.0,
        volatility=12.5,
        sharpe_ratio=1.8,
        sortino_ratio=2.1,
        max_drawdown=4.0,
        win_rate=60.0,
        profit_factor=1.9,
        best_day=3.0,
        worst_day=-2.0,
        avg_daily_return=0.4,
    )


def _trade_stats() -> TradeStats:
    return TradeStats(
        total_trades=5,
        winning_trades=3,
        losing_trades=2,
        win_rate=60.0,
        profit_factor=1.9,
        average_win=120.0,
        average_loss=50.0,
        realized_pnl=250.0,
    )


def test_live_metrics_maps_stats_and_series_metrics() -> None:
    proto = live_metrics_to_proto(
        _equity_metrics(),
        _trade_stats(),
        starting_capital=Decimal("10000"),
        current_equity=Decimal("10250"),
        peak_equity=Decimal("10300"),
        current_drawdown=Decimal("0.5"),
    )
    assert proto.total_trades == 5
    assert proto.winning_trades == 3
    # Money kept as Decimal (str-converted, no float artifact).
    assert Decimal(proto.total_pnl.value) == Decimal("250")
    assert Decimal(proto.starting_capital.value) == Decimal("10000")
    assert Decimal(proto.sharpe_ratio.value) == Decimal("1.8")
    assert Decimal(proto.max_drawdown.value) == Decimal("4")


def test_live_metrics_completeness_allowlist() -> None:
    proto = live_metrics_to_proto(
        _equity_metrics(),
        _trade_stats(),
        starting_capital=Decimal("10000"),
        current_equity=Decimal("10250"),
        peak_equity=Decimal("10300"),
        current_drawdown=Decimal("0.5"),
    )
    for name in _decimal_field_names(proto):
        if name in _LIVE_METRICS_UNSET_ALLOWLIST:
            assert not proto.HasField(name), f"{name} should be unset (uncomputed)"
        else:
            assert proto.HasField(name), f"{name} unexpectedly left at default"


def test_live_metrics_no_series_leaves_risk_metrics_unset() -> None:
    proto = live_metrics_to_proto(
        None,
        _trade_stats(),
        starting_capital=None,
        current_equity=None,
        peak_equity=None,
        current_drawdown=None,
    )
    # Series-derived metrics unset when there is no series...
    for name in ("sharpe_ratio", "sortino_ratio", "max_drawdown", "volatility"):
        assert not proto.HasField(name)
    # ...but trade stats are still present.
    assert proto.total_trades == 5
    assert Decimal(proto.win_rate.value) == Decimal("60")
