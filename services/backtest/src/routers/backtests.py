"""Backtests router - backtest management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.models import (
    BacktestCreate,
    BacktestResponse,
    BacktestResultResponse,
    BacktestStatus,
)
from src.services.backtest_service import BacktestService, get_backtest_service

router = APIRouter()


@router.post("", response_model=BacktestResponse, status_code=status.HTTP_201_CREATED)
async def create_backtest(
    request: BacktestCreate,
    ctx: TenantContext = Depends(require_auth),
    service: BacktestService = Depends(get_backtest_service),
):
    """Create and queue a new backtest run."""
    try:
        backtest = await service.create_backtest(
            tenant_id=ctx.tenant_id,
            strategy_id=request.strategy_id,
            strategy_version=request.strategy_version,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            symbols=request.symbols,
            commission=request.commission,
            slippage=request.slippage,
        )
        return backtest
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=PaginatedResponse[BacktestResponse])
async def list_backtests(
    strategy_id: UUID | None = None,
    status: BacktestStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_auth),
    service: BacktestService = Depends(get_backtest_service),
):
    """List backtests for the tenant."""
    backtests, total = await service.list_backtests(
        tenant_id=ctx.tenant_id,
        strategy_id=strategy_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.create(items=backtests, total=total, page=page, page_size=page_size)


@router.get("/{backtest_id}", response_model=BacktestResponse)
async def get_backtest(
    backtest_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get backtest status and metadata."""
    backtest = await service.get_backtest(backtest_id=backtest_id, tenant_id=ctx.tenant_id)
    if not backtest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found")
    return backtest


@router.get("/{backtest_id}/results", response_model=BacktestResultResponse)
async def get_backtest_results(
    backtest_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get backtest results including metrics and trades."""
    results = await service.get_results(backtest_id=backtest_id, tenant_id=ctx.tenant_id)
    if not results:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Results not found")
    return results


@router.delete("/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_backtest(
    backtest_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: BacktestService = Depends(get_backtest_service),
):
    """Cancel a pending or running backtest."""
    success = await service.cancel_backtest(backtest_id=backtest_id, tenant_id=ctx.tenant_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel backtest"
        )


@router.post("/{backtest_id}/retry", response_model=BacktestResponse)
async def retry_backtest(
    backtest_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: BacktestService = Depends(get_backtest_service),
):
    """Retry a failed backtest."""
    backtest = await service.retry_backtest(backtest_id=backtest_id, tenant_id=ctx.tenant_id)
    if not backtest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backtest not found")
    return backtest
