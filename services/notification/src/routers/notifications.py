"""Notifications router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.models import NotificationResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[NotificationResponse])
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_auth),
):
    """List notifications."""
    return PaginatedResponse.create(items=[], total=0, page=page, page_size=page_size)


@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: UUID,
    ctx: TenantContext = Depends(require_auth),
):
    """Mark notification as read."""
    return {"status": "ok"}
