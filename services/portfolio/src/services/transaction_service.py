"""Transaction service - transaction history with database persistence."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import Depends
from llamatrade_db import get_db
from llamatrade_db.models.portfolio import Transaction
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import TransactionCreate, TransactionResponse, TransactionType


class TransactionService:
    """Service for transaction operations with database persistence."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_transactions(
        self,
        tenant_id: UUID,
        type: TransactionType | None,
        symbol: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TransactionResponse], int]:
        """List transactions with filtering and pagination.

        Args:
            tenant_id: Tenant ID for isolation
            type: Optional transaction type filter
            symbol: Optional symbol filter
            page: Page number (1-indexed)
            page_size: Number of items per page

        Returns:
            Tuple of (transactions list, total count)
        """
        # Build base query
        base_stmt = select(Transaction).where(Transaction.tenant_id == tenant_id)

        # Apply type filter
        if type:
            base_stmt = base_stmt.where(Transaction.transaction_type == type.value)

        # Apply symbol filter
        if symbol:
            base_stmt = base_stmt.where(Transaction.symbol == symbol.upper())

        # Get total count
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Apply pagination and ordering
        offset = (page - 1) * page_size
        paginated_stmt = (
            base_stmt.order_by(Transaction.transaction_date.desc()).offset(offset).limit(page_size)
        )

        result = await self.db.execute(paginated_stmt)
        transactions = result.scalars().all()

        return [self._to_response(tx) for tx in transactions], total

    async def get_transaction(
        self, transaction_id: UUID, tenant_id: UUID
    ) -> TransactionResponse | None:
        """Get a specific transaction by ID.

        Args:
            transaction_id: Transaction ID
            tenant_id: Tenant ID for isolation

        Returns:
            Transaction details or None if not found
        """
        stmt = (
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .where(Transaction.tenant_id == tenant_id)
        )
        result = await self.db.execute(stmt)
        tx = result.scalar_one_or_none()

        if not tx:
            return None

        return self._to_response(tx)

    async def create_transaction(
        self,
        tenant_id: UUID,
        data: TransactionCreate,
        session_id: UUID | None = None,
        order_id: UUID | None = None,
    ) -> TransactionResponse:
        """Create a new transaction record.

        Args:
            tenant_id: Tenant ID
            data: Transaction creation data
            session_id: Optional trading session ID
            order_id: Optional order ID

        Returns:
            Created transaction
        """
        # Calculate net amount
        net_amount = data.amount - data.commission

        tx = Transaction(
            tenant_id=tenant_id,
            session_id=session_id,
            order_id=order_id,
            transaction_type=data.type.value,
            symbol=data.symbol.upper() if data.symbol else None,
            side=self._get_side_from_type(data.type),
            qty=Decimal(str(data.qty)) if data.qty else None,
            price=Decimal(str(data.price)) if data.price else None,
            amount=Decimal(str(data.amount)),
            fees=Decimal(str(data.commission)),
            net_amount=Decimal(str(net_amount)),
            description=data.description,
            transaction_date=datetime.now(UTC),
        )

        self.db.add(tx)
        await self.db.commit()
        await self.db.refresh(tx)

        return self._to_response(tx)

    async def get_realized_pnl(
        self,
        tenant_id: UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> float:
        """Calculate total realized P&L from transactions.

        Args:
            tenant_id: Tenant ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Total realized P&L
        """
        stmt = (
            select(func.sum(Transaction.net_amount))
            .where(Transaction.tenant_id == tenant_id)
            .where(Transaction.transaction_type.in_(["buy", "sell"]))
        )

        if start_date:
            stmt = stmt.where(Transaction.transaction_date >= start_date)
        if end_date:
            stmt = stmt.where(Transaction.transaction_date <= end_date)

        result = await self.db.execute(stmt)
        total = result.scalar() or Decimal("0")
        return float(total)

    async def get_transaction_count(
        self,
        tenant_id: UUID,
        winning: bool | None = None,
    ) -> int:
        """Get count of transactions, optionally filtered by winning/losing.

        Args:
            tenant_id: Tenant ID
            winning: If True, count winning trades; if False, count losing trades

        Returns:
            Transaction count
        """
        stmt = (
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.tenant_id == tenant_id)
            .where(Transaction.transaction_type == "sell")  # Only count sell transactions
        )

        if winning is True:
            stmt = stmt.where(Transaction.net_amount > 0)
        elif winning is False:
            stmt = stmt.where(Transaction.net_amount <= 0)

        result = await self.db.execute(stmt)
        return result.scalar() or 0

    def _to_response(self, tx: Transaction) -> TransactionResponse:
        """Convert Transaction ORM object to response."""
        # Map transaction_type to TransactionType enum
        try:
            tx_type = TransactionType(tx.transaction_type)
        except ValueError:
            # Default to buy if unknown type
            tx_type = TransactionType.BUY

        return TransactionResponse(
            id=tx.id,
            type=tx_type,
            symbol=tx.symbol,
            qty=float(tx.qty) if tx.qty else None,
            price=float(tx.price) if tx.price else None,
            amount=float(tx.amount),
            commission=float(tx.fees),
            description=tx.description,
            executed_at=tx.transaction_date,
        )

    def _get_side_from_type(self, tx_type: TransactionType) -> str | None:
        """Get side (buy/sell) from transaction type."""
        if tx_type == TransactionType.BUY:
            return "buy"
        elif tx_type == TransactionType.SELL:
            return "sell"
        return None


async def get_transaction_service(
    db: AsyncSession = Depends(get_db),
) -> TransactionService:
    """Dependency to get transaction service."""
    return TransactionService(db=db)
