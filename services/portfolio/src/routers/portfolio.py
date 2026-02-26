"""Portfolio router - portfolio and positions endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import PortfolioSummary, PositionResponse
from src.services.portfolio_service import PortfolioService, get_portfolio_service

router = APIRouter()


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    ctx: TenantContext = Depends(require_auth),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioSummary:
    """Get portfolio summary including all positions and P&L."""
    return await service.get_summary(tenant_id=ctx.tenant_id)


@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    ctx: TenantContext = Depends(require_auth),
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[PositionResponse]:
    """List all current positions."""
    return await service.list_positions(tenant_id=ctx.tenant_id)


@router.get("/positions/{symbol}", response_model=PositionResponse)
async def get_position(
    symbol: str,
    ctx: TenantContext = Depends(require_auth),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PositionResponse:
    """Get position for a specific symbol."""
    position = await service.get_position(tenant_id=ctx.tenant_id, symbol=symbol.upper())
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position not found for symbol: {symbol.upper()}",
        )
    return position
