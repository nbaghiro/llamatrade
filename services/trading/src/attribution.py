"""Order ledger attribution, shared by RPC submission and recovery emission."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from llamatrade_db.models.trading import TradingSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from llamatrade_proto.clients.ledger import LedgerClient, SleeveInfo

logger = logging.getLogger(__name__)

_ledger_client: LedgerClient | None = None


def get_ledger_client() -> LedgerClient:
    """Process-wide LedgerClient to the portfolio service (sleeve resolution)."""
    global _ledger_client
    if _ledger_client is None:
        from llamatrade_proto.clients.ledger import LedgerClient

        _ledger_client = LedgerClient(
            os.getenv("PORTFOLIO_GRPC_TARGET", "portfolio:8860"), service_name="trading"
        )
    return _ledger_client


async def resolve_order_attribution(
    db: AsyncSession,
    ledger: LedgerClient,
    tenant_id: UUID,
    session_id: UUID,
    requested_sleeve_id: str,
    user_id: str | None = None,
    *,
    symbol: str | None = None,
    side: str | None = None,
) -> tuple[UUID | None, UUID | None]:
    """(sleeve_id, account_id) for an order, fixed at origination.

    Resolution order (portfolio-ledger.md): the session's strategy sleeve → the
    account's Manual sleeve (an unattributed order is a manual trade), except a
    sell of a symbol the Manual sleeve does not hold books to Unmanaged, where a
    connected account's pre-existing broker holdings live (otherwise the sell
    finds no Manual lots and freezes the book). A caller-supplied
    ``requested_sleeve_id`` is NOT trusted: the order's sleeve is always derived
    from its session, so a client cannot book a fill against a sleeve it does not
    own. Resolution failures **raise** (callers decide whether to fail the RPC or
    fall back). ``user_id`` defaults to the session's creator — recovery paths
    carry no request identity.
    """
    session = await db.scalar(
        select(TradingSession).where(
            TradingSession.tenant_id == tenant_id,
            TradingSession.id == session_id,
        )
    )
    if requested_sleeve_id:
        logger.warning(
            "Ignoring caller-supplied sleeve_id %s for session %s; the order's sleeve is "
            "derived from its session",
            requested_sleeve_id,
            session_id,
        )
    effective_user = (
        user_id
        if user_id is not None
        else (str(session.created_by) if session is not None else None)
    )

    if session is not None and session.sleeve_id is not None:
        return session.sleeve_id, session.account_id

    if session is not None and effective_user is not None:
        from llamatrade_proto.generated.ledger_pb2 import (
            SLEEVE_TYPE_MANUAL,
            SLEEVE_TYPE_UNMANAGED,
        )

        bootstrap = await ledger.get_or_create_account(
            str(tenant_id), effective_user, str(session.credentials_id)
        )
        manual = next((s for s in bootstrap.base_sleeves if s.type == SLEEVE_TYPE_MANUAL), None)
        unmanaged = next(
            (s for s in bootstrap.base_sleeves if s.type == SLEEVE_TYPE_UNMANAGED), None
        )
        target = await _fallback_sleeve(
            ledger, tenant_id, effective_user, manual, unmanaged, symbol, side
        )
        if target is not None:
            return UUID(target), UUID(bootstrap.account.id)
    return None, None


async def _fallback_sleeve(
    ledger: LedgerClient,
    tenant_id: UUID,
    user_id: str,
    manual: SleeveInfo | None,
    unmanaged: SleeveInfo | None,
    symbol: str | None,
    side: str | None,
) -> str | None:
    """The sleeve an unattributed order books to.

    Manual by default; a sell of a symbol the Manual sleeve does not hold books
    to Unmanaged instead when that sleeve holds it (a connected account's
    pre-existing broker holdings live in Unmanaged). Best-effort: any lookup
    failure falls back to Manual so the order still books.
    """
    if manual is None:
        return unmanaged.id if unmanaged is not None else None
    if unmanaged is None or symbol is None or side is None or side.lower() != "sell":
        return manual.id
    try:
        if await _sleeve_holds(ledger, tenant_id, user_id, manual.id, symbol):
            return manual.id
        if await _sleeve_holds(ledger, tenant_id, user_id, unmanaged.id, symbol):
            return unmanaged.id
    except Exception:
        logger.warning(
            "Unmanaged-routing lookup failed for %s; booking to Manual", symbol, exc_info=True
        )
    return manual.id


async def _sleeve_holds(
    ledger: LedgerClient, tenant_id: UUID, user_id: str, sleeve_id: str, symbol: str
) -> bool:
    """Whether a sleeve carries an open lot for ``symbol``."""
    detail = await ledger.get_sleeve(str(tenant_id), user_id, sleeve_id)
    want = symbol.upper()
    return any(lot.symbol.upper() == want and lot.is_open and lot.qty > 0 for lot in detail.lots)
