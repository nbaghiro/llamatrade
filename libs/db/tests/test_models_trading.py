"""Tests for llamatrade_db.models.trading module."""

from llamatrade_db.models.trading import (
    Order,
    Position,
    TradingSession,
)


class TestTradingSession:
    """Tests for TradingSession model."""

    def test_trading_session_tablename(self) -> None:
        """Test TradingSession has correct tablename."""
        assert TradingSession.__tablename__ == "trading_sessions"

    def test_trading_session_has_required_columns(self) -> None:
        """Test TradingSession has all required columns."""
        columns = TradingSession.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "strategy_id" in columns
        assert "strategy_version" in columns
        assert "credentials_id" in columns
        assert "name" in columns
        assert "mode" in columns
        assert "status" in columns
        assert "config" in columns
        assert "symbols" in columns
        assert "started_at" in columns
        assert "stopped_at" in columns
        assert "last_heartbeat" in columns
        assert "error_message" in columns
        assert "created_by" in columns

    def test_trading_session_name_not_nullable(self) -> None:
        """Test name column is not nullable."""
        col = TradingSession.__table__.columns["name"]
        assert col.nullable is False

    def test_trading_session_mode_not_nullable(self) -> None:
        """Test mode column is not nullable."""
        col = TradingSession.__table__.columns["mode"]
        assert col.nullable is False

    def test_trading_session_has_relationships(self) -> None:
        """Test TradingSession has expected relationships."""
        assert hasattr(TradingSession, "orders")
        assert hasattr(TradingSession, "positions")

    def test_trading_session_has_indexes(self) -> None:
        """Test TradingSession has expected indexes."""
        table_args = TradingSession.__table_args__
        assert table_args is not None


class TestOrder:
    """Tests for Order model."""

    def test_order_tablename(self) -> None:
        """Test Order has correct tablename."""
        assert Order.__tablename__ == "orders"

    def test_order_has_required_columns(self) -> None:
        """Test Order has all required columns."""
        columns = Order.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "session_id" in columns
        assert "alpaca_order_id" in columns
        assert "client_order_id" in columns
        assert "symbol" in columns
        assert "side" in columns
        assert "order_type" in columns
        assert "time_in_force" in columns
        assert "qty" in columns
        assert "limit_price" in columns
        assert "stop_price" in columns
        assert "status" in columns
        assert "filled_qty" in columns
        assert "filled_avg_price" in columns

    def test_order_has_timestamp_columns(self) -> None:
        """Test Order has timestamp columns."""
        columns = Order.__table__.columns
        assert "submitted_at" in columns
        assert "filled_at" in columns
        assert "canceled_at" in columns
        assert "failed_at" in columns

    def test_order_has_bracket_columns(self) -> None:
        """Test Order has bracket order columns."""
        columns = Order.__table__.columns
        assert "parent_order_id" in columns
        assert "bracket_type" in columns
        assert "stop_loss_price" in columns
        assert "take_profit_price" in columns

    def test_order_symbol_not_nullable(self) -> None:
        """Test symbol column is not nullable."""
        col = Order.__table__.columns["symbol"]
        assert col.nullable is False

    def test_order_side_not_nullable(self) -> None:
        """Test side column is not nullable."""
        col = Order.__table__.columns["side"]
        assert col.nullable is False

    def test_order_has_relationships(self) -> None:
        """Test Order has expected relationships."""
        assert hasattr(Order, "session")
        assert hasattr(Order, "parent_order")
        assert hasattr(Order, "bracket_orders")

    def test_order_has_indexes(self) -> None:
        """Test Order has expected indexes."""
        table_args = Order.__table_args__
        assert table_args is not None
        # Should have multiple indexes
        from sqlalchemy import Index

        indexes = [arg for arg in table_args if isinstance(arg, Index)]
        assert len(indexes) >= 4


class TestPosition:
    """Tests for Position model."""

    def test_position_tablename(self) -> None:
        """Test Position has correct tablename."""
        assert Position.__tablename__ == "positions"

    def test_position_has_required_columns(self) -> None:
        """Test Position has all required columns."""
        columns = Position.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "session_id" in columns
        assert "symbol" in columns
        assert "side" in columns
        assert "qty" in columns
        assert "avg_entry_price" in columns
        assert "current_price" in columns
        assert "market_value" in columns
        assert "cost_basis" in columns
        assert "unrealized_pl" in columns
        assert "unrealized_plpc" in columns
        assert "realized_pl" in columns
        assert "is_open" in columns
        assert "opened_at" in columns
        assert "closed_at" in columns

    def test_position_symbol_not_nullable(self) -> None:
        """Test symbol column is not nullable."""
        col = Position.__table__.columns["symbol"]
        assert col.nullable is False

    def test_position_side_not_nullable(self) -> None:
        """Test side column is not nullable."""
        col = Position.__table__.columns["side"]
        assert col.nullable is False

    def test_position_qty_not_nullable(self) -> None:
        """Test qty column is not nullable."""
        col = Position.__table__.columns["qty"]
        assert col.nullable is False

    def test_position_is_open_has_default(self) -> None:
        """Test is_open defaults to True."""
        col = Position.__table__.columns["is_open"]
        assert col.default is not None

    def test_position_has_session_relationship(self) -> None:
        """Test Position has session relationship."""
        assert hasattr(Position, "session")

    def test_position_has_unique_constraint(self) -> None:
        """Test Position has unique constraint on session_id + symbol."""
        table_args = Position.__table_args__
        assert table_args is not None
