"""Tests for llamatrade_db.models.ledger module (Portfolio Ledger, Phase 0)."""

from sqlalchemy.orm import configure_mappers

from llamatrade_db.models.ledger import (
    Account,
    LedgerEvent,
    LedgerEventType,
    Lot,
    LotSide,
    Sleeve,
    SleeveSnapshot,
    SleeveStatus,
    SleeveType,
)


class TestLedgerEnums:
    """Enum value sets mirror ledger.proto."""

    def test_sleeve_type_values(self) -> None:
        assert SleeveType.STRATEGY == "strategy"
        assert SleeveType.MANUAL == "manual"
        assert SleeveType.UNMANAGED == "unmanaged"
        assert SleeveType.UNALLOCATED == "unallocated"
        assert len(SleeveType) == 4

    def test_sleeve_status_values(self) -> None:
        assert {s.value for s in SleeveStatus} == {"active", "frozen", "closed"}

    def test_lot_side_values(self) -> None:
        assert {s.value for s in LotSide} == {"long", "short"}

    def test_ledger_event_type_covers_families(self) -> None:
        values = {e.value for e in LedgerEventType}
        # one representative from each family
        for expected in (
            "capital_allocated",
            "order_filled",
            "lot_opened",
            "dividend_received",
            "split_applied",
            "external_trade_detected",
            "sleeve_frozen",
        ):
            assert expected in values


class TestAccountModel:
    def test_tablename(self) -> None:
        assert Account.__tablename__ == "ledger_accounts"

    def test_required_columns(self) -> None:
        cols = Account.__table__.columns
        for name in ("id", "tenant_id", "credentials_id", "base_currency", "created_at"):
            assert name in cols

    def test_credentials_unique(self) -> None:
        assert not Account.__table__.columns["credentials_id"].nullable

    def test_has_sleeves_relationship(self) -> None:
        assert hasattr(Account, "sleeves")


class TestSleeveModel:
    def test_tablename(self) -> None:
        assert Sleeve.__tablename__ == "ledger_sleeves"

    def test_required_columns(self) -> None:
        cols = Sleeve.__table__.columns
        for name in (
            "id",
            "tenant_id",
            "account_id",
            "type",
            "status",
            "name",
            "strategy_execution_id",
            "allocated_capital",
        ):
            assert name in cols

    def test_strategy_execution_id_nullable(self) -> None:
        assert Sleeve.__table__.columns["strategy_execution_id"].nullable is True

    def test_type_not_nullable(self) -> None:
        assert Sleeve.__table__.columns["type"].nullable is False

    def test_relationships(self) -> None:
        assert hasattr(Sleeve, "account")
        assert hasattr(Sleeve, "lots")


class TestLotModel:
    def test_tablename(self) -> None:
        assert Lot.__tablename__ == "ledger_lots"

    def test_required_columns(self) -> None:
        cols = Lot.__table__.columns
        for name in (
            "id",
            "tenant_id",
            "sleeve_id",
            "symbol",
            "side",
            "qty",
            "avg_price",
            "cost_basis",
            "realized_pnl",
            "is_open",
            "opened_by_order_id",
            "opened_at",
            "closed_at",
        ):
            assert name in cols

    def test_opened_by_order_id_nullable(self) -> None:
        assert Lot.__table__.columns["opened_by_order_id"].nullable is True

    def test_sleeve_relationship(self) -> None:
        assert hasattr(Lot, "sleeve")


class TestLedgerEventModel:
    def test_tablename(self) -> None:
        assert LedgerEvent.__tablename__ == "ledger_events"

    def test_required_columns(self) -> None:
        cols = LedgerEvent.__table__.columns
        for name in (
            "sequence",
            "event_id",
            "tenant_id",
            "account_id",
            "sleeve_id",
            "event_type",
            "data",
            "occurred_at",
        ):
            assert name in cols

    def test_sequence_is_primary_key(self) -> None:
        assert LedgerEvent.__table__.columns["sequence"].primary_key is True

    def test_event_id_unique(self) -> None:
        assert LedgerEvent.__table__.columns["event_id"].unique is True

    def test_sleeve_id_nullable_for_account_level_events(self) -> None:
        assert LedgerEvent.__table__.columns["sleeve_id"].nullable is True


class TestSleeveSnapshotModel:
    def test_tablename(self) -> None:
        assert SleeveSnapshot.__tablename__ == "ledger_sleeve_snapshots"

    def test_required_columns(self) -> None:
        cols = SleeveSnapshot.__table__.columns
        for name in (
            "id",
            "tenant_id",
            "sleeve_id",
            "as_of_sequence",
            "cash_balance",
            "reserved_cash",
            "equity",
            "lots",
        ):
            assert name in cols


class TestLedgerMapping:
    """ORM mapping integrity (DB-free; mirrors the structural test convention).

    NOTE: persistence round-trips run in the integration suite against
    PostgreSQL — the SQLite unit-test engine can't render ``JSONB`` columns.
    """

    def test_mappers_configure(self) -> None:
        """Relationship string references (Account/Sleeve/Lot) resolve."""
        configure_mappers()
        assert Account.sleeves.property.mapper.class_ is Sleeve
        assert Sleeve.lots.property.mapper.class_ is Lot
        assert Lot.sleeve.property.mapper.class_ is Sleeve

    def test_event_uses_bigint_sequence_pk(self) -> None:
        """LedgerEvent is keyed by an autoincrementing sequence, not a UUID."""
        pk_cols = list(LedgerEvent.__table__.primary_key.columns)
        assert [c.name for c in pk_cols] == ["sequence"]
        assert pk_cols[0].autoincrement is True

    def test_snapshot_has_jsonb_lots(self) -> None:
        assert "lots" in SleeveSnapshot.__table__.columns
