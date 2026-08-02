"""Equity-snapshot pure-core tests."""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

from sqlalchemy.dialects import postgresql

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


def test_compute_skips_sleeve_when_held_symbol_unpriced() -> None:
    # A market-data gap (held symbol has no price) must skip the sleeve, not
    # persist a cost-valued point that would distort the immutable curve.
    assert compute_snapshot_values(_proj(), {}, sequence=1) == []


async def test_snapshot_account_persists_rows() -> None:
    """The DB writer inserts one SleeveSnapshot per non-empty sleeve, idempotently."""
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
    db.execute = AsyncMock()
    db.scalar = AsyncMock(return_value=7)  # latest sequence
    account = SimpleNamespace(id=account_id, tenant_id=tenant)

    n = await snapshot_account(db, cast(Any, projector), cast(Any, prices), cast(Any, account))
    assert n == 1
    compiled = db.execute.call_args[0][0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert SleeveSnapshot.__tablename__ in sql
    # A repeat at the same ledger sequence within a day is not a second point but a
    # fresher mark: on conflict the row is UPDATED when the incoming created_at is
    # newer (last-mark-of-day wins), not dropped.
    assert "ON CONFLICT" in sql and "DO UPDATE" in sql
    assert compiled.params["equity_m0"] == Decimal("3000")  # 1000 + 10*200
    assert compiled.params["as_of_sequence_m0"] == 7
    assert compiled.params["sleeve_id_m0"] == sleeve_id


async def test_snapshot_pass_discards_its_writes_when_leadership_is_lost() -> None:
    """The fence sits between the read/price phase and the first commit.

    A leader torn mid-pass must not commit work it started as leader — the peer
    that took the lock is already sweeping, and both landing points at the same
    ledger sequence is exactly the duplicate the election exists to prevent.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    from src.tasks.equity_snapshot import run_snapshot_pass

    account = SimpleNamespace(id=uuid4(), tenant_id=uuid4())
    proj = AccountProjection()
    proj.sleeve(str(uuid4())).cash = Decimal("1000")

    async def not_leader() -> bool:
        return False

    with (
        patch("src.tasks.equity_snapshot.system_session") as system,
        patch("src.tasks.equity_snapshot.tenant_session") as tenant,
        patch("src.tasks.equity_snapshot._load_accounts", AsyncMock(return_value=[account])),
        patch("src.tasks.equity_snapshot._latest_sequence", AsyncMock(return_value=4)),
        patch("src.tasks.equity_snapshot.LedgerProjector") as projector,
    ):
        system.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        system.return_value.__aexit__ = AsyncMock(return_value=False)
        projector.return_value.project_account = AsyncMock(return_value=proj)
        prices = SimpleNamespace(get_prices=AsyncMock(return_value={}))

        written = await run_snapshot_pass(
            cast(Any, MagicMock()), cast(Any, prices), is_leader=not_leader
        )

    assert written == 0
    tenant.assert_not_called()  # no transaction was even opened
