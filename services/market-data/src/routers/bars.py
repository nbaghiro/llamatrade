"""Bars router - historical OHLCV data endpoints."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import Bar, BarsRequest, BarsResponse, Timeframe
from src.services.market_data_service import MarketDataService, get_market_data_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{symbol}", response_model=list[Bar])
async def get_bars(
    symbol: str,
    timeframe: Timeframe = Query(default=Timeframe.DAY_1),
    start: datetime = Query(...),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
    refresh: bool = Query(default=False, description="Bypass cache and fetch fresh data"),
    ctx: TenantContext = Depends(require_auth),
    service: MarketDataService = Depends(get_market_data_service),
) -> list[Bar]:
    """Get historical bars for a single symbol.

    - Cached for 24h (historical) or 5min (today's data)
    - Use refresh=true to bypass cache
    """
    logger.info(
        f"Getting bars for {symbol}",
        extra={
            "symbol": symbol,
            "timeframe": timeframe.value,
            "tenant_id": ctx.tenant_id,
        },
    )
    return await service.get_bars(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
        refresh=refresh,
    )


@router.post("", response_model=BarsResponse)
async def get_multi_bars(
    request: BarsRequest,
    refresh: bool = Query(default=False, description="Bypass cache and fetch fresh data"),
    ctx: TenantContext = Depends(require_auth),
    service: MarketDataService = Depends(get_market_data_service),
) -> BarsResponse:
    """Get historical bars for multiple symbols.

    - Each symbol is cached individually
    - Missing symbols in response indicate no data available
    """
    logger.info(
        f"Getting bars for {len(request.symbols)} symbols",
        extra={
            "symbols": request.symbols,
            "timeframe": request.timeframe.value,
            "tenant_id": ctx.tenant_id,
        },
    )
    bars = await service.get_multi_bars(
        symbols=request.symbols,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        limit=request.limit,
        refresh=refresh,
    )
    return BarsResponse(bars=bars)


@router.get("/{symbol}/latest", response_model=Bar)
async def get_latest_bar(
    symbol: str,
    refresh: bool = Query(default=False, description="Bypass cache and fetch fresh data"),
    ctx: TenantContext = Depends(require_auth),
    service: MarketDataService = Depends(get_market_data_service),
) -> Bar:
    """Get the latest bar for a symbol.

    - Cached for 2 minutes
    - Use refresh=true to bypass cache
    """
    logger.info(
        f"Getting latest bar for {symbol}",
        extra={"symbol": symbol, "tenant_id": ctx.tenant_id},
    )
    bar = await service.get_latest_bar(symbol=symbol, refresh=refresh)
    if not bar:
        raise HTTPException(status_code=404, detail=f"No bar found for {symbol}")
    return bar
