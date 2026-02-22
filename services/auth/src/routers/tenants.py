"""Tenants router - tenant management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from llamatrade_common.middleware import TenantContext, require_auth, require_roles

from src.models import AlpacaCredentials, AlpacaCredentialsUpdate, TenantResponse
from src.services.tenant_service import TenantService, get_tenant_service

router = APIRouter()


@router.get("/current", response_model=TenantResponse)
async def get_current_tenant(
    ctx: TenantContext = Depends(require_auth),
    tenant_service: TenantService = Depends(get_tenant_service),
):
    """Get the current tenant."""
    tenant = await tenant_service.get_tenant(tenant_id=ctx.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.patch("/current", response_model=TenantResponse)
async def update_current_tenant(
    settings: dict,
    ctx: TenantContext = Depends(require_roles("admin")),
    tenant_service: TenantService = Depends(get_tenant_service),
):
    """Update the current tenant settings (admin only)."""
    tenant = await tenant_service.update_tenant_settings(
        tenant_id=ctx.tenant_id,
        settings=settings,
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.get("/current/alpaca", response_model=AlpacaCredentials)
async def get_alpaca_credentials(
    ctx: TenantContext = Depends(require_roles("admin")),
    tenant_service: TenantService = Depends(get_tenant_service),
):
    """Get Alpaca API credentials (masked)."""
    creds = await tenant_service.get_alpaca_credentials(tenant_id=ctx.tenant_id)
    if not creds:
        return AlpacaCredentials()

    # Mask credentials - only show if they exist
    return AlpacaCredentials(
        paper_key="***" if creds.get("paper_key") else None,
        paper_secret="***" if creds.get("paper_secret") else None,
        live_key="***" if creds.get("live_key") else None,
        live_secret="***" if creds.get("live_secret") else None,
    )


@router.put("/current/alpaca", response_model=AlpacaCredentials)
async def update_alpaca_credentials(
    credentials: AlpacaCredentialsUpdate,
    ctx: TenantContext = Depends(require_roles("admin")),
    tenant_service: TenantService = Depends(get_tenant_service),
):
    """Update Alpaca API credentials (admin only)."""
    await tenant_service.update_alpaca_credentials(
        tenant_id=ctx.tenant_id,
        paper_key=credentials.paper_key,
        paper_secret=credentials.paper_secret,
        live_key=credentials.live_key,
        live_secret=credentials.live_secret,
    )
    return AlpacaCredentials(
        paper_key="***" if credentials.paper_key else None,
        paper_secret="***" if credentials.paper_secret else None,
        live_key="***" if credentials.live_key else None,
        live_secret="***" if credentials.live_secret else None,
    )


@router.delete("/current/alpaca")
async def delete_alpaca_credentials(
    ctx: TenantContext = Depends(require_roles("admin")),
    tenant_service: TenantService = Depends(get_tenant_service),
):
    """Delete Alpaca API credentials (admin only)."""
    await tenant_service.delete_alpaca_credentials(tenant_id=ctx.tenant_id)
    return {"message": "Alpaca credentials deleted"}
