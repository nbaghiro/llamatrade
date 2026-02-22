"""Bars router - historical OHLCV data endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.alpaca.client import AlpacaDataClient, get_alpaca_client
from src.models import Bar, BarsRequest, BarsResponse, Timeframe

router = APIRouter()


@router.get("/{symbol}", response_model=list[Bar])
async def get_bars(
    symbol: str,
    timeframe: Timeframe = Query(default=Timeframe.DAY_1),
    start: datetime = Query(...),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
    ctx: TenantContext = Depends(require_auth),
    alpaca: AlpacaDataClient = Depends(get_alpaca_client),
):
    """Get historical bars for a single symbol."""
    try:
        bars = await alpaca.get_bars(
            symbol=symbol.upper(),
            timeframe=timeframe,
            start=start,
            end=end,
            limit=limit,
        )
        return bars
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch bars: {str(e)}",
        )


@router.post("", response_model=BarsResponse)
async def get_multi_bars(
    request: BarsRequest,
    ctx: TenantContext = Depends(require_auth),
    alpaca: AlpacaDataClient = Depends(get_alpaca_client),
):
    """Get historical bars for multiple symbols."""
    try:
        bars = await alpaca.get_multi_bars(
            symbols=[s.upper() for s in request.symbols],
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            limit=request.limit,
        )
        return BarsResponse(bars=bars)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch bars: {str(e)}",
        )


@router.get("/{symbol}/latest", response_model=Bar)
async def get_latest_bar(
    symbol: str,
    ctx: TenantContext = Depends(require_auth),
    alpaca: AlpacaDataClient = Depends(get_alpaca_client),
):
    """Get the latest bar for a symbol."""
    try:
        bar = await alpaca.get_latest_bar(symbol=symbol.upper())
        if not bar:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No bar found for {symbol}",
            )
        return bar
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch latest bar: {str(e)}",
        )
