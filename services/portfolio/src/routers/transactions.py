"""Transactions router - transaction history endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.models import TransactionResponse, TransactionType
from src.services.transaction_service import TransactionService, get_transaction_service

router = APIRouter()


@router.get("", response_model=PaginatedResponse[TransactionResponse])
async def list_transactions(
    type: TransactionType | None = None,
    symbol: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_auth),
    service: TransactionService = Depends(get_transaction_service),
) -> PaginatedResponse[TransactionResponse]:
    """List transactions."""
    transactions, total = await service.list_transactions(
        tenant_id=ctx.tenant_id,
        type=type,
        symbol=symbol.upper() if symbol else None,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.create(items=transactions, total=total, page=page, page_size=page_size)


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: TransactionService = Depends(get_transaction_service),
) -> TransactionResponse:
    """Get a specific transaction."""
    tx = await service.get_transaction(transaction_id=transaction_id, tenant_id=ctx.tenant_id)
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return tx
