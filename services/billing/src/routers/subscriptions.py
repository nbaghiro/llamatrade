"""Subscriptions router - plan and subscription management."""

from fastapi import APIRouter, Depends, HTTPException, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import (
    InvoiceResponse,
    PlanResponse,
    SubscriptionCancelRequest,
    SubscriptionCreateRequest,
    SubscriptionResponse,
    SubscriptionUpdateRequest,
)
from src.services.billing_service import BillingService, get_billing_service
from src.stripe.client import get_stripe_client

router = APIRouter()


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    billing_service: BillingService = Depends(get_billing_service),
) -> list[PlanResponse]:
    """List available subscription plans."""
    return await billing_service.list_plans()


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: str,
    billing_service: BillingService = Depends(get_billing_service),
) -> PlanResponse:
    """Get a specific plan by ID."""
    plan = await billing_service.get_plan(plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )
    return plan


@router.get("/current", response_model=SubscriptionResponse | None)
async def get_current_subscription(
    ctx: TenantContext = Depends(require_auth),
    billing_service: BillingService = Depends(get_billing_service),
) -> SubscriptionResponse | None:
    """Get current subscription for the tenant."""
    return await billing_service.get_subscription(ctx.tenant_id)


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    request: SubscriptionCreateRequest,
    ctx: TenantContext = Depends(require_auth),
    billing_service: BillingService = Depends(get_billing_service),
) -> SubscriptionResponse:
    """Create a new subscription."""
    try:
        return await billing_service.create_subscription(
            tenant_id=ctx.tenant_id,
            email=ctx.email,
            request=request,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("", response_model=SubscriptionResponse)
async def update_subscription(
    request: SubscriptionUpdateRequest,
    ctx: TenantContext = Depends(require_auth),
    billing_service: BillingService = Depends(get_billing_service),
) -> SubscriptionResponse:
    """Update subscription (change plan)."""
    try:
        return await billing_service.update_subscription(
            tenant_id=ctx.tenant_id,
            plan_id=request.plan_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    request: SubscriptionCancelRequest = SubscriptionCancelRequest(),
    ctx: TenantContext = Depends(require_auth),
    billing_service: BillingService = Depends(get_billing_service),
) -> SubscriptionResponse:
    """Cancel subscription."""
    try:
        return await billing_service.cancel_subscription(
            tenant_id=ctx.tenant_id,
            at_period_end=request.at_period_end,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/reactivate", response_model=SubscriptionResponse)
async def reactivate_subscription(
    ctx: TenantContext = Depends(require_auth),
    billing_service: BillingService = Depends(get_billing_service),
) -> SubscriptionResponse:
    """Reactivate a cancelled subscription."""
    try:
        return await billing_service.reactivate_subscription(
            tenant_id=ctx.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    ctx: TenantContext = Depends(require_auth),
    billing_service: BillingService = Depends(get_billing_service),
) -> list[InvoiceResponse]:
    """List invoices for the current subscription."""
    # Get subscription to find customer ID
    subscription = await billing_service.get_subscription(ctx.tenant_id)

    if not subscription or not subscription.stripe_subscription_id:
        return []

    # Get Stripe customer ID from subscription
    from llamatrade_db.models import Subscription
    from sqlalchemy import select

    result = await billing_service.db.execute(
        select(Subscription.stripe_customer_id).where(Subscription.tenant_id == ctx.tenant_id)
    )
    customer_id = result.scalar_one_or_none()

    if not customer_id:
        return []

    # Get invoices from Stripe
    stripe_client = get_stripe_client()
    stripe_invoices = await stripe_client.list_invoices(customer_id)

    return [
        InvoiceResponse(
            id=inv.id,
            amount=inv.amount_due / 100,  # Convert from cents
            currency=inv.currency,
            status=inv.status,
            period_start=inv.period_start,
            period_end=inv.period_end,
            paid_at=inv.paid_at,
            invoice_pdf=inv.invoice_pdf,
            hosted_invoice_url=inv.hosted_invoice_url,
        )
        for inv in stripe_invoices
    ]
