"""Positions router - position management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.alpaca_client import AlpacaTradingClient, get_alpaca_trading_client
from src.models import PositionResponse

router = APIRouter()


@router.get("", response_model=list[PositionResponse])
async def list_positions(
    ctx: TenantContext = Depends(require_auth),
    client: AlpacaTradingClient = Depends(get_alpaca_trading_client),
):
    """List all open positions."""
    positions = await client.get_positions(tenant_id=ctx.tenant_id)
    return positions


@router.get("/{symbol}", response_model=PositionResponse)
async def get_position(
    symbol: str,
    ctx: TenantContext = Depends(require_auth),
    client: AlpacaTradingClient = Depends(get_alpaca_trading_client),
):
    """Get position for a specific symbol."""
    position = await client.get_position(tenant_id=ctx.tenant_id, symbol=symbol.upper())
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    return position


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def close_position(
    symbol: str,
    ctx: TenantContext = Depends(require_auth),
    client: AlpacaTradingClient = Depends(get_alpaca_trading_client),
):
    """Close a position for a specific symbol."""
    success = await client.close_position(tenant_id=ctx.tenant_id, symbol=symbol.upper())
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot close position")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def close_all_positions(
    ctx: TenantContext = Depends(require_auth),
    client: AlpacaTradingClient = Depends(get_alpaca_trading_client),
):
    """Close all open positions."""
    await client.close_all_positions(tenant_id=ctx.tenant_id)
