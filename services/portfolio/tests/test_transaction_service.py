"""Tests for TransactionService."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated.portfolio_pb2 import (
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_DEPOSIT,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_SELL,
)

from src.models import TransactionCreate, TransactionResponse
from src.services.transaction_service import TransactionService

pytestmark = pytest.mark.asyncio

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_TRANSACTION_ID = UUID("33333333-3333-3333-3333-333333333333")
TEST_SESSION_ID = UUID("44444444-4444-4444-4444-444444444444")
TEST_ORDER_ID = UUID("55555555-5555-5555-5555-555555555555")


def make_mock_transaction(
    id: UUID = TEST_TRANSACTION_ID,
    tenant_id: UUID = TEST_TENANT_ID,
    transaction_type: str = "buy",
    symbol: str = "AAPL",
    qty: Decimal = Decimal("100"),
    price: Decimal = Decimal("150.00"),
    amount: Decimal = Decimal("15000.00"),
    fees: Decimal = Decimal("0.00"),
    net_amount: Decimal = Decimal("15000.00"),
    description: str = "Buy 100 AAPL",
    transaction_date: datetime | None = None,
) -> MagicMock:
    """Create a mock transaction ORM object."""
    tx = MagicMock()
    tx.id = id
    tx.tenant_id = tenant_id
    tx.transaction_type = transaction_type
    tx.symbol = symbol
    tx.side = "buy" if transaction_type == "buy" else "sell"
    tx.qty = qty
    tx.price = price
    tx.amount = amount
    tx.fees = fees
    tx.net_amount = net_amount
    tx.description = description
    tx.transaction_date = transaction_date or datetime.now(UTC)
    return tx


class TestListTransactions:
    """Tests for list_transactions method."""

    async def test_list_transactions_empty(self, mock_db: AsyncMock) -> None:
        """Test listing transactions returns empty when none exist."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_result])

        service = TransactionService(db=mock_db)

        transactions, total = await service.list_transactions(
            tenant_id=TEST_TENANT_ID,
            type=None,
            symbol=None,
            page=1,
            page_size=20,
        )

        assert transactions == []
        assert total == 0

    async def test_list_transactions_with_data(self, mock_db: AsyncMock) -> None:
        """Test listing transactions returns stored transactions."""
        mock_transactions = [
            make_mock_transaction(id=uuid4()),
            make_mock_transaction(id=uuid4(), transaction_type="sell", symbol="GOOGL"),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_transactions
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2
        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_result])

        service = TransactionService(db=mock_db)

        transactions, total = await service.list_transactions(
            tenant_id=TEST_TENANT_ID,
            type=None,
            symbol=None,
            page=1,
            page_size=20,
        )

        assert len(transactions) == 2
        assert total == 2
        assert all(isinstance(t, TransactionResponse) for t in transactions)

    async def test_list_transactions_filter_by_type(self, mock_db: AsyncMock) -> None:
        """Test filtering transactions by type."""
        mock_transactions = [make_mock_transaction(transaction_type="buy")]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_transactions
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_result])

        service = TransactionService(db=mock_db)

        transactions, _ = await service.list_transactions(
            tenant_id=TEST_TENANT_ID,
            type=TRANSACTION_TYPE_BUY,
            symbol=None,
            page=1,
            page_size=20,
        )

        assert len(transactions) == 1
        assert transactions[0].type == TRANSACTION_TYPE_BUY

    async def test_list_transactions_filter_by_symbol(self, mock_db: AsyncMock) -> None:
        """Test filtering transactions by symbol."""
        mock_transactions = [make_mock_transaction(symbol="AAPL")]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_transactions
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_result])

        service = TransactionService(db=mock_db)

        transactions, _ = await service.list_transactions(
            tenant_id=TEST_TENANT_ID,
            type=None,
            symbol="aapl",  # lowercase should be normalized
            page=1,
            page_size=20,
        )

        assert len(transactions) == 1
        assert transactions[0].symbol == "AAPL"

    async def test_list_transactions_pagination(self, mock_db: AsyncMock) -> None:
        """Test pagination of transactions."""
        # Page 2 should skip first page_size items
        mock_transactions = [make_mock_transaction()]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_transactions
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 25  # Total of 25 items
        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_result])

        service = TransactionService(db=mock_db)

        _, total = await service.list_transactions(
            tenant_id=TEST_TENANT_ID,
            type=None,
            symbol=None,
            page=2,
            page_size=10,
        )

        assert total == 25
        # Verify execute was called (can't verify offset/limit without complex mocking)
        assert mock_db.execute.call_count == 2


class TestGetTransaction:
    """Tests for get_transaction method."""

    async def test_get_transaction_found(self, mock_db: AsyncMock) -> None:
        """Test getting a transaction that exists."""
        mock_tx = make_mock_transaction()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tx
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        transaction = await service.get_transaction(
            transaction_id=TEST_TRANSACTION_ID,
            tenant_id=TEST_TENANT_ID,
        )

        assert transaction is not None
        assert isinstance(transaction, TransactionResponse)
        assert transaction.id == TEST_TRANSACTION_ID
        assert transaction.symbol == "AAPL"

    async def test_get_transaction_not_found(self, mock_db: AsyncMock) -> None:
        """Test getting a transaction that doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        transaction = await service.get_transaction(
            transaction_id=uuid4(),
            tenant_id=TEST_TENANT_ID,
        )

        assert transaction is None

    async def test_get_transaction_tenant_isolation(self, mock_db: AsyncMock) -> None:
        """Test that transactions are isolated by tenant."""
        # Transaction exists but for different tenant
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Not found due to tenant filter
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        other_tenant = uuid4()
        transaction = await service.get_transaction(
            transaction_id=TEST_TRANSACTION_ID,
            tenant_id=other_tenant,
        )

        assert transaction is None


class TestCreateTransaction:
    """Tests for create_transaction method."""

    async def test_create_transaction_buy(self, mock_db: AsyncMock) -> None:
        """Test creating a buy transaction."""
        mock_db.refresh = AsyncMock(return_value=None)

        # Make the mock return the transaction after add/commit
        def setup_tx_after_add(tx: MagicMock) -> None:
            tx.id = TEST_TRANSACTION_ID
            tx.transaction_date = datetime.now(UTC)

        mock_db.add = MagicMock(side_effect=setup_tx_after_add)

        service = TransactionService(db=mock_db)

        with patch.object(
            service,
            "_to_response",
            return_value=TransactionResponse(
                id=TEST_TRANSACTION_ID,
                tenant_id=TEST_TENANT_ID,
                type=TRANSACTION_TYPE_BUY,
                symbol="AAPL",
                quantity=100.0,
                price=150.0,
                amount=15000.0,
                fees=0.0,
                description="Buy 100 AAPL",
                created_at=datetime.now(UTC),
            ),
        ):
            create_data = TransactionCreate(
                type=TRANSACTION_TYPE_BUY,
                symbol="AAPL",
                qty=100.0,
                price=150.0,
                amount=15000.0,
                commission=0.0,
                description="Buy 100 AAPL",
            )

            transaction = await service.create_transaction(
                tenant_id=TEST_TENANT_ID,
                data=create_data,
                session_id=TEST_SESSION_ID,
                order_id=TEST_ORDER_ID,
            )

            assert transaction is not None
            assert transaction.type == TRANSACTION_TYPE_BUY
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()

    async def test_create_transaction_sell(self, mock_db: AsyncMock) -> None:
        """Test creating a sell transaction."""
        mock_db.refresh = AsyncMock(return_value=None)

        service = TransactionService(db=mock_db)

        with patch.object(
            service,
            "_to_response",
            return_value=TransactionResponse(
                id=TEST_TRANSACTION_ID,
                tenant_id=TEST_TENANT_ID,
                type=TRANSACTION_TYPE_SELL,
                symbol="AAPL",
                quantity=50.0,
                price=160.0,
                amount=8000.0,
                fees=1.0,
                description="Sell 50 AAPL",
                created_at=datetime.now(UTC),
            ),
        ):
            create_data = TransactionCreate(
                type=TRANSACTION_TYPE_SELL,
                symbol="AAPL",
                qty=50.0,
                price=160.0,
                amount=8000.0,
                commission=1.0,
                description="Sell 50 AAPL",
            )

            transaction = await service.create_transaction(
                tenant_id=TEST_TENANT_ID,
                data=create_data,
            )

            assert transaction is not None
            assert transaction.type == TRANSACTION_TYPE_SELL

    async def test_create_transaction_dividend(self, mock_db: AsyncMock) -> None:
        """Test creating a dividend transaction."""
        mock_db.refresh = AsyncMock(return_value=None)

        service = TransactionService(db=mock_db)

        with patch.object(
            service,
            "_to_response",
            return_value=TransactionResponse(
                id=TEST_TRANSACTION_ID,
                tenant_id=TEST_TENANT_ID,
                type=TRANSACTION_TYPE_DIVIDEND,
                symbol="AAPL",
                quantity=None,
                price=None,
                amount=50.0,
                fees=0.0,
                description="Dividend from AAPL",
                created_at=datetime.now(UTC),
            ),
        ):
            create_data = TransactionCreate(
                type=TRANSACTION_TYPE_DIVIDEND,
                symbol="AAPL",
                amount=50.0,
                description="Dividend from AAPL",
            )

            transaction = await service.create_transaction(
                tenant_id=TEST_TENANT_ID,
                data=create_data,
            )

            assert transaction is not None
            assert transaction.type == TRANSACTION_TYPE_DIVIDEND

    async def test_create_transaction_symbol_normalized(self, mock_db: AsyncMock) -> None:
        """Test that symbol is normalized to uppercase."""
        mock_db.refresh = AsyncMock(return_value=None)
        added_tx: MagicMock | None = None

        def capture_tx(tx: MagicMock) -> None:
            nonlocal added_tx
            added_tx = tx

        mock_db.add = MagicMock(side_effect=capture_tx)

        service = TransactionService(db=mock_db)

        create_data = TransactionCreate(
            type=TRANSACTION_TYPE_BUY,
            symbol="aapl",  # lowercase
            qty=100.0,
            price=150.0,
            amount=15000.0,
        )

        with patch.object(
            service,
            "_to_response",
            return_value=TransactionResponse(
                id=TEST_TRANSACTION_ID,
                tenant_id=TEST_TENANT_ID,
                type=TRANSACTION_TYPE_BUY,
                symbol="AAPL",
                quantity=100.0,
                price=150.0,
                amount=15000.0,
                fees=0.0,
                created_at=datetime.now(UTC),
            ),
        ):
            await service.create_transaction(
                tenant_id=TEST_TENANT_ID,
                data=create_data,
            )

            assert added_tx is not None
            assert added_tx.symbol == "AAPL"


class TestGetRealizedPnl:
    """Tests for get_realized_pnl method."""

    async def test_get_realized_pnl_no_transactions(self, mock_db: AsyncMock) -> None:
        """Test realized P&L with no transactions."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        pnl = await service.get_realized_pnl(tenant_id=TEST_TENANT_ID)

        assert pnl == 0.0

    async def test_get_realized_pnl_with_transactions(self, mock_db: AsyncMock) -> None:
        """Test realized P&L with transactions."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("5000.00")
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        pnl = await service.get_realized_pnl(tenant_id=TEST_TENANT_ID)

        assert pnl == 5000.0

    async def test_get_realized_pnl_with_date_range(self, mock_db: AsyncMock) -> None:
        """Test realized P&L with date range filter."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("2500.00")
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        start_date = datetime(2024, 1, 1, tzinfo=UTC)
        end_date = datetime(2024, 1, 31, tzinfo=UTC)

        pnl = await service.get_realized_pnl(
            tenant_id=TEST_TENANT_ID,
            start_date=start_date,
            end_date=end_date,
        )

        assert pnl == 2500.0

    async def test_get_realized_pnl_negative(self, mock_db: AsyncMock) -> None:
        """Test realized P&L with negative value (losses)."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("-1500.00")
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        pnl = await service.get_realized_pnl(tenant_id=TEST_TENANT_ID)

        assert pnl == -1500.0


class TestGetTransactionCount:
    """Tests for get_transaction_count method."""

    async def test_get_transaction_count_all(self, mock_db: AsyncMock) -> None:
        """Test getting total transaction count."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        count = await service.get_transaction_count(tenant_id=TEST_TENANT_ID)

        assert count == 10

    async def test_get_transaction_count_winning(self, mock_db: AsyncMock) -> None:
        """Test getting winning transaction count."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 7
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        count = await service.get_transaction_count(
            tenant_id=TEST_TENANT_ID,
            winning=True,
        )

        assert count == 7

    async def test_get_transaction_count_losing(self, mock_db: AsyncMock) -> None:
        """Test getting losing transaction count."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        count = await service.get_transaction_count(
            tenant_id=TEST_TENANT_ID,
            winning=False,
        )

        assert count == 3

    async def test_get_transaction_count_empty(self, mock_db: AsyncMock) -> None:
        """Test transaction count with no transactions."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = TransactionService(db=mock_db)

        count = await service.get_transaction_count(tenant_id=TEST_TENANT_ID)

        assert count == 0


class TestToResponse:
    """Tests for _to_response helper method."""

    async def test_to_response_buy_transaction(self, mock_db: AsyncMock) -> None:
        """Test converting a buy transaction to response."""
        mock_tx = make_mock_transaction(transaction_type="buy")

        service = TransactionService(db=mock_db)
        response = service._to_response(mock_tx)

        assert isinstance(response, TransactionResponse)
        assert response.type == TRANSACTION_TYPE_BUY
        assert response.symbol == "AAPL"
        assert response.quantity == 100.0
        assert response.price == 150.0

    async def test_to_response_sell_transaction(self, mock_db: AsyncMock) -> None:
        """Test converting a sell transaction to response."""
        mock_tx = make_mock_transaction(transaction_type="sell")

        service = TransactionService(db=mock_db)
        response = service._to_response(mock_tx)

        assert response.type == TRANSACTION_TYPE_SELL

    async def test_to_response_unknown_type_defaults_to_buy(self, mock_db: AsyncMock) -> None:
        """Test that unknown transaction type defaults to BUY."""
        mock_tx = make_mock_transaction(transaction_type="unknown_type")

        service = TransactionService(db=mock_db)
        response = service._to_response(mock_tx)

        assert response.type == TRANSACTION_TYPE_BUY


class TestGetSideFromType:
    """Tests for _get_side_from_type helper method."""

    async def test_get_side_from_buy(self, mock_db: AsyncMock) -> None:
        """Test getting side from BUY type."""
        service = TransactionService(db=mock_db)
        side = service._get_side_from_type(TRANSACTION_TYPE_BUY)
        assert side == "buy"

    async def test_get_side_from_sell(self, mock_db: AsyncMock) -> None:
        """Test getting side from SELL type."""
        service = TransactionService(db=mock_db)
        side = service._get_side_from_type(TRANSACTION_TYPE_SELL)
        assert side == "sell"

    async def test_get_side_from_dividend(self, mock_db: AsyncMock) -> None:
        """Test getting side from DIVIDEND type returns None."""
        service = TransactionService(db=mock_db)
        side = service._get_side_from_type(TRANSACTION_TYPE_DIVIDEND)
        assert side is None

    async def test_get_side_from_deposit(self, mock_db: AsyncMock) -> None:
        """Test getting side from DEPOSIT type returns None."""
        service = TransactionService(db=mock_db)
        side = service._get_side_from_type(TRANSACTION_TYPE_DEPOSIT)
        assert side is None
