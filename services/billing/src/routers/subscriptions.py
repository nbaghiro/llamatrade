"""Subscriptions router."""

from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import (
    InvoiceResponse,
    PlanResponse,
    PlanTier,
    SubscriptionCreate,
    SubscriptionResponse,
)

router = APIRouter()

PLANS = [
    PlanResponse(
        id="free",
        name="Free",
        tier=PlanTier.FREE,
        price_monthly=0,
        price_yearly=0,
        features=["5 backtests/month", "Paper trading", "Basic indicators"],
        limits={"backtests": 5, "live_strategies": 0, "api_calls": 1000},
    ),
    PlanResponse(
        id="starter",
        name="Starter",
        tier=PlanTier.STARTER,
        price_monthly=29,
        price_yearly=290,
        features=["50 backtests/month", "Paper trading", "All indicators", "Email alerts"],
        limits={"backtests": 50, "live_strategies": 1, "api_calls": 10000},
    ),
    PlanResponse(
        id="pro",
        name="Pro",
        tier=PlanTier.PRO,
        price_monthly=99,
        price_yearly=990,
        features=[
            "Unlimited backtests",
            "Live trading",
            "All indicators",
            "All alerts",
            "Priority support",
        ],
        limits={"backtests": None, "live_strategies": 5, "api_calls": 100000},
    ),
    PlanResponse(
        id="enterprise",
        name="Enterprise",
        tier=PlanTier.ENTERPRISE,
        price_monthly=299,
        price_yearly=2990,
        features=[
            "Everything in Pro",
            "Unlimited live strategies",
            "Dedicated support",
            "Custom integrations",
        ],
        limits={"backtests": None, "live_strategies": None, "api_calls": None},
    ),
]


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans():
    """List available subscription plans."""
    return PLANS


@router.get("/current", response_model=SubscriptionResponse)
async def get_current_subscription(ctx: TenantContext = Depends(require_auth)):
    """Get current subscription."""
    from datetime import datetime
    from uuid import uuid4

    now = datetime.now(UTC)
    return {
        "id": uuid4(),
        "tenant_id": ctx.tenant_id,
        "plan": PLANS[0],
        "status": "active",
        "current_period_start": now,
        "current_period_end": now,
        "cancel_at_period_end": False,
        "stripe_subscription_id": None,
        "created_at": now,
    }


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    request: SubscriptionCreate,
    ctx: TenantContext = Depends(require_auth),
):
    """Create or upgrade subscription."""
    # In production, integrate with Stripe
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Stripe integration required"
    )


@router.post("/cancel")
async def cancel_subscription(ctx: TenantContext = Depends(require_auth)):
    """Cancel subscription at period end."""
    return {"status": "cancelled", "cancel_at_period_end": True}


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(ctx: TenantContext = Depends(require_auth)):
    """List invoices."""
    return []


@router.post("/portal-session")
async def create_portal_session(ctx: TenantContext = Depends(require_auth)):
    """Create Stripe customer portal session."""
    # In production, create Stripe portal session
    return {"url": "https://billing.stripe.com/session/..."}
