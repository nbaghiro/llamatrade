"""Equity-snapshot pure-core tests."""

from decimal import Decimal

from src.ledger.projection import AccountProjection, PositionState, SleeveProjection
from src.tasks.equity_snapshot import compute_snapshot_values, projection_symbols


def _proj() -> AccountProjection:
    acc = AccountProjection()
    s = acc.sleeve("sleeve-1")
    s.cash = Decimal("1000")
    s.reserved = Decimal("200")
    s.positions["AAPL"] = PositionState(qty=Decimal("10"), cost_basis=Decimal("1500"))
    # An empty sleeve that should be skipped.
    acc.sleeves["empty"] = SleeveProjection()
    return acc


def test_projection_symbols_dedupes_and_sorts() -> None:
    acc = AccountProjection()
    acc.sleeve("a").positions["TSLA"] = PositionState(qty=Decimal("1"))
    acc.sleeve("b").positions["AAPL"] = PositionState(qty=Decimal("1"))
    acc.sleeve("c").positions["AAPL"] = PositionState(qty=Decimal("2"))
    assert projection_symbols(acc) == ["AAPL", "TSLA"]


def test_compute_marks_to_market_and_skips_empty() -> None:
    values = compute_snapshot_values(_proj(), {"AAPL": Decimal("200")}, sequence=42)
    assert len(values) == 1  # empty sleeve skipped
    v = values[0]
    assert v.sleeve_id == "sleeve-1"
    assert v.as_of_sequence == 42
    assert v.cash_balance == Decimal("1000")
    assert v.reserved_cash == Decimal("200")
    # equity = cash 1000 + 10 * 200 = 3000
    assert v.equity == Decimal("3000")
    assert v.lots == [{"symbol": "AAPL", "qty": "10", "cost_basis": "1500"}]


def test_compute_values_positions_without_price_use_cost() -> None:
    values = compute_snapshot_values(_proj(), {}, sequence=1)  # no prices
    # equity = cash 1000 + cost_basis 1500 = 2500 (valued at cost)
    assert values[0].equity == Decimal("2500")


async def test_snapshot_account_persists_rows() -> None:
    """The DB writer builds one SleeveSnapshot per non-empty sleeve."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    from llamatrade_db.models.ledger import SleeveSnapshot

    from src.tasks.equity_snapshot import snapshot_account

    tenant, account_id = uuid4(), uuid4()
    sleeve_id = uuid4()
    proj = AccountProjection()
    s = proj.sleeve(str(sleeve_id))
    s.cash = Decimal("1000")
    s.positions["AAPL"] = PositionState(qty=Decimal("10"), cost_basis=Decimal("1500"))

    projector = SimpleNamespace(project_account=AsyncMock(return_value=proj))
    prices = SimpleNamespace(get_prices=AsyncMock(return_value={"AAPL": Decimal("200")}))
    db = MagicMock()
    db.add = MagicMock()
    db.scalar = AsyncMock(return_value=7)  # latest sequence
    account = SimpleNamespace(id=account_id, tenant_id=tenant)

    n = await snapshot_account(db, projector, prices, account)
    assert n == 1
    added = db.add.call_args[0][0]
    assert isinstance(added, SleeveSnapshot)
    assert added.equity == Decimal("3000")  # 1000 + 10*200
    assert added.as_of_sequence == 7
    assert added.sleeve_id == sleeve_id
