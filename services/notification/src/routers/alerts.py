"""Alerts router."""

from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.models import AlertCreate, AlertResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[AlertResponse])
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_auth),
):
    """List alerts."""
    return PaginatedResponse.create(items=[], total=0, page=page, page_size=page_size)


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert: AlertCreate,
    ctx: TenantContext = Depends(require_auth),
):
    """Create a new alert."""
    from datetime import datetime
    from uuid import uuid4

    return {
        "id": uuid4(),
        "type": alert.type,
        "symbol": alert.symbol,
        "threshold": alert.threshold,
        "channels": alert.channels,
        "is_active": True,
        "triggered_count": 0,
        "last_triggered_at": None,
        "created_at": datetime.now(UTC),
    }


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: UUID,
    ctx: TenantContext = Depends(require_auth),
):
    """Delete an alert."""
    pass


@router.post("/{alert_id}/toggle")
async def toggle_alert(
    alert_id: UUID,
    ctx: TenantContext = Depends(require_auth),
):
    """Toggle alert on/off."""
    return {"status": "ok"}
