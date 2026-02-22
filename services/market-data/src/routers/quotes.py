"""Quotes router - real-time quote data endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.alpaca.client import AlpacaDataClient, get_alpaca_client
from src.models import Quote, Snapshot

router = APIRouter()


@router.get("/{symbol}", response_model=Quote)
async def get_latest_quote(
    symbol: str,
    ctx: TenantContext = Depends(require_auth),
    alpaca: AlpacaDataClient = Depends(get_alpaca_client),
):
    """Get the latest quote for a symbol."""
    try:
        quote = await alpaca.get_latest_quote(symbol=symbol.upper())
        if not quote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No quote found for {symbol}",
            )
        return quote
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch quote: {str(e)}",
        )


@router.get("/{symbol}/snapshot", response_model=Snapshot)
async def get_snapshot(
    symbol: str,
    ctx: TenantContext = Depends(require_auth),
    alpaca: AlpacaDataClient = Depends(get_alpaca_client),
):
    """Get a complete market snapshot for a symbol."""
    try:
        snapshot = await alpaca.get_snapshot(symbol=symbol.upper())
        if not snapshot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No snapshot found for {symbol}",
            )
        return snapshot
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch snapshot: {str(e)}",
        )


@router.post("/snapshots", response_model=dict[str, Snapshot])
async def get_multi_snapshots(
    symbols: list[str],
    ctx: TenantContext = Depends(require_auth),
    alpaca: AlpacaDataClient = Depends(get_alpaca_client),
):
    """Get market snapshots for multiple symbols."""
    try:
        snapshots = await alpaca.get_multi_snapshots(symbols=[s.upper() for s in symbols])
        return snapshots
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch snapshots: {str(e)}",
        )
