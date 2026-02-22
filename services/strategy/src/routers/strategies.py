"""Strategies router - strategy CRUD endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.models import (
    StrategyCreate,
    StrategyDetailResponse,
    StrategyResponse,
    StrategyStatus,
    StrategyUpdate,
    StrategyVersionResponse,
)
from src.services.strategy_service import StrategyService, get_strategy_service

router = APIRouter()


@router.get("", response_model=PaginatedResponse[StrategyResponse])
async def list_strategies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: StrategyStatus | None = None,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """List strategies for the tenant."""
    strategies, total = await strategy_service.list_strategies(
        tenant_id=ctx.tenant_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.create(
        items=strategies,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{strategy_id}", response_model=StrategyDetailResponse)
async def get_strategy(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Get a specific strategy by ID."""
    strategy = await strategy_service.get_strategy(
        strategy_id=strategy_id,
        tenant_id=ctx.tenant_id,
    )
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.post("", response_model=StrategyDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    strategy_data: StrategyCreate,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Create a new strategy."""
    try:
        strategy = await strategy_service.create_strategy(
            tenant_id=ctx.tenant_id,
            name=strategy_data.name,
            description=strategy_data.description,
            strategy_type=strategy_data.strategy_type,
            config=strategy_data.config,
        )
        return strategy
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{strategy_id}", response_model=StrategyDetailResponse)
async def update_strategy(
    strategy_id: UUID,
    strategy_data: StrategyUpdate,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Update a strategy."""
    strategy = await strategy_service.update_strategy(
        strategy_id=strategy_id,
        tenant_id=ctx.tenant_id,
        **strategy_data.model_dump(exclude_unset=True),
    )
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Delete a strategy."""
    success = await strategy_service.delete_strategy(
        strategy_id=strategy_id,
        tenant_id=ctx.tenant_id,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")


@router.post("/{strategy_id}/activate", response_model=StrategyDetailResponse)
async def activate_strategy(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Activate a strategy for live trading."""
    strategy = await strategy_service.update_strategy(
        strategy_id=strategy_id,
        tenant_id=ctx.tenant_id,
        status=StrategyStatus.ACTIVE,
    )
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.post("/{strategy_id}/pause", response_model=StrategyDetailResponse)
async def pause_strategy(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Pause a strategy."""
    strategy = await strategy_service.update_strategy(
        strategy_id=strategy_id,
        tenant_id=ctx.tenant_id,
        status=StrategyStatus.PAUSED,
    )
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionResponse])
async def list_strategy_versions(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """List all versions of a strategy."""
    versions = await strategy_service.list_versions(
        strategy_id=strategy_id,
        tenant_id=ctx.tenant_id,
    )
    return versions


@router.get("/{strategy_id}/versions/{version}", response_model=StrategyVersionResponse)
async def get_strategy_version(
    strategy_id: UUID,
    version: int,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Get a specific version of a strategy."""
    version_data = await strategy_service.get_version(
        strategy_id=strategy_id,
        version=version,
        tenant_id=ctx.tenant_id,
    )
    if not version_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return version_data


@router.post(
    "/{strategy_id}/clone",
    response_model=StrategyDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clone_strategy(
    strategy_id: UUID,
    name: str = Query(..., min_length=1, max_length=255),
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Clone a strategy with a new name."""
    strategy = await strategy_service.clone_strategy(
        strategy_id=strategy_id,
        tenant_id=ctx.tenant_id,
        new_name=name,
    )
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.post("/{strategy_id}/validate")
async def validate_strategy(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Validate a strategy configuration."""
    result = await strategy_service.validate_strategy(
        strategy_id=strategy_id,
        tenant_id=ctx.tenant_id,
    )
    return result
