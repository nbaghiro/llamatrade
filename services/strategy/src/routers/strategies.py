"""Strategies router - strategy CRUD endpoints with S-expression DSL support."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.models import (
    DeploymentCreate,
    DeploymentResponse,
    DeploymentStatus,
    StrategyCreate,
    StrategyDetailResponse,
    StrategyResponse,
    StrategyStatus,
    StrategyType,
    StrategyUpdate,
    StrategyVersionResponse,
    ValidationResult,
)
from src.services.strategy_service import StrategyService, get_strategy_service

router = APIRouter()


@router.get("", response_model=PaginatedResponse[StrategyResponse])
async def list_strategies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: StrategyStatus | None = None,
    strategy_type: StrategyType | None = None,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> PaginatedResponse[StrategyResponse]:
    """List strategies for the tenant."""
    strategies, total = await strategy_service.list_strategies(
        tenant_id=ctx.tenant_id,
        status=status,
        strategy_type=strategy_type,
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
) -> StrategyDetailResponse:
    """Get a specific strategy by ID."""
    strategy = await strategy_service.get_strategy(
        tenant_id=ctx.tenant_id,
        strategy_id=strategy_id,
    )
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.post("", response_model=StrategyDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    data: StrategyCreate,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> StrategyDetailResponse:
    """Create a new strategy with S-expression configuration."""
    try:
        strategy = await strategy_service.create_strategy(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            data=data,
        )
        return strategy
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{strategy_id}", response_model=StrategyDetailResponse)
async def update_strategy(
    strategy_id: UUID,
    data: StrategyUpdate,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> StrategyDetailResponse:
    """Update a strategy. If config_sexpr changes, creates a new version."""
    try:
        strategy = await strategy_service.update_strategy(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            strategy_id=strategy_id,
            data=data,
        )
        if not strategy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
        return strategy
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> None:
    """Soft delete (archive) a strategy."""
    success = await strategy_service.delete_strategy(
        tenant_id=ctx.tenant_id,
        strategy_id=strategy_id,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")


@router.post("/{strategy_id}/activate", response_model=StrategyResponse)
async def activate_strategy(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> StrategyResponse:
    """Activate a strategy for live trading."""
    strategy = await strategy_service.activate_strategy(
        tenant_id=ctx.tenant_id,
        strategy_id=strategy_id,
    )
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.post("/{strategy_id}/pause", response_model=StrategyResponse)
async def pause_strategy(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> StrategyResponse:
    """Pause a strategy."""
    strategy = await strategy_service.pause_strategy(
        tenant_id=ctx.tenant_id,
        strategy_id=strategy_id,
    )
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionResponse])
async def list_strategy_versions(
    strategy_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> list[StrategyVersionResponse]:
    """List all versions of a strategy."""
    versions = await strategy_service.list_versions(
        tenant_id=ctx.tenant_id,
        strategy_id=strategy_id,
    )
    return versions


@router.get("/{strategy_id}/versions/{version}", response_model=StrategyVersionResponse)
async def get_strategy_version(
    strategy_id: UUID,
    version: int,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> StrategyVersionResponse:
    """Get a specific version of a strategy."""
    version_data = await strategy_service.get_version(
        tenant_id=ctx.tenant_id,
        strategy_id=strategy_id,
        version=version,
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
) -> StrategyDetailResponse:
    """Clone a strategy with a new name."""
    strategy = await strategy_service.clone_strategy(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        strategy_id=strategy_id,
        new_name=name,
    )
    if not strategy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


@router.post("/validate", response_model=ValidationResult)
async def validate_config(
    config_sexpr: str,
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> ValidationResult:
    """Validate a strategy configuration without saving."""
    result = await strategy_service.validate_config(config_sexpr)
    return result


# ===================
# Deployment endpoints
# ===================


@router.post(
    "/{strategy_id}/deployments",
    response_model=DeploymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_deployment(
    strategy_id: UUID,
    data: DeploymentCreate,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> DeploymentResponse:
    """Create a new deployment for a strategy."""
    try:
        deployment = await strategy_service.create_deployment(
            tenant_id=ctx.tenant_id,
            strategy_id=strategy_id,
            data=data,
        )
        if not deployment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
        return deployment
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{strategy_id}/deployments", response_model=list[DeploymentResponse])
async def list_strategy_deployments(
    strategy_id: UUID,
    status: DeploymentStatus | None = None,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> list[DeploymentResponse]:
    """List deployments for a specific strategy."""
    deployments = await strategy_service.list_deployments(
        tenant_id=ctx.tenant_id,
        strategy_id=strategy_id,
        status=status,
    )
    return deployments


@router.get("/deployments", response_model=list[DeploymentResponse])
async def list_all_deployments(
    status: DeploymentStatus | None = None,
    ctx: TenantContext = Depends(require_auth),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> list[DeploymentResponse]:
    """List all deployments for the tenant."""
    deployments = await strategy_service.list_deployments(
        tenant_id=ctx.tenant_id,
        status=status,
    )
    return deployments
