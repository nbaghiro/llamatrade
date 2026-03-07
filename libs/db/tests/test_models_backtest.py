"""Tests for llamatrade_db.models.backtest module."""

from llamatrade_db.models.backtest import (
    Backtest,
    BacktestResult,
)


class TestBacktest:
    """Tests for Backtest model."""

    def test_backtest_tablename(self) -> None:
        """Test Backtest has correct tablename."""
        assert Backtest.__tablename__ == "backtests"

    def test_backtest_has_required_columns(self) -> None:
        """Test Backtest has all required columns."""
        columns = Backtest.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "strategy_id" in columns
        assert "strategy_version" in columns
        assert "name" in columns
        assert "status" in columns
        assert "config" in columns
        assert "symbols" in columns
        assert "start_date" in columns
        assert "end_date" in columns
        assert "initial_capital" in columns
        assert "started_at" in columns
        assert "completed_at" in columns
        assert "error_message" in columns
        assert "created_by" in columns

    def test_backtest_name_not_nullable(self) -> None:
        """Test name column is not nullable."""
        col = Backtest.__table__.columns["name"]
        assert col.nullable is False

    def test_backtest_initial_capital_not_nullable(self) -> None:
        """Test initial_capital is not nullable."""
        col = Backtest.__table__.columns["initial_capital"]
        assert col.nullable is False

    def test_backtest_has_results_relationship(self) -> None:
        """Test Backtest has results relationship."""
        assert hasattr(Backtest, "results")

    def test_backtest_has_indexes(self) -> None:
        """Test Backtest has expected indexes."""
        table_args = Backtest.__table_args__
        assert table_args is not None


class TestBacktestResult:
    """Tests for BacktestResult model."""

    def test_backtest_result_tablename(self) -> None:
        """Test BacktestResult has correct tablename."""
        assert BacktestResult.__tablename__ == "backtest_results"

    def test_backtest_result_has_performance_metrics(self) -> None:
        """Test BacktestResult has performance metric columns."""
        columns = BacktestResult.__table__.columns
        assert "total_return" in columns
        assert "annual_return" in columns
        assert "sharpe_ratio" in columns
        assert "sortino_ratio" in columns
        assert "max_drawdown" in columns
        assert "max_drawdown_duration" in columns
        assert "win_rate" in columns
        assert "profit_factor" in columns
        assert "exposure_time" in columns

    def test_backtest_result_has_trade_statistics(self) -> None:
        """Test BacktestResult has trade statistic columns."""
        columns = BacktestResult.__table__.columns
        assert "total_trades" in columns
        assert "winning_trades" in columns
        assert "losing_trades" in columns
        assert "avg_trade_return" in columns

    def test_backtest_result_has_final_state(self) -> None:
        """Test BacktestResult has final state columns."""
        columns = BacktestResult.__table__.columns
        assert "final_equity" in columns

    def test_backtest_result_has_detailed_data(self) -> None:
        """Test BacktestResult has detailed data columns."""
        columns = BacktestResult.__table__.columns
        assert "equity_curve" in columns
        assert "trades" in columns
        assert "daily_returns" in columns
        assert "monthly_returns" in columns

    def test_backtest_result_has_benchmark_data(self) -> None:
        """Test BacktestResult has benchmark comparison columns."""
        columns = BacktestResult.__table__.columns
        assert "benchmark_return" in columns
        assert "benchmark_symbol" in columns
        assert "alpha" in columns
        assert "beta" in columns
        assert "information_ratio" in columns
        assert "benchmark_equity_curve" in columns

    def test_backtest_result_backtest_id_unique(self) -> None:
        """Test backtest_id is unique (one result per backtest)."""
        col = BacktestResult.__table__.columns["backtest_id"]
        assert col.unique is True

    def test_backtest_result_has_backtest_relationship(self) -> None:
        """Test BacktestResult has backtest relationship."""
        assert hasattr(BacktestResult, "backtest")

    def test_total_return_not_nullable(self) -> None:
        """Test total_return is not nullable."""
        col = BacktestResult.__table__.columns["total_return"]
        assert col.nullable is False

    def test_sharpe_ratio_not_nullable(self) -> None:
        """Test sharpe_ratio is not nullable."""
        col = BacktestResult.__table__.columns["sharpe_ratio"]
        assert col.nullable is False

    def test_max_drawdown_not_nullable(self) -> None:
        """Test max_drawdown is not nullable."""
        col = BacktestResult.__table__.columns["max_drawdown"]
        assert col.nullable is False

    def test_win_rate_not_nullable(self) -> None:
        """Test win_rate is not nullable."""
        col = BacktestResult.__table__.columns["win_rate"]
        assert col.nullable is False
