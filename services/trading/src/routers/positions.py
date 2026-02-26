"""Positions router - position management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.alpaca_client import AlpacaTradingClient, get_alpaca_trading_client
from src.models import PositionResponse
from src.services.position_service import PositionService, get_position_service

router = APIRouter()


@router.get("", response_model=list[PositionResponse])
async def list_positions(
    session_id: UUID | None = Query(
        None, description="Trading session ID for session-specific positions"
    ),
    ctx: TenantContext = Depends(require_auth),
    position_service: PositionService = Depends(get_position_service),
    alpaca_client: AlpacaTradingClient = Depends(get_alpaca_trading_client),
) -> list[PositionResponse]:
    """List all open positions.

    If session_id is provided, returns positions from the local database for that session.
    Otherwise, returns positions from the Alpaca account.
    """
    if session_id:
        # Session-specific positions from database
        return await position_service.list_open_positions(ctx.tenant_id, session_id)
    else:
        # All positions from Alpaca account
        return await alpaca_client.get_positions(tenant_id=ctx.tenant_id)


@router.get("/{symbol}", response_model=PositionResponse)
async def get_position(
    symbol: str,
    session_id: UUID | None = Query(None, description="Trading session ID"),
    ctx: TenantContext = Depends(require_auth),
    position_service: PositionService = Depends(get_position_service),
    alpaca_client: AlpacaTradingClient = Depends(get_alpaca_trading_client),
) -> PositionResponse:
    """Get position for a specific symbol."""
    if session_id:
        position = await position_service.get_position(ctx.tenant_id, session_id, symbol)
    else:
        position = await alpaca_client.get_position(tenant_id=ctx.tenant_id, symbol=symbol.upper())

    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")
    return position


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def close_position(
    symbol: str,
    exit_price: float | None = Query(None, description="Exit price for P&L calculation"),
    session_id: UUID | None = Query(None, description="Trading session ID"),
    ctx: TenantContext = Depends(require_auth),
    position_service: PositionService = Depends(get_position_service),
    alpaca_client: AlpacaTradingClient = Depends(get_alpaca_trading_client),
) -> None:
    """Close a position for a specific symbol.

    For session-based positions, provide session_id and exit_price to track P&L locally.
    This also closes the position on Alpaca.
    """
    # Always close on Alpaca first
    success = await alpaca_client.close_position(tenant_id=ctx.tenant_id, symbol=symbol.upper())
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot close position on Alpaca"
        )

    # If session-based, also close in local database
    if session_id:
        # Get current price from Alpaca position if exit_price not provided
        actual_exit_price = exit_price
        if actual_exit_price is None:
            # Try to get last price from market data
            from src.clients.market_data import get_market_data_client

            market_data = get_market_data_client()
            actual_exit_price = await market_data.get_latest_price(symbol)

        if actual_exit_price:
            await position_service.close_position(
                ctx.tenant_id, session_id, symbol, actual_exit_price
            )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def close_all_positions(
    session_id: UUID | None = Query(None, description="Trading session ID"),
    ctx: TenantContext = Depends(require_auth),
    position_service: PositionService = Depends(get_position_service),
    alpaca_client: AlpacaTradingClient = Depends(get_alpaca_trading_client),
) -> None:
    """Close all open positions.

    Closes all positions on Alpaca. If session_id is provided, also updates
    local position tracking.
    """
    # Close all on Alpaca
    await alpaca_client.close_all_positions(tenant_id=ctx.tenant_id)

    # If session-based, close all in local database
    if session_id:
        from src.clients.market_data import get_market_data_client

        market_data = get_market_data_client()

        positions = await position_service.list_open_positions(ctx.tenant_id, session_id)
        for pos in positions:
            exit_price = await market_data.get_latest_price(pos.symbol)
            if exit_price:
                await position_service.close_position(
                    ctx.tenant_id, session_id, pos.symbol, exit_price
                )


@router.post("/{symbol}/sync", response_model=PositionResponse)
async def sync_position(
    symbol: str,
    session_id: UUID = Query(..., description="Trading session ID"),
    ctx: TenantContext = Depends(require_auth),
    position_service: PositionService = Depends(get_position_service),
) -> PositionResponse:
    """Sync position prices with market data.

    Updates the current price and unrealized P&L for a session position.
    """
    updated = await position_service.update_prices(
        ctx.tenant_id,
        session_id,
        prices=None,  # Will fetch from market data
    )

    if updated == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No positions found to sync",
        )

    position = await position_service.get_position(ctx.tenant_id, session_id, symbol)
    if not position:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position not found")

    return position
