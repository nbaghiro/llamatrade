"""Tests for base executor mixin."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from llamatrade_alpaca import Order as AlpacaOrder
from llamatrade_alpaca import OrderSide as AlpacaOrderSide
from llamatrade_alpaca import OrderStatus as AlpacaOrderStatus
from llamatrade_alpaca import OrderType as AlpacaOrderType
from llamatrade_alpaca import TimeInForce as AlpacaTimeInForce
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_ACCEPTED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    ORDER_TYPE_STOP_LIMIT,
    TIME_IN_FORCE_DAY,
    TIME_IN_FORCE_GTC,
)

from src.executor.base import (
    AlpacaSubmitResult,
    OrderSubmissionMixin,
)
from src.models import OrderCreate, RiskCheckResult


class MockExecutor(OrderSubmissionMixin):
    """Mock executor for testing the mixin."""

    def __init__(
        self,
        alpaca_client: MagicMock,
        risk_manager: MagicMock,
        alert_service: MagicMock | None = None,
    ):
        self.alpaca = alpaca_client
        self.risk = risk_manager
        self.alerts = alert_service


@pytest.fixture
def mock_alpaca() -> MagicMock:
    """Create mock Alpaca client."""
    client = MagicMock()
    client.submit_order = AsyncMock(
        return_value=AlpacaOrder(
            id="alpaca-order-123",
            client_order_id="test-client-123",
            symbol="AAPL",
            qty=10.0,
            side=AlpacaOrderSide.BUY,
            order_type=AlpacaOrderType.MARKET,
            status=AlpacaOrderStatus.NEW,
            time_in_force=AlpacaTimeInForce.DAY,
            created_at=datetime.now(UTC),
        )
    )
    client.get_order = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_risk_manager() -> MagicMock:
    """Create mock risk manager."""
    manager = MagicMock()
    manager.check_order = AsyncMock(return_value=RiskCheckResult(passed=True, violations=[]))
    return manager


@pytest.fixture
def mock_alert_service() -> MagicMock:
    """Create mock alert service."""
    service = MagicMock()
    service.on_order_rejected = AsyncMock()
    return service


@pytest.fixture
def sample_order() -> OrderCreate:
    """Create sample order for testing."""
    return OrderCreate(
        symbol="AAPL",
        side=ORDER_SIDE_BUY,
        qty=10.0,
        order_type=ORDER_TYPE_MARKET,
        time_in_force=TIME_IN_FORCE_DAY,
    )


@pytest.fixture
def executor(
    mock_alpaca: MagicMock,
    mock_risk_manager: MagicMock,
    mock_alert_service: MagicMock,
) -> MockExecutor:
    """Create mock executor with all dependencies."""
    return MockExecutor(
        alpaca_client=mock_alpaca,
        risk_manager=mock_risk_manager,
        alert_service=mock_alert_service,
    )


class TestRunRiskCheck:
    """Tests for _run_risk_check method."""

    async def test_passes_correct_parameters(
        self,
        executor: MockExecutor,
        mock_risk_manager: MagicMock,
        sample_order: OrderCreate,
    ) -> None:
        """Test that risk check is called with correct parameters."""
        tenant_id = uuid4()
        session_id = uuid4()

        await executor._run_risk_check(
            tenant_id=tenant_id,
            order=sample_order,
            session_id=session_id,
        )

        mock_risk_manager.check_order.assert_called_once_with(
            tenant_id=tenant_id,
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            limit_price=None,
            session_id=session_id,
        )

    async def test_returns_risk_result(
        self,
        executor: MockExecutor,
        mock_risk_manager: MagicMock,
        sample_order: OrderCreate,
    ) -> None:
        """Test that risk check result is returned."""
        mock_risk_manager.check_order.return_value = RiskCheckResult(
            passed=False,
            violations=["Max position size exceeded"],
        )

        result = await executor._run_risk_check(
            tenant_id=uuid4(),
            order=sample_order,
        )

        assert result.passed is False
        assert "Max position size exceeded" in result.violations

    async def test_handles_limit_order_price(
        self,
        executor: MockExecutor,
        mock_risk_manager: MagicMock,
    ) -> None:
        """Test that limit price is passed to risk check."""
        order = OrderCreate(
            symbol="AAPL",
            side=ORDER_SIDE_BUY,
            qty=10.0,
            order_type=ORDER_TYPE_LIMIT,
            limit_price=150.50,
            time_in_force=TIME_IN_FORCE_DAY,
        )

        await executor._run_risk_check(
            tenant_id=uuid4(),
            order=order,
        )

        call_args = mock_risk_manager.check_order.call_args
        assert call_args.kwargs["limit_price"] == 150.50


class TestHandleRiskRejection:
    """Tests for _handle_risk_rejection method."""

    async def test_sends_alert_on_rejection(
        self,
        executor: MockExecutor,
        mock_alert_service: MagicMock,
        sample_order: OrderCreate,
    ) -> None:
        """Test that alert is sent when order is rejected."""
        tenant_id = uuid4()
        session_id = uuid4()
        violations = ["Max order value exceeded", "Symbol not allowed"]

        await executor._handle_risk_rejection(
            tenant_id=tenant_id,
            session_id=session_id,
            order=sample_order,
            violations=violations,
            start_time=0.0,
        )

        mock_alert_service.on_order_rejected.assert_called_once_with(
            tenant_id=tenant_id,
            session_id=session_id,
            symbol="AAPL",
            side="buy",
            qty=10.0,
            reason="Max order value exceeded, Symbol not allowed",
        )

    async def test_no_alert_when_service_missing(
        self,
        mock_alpaca: MagicMock,
        mock_risk_manager: MagicMock,
        sample_order: OrderCreate,
    ) -> None:
        """Test that no error when alert service is None."""
        executor = MockExecutor(
            alpaca_client=mock_alpaca,
            risk_manager=mock_risk_manager,
            alert_service=None,
        )

        # Should not raise
        await executor._handle_risk_rejection(
            tenant_id=uuid4(),
            session_id=uuid4(),
            order=sample_order,
            violations=["Some violation"],
            start_time=0.0,
        )


class TestSubmitToAlpaca:
    """Tests for _submit_to_alpaca method."""

    async def test_submits_market_order(
        self,
        executor: MockExecutor,
        mock_alpaca: MagicMock,
        sample_order: OrderCreate,
    ) -> None:
        """Test market order submission."""
        result = await executor._submit_to_alpaca(order=sample_order)

        assert isinstance(result, AlpacaSubmitResult)
        assert result.alpaca_order_id == "alpaca-order-123"
        assert result.status == "new"

        mock_alpaca.submit_order.assert_called_once_with(
            symbol="AAPL",
            qty=10.0,
            side="buy",
            order_type="market",
            time_in_force="day",
            limit_price=None,
            stop_price=None,
            client_order_id=None,
        )

    async def test_submits_limit_order(
        self,
        executor: MockExecutor,
        mock_alpaca: MagicMock,
    ) -> None:
        """Test limit order submission."""
        order = OrderCreate(
            symbol="MSFT",
            side=ORDER_SIDE_SELL,
            qty=5.0,
            order_type=ORDER_TYPE_LIMIT,
            limit_price=400.50,
            time_in_force=TIME_IN_FORCE_GTC,
        )

        await executor._submit_to_alpaca(order=order)

        mock_alpaca.submit_order.assert_called_once_with(
            symbol="MSFT",
            qty=5.0,
            side="sell",
            order_type="limit",
            time_in_force="gtc",
            limit_price=400.50,
            stop_price=None,
            client_order_id=None,
        )

    async def test_submits_stop_limit_order(
        self,
        executor: MockExecutor,
        mock_alpaca: MagicMock,
    ) -> None:
        """Test stop-limit order submission."""
        order = OrderCreate(
            symbol="GOOGL",
            side=ORDER_SIDE_SELL,
            qty=2.0,
            order_type=ORDER_TYPE_STOP_LIMIT,
            limit_price=180.00,
            stop_price=185.00,
            time_in_force=TIME_IN_FORCE_DAY,
        )

        await executor._submit_to_alpaca(order=order)

        mock_alpaca.submit_order.assert_called_once_with(
            symbol="GOOGL",
            qty=2.0,
            side="sell",
            order_type="stop_limit",
            time_in_force="day",
            limit_price=180.00,
            stop_price=185.00,
            client_order_id=None,
        )

    async def test_passes_client_order_id(
        self,
        executor: MockExecutor,
        mock_alpaca: MagicMock,
        sample_order: OrderCreate,
    ) -> None:
        """Test client order ID is passed for idempotency."""
        await executor._submit_to_alpaca(
            order=sample_order,
            client_order_id="lt-abc123def456",
        )

        call_args = mock_alpaca.submit_order.call_args
        assert call_args.kwargs["client_order_id"] == "lt-abc123def456"

    async def test_raises_on_alpaca_error(
        self,
        executor: MockExecutor,
        mock_alpaca: MagicMock,
        sample_order: OrderCreate,
    ) -> None:
        """Test that Alpaca errors are propagated."""
        mock_alpaca.submit_order.side_effect = Exception("Insufficient buying power")

        with pytest.raises(Exception, match="Insufficient buying power"):
            await executor._submit_to_alpaca(order=sample_order)


class TestHandleAlpacaRejection:
    """Tests for _handle_alpaca_rejection method."""

    async def test_sends_alert_on_api_error(
        self,
        executor: MockExecutor,
        mock_alert_service: MagicMock,
        sample_order: OrderCreate,
    ) -> None:
        """Test that alert is sent when Alpaca rejects order."""
        tenant_id = uuid4()
        session_id = uuid4()
        error = Exception("Insufficient buying power")

        await executor._handle_alpaca_rejection(
            tenant_id=tenant_id,
            session_id=session_id,
            order=sample_order,
            error=error,
            start_time=0.0,
        )

        mock_alert_service.on_order_rejected.assert_called_once()
        call_args = mock_alert_service.on_order_rejected.call_args
        assert "Alpaca API error" in call_args.kwargs["reason"]
        assert "Insufficient buying power" in call_args.kwargs["reason"]


class TestRecordSubmissionSuccess:
    """Tests for _record_submission_success method."""

    def test_records_metric(
        self,
        executor: MockExecutor,
        sample_order: OrderCreate,
    ) -> None:
        """Test that success metric is recorded."""
        # This just ensures the method runs without error
        # Actual metric recording is tested via the metrics module
        executor._record_submission_success(
            order=sample_order,
            start_time=0.0,
        )


class TestMapAlpacaStatus:
    """Tests for _map_alpaca_status static method."""

    @pytest.mark.parametrize(
        "alpaca_status,expected",
        [
            ("new", ORDER_STATUS_SUBMITTED),
            ("NEW", ORDER_STATUS_SUBMITTED),
            ("accepted", ORDER_STATUS_ACCEPTED),
            ("pending_new", ORDER_STATUS_PENDING),
            ("partially_filled", ORDER_STATUS_PARTIAL),
            ("filled", ORDER_STATUS_FILLED),
            ("canceled", ORDER_STATUS_CANCELLED),
            ("expired", ORDER_STATUS_EXPIRED),
            ("rejected", ORDER_STATUS_REJECTED),
            ("done_for_day", ORDER_STATUS_EXPIRED),
            ("replaced", ORDER_STATUS_CANCELLED),
            ("pending_cancel", ORDER_STATUS_PENDING),
            ("pending_replace", ORDER_STATUS_PENDING),
            ("stopped", ORDER_STATUS_CANCELLED),
            ("suspended", ORDER_STATUS_PENDING),
            ("calculated", ORDER_STATUS_PENDING),
            ("accepted_for_bidding", ORDER_STATUS_ACCEPTED),
        ],
    )
    def test_maps_known_statuses(
        self,
        alpaca_status: str,
        expected: int,
    ) -> None:
        """Test mapping of known Alpaca statuses to int constants."""
        result = OrderSubmissionMixin._map_alpaca_status(alpaca_status)
        assert result == expected

    def test_returns_pending_for_unknown_status(self) -> None:
        """Test unknown status returns pending (default)."""
        result = OrderSubmissionMixin._map_alpaca_status("UNKNOWN_STATUS")
        assert result == ORDER_STATUS_PENDING


class TestGetCurrentUtcTime:
    """Tests for _get_current_utc_time method."""

    def test_returns_utc_datetime(
        self,
        executor: MockExecutor,
    ) -> None:
        """Test that UTC datetime is returned."""

        result = executor._get_current_utc_time()
        assert result.tzinfo == UTC
