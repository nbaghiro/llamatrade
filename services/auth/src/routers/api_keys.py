"""API Keys router - API key management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.models import APIKeyCreate, APIKeyCreatedResponse, APIKeyResponse
from src.services.api_key_service import APIKeyService, get_api_key_service

router = APIRouter()


@router.get("", response_model=PaginatedResponse[APIKeyResponse])
async def list_api_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_auth),
    api_key_service: APIKeyService = Depends(get_api_key_service),
):
    """List API keys for the current user."""
    keys, total = await api_key_service.list_api_keys(
        user_id=ctx.user_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.create(
        items=keys,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=APIKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: APIKeyCreate,
    ctx: TenantContext = Depends(require_auth),
    api_key_service: APIKeyService = Depends(get_api_key_service),
):
    """Create a new API key.

    Note: The full API key is only returned once upon creation.
    Store it securely as it cannot be retrieved again.
    """
    key = await api_key_service.create_api_key(
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        name=key_data.name,
        scopes=key_data.scopes,
    )
    return key


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    api_key_service: APIKeyService = Depends(get_api_key_service),
):
    """Delete an API key."""
    success = await api_key_service.delete_api_key(key_id=key_id, user_id=ctx.user_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
