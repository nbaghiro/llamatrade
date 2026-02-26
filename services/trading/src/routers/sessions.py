"""Sessions router - trading session management.

Uses LiveSessionService which integrates runner lifecycle management:
- Starting a session creates and starts a StrategyRunner
- Stopping a session stops the runner
- Pausing/resuming affects the runner state
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth
from llamatrade_common.models import PaginatedResponse

from src.models import SessionCreate, SessionResponse, SessionStatus
from src.services.live_session_service import LiveSessionService, get_live_session_service
from src.services.session_service import SessionService, get_session_service

router = APIRouter()


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    session: SessionCreate,
    ctx: TenantContext = Depends(require_auth),
    service: LiveSessionService = Depends(get_live_session_service),
) -> SessionResponse:
    """Start a new trading session with live strategy execution.

    This creates a session in the database AND starts a StrategyRunner
    to execute the strategy in real-time against market data.
    """
    try:
        result = await service.start_session(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            strategy_id=session.strategy_id,
            strategy_version=session.strategy_version,
            name=session.name,
            mode=session.mode,
            credentials_id=session.credentials_id,
            symbols=session.symbols,
            config=session.config,
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
) -> PaginatedResponse[SessionResponse]:
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
) -> SessionResponse:
    """Get a specific trading session."""
    session = await service.get_session(session_id=session_id, tenant_id=ctx.tenant_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("/{session_id}/stop", response_model=SessionResponse)
async def stop_session(
    session_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: LiveSessionService = Depends(get_live_session_service),
) -> SessionResponse:
    """Stop a trading session and its strategy runner."""
    session = await service.stop_session(session_id=session_id, tenant_id=ctx.tenant_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


@router.post("/{session_id}/pause", response_model=SessionResponse)
async def pause_session(
    session_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: LiveSessionService = Depends(get_live_session_service),
) -> SessionResponse:
    """Pause a trading session (runner continues receiving bars but doesn't trade)."""
    try:
        session = await service.pause_session(session_id=session_id, tenant_id=ctx.tenant_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{session_id}/resume", response_model=SessionResponse)
async def resume_session(
    session_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    service: LiveSessionService = Depends(get_live_session_service),
) -> SessionResponse:
    """Resume a paused trading session."""
    try:
        session = await service.resume_session(session_id=session_id, tenant_id=ctx.tenant_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
