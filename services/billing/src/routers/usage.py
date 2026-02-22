"""Usage router - usage metering endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import UsageSummary

router = APIRouter()


@router.get("/summary", response_model=UsageSummary)
async def get_usage_summary(ctx: TenantContext = Depends(require_auth)):
    """Get current period usage summary."""
    now = datetime.now(UTC)
    return {
        "backtests_count": 0,
        "backtests_limit": 5,
        "live_strategies_count": 0,
        "live_strategies_limit": 0,
        "api_calls_count": 0,
        "api_calls_limit": 1000,
        "data_requests_count": 0,
        "period_start": now,
        "period_end": now,
    }


@router.get("/history")
async def get_usage_history(
    months: int = 3,
    ctx: TenantContext = Depends(require_auth),
):
    """Get usage history."""
    return []
