"""Sessions router - trading session management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.models import SessionCreate, SessionResponse, SessionStatus
from src.services.session_service import SessionService, get_session_service

router = APIRouter()


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    session: SessionCreate,
    ctx: TenantContext = Depends(require_auth),
    service: SessionService = Depends(get_session_service),
):
    """Start a new trading session."""
    try:
        result = await service.start_session(
            tenant_id=ctx.tenant_id,
            strategy_id=session.strategy_id,
            mode=session.mode,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=PaginatedResponse[SessionResponse])
async def list_sessions(
    status: SessionStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_auth),
    service: SessionService = Depends(get_session_service),
):
    """List trading sessions."""
    sessions, total = await service.list_sessions(
        tenant_id=ctx.tenant_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse.create(items=sessions, total=total, page=page, page_size=page_size)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: SessionService = Depends(get_session_service),
):
    """Get a specific trading session."""
    session = await service.get_session(session_id=session_id, tenant_id=ctx.tenant_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("/{session_id}/stop", response_model=SessionResponse)
async def stop_session(
    session_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: SessionService = Depends(get_session_service),
):
    """Stop a trading session."""
    session = await service.stop_session(session_id=session_id, tenant_id=ctx.tenant_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("/{session_id}/pause", response_model=SessionResponse)
async def pause_session(
    session_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: SessionService = Depends(get_session_service),
):
    """Pause a trading session."""
    session = await service.pause_session(session_id=session_id, tenant_id=ctx.tenant_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("/{session_id}/resume", response_model=SessionResponse)
async def resume_session(
    session_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: SessionService = Depends(get_session_service),
):
    """Resume a paused trading session."""
    session = await service.resume_session(session_id=session_id, tenant_id=ctx.tenant_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session
