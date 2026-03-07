"""Tests for llamatrade_db.models.audit module."""

from llamatrade_db.models.audit import (
    AuditEventType,
    AuditLog,
    DailyPnL,
    RiskConfig,
)


class TestAuditEventType:
    """Tests for AuditEventType enum."""

    def test_signal_events(self) -> None:
        """Test signal event types exist."""
        assert AuditEventType.SIGNAL_GENERATED == "signal_generated"
        assert AuditEventType.SIGNAL_REJECTED == "signal_rejected"

    def test_order_events(self) -> None:
        """Test order event types exist."""
        assert AuditEventType.ORDER_SUBMITTED == "order_submitted"
        assert AuditEventType.ORDER_FILLED == "order_filled"
        assert AuditEventType.ORDER_PARTIAL_FILL == "order_partial_fill"
        assert AuditEventType.ORDER_CANCELLED == "order_cancelled"
        assert AuditEventType.ORDER_REJECTED == "order_rejected"
        assert AuditEventType.ORDER_EXPIRED == "order_expired"

    def test_position_events(self) -> None:
        """Test position event types exist."""
        assert AuditEventType.POSITION_OPENED == "position_opened"
        assert AuditEventType.POSITION_CLOSED == "position_closed"
        assert AuditEventType.POSITION_UPDATED == "position_updated"

    def test_risk_events(self) -> None:
        """Test risk event types exist."""
        assert AuditEventType.RISK_CHECK_PASSED == "risk_check_passed"
        assert AuditEventType.RISK_CHECK_FAILED == "risk_check_failed"
        assert AuditEventType.RISK_LIMIT_BREACH == "risk_limit_breach"

    def test_session_events(self) -> None:
        """Test session event types exist."""
        assert AuditEventType.SESSION_STARTED == "session_started"
        assert AuditEventType.SESSION_PAUSED == "session_paused"
        assert AuditEventType.SESSION_RESUMED == "session_resumed"
        assert AuditEventType.SESSION_STOPPED == "session_stopped"
        assert AuditEventType.SESSION_ERROR == "session_error"

    def test_system_events(self) -> None:
        """Test system event types exist."""
        assert AuditEventType.STRATEGY_LOADED == "strategy_loaded"
        assert AuditEventType.STRATEGY_ERROR == "strategy_error"
        assert AuditEventType.CONNECTION_LOST == "connection_lost"
        assert AuditEventType.CONNECTION_RESTORED == "connection_restored"

    def test_event_type_is_string_enum(self) -> None:
        """Test AuditEventType inherits from StrEnum."""
        event = AuditEventType.ORDER_FILLED
        assert isinstance(event, str)
        assert event == "order_filled"


class TestAuditLog:
    """Tests for AuditLog model."""

    def test_audit_log_tablename(self) -> None:
        """Test AuditLog has correct tablename."""
        assert AuditLog.__tablename__ == "audit_logs"

    def test_audit_log_has_required_columns(self) -> None:
        """Test AuditLog has all required columns."""
        columns = AuditLog.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "session_id" in columns
        assert "event_type" in columns
        assert "timestamp" in columns
        assert "symbol" in columns
        assert "order_id" in columns
        assert "data" in columns
        assert "summary" in columns
        assert "source" in columns

    def test_audit_log_event_type_not_nullable(self) -> None:
        """Test event_type column is not nullable."""
        col = AuditLog.__table__.columns["event_type"]
        assert col.nullable is False

    def test_audit_log_timestamp_not_nullable(self) -> None:
        """Test timestamp column is not nullable."""
        col = AuditLog.__table__.columns["timestamp"]
        assert col.nullable is False

    def test_audit_log_data_not_nullable(self) -> None:
        """Test data column is not nullable."""
        col = AuditLog.__table__.columns["data"]
        assert col.nullable is False

    def test_audit_log_session_id_nullable(self) -> None:
        """Test session_id is nullable."""
        col = AuditLog.__table__.columns["session_id"]
        assert col.nullable is True

    def test_audit_log_symbol_nullable(self) -> None:
        """Test symbol is nullable."""
        col = AuditLog.__table__.columns["symbol"]
        assert col.nullable is True

    def test_audit_log_has_indexes(self) -> None:
        """Test AuditLog has expected indexes."""
        table_args = AuditLog.__table_args__
        assert table_args is not None
        # Should have multiple indexes
        from sqlalchemy import Index

        indexes = [arg for arg in table_args if isinstance(arg, Index)]
        assert len(indexes) >= 4


class TestRiskConfig:
    """Tests for RiskConfig model."""

    def test_risk_config_tablename(self) -> None:
        """Test RiskConfig has correct tablename."""
        assert RiskConfig.__tablename__ == "risk_configs"

    def test_risk_config_has_required_columns(self) -> None:
        """Test RiskConfig has all required columns."""
        columns = RiskConfig.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "session_id" in columns

    def test_risk_config_has_position_limit_columns(self) -> None:
        """Test RiskConfig has position limit columns."""
        columns = RiskConfig.__table__.columns
        assert "max_position_size_pct" in columns
        assert "max_position_value" in columns
        assert "max_positions" in columns

    def test_risk_config_has_loss_limit_columns(self) -> None:
        """Test RiskConfig has loss limit columns."""
        columns = RiskConfig.__table__.columns
        assert "max_daily_loss_pct" in columns
        assert "max_daily_loss_value" in columns
        assert "max_drawdown_pct" in columns

    def test_risk_config_has_order_limit_columns(self) -> None:
        """Test RiskConfig has order limit columns."""
        columns = RiskConfig.__table__.columns
        assert "max_order_value" in columns
        assert "max_orders_per_minute" in columns
        assert "max_orders_per_day" in columns

    def test_risk_config_has_symbol_restriction_columns(self) -> None:
        """Test RiskConfig has symbol restriction columns."""
        columns = RiskConfig.__table__.columns
        assert "allowed_symbols" in columns
        assert "blocked_symbols" in columns

    def test_risk_config_has_active_flag(self) -> None:
        """Test RiskConfig has is_active column."""
        columns = RiskConfig.__table__.columns
        assert "is_active" in columns
        col = columns["is_active"]
        assert col.nullable is False
        assert col.default is not None

    def test_risk_config_session_id_nullable(self) -> None:
        """Test session_id is nullable (for tenant-wide config)."""
        col = RiskConfig.__table__.columns["session_id"]
        assert col.nullable is True

    def test_risk_config_has_indexes(self) -> None:
        """Test RiskConfig has expected indexes."""
        table_args = RiskConfig.__table_args__
        assert table_args is not None


class TestDailyPnL:
    """Tests for DailyPnL model."""

    def test_daily_pnl_tablename(self) -> None:
        """Test DailyPnL has correct tablename."""
        assert DailyPnL.__tablename__ == "daily_pnl"

    def test_daily_pnl_has_required_columns(self) -> None:
        """Test DailyPnL has all required columns."""
        columns = DailyPnL.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "session_id" in columns
        assert "date" in columns

    def test_daily_pnl_has_pnl_columns(self) -> None:
        """Test DailyPnL has P&L columns."""
        columns = DailyPnL.__table__.columns
        assert "realized_pnl" in columns
        assert "unrealized_pnl" in columns
        assert "total_pnl" in columns

    def test_daily_pnl_has_equity_columns(self) -> None:
        """Test DailyPnL has equity tracking columns."""
        columns = DailyPnL.__table__.columns
        assert "equity_start" in columns
        assert "equity_high" in columns
        assert "equity_low" in columns
        assert "equity_end" in columns

    def test_daily_pnl_has_drawdown_column(self) -> None:
        """Test DailyPnL has drawdown column."""
        columns = DailyPnL.__table__.columns
        assert "max_drawdown_pct" in columns

    def test_daily_pnl_has_trade_stats_columns(self) -> None:
        """Test DailyPnL has trade statistics columns."""
        columns = DailyPnL.__table__.columns
        assert "trades_count" in columns
        assert "winning_trades" in columns
        assert "losing_trades" in columns

    def test_daily_pnl_session_id_not_nullable(self) -> None:
        """Test session_id is not nullable."""
        col = DailyPnL.__table__.columns["session_id"]
        assert col.nullable is False

    def test_daily_pnl_date_not_nullable(self) -> None:
        """Test date is not nullable."""
        col = DailyPnL.__table__.columns["date"]
        assert col.nullable is False

    def test_daily_pnl_equity_start_not_nullable(self) -> None:
        """Test equity_start is not nullable."""
        col = DailyPnL.__table__.columns["equity_start"]
        assert col.nullable is False

    def test_daily_pnl_equity_end_nullable(self) -> None:
        """Test equity_end is nullable (intraday)."""
        col = DailyPnL.__table__.columns["equity_end"]
        assert col.nullable is True

    def test_daily_pnl_pnl_defaults(self) -> None:
        """Test P&L columns have defaults."""
        columns = DailyPnL.__table__.columns
        assert columns["realized_pnl"].default is not None
        assert columns["unrealized_pnl"].default is not None
        assert columns["total_pnl"].default is not None

    def test_daily_pnl_trade_stats_defaults(self) -> None:
        """Test trade stats have defaults."""
        columns = DailyPnL.__table__.columns
        assert columns["trades_count"].default is not None
        assert columns["winning_trades"].default is not None
        assert columns["losing_trades"].default is not None

    def test_daily_pnl_has_indexes(self) -> None:
        """Test DailyPnL has expected indexes."""
        table_args = DailyPnL.__table_args__
        assert table_args is not None
        # Should have indexes including unique constraint on session_id + date
        from sqlalchemy import Index

        indexes = [arg for arg in table_args if isinstance(arg, Index)]
        assert len(indexes) >= 2
