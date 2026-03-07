"""Tests for llamatrade_db.models.portfolio module."""

from llamatrade_db.models.portfolio import (
    PerformanceMetrics,
    PortfolioHistory,
    PortfolioSummary,
    Transaction,
)


class TestPortfolioSummary:
    """Tests for PortfolioSummary model."""

    def test_portfolio_summary_tablename(self) -> None:
        """Test PortfolioSummary has correct tablename."""
        assert PortfolioSummary.__tablename__ == "portfolio_summary"

    def test_portfolio_summary_has_required_columns(self) -> None:
        """Test PortfolioSummary has all required columns."""
        columns = PortfolioSummary.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "equity" in columns
        assert "cash" in columns
        assert "buying_power" in columns
        assert "portfolio_value" in columns
        assert "daily_pl" in columns
        assert "daily_pl_percent" in columns
        assert "total_pl" in columns
        assert "total_pl_percent" in columns
        assert "positions" in columns
        assert "position_count" in columns
        assert "last_synced_at" in columns

    def test_portfolio_summary_equity_not_nullable(self) -> None:
        """Test equity column is not nullable."""
        col = PortfolioSummary.__table__.columns["equity"]
        assert col.nullable is False

    def test_portfolio_summary_cash_not_nullable(self) -> None:
        """Test cash column is not nullable."""
        col = PortfolioSummary.__table__.columns["cash"]
        assert col.nullable is False


class TestTransaction:
    """Tests for Transaction model."""

    def test_transaction_tablename(self) -> None:
        """Test Transaction has correct tablename."""
        assert Transaction.__tablename__ == "transactions"

    def test_transaction_has_required_columns(self) -> None:
        """Test Transaction has all required columns."""
        columns = Transaction.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "session_id" in columns
        assert "order_id" in columns
        assert "transaction_type" in columns
        assert "symbol" in columns
        assert "side" in columns
        assert "qty" in columns
        assert "price" in columns
        assert "amount" in columns
        assert "fees" in columns
        assert "net_amount" in columns
        assert "description" in columns
        assert "transaction_date" in columns
        assert "settlement_date" in columns
        assert "external_id" in columns

    def test_transaction_type_not_nullable(self) -> None:
        """Test transaction_type column is not nullable."""
        col = Transaction.__table__.columns["transaction_type"]
        assert col.nullable is False

    def test_transaction_amount_not_nullable(self) -> None:
        """Test amount column is not nullable."""
        col = Transaction.__table__.columns["amount"]
        assert col.nullable is False

    def test_transaction_has_indexes(self) -> None:
        """Test Transaction has expected indexes."""
        table_args = Transaction.__table_args__
        assert table_args is not None


class TestPortfolioHistory:
    """Tests for PortfolioHistory model."""

    def test_portfolio_history_tablename(self) -> None:
        """Test PortfolioHistory has correct tablename."""
        assert PortfolioHistory.__tablename__ == "portfolio_history"

    def test_portfolio_history_has_required_columns(self) -> None:
        """Test PortfolioHistory has all required columns."""
        columns = PortfolioHistory.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "snapshot_date" in columns
        assert "equity" in columns
        assert "cash" in columns
        assert "portfolio_value" in columns
        assert "daily_return" in columns
        assert "cumulative_return" in columns
        assert "positions_snapshot" in columns
        assert "created_at" in columns

    def test_portfolio_history_snapshot_date_not_nullable(self) -> None:
        """Test snapshot_date column is not nullable."""
        col = PortfolioHistory.__table__.columns["snapshot_date"]
        assert col.nullable is False

    def test_portfolio_history_equity_not_nullable(self) -> None:
        """Test equity column is not nullable."""
        col = PortfolioHistory.__table__.columns["equity"]
        assert col.nullable is False


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics model."""

    def test_performance_metrics_tablename(self) -> None:
        """Test PerformanceMetrics has correct tablename."""
        assert PerformanceMetrics.__tablename__ == "performance_metrics"

    def test_performance_metrics_has_period_columns(self) -> None:
        """Test PerformanceMetrics has period columns."""
        columns = PerformanceMetrics.__table__.columns
        assert "period_type" in columns
        assert "period_start" in columns
        assert "period_end" in columns

    def test_performance_metrics_has_return_columns(self) -> None:
        """Test PerformanceMetrics has return columns."""
        columns = PerformanceMetrics.__table__.columns
        assert "total_return" in columns
        assert "annualized_return" in columns

    def test_performance_metrics_has_risk_columns(self) -> None:
        """Test PerformanceMetrics has risk columns."""
        columns = PerformanceMetrics.__table__.columns
        assert "volatility" in columns
        assert "sharpe_ratio" in columns
        assert "sortino_ratio" in columns
        assert "max_drawdown" in columns
        assert "calmar_ratio" in columns

    def test_performance_metrics_has_trade_columns(self) -> None:
        """Test PerformanceMetrics has trade statistic columns."""
        columns = PerformanceMetrics.__table__.columns
        assert "total_trades" in columns
        assert "winning_trades" in columns
        assert "losing_trades" in columns
        assert "win_rate" in columns
        assert "profit_factor" in columns

    def test_performance_metrics_has_pnl_columns(self) -> None:
        """Test PerformanceMetrics has P&L columns."""
        columns = PerformanceMetrics.__table__.columns
        assert "realized_pl" in columns
        assert "unrealized_pl" in columns

    def test_performance_metrics_period_type_not_nullable(self) -> None:
        """Test period_type column is not nullable."""
        col = PerformanceMetrics.__table__.columns["period_type"]
        assert col.nullable is False

    def test_performance_metrics_total_return_not_nullable(self) -> None:
        """Test total_return column is not nullable."""
        col = PerformanceMetrics.__table__.columns["total_return"]
        assert col.nullable is False
