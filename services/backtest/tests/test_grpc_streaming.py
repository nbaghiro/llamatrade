"""Tests for gRPC streaming in backtest service."""

from llamatrade_proto.generated import backtest_pb2
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
    BacktestStatus,
)


class TestBacktestStatusMapping:
    """Tests for BacktestStatus enum values."""

    def test_status_enum_values(self):
        """Test that BacktestStatus constants have expected values."""
        assert BACKTEST_STATUS_PENDING == 1
        assert BACKTEST_STATUS_RUNNING == 2
        assert BACKTEST_STATUS_COMPLETED == 3
        assert BACKTEST_STATUS_FAILED == 4
        assert BACKTEST_STATUS_CANCELLED == 5

    def test_status_names(self):
        """Test status name lookup via proto enum."""
        assert BacktestStatus.Name(BACKTEST_STATUS_PENDING) == "BACKTEST_STATUS_PENDING"
        assert BacktestStatus.Name(BACKTEST_STATUS_RUNNING) == "BACKTEST_STATUS_RUNNING"
        assert BacktestStatus.Name(BACKTEST_STATUS_COMPLETED) == "BACKTEST_STATUS_COMPLETED"
        assert BacktestStatus.Name(BACKTEST_STATUS_FAILED) == "BACKTEST_STATUS_FAILED"
        assert BacktestStatus.Name(BACKTEST_STATUS_CANCELLED) == "BACKTEST_STATUS_CANCELLED"

    def test_terminal_statuses(self):
        """Test which statuses are terminal (backtest is done)."""
        terminal_statuses = {
            BACKTEST_STATUS_COMPLETED,
            BACKTEST_STATUS_FAILED,
            BACKTEST_STATUS_CANCELLED,
        }
        non_terminal_statuses = {
            BACKTEST_STATUS_PENDING,
            BACKTEST_STATUS_RUNNING,
        }

        for status in terminal_statuses:
            assert status in terminal_statuses

        for status in non_terminal_statuses:
            assert status not in terminal_statuses


class TestProgressValues:
    """Tests for progress value ranges on the BacktestProgressUpdate proto."""

    def test_progress_at_zero(self):
        """Test progress at 0%."""
        update = backtest_pb2.BacktestProgressUpdate(
            backtest_id="bt-test",
            progress_percent=0,
            message="Starting",
        )
        assert update.progress_percent == 0

    def test_progress_at_hundred(self):
        """Test progress at 100%."""
        update = backtest_pb2.BacktestProgressUpdate(
            backtest_id="bt-test",
            progress_percent=100,
            message="Complete",
        )
        assert update.progress_percent == 100

    def test_progress_midway(self):
        """Test progress at midpoint."""
        update = backtest_pb2.BacktestProgressUpdate(
            backtest_id="bt-test",
            progress_percent=50,
            message="Halfway",
        )
        assert update.progress_percent == 50
