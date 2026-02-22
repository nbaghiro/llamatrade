"""Performance router - analytics endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import EquityPoint, PerformanceMetrics
from src.services.performance_service import PerformanceService, get_performance_service

router = APIRouter()


@router.get("/metrics", response_model=PerformanceMetrics)
async def get_performance_metrics(
    period: str = Query(default="1M", regex="^(1D|1W|1M|3M|6M|1Y|YTD|ALL)$"),
    ctx: TenantContext = Depends(require_auth),
    service: PerformanceService = Depends(get_performance_service),
):
    """Get performance metrics for a period."""
    return await service.get_metrics(tenant_id=ctx.tenant_id, period=period)


@router.get("/equity-curve", response_model=list[EquityPoint])
async def get_equity_curve(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    ctx: TenantContext = Depends(require_auth),
    service: PerformanceService = Depends(get_performance_service),
):
    """Get historical equity curve."""
    return await service.get_equity_curve(
        tenant_id=ctx.tenant_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/daily-returns", response_model=list[dict])
async def get_daily_returns(
    period: str = Query(default="1M", regex="^(1W|1M|3M|6M|1Y|YTD|ALL)$"),
    ctx: TenantContext = Depends(require_auth),
    service: PerformanceService = Depends(get_performance_service),
):
    """Get daily returns for a period."""
    return await service.get_daily_returns(tenant_id=ctx.tenant_id, period=period)
