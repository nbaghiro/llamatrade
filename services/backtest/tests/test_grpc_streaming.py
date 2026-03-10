"""Tests for gRPC streaming in backtest service."""

import json

import pytest

from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
    BacktestStatus,
)

from src.progress import ProgressUpdate


class TestProgressUpdateSerialization:
    """Tests for ProgressUpdate serialization."""

    def test_progress_update_to_dict(self):
        """Test that ProgressUpdate serializes correctly."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=75.0,
            message="Processing indicators",
            eta_seconds=45,
            timestamp="2024-01-01T12:00:00Z",
        )

        result = update.to_dict()

        assert result["backtest_id"] == "bt-123"
        assert result["progress"] == 75.0
        assert result["message"] == "Processing indicators"
        assert result["eta_seconds"] == 45
        assert result["timestamp"] == "2024-01-01T12:00:00Z"

    def test_progress_update_json_serializable(self):
        """Test that ProgressUpdate is JSON serializable."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=100.0,
            message="Complete",
        )

        json_str = json.dumps(update.to_dict())
        assert "bt-123" in json_str
        assert "100.0" in json_str

    def test_progress_update_generates_timestamp(self):
        """Test that ProgressUpdate generates timestamp if not provided."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=50.0,
            message="Processing",
        )

        result = update.to_dict()
        assert result["timestamp"] is not None
        assert "T" in result["timestamp"]

    def test_progress_update_with_eta(self):
        """Test ProgressUpdate with ETA."""
        update = ProgressUpdate(
            backtest_id="bt-456",
            progress=25.0,
            message="Quarter done",
            eta_seconds=180,
        )

        result = update.to_dict()
        assert result["eta_seconds"] == 180

    def test_progress_update_without_eta(self):
        """Test ProgressUpdate without ETA."""
        update = ProgressUpdate(
            backtest_id="bt-789",
            progress=0.0,
            message="Starting",
        )

        result = update.to_dict()
        assert result["eta_seconds"] is None


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
    """Tests for progress value ranges."""

    def test_progress_at_zero(self):
        """Test progress at 0%."""
        update = ProgressUpdate(
            backtest_id="bt-test",
            progress=0.0,
            message="Starting",
        )
        assert update.progress == 0.0

    def test_progress_at_hundred(self):
        """Test progress at 100%."""
        update = ProgressUpdate(
            backtest_id="bt-test",
            progress=100.0,
            message="Complete",
        )
        assert update.progress == 100.0

    def test_progress_midway(self):
        """Test progress at midpoint."""
        update = ProgressUpdate(
            backtest_id="bt-test",
            progress=50.0,
            message="Halfway",
        )
        assert update.progress == 50.0

    def test_progress_fractional(self):
        """Test fractional progress values."""
        update = ProgressUpdate(
            backtest_id="bt-test",
            progress=33.33,
            message="One third",
        )
        assert update.progress == pytest.approx(33.33)
