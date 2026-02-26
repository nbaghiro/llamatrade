"""Users router - user management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth, require_roles
from llamatrade_common.models import PaginatedResponse

from src.models import UserCreate, UserResponse, UserUpdate
from src.services.user_service import UserService, get_user_service

router = APIRouter()


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_auth),
    user_service: UserService = Depends(get_user_service),
) -> PaginatedResponse[UserResponse]:
    """List users in the tenant."""
    users, total = await user_service.list_users(
        tenant_id=ctx.tenant_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.create(
        items=users,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Get a specific user by ID."""
    user = await user_service.get_user(user_id=user_id, tenant_id=ctx.tenant_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    ctx: TenantContext = Depends(require_roles("admin")),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Create a new user in the tenant (admin only)."""
    try:
        user = await user_service.create_user(
            tenant_id=ctx.tenant_id,
            email=user_data.email,
            password=user_data.password,
            role=user_data.role,
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    ctx: TenantContext = Depends(require_roles("admin")),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Update a user (admin only)."""
    user = await user_service.update_user(
        user_id=user_id,
        tenant_id=ctx.tenant_id,
        **user_data.model_dump(exclude_unset=True),
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    ctx: TenantContext = Depends(require_roles("admin")),
    user_service: UserService = Depends(get_user_service),
) -> None:
    """Delete a user (admin only)."""
    if user_id == ctx.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )
    success = await user_service.delete_user(user_id=user_id, tenant_id=ctx.tenant_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
