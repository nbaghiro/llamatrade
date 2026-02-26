"""Indicators router - indicator information endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from src.models import IndicatorInfoResponse, IndicatorType
from src.services.indicator_service import IndicatorService, get_indicator_service

router = APIRouter()


@router.get("", response_model=list[IndicatorInfoResponse])
async def list_indicators(
    category: str | None = None,
    indicator_service: IndicatorService = Depends(get_indicator_service),
) -> list[IndicatorInfoResponse]:
    """List available indicators."""
    indicators = await indicator_service.list_indicators(category=category)
    return indicators


@router.get("/categories")
async def list_categories(
    indicator_service: IndicatorService = Depends(get_indicator_service),
) -> list[str]:
    """List indicator categories."""
    return await indicator_service.list_categories()


@router.get("/{indicator_type}", response_model=IndicatorInfoResponse)
async def get_indicator(
    indicator_type: IndicatorType,
    indicator_service: IndicatorService = Depends(get_indicator_service),
) -> IndicatorInfoResponse:
    """Get information about a specific indicator."""
    indicator = await indicator_service.get_indicator(indicator_type=indicator_type)
    if not indicator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Indicator not found")
    return indicator
