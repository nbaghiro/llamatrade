"""Test audit service."""

from datetime import UTC, datetime

import pytest
from src.models import OrderResponse, OrderStatus, RiskCheckResult
from src.runner.runner import Signal
from src.services.audit_service import AuditService


@pytest.fixture
def audit_service(mock_db):
    """Create audit service with mocked database."""
    return AuditService(mock_db)


@pytest.fixture
def sample_signal():
    """Create a sample signal."""
    return Signal(
        type="buy",
        symbol="AAPL",
        quantity=10.0,
        price=150.0,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def sample_order_response(order_id):
    """Create a sample order response."""
    return OrderResponse(
        id=order_id,
        alpaca_order_id="alpaca-123",
        symbol="AAPL",
        side="buy",
        qty=10.0,
        order_type="market",
        status=OrderStatus.FILLED,
        filled_qty=10.0,
        filled_avg_price=150.50,
        submitted_at=datetime.now(UTC),
        filled_at=datetime.now(UTC),
    )


class TestAuditServiceSignals:
    """Tests for signal logging."""

    async def test_log_signal(self, audit_service, mock_db, tenant_id, session_id, sample_signal):
        """Test logging a generated signal."""
        await audit_service.log_signal(
            tenant_id=tenant_id,
            session_id=session_id,
            signal=sample_signal,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify the log entry
        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "signal_generated"
        assert log_entry.symbol == "AAPL"
        assert log_entry.data["signal_type"] == "buy"
        assert log_entry.data["quantity"] == 10.0

    async def test_log_signal_rejected(
        self, audit_service, mock_db, tenant_id, session_id, sample_signal
    ):
        """Test logging a rejected signal."""
        await audit_service.log_signal_rejected(
            tenant_id=tenant_id,
            session_id=session_id,
            signal=sample_signal,
            reason="Risk check failed",
        )

        mock_db.add.assert_called_once()
        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "signal_rejected"
        assert log_entry.data["rejection_reason"] == "Risk check failed"


class TestAuditServiceOrders:
    """Tests for order logging."""

    async def test_log_order_submitted(
        self, audit_service, mock_db, tenant_id, session_id, sample_order_response
    ):
        """Test logging order submission."""
        await audit_service.log_order_submitted(
            tenant_id=tenant_id,
            session_id=session_id,
            order=sample_order_response,
        )

        mock_db.add.assert_called_once()
        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "order_submitted"
        assert log_entry.symbol == "AAPL"
        assert log_entry.order_id == sample_order_response.id

    async def test_log_order_filled(
        self, audit_service, mock_db, tenant_id, session_id, sample_order_response
    ):
        """Test logging order fill."""
        await audit_service.log_order_filled(
            tenant_id=tenant_id,
            session_id=session_id,
            order=sample_order_response,
        )

        mock_db.add.assert_called_once()
        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "order_filled"
        assert log_entry.data["filled_qty"] == 10.0
        assert log_entry.data["filled_avg_price"] == 150.50

    async def test_log_order_partial_fill(
        self, audit_service, mock_db, tenant_id, session_id, sample_order_response
    ):
        """Test logging partial order fill."""
        sample_order_response.filled_qty = 5.0  # Partial fill

        await audit_service.log_order_filled(
            tenant_id=tenant_id,
            session_id=session_id,
            order=sample_order_response,
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "order_partial_fill"

    async def test_log_order_cancelled(
        self, audit_service, mock_db, tenant_id, session_id, sample_order_response
    ):
        """Test logging order cancellation."""
        await audit_service.log_order_cancelled(
            tenant_id=tenant_id,
            session_id=session_id,
            order=sample_order_response,
            reason="User requested",
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "order_cancelled"
        assert log_entry.data["reason"] == "User requested"

    async def test_log_order_rejected(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging order rejection."""
        await audit_service.log_order_rejected(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            side="buy",
            qty=100.0,
            reason="Insufficient buying power",
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "order_rejected"
        assert log_entry.data["rejection_reason"] == "Insufficient buying power"


class TestAuditServiceRisk:
    """Tests for risk logging."""

    async def test_log_risk_check_passed(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging passed risk check."""
        result = RiskCheckResult(passed=True, violations=[])

        await audit_service.log_risk_check(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            result=result,
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "risk_check_passed"
        assert log_entry.data["passed"] is True

    async def test_log_risk_check_failed(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging failed risk check."""
        result = RiskCheckResult(
            passed=False,
            violations=["Order value exceeds limit"],
        )

        await audit_service.log_risk_check(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            result=result,
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "risk_check_failed"
        assert log_entry.data["passed"] is False
        assert "Order value exceeds limit" in log_entry.data["violations"]

    async def test_log_risk_breach(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging risk limit breach."""
        await audit_service.log_risk_breach(
            tenant_id=tenant_id,
            session_id=session_id,
            breach_type="daily_loss",
            details={"current_loss": -1500.0, "limit": 1000.0},
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "risk_limit_breach"
        assert log_entry.data["breach_type"] == "daily_loss"


class TestAuditServicePositions:
    """Tests for position logging."""

    async def test_log_position_opened(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging position opened."""
        await audit_service.log_position_opened(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            side="long",
            qty=10.0,
            entry_price=150.0,
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "position_opened"
        assert log_entry.data["side"] == "long"
        assert log_entry.data["entry_price"] == 150.0

    async def test_log_position_closed(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging position closed."""
        await audit_service.log_position_closed(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            qty=10.0,
            entry_price=150.0,
            exit_price=155.0,
            pnl=50.0,
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "position_closed"
        assert log_entry.data["pnl"] == 50.0


class TestAuditServiceSessions:
    """Tests for session logging."""

    async def test_log_session_started(
        self, audit_service, mock_db, tenant_id, session_id, strategy_id
    ):
        """Test logging session start."""
        await audit_service.log_session_started(
            tenant_id=tenant_id,
            session_id=session_id,
            strategy_id=strategy_id,
            mode="paper",
            symbols=["AAPL", "GOOGL"],
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "session_started"
        assert log_entry.data["mode"] == "paper"
        assert "AAPL" in log_entry.data["symbols"]

    async def test_log_session_stopped(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging session stop."""
        await audit_service.log_session_stopped(
            tenant_id=tenant_id,
            session_id=session_id,
            reason="User requested",
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "session_stopped"
        assert log_entry.data["reason"] == "User requested"

    async def test_log_session_paused(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging session pause."""
        await audit_service.log_session_paused(
            tenant_id=tenant_id,
            session_id=session_id,
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "session_paused"

    async def test_log_session_resumed(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging session resume."""
        await audit_service.log_session_resumed(
            tenant_id=tenant_id,
            session_id=session_id,
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "session_resumed"

    async def test_log_session_error(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging session error."""
        await audit_service.log_session_error(
            tenant_id=tenant_id,
            session_id=session_id,
            error="Connection timeout",
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "session_error"
        assert log_entry.data["error"] == "Connection timeout"


class TestAuditServiceErrors:
    """Tests for error and connection logging."""

    async def test_log_strategy_error(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging strategy error."""
        await audit_service.log_strategy_error(
            tenant_id=tenant_id,
            session_id=session_id,
            error="Division by zero",
            symbol="AAPL",
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "strategy_error"
        assert log_entry.data["error"] == "Division by zero"

    async def test_log_connection_lost(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging connection loss."""
        await audit_service.log_connection_lost(
            tenant_id=tenant_id,
            session_id=session_id,
            service="Alpaca",
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "connection_lost"
        assert log_entry.data["service"] == "Alpaca"

    async def test_log_connection_restored(self, audit_service, mock_db, tenant_id, session_id):
        """Test logging connection restoration."""
        await audit_service.log_connection_restored(
            tenant_id=tenant_id,
            session_id=session_id,
            service="Alpaca",
        )

        log_entry = mock_db.add.call_args[0][0]
        assert log_entry.event_type == "connection_restored"
        assert log_entry.data["service"] == "Alpaca"
