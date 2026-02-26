"""Orders router - order management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.executor.order_executor import OrderExecutor, get_order_executor
from src.models import OrderCreate, OrderResponse, OrderStatus

router = APIRouter()


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def submit_order(
    order: OrderCreate,
    session_id: UUID = Query(..., description="Trading session ID"),
    ctx: TenantContext = Depends(require_auth),
    executor: OrderExecutor = Depends(get_order_executor),
) -> OrderResponse:
    """Submit a new order."""
    try:
        result = await executor.submit_order(
            tenant_id=ctx.tenant_id,
            session_id=session_id,
            order=order,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=PaginatedResponse[OrderResponse])
async def list_orders(
    session_id: UUID | None = None,
    status: OrderStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_auth),
    executor: OrderExecutor = Depends(get_order_executor),
) -> PaginatedResponse[OrderResponse]:
    """List orders for the tenant."""
    orders, total = await executor.list_orders(
        tenant_id=ctx.tenant_id,
        session_id=session_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.create(items=orders, total=total, page=page, page_size=page_size)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    executor: OrderExecutor = Depends(get_order_executor),
) -> OrderResponse:
    """Get a specific order."""
    order = await executor.get_order(order_id=order_id, tenant_id=ctx.tenant_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.post("/{order_id}/sync", response_model=OrderResponse)
async def sync_order_status(
    order_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    executor: OrderExecutor = Depends(get_order_executor),
) -> OrderResponse:
    """Sync order status with Alpaca."""
    order = await executor.sync_order_status(order_id=order_id, tenant_id=ctx.tenant_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_order(
    order_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    executor: OrderExecutor = Depends(get_order_executor),
) -> None:
    """Cancel an order."""
    success = await executor.cancel_order(order_id=order_id, tenant_id=ctx.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel order")
