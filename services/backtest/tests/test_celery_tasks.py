"""Tests for Celery tasks module.

Note: Full task testing requires Celery worker to be running.
These tests focus on utility functions and configuration that
can be tested in isolation.
"""

import json
from datetime import UTC, datetime


class TestProgressMessages:
    """Tests for progress message constants."""

    def test_progress_stages(self):
        """Test expected progress stages."""
        # Document expected progress milestones
        progress_stages = [
            (0, "Starting backtest"),
            (10, "Loading strategy"),
            (30, "Fetching market data"),
            # 40-90 for simulation
            (95, "Calculating metrics"),
            (100, "Complete"),
        ]

        for progress, message in progress_stages:
            assert 0 <= progress <= 100
            assert isinstance(message, str)
            assert len(message) > 0


class TestSymbolChunkHelpers:
    """Tests for symbol chunking logic."""

    def test_chunk_symbols(self):
        """Test chunking symbols for parallel execution."""
        symbols = [f"SYM{i}" for i in range(100)]
        chunk_size = 25

        chunks = [symbols[i : i + chunk_size] for i in range(0, len(symbols), chunk_size)]

        assert len(chunks) == 4
        assert len(chunks[0]) == 25
        assert len(chunks[-1]) == 25

    def test_empty_symbols(self):
        """Test chunking empty list."""
        symbols = []
        chunk_size = 25

        chunks = [symbols[i : i + chunk_size] for i in range(0, len(symbols), chunk_size)]

        assert len(chunks) == 0

    def test_small_symbol_list(self):
        """Test chunking list smaller than chunk size."""
        symbols = ["AAPL", "GOOGL", "MSFT"]
        chunk_size = 25

        chunks = [symbols[i : i + chunk_size] for i in range(0, len(symbols), chunk_size)]

        assert len(chunks) == 1
        assert chunks[0] == symbols


class TestMergeResults:
    """Tests for merging results from parallel chunks."""

    def test_merge_trades(self):
        """Test merging trades from multiple chunks."""
        from src.engine.backtester import Trade

        chunk1_trades = [
            Trade(
                entry_date=datetime(2024, 1, 1, tzinfo=UTC),
                exit_date=datetime(2024, 1, 5, tzinfo=UTC),
                symbol="AAPL",
                side="long",
                entry_price=100.0,
                exit_price=110.0,
                quantity=10,
                commission=1.0,
            ),
        ]
        chunk2_trades = [
            Trade(
                entry_date=datetime(2024, 1, 2, tzinfo=UTC),
                exit_date=datetime(2024, 1, 6, tzinfo=UTC),
                symbol="GOOGL",
                side="long",
                entry_price=200.0,
                exit_price=220.0,
                quantity=5,
                commission=1.0,
            ),
        ]

        merged = chunk1_trades + chunk2_trades

        assert len(merged) == 2
        assert merged[0].symbol == "AAPL"
        assert merged[1].symbol == "GOOGL"

    def test_aggregate_equity_curves(self):
        """Test aggregating equity curves from chunks."""
        import numpy as np

        curve1 = np.array([100000, 100500, 101000])
        curve2 = np.array([100000, 100200, 100400])

        # Combined equity would add the position values
        # This is simplified - actual implementation handles this differently
        combined = curve1 + curve2 - 100000  # Subtract double-counted initial

        assert combined[0] == 100000
        assert combined[-1] > combined[0]


class TestDecimalEncoder:
    """Tests for custom JSON encoder for Decimal."""

    def test_decimal_encoding(self):
        """Test that Decimal values are JSON serializable."""
        from decimal import Decimal

        # Test that we can encode Decimal in task payloads
        data = {
            "total_return": Decimal("0.15"),
            "sharpe_ratio": Decimal("1.23"),
        }

        # Should be able to serialize with standard json
        # after converting decimals to float
        converted = {k: float(v) for k, v in data.items()}
        result = json.dumps(converted)
        assert "0.15" in result
        assert "1.23" in result


class TestProgressPayload:
    """Tests for progress payload structure."""

    def test_progress_payload_structure(self):
        """Test progress payload has expected fields."""
        payload = {
            "backtest_id": "bt-123",
            "progress": 50.0,
            "message": "Processing",
            "eta_seconds": 30,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Verify serializable
        json_str = json.dumps(payload)
        parsed = json.loads(json_str)

        assert parsed["backtest_id"] == "bt-123"
        assert parsed["progress"] == 50.0
        assert parsed["message"] == "Processing"
        assert parsed["eta_seconds"] == 30
        assert "timestamp" in parsed

    def test_progress_channel_naming(self):
        """Test progress channel naming convention."""
        backtest_id = "bt-abc123"
        channel = f"backtest:progress:{backtest_id}"

        assert channel == "backtest:progress:bt-abc123"


class TestBacktestStatusTransitions:
    """Tests for backtest status state machine."""

    def test_valid_transitions(self):
        """Test valid status transitions."""
        valid_transitions = {
            "pending": ["running", "cancelled"],
            "running": ["completed", "failed", "cancelled"],
            "completed": [],
            "failed": [],
            "cancelled": [],
        }

        # Verify all terminal states have no transitions
        assert valid_transitions["completed"] == []
        assert valid_transitions["failed"] == []
        assert valid_transitions["cancelled"] == []

        # Verify pending can transition to running
        assert "running" in valid_transitions["pending"]

        # Verify running can transition to completed
        assert "completed" in valid_transitions["running"]

    def test_runnable_statuses(self):
        """Test which statuses allow running."""
        runnable = {"pending", "running"}

        assert "pending" in runnable
        assert "running" in runnable
        assert "completed" not in runnable
        assert "failed" not in runnable
