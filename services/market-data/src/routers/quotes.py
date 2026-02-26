"""Quotes router - real-time quote data endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import Quote, Snapshot
from src.services.market_data_service import MarketDataService, get_market_data_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{symbol}", response_model=Quote)
async def get_latest_quote(
    symbol: str,
    refresh: bool = Query(default=False, description="Bypass cache and fetch fresh data"),
    ctx: TenantContext = Depends(require_auth),
    service: MarketDataService = Depends(get_market_data_service),
) -> Quote:
    """Get the latest quote for a symbol.

    - Cached for 10 seconds (near real-time)
    - Use refresh=true to bypass cache
    """
    logger.info(
        f"Getting latest quote for {symbol}",
        extra={"symbol": symbol, "tenant_id": ctx.tenant_id},
    )
    quote = await service.get_latest_quote(symbol=symbol, refresh=refresh)
    if not quote:
        raise HTTPException(status_code=404, detail=f"No quote found for {symbol}")
    return quote


@router.get("/{symbol}/snapshot", response_model=Snapshot)
async def get_snapshot(
    symbol: str,
    refresh: bool = Query(default=False, description="Bypass cache and fetch fresh data"),
    ctx: TenantContext = Depends(require_auth),
    service: MarketDataService = Depends(get_market_data_service),
) -> Snapshot:
    """Get a complete market snapshot for a symbol.

    Includes latest trade, quote, minute bar, daily bar, and previous daily bar.

    - Cached for 15 seconds
    - Use refresh=true to bypass cache
    """
    logger.info(
        f"Getting snapshot for {symbol}",
        extra={"symbol": symbol, "tenant_id": ctx.tenant_id},
    )
    snapshot = await service.get_snapshot(symbol=symbol, refresh=refresh)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {symbol}")
    return snapshot


@router.post("/snapshots", response_model=dict[str, Snapshot])
async def get_multi_snapshots(
    symbols: list[str],
    refresh: bool = Query(default=False, description="Bypass cache and fetch fresh data"),
    ctx: TenantContext = Depends(require_auth),
    service: MarketDataService = Depends(get_market_data_service),
) -> dict[str, Snapshot]:
    """Get market snapshots for multiple symbols.

    - Each symbol is cached individually
    - Missing symbols in response indicate no data available
    """
    logger.info(
        f"Getting snapshots for {len(symbols)} symbols",
        extra={"symbols": symbols, "tenant_id": ctx.tenant_id},
    )
    return await service.get_multi_snapshots(symbols=symbols, refresh=refresh)
