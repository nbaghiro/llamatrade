"""Transaction service."""

from typing import Any
from uuid import UUID

from src.models import TransactionType


class TransactionService:
    async def list_transactions(
        self,
        tenant_id: UUID,
        type: TransactionType | None,
        symbol: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        return [], 0

    async def get_transaction(self, transaction_id: UUID, tenant_id: UUID) -> dict[str, Any] | None:
        return None


def get_transaction_service() -> TransactionService:
    return TransactionService()
