"""Behavioural pins for llamatrade_db.models.trading.

Column presence and nullability are proven against the migrated schema by the
metadata-drift test (``test_migrated_schema_pg.py``); what stays here are the
intent pins: defaults with a semantic reason and named uniqueness rules.
"""

from sqlalchemy import UniqueConstraint

from llamatrade_db.models.trading import (
    Order,
    Position,
    TradingSession,
)
from llamatrade_proto.generated import common_pb2


class TestTradingSession:
    def test_status_defaults_to_stopped(self) -> None:
        """A session created without an explicit status is stopped, not paused —
        a 'paused' default reads as a live session waiting to resume."""
        col = TradingSession.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == common_pb2.EXECUTION_STATUS_STOPPED
        assert col.default.arg != common_pb2.EXECUTION_STATUS_PAUSED


class TestOrder:
    def test_client_order_id_unique_constraint(self) -> None:
        """Idempotent submission (crash recovery) rides on this named constraint."""
        constraint = next(
            c
            for c in Order.__table__.constraints
            if isinstance(c, UniqueConstraint) and c.name == "uq_orders_client_order_id"
        )
        assert [c.name for c in constraint.columns] == ["client_order_id"]


class TestPosition:
    def test_one_open_position_per_session_and_symbol(self) -> None:
        """The named unique index enforces one position row per (session, symbol)."""
        (index,) = [i for i in Position.__table__.indexes if i.unique]
        assert index.name == "ix_positions_session_symbol"
        assert [c.name for c in index.columns] == ["session_id", "symbol"]

    def test_is_open_defaults_true(self) -> None:
        column = Position.__table__.columns["is_open"]
        assert column.default is not None and column.default.arg is True
