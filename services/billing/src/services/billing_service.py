"""Billing service - subscription and plan management."""

import logging
from typing import cast
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from llamatrade_db.models import Plan, Subscription
from llamatrade_proto.generated import billing_pb2
from llamatrade_proto.generated.billing_pb2 import SubscriptionStatus

from src.models import (
    PlanResponse,
    SubscriptionCreateRequest,
    SubscriptionResponse,
)
from src.services.database import get_db
from src.stripe.client import StripeClient, StripeError, get_stripe_client

logger = logging.getLogger(__name__)


def stripe_status_to_proto(status: str) -> SubscriptionStatus.ValueType:
    """Convert Stripe subscription status string to proto ValueType."""
    mapping: dict[str, int] = {
        "active": billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
        "past_due": billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE,
        "canceled": billing_pb2.SUBSCRIPTION_STATUS_CANCELED,
        "cancelled": billing_pb2.SUBSCRIPTION_STATUS_CANCELED,  # British spelling
        "trialing": billing_pb2.SUBSCRIPTION_STATUS_TRIALING,
        "paused": billing_pb2.SUBSCRIPTION_STATUS_PAUSED,
        "incomplete": billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE,  # Map to past_due
        "incomplete_expired": billing_pb2.SUBSCRIPTION_STATUS_CANCELED,
        "unpaid": billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE,
    }
    result = mapping.get(status.lower()) or billing_pb2.SUBSCRIPTION_STATUS_UNSPECIFIED
    return cast(SubscriptionStatus.ValueType, result)


# Default plans - used when database plans are not available
DEFAULT_PLANS = [
    PlanResponse(
        id="free",
        name="Free",
        tier=billing_pb2.PLAN_TIER_FREE,
        price_monthly=0,
        price_yearly=0,
        features={
            "backtests": True,
            "paper_trading": True,
            "live_trading": False,
            "basic_indicators": True,
            "all_indicators": False,
            "email_alerts": False,
            "priority_support": False,
        },
        limits={
            "backtests_per_month": 5,
            "live_strategies": 0,
            "api_calls_per_day": 1000,
        },
        trial_days=0,
    ),
    PlanResponse(
        id="starter",
        name="Starter",
        tier=billing_pb2.PLAN_TIER_STARTER,
        price_monthly=29,
        price_yearly=290,
        features={
            "backtests": True,
            "paper_trading": True,
            "live_trading": False,
            "basic_indicators": True,
            "all_indicators": True,
            "email_alerts": True,
            "priority_support": False,
        },
        limits={
            "backtests_per_month": 50,
            "live_strategies": 1,
            "api_calls_per_day": 10000,
        },
        trial_days=14,
    ),
    PlanResponse(
        id="pro",
        name="Pro",
        tier=billing_pb2.PLAN_TIER_PRO,
        price_monthly=99,
        price_yearly=990,
        features={
            "backtests": True,
            "paper_trading": True,
            "live_trading": True,
            "basic_indicators": True,
            "all_indicators": True,
            "email_alerts": True,
            "priority_support": True,
        },
        limits={
            "backtests_per_month": None,
            "live_strategies": 5,
            "api_calls_per_day": 100000,
        },
        trial_days=14,
    ),
]


class BillingService:
    """Service for managing subscriptions and plans."""

    def __init__(self, db: AsyncSession, stripe_client: StripeClient):
        self.db = db
        self.stripe = stripe_client

    # ===================
    # Plans
    # ===================

    async def list_plans(self) -> list[PlanResponse]:
        """List all available plans."""
        result = await self.db.execute(
            select(Plan).where(Plan.is_active == True).order_by(Plan.sort_order)  # noqa: E712
        )
        plans = result.scalars().all()

        if not plans:
            # Return default plans if none in database
            return DEFAULT_PLANS

        return [self._plan_to_response(p) for p in plans]

    async def get_plan(self, plan_id: str) -> PlanResponse | None:
        """Get a specific plan by ID or name."""
        # First try to find in database
        result = await self.db.execute(
            select(Plan).where(
                (Plan.name == plan_id) | (Plan.id == plan_id if self._is_uuid(plan_id) else False)
            )
        )
        plan = result.scalar_one_or_none()

        if plan:
            return self._plan_to_response(plan)

        # Fall back to default plans
        for p in DEFAULT_PLANS:
            if p.id == plan_id or p.name.lower() == plan_id.lower():
                return p

        return None

    async def get_plan_db(self, plan_id: str) -> Plan | None:
        """Get a plan database object."""
        result = await self.db.execute(
            select(Plan).where(
                (Plan.name == plan_id) | (Plan.id == plan_id if self._is_uuid(plan_id) else False)
            )
        )
        return result.scalar_one_or_none()

    def _plan_to_response(self, plan: Plan) -> PlanResponse:
        """Convert Plan model to PlanResponse."""
        # Explicitly cast the dict types from the database model
        features: dict[str, bool] = plan.features if plan.features else {}
        limits: dict[str, int | None] = plan.limits if plan.limits else {}
        return PlanResponse(
            id=plan.name,
            name=plan.display_name,
            tier=plan.tier,
            price_monthly=float(plan.price_monthly),
            price_yearly=float(plan.price_yearly or plan.price_monthly * 10),
            features=features,
            limits=limits,
            trial_days=plan.trial_days,
        )

    def _is_uuid(self, value: str) -> bool:
        """Check if string is a valid UUID."""
        try:
            UUID(value)
            return True
        except ValueError, AttributeError:
            return False

    # ===================
    # Subscriptions
    # ===================

    async def get_subscription(self, tenant_id: UUID) -> SubscriptionResponse | None:
        """Get the current subscription for a tenant."""
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.tenant_id == tenant_id)
            .where(Subscription.status.in_(["active", "trialing", "past_due"]))
            .order_by(Subscription.created_at.desc())
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            return None

        return self._subscription_to_response(subscription)

    async def create_subscription(
        self,
        tenant_id: UUID,
        email: str,
        request: SubscriptionCreateRequest,
    ) -> SubscriptionResponse:
        """Create a new subscription for a tenant."""
        # Get the plan
        plan = await self.get_plan(request.plan_id)
        if not plan:
            raise ValueError(f"Plan {request.plan_id} not found")

        # For free plan, create subscription without Stripe
        if plan.tier == "free":
            return await self._create_free_subscription(tenant_id, plan)

        # Get the plan from database for Stripe price IDs
        plan_db = await self.get_plan_db(request.plan_id)
        if not plan_db:
            raise ValueError(f"Plan {request.plan_id} not found in database")

        # Get the Stripe price ID based on billing cycle
        price_id = (
            plan_db.stripe_price_id_monthly
            if request.billing_cycle == billing_pb2.BILLING_INTERVAL_MONTHLY
            else plan_db.stripe_price_id_yearly
        )
        if not price_id:
            raise ValueError(f"No Stripe price configured for {request.billing_cycle} billing")

        # Get or create Stripe customer
        customer_id = await self.stripe.get_or_create_customer(
            tenant_id=str(tenant_id),
            email=email,
        )

        # Create Stripe subscription
        try:
            stripe_sub = await self.stripe.create_subscription(
                customer_id=customer_id,
                price_id=price_id,
                payment_method_id=request.payment_method_id,
                trial_days=plan.trial_days,
            )
        except StripeError as e:
            logger.error(f"Failed to create Stripe subscription: {e}")
            raise ValueError(f"Payment failed: {e.message}")

        # Create subscription record in database
        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_db.id,
            status=stripe_sub.status,
            billing_cycle=request.billing_cycle,
            stripe_subscription_id=stripe_sub.id,
            stripe_customer_id=customer_id,
            current_period_start=stripe_sub.current_period_start,
            current_period_end=stripe_sub.current_period_end,
            cancel_at_period_end=stripe_sub.cancel_at_period_end,
            trial_start=stripe_sub.trial_start,
            trial_end=stripe_sub.trial_end,
        )

        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription, ["plan"])

        return self._subscription_to_response(subscription)

    async def _create_free_subscription(
        self, tenant_id: UUID, plan: PlanResponse
    ) -> SubscriptionResponse:
        """Create a free subscription (no Stripe involvement)."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        period_end = now + timedelta(days=365 * 100)  # Effectively forever

        # Get or create free plan in database
        plan_db = await self.get_plan_db("free")
        if not plan_db:
            # Create the free plan
            plan_db = Plan(
                name="free",
                display_name="Free",
                tier="free",
                price_monthly=0,
                price_yearly=0,
                features=plan.features,
                limits=plan.limits,
                trial_days=0,
                is_active=True,
                sort_order=0,
            )
            self.db.add(plan_db)
            await self.db.flush()

        subscription = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_db.id,
            status=billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
            billing_cycle=billing_pb2.BILLING_INTERVAL_MONTHLY,
            current_period_start=now,
            current_period_end=period_end,
            cancel_at_period_end=False,
        )

        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription, ["plan"])

        return self._subscription_to_response(subscription)

    async def update_subscription(
        self,
        tenant_id: UUID,
        plan_id: str,
    ) -> SubscriptionResponse:
        """Update subscription to a new plan."""
        # Get current subscription
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.tenant_id == tenant_id)
            .where(Subscription.status.in_(["active", "trialing"]))
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ValueError("No active subscription found")

        # Get the new plan
        new_plan = await self.get_plan(plan_id)
        if not new_plan:
            raise ValueError(f"Plan {plan_id} not found")

        new_plan_db = await self.get_plan_db(plan_id)
        if not new_plan_db:
            raise ValueError(f"Plan {plan_id} not found in database")

        # Get the price ID
        price_id = (
            new_plan_db.stripe_price_id_monthly
            if subscription.billing_cycle == "monthly"
            else new_plan_db.stripe_price_id_yearly
        )

        if not price_id:
            raise ValueError("No Stripe price configured for this plan")

        if not subscription.stripe_subscription_id:
            raise ValueError("Cannot update non-Stripe subscription")

        # Update Stripe subscription
        try:
            stripe_sub = await self.stripe.update_subscription(
                subscription_id=subscription.stripe_subscription_id,
                price_id=price_id,
            )
        except StripeError as e:
            logger.error(f"Failed to update Stripe subscription: {e}")
            raise ValueError(f"Subscription update failed: {e.message}")

        # Update local record
        subscription.plan_id = new_plan_db.id
        subscription.status = stripe_status_to_proto(stripe_sub.status)
        subscription.current_period_start = stripe_sub.current_period_start
        subscription.current_period_end = stripe_sub.current_period_end

        await self.db.commit()
        await self.db.refresh(subscription, ["plan"])

        return self._subscription_to_response(subscription)

    async def cancel_subscription(
        self,
        tenant_id: UUID,
        at_period_end: bool = True,
    ) -> SubscriptionResponse:
        """Cancel a subscription."""
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.tenant_id == tenant_id)
            .where(Subscription.status.in_(["active", "trialing"]))
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ValueError("No active subscription found")

        if subscription.stripe_subscription_id:
            try:
                await self.stripe.cancel_subscription(
                    subscription_id=subscription.stripe_subscription_id,
                    at_period_end=at_period_end,
                )
            except StripeError as e:
                logger.error(f"Failed to cancel Stripe subscription: {e}")
                raise ValueError(f"Cancellation failed: {e.message}")

        if at_period_end:
            subscription.cancel_at_period_end = True
        else:
            subscription.status = billing_pb2.SUBSCRIPTION_STATUS_CANCELED
            from datetime import UTC, datetime

            subscription.canceled_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(subscription, ["plan"])

        return self._subscription_to_response(subscription)

    async def reactivate_subscription(self, tenant_id: UUID) -> SubscriptionResponse:
        """Reactivate a subscription that was set to cancel at period end."""
        result = await self.db.execute(
            select(Subscription)
            .options(selectinload(Subscription.plan))
            .where(Subscription.tenant_id == tenant_id)
            .where(Subscription.cancel_at_period_end == True)  # noqa: E712
            .where(Subscription.status.in_(["active", "trialing"]))
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ValueError("No subscription pending cancellation found")

        if subscription.stripe_subscription_id:
            try:
                await self.stripe.reactivate_subscription(
                    subscription_id=subscription.stripe_subscription_id,
                )
            except StripeError as e:
                logger.error(f"Failed to reactivate Stripe subscription: {e}")
                raise ValueError(f"Reactivation failed: {e.message}")

        subscription.cancel_at_period_end = False
        await self.db.commit()
        await self.db.refresh(subscription, ["plan"])

        return self._subscription_to_response(subscription)

    async def ensure_stripe_customer(self, tenant_id: UUID, email: str) -> str:
        """Ensure a Stripe customer exists for the tenant."""
        return await self.stripe.get_or_create_customer(
            tenant_id=str(tenant_id),
            email=email,
        )

    def _subscription_to_response(self, subscription: Subscription) -> SubscriptionResponse:
        """Convert Subscription model to SubscriptionResponse."""
        plan_response = self._plan_to_response(subscription.plan)

        return SubscriptionResponse(
            id=subscription.id,
            tenant_id=subscription.tenant_id,
            plan=plan_response,
            status=subscription.status,
            billing_cycle=subscription.billing_cycle,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            trial_start=subscription.trial_start,
            trial_end=subscription.trial_end,
            stripe_subscription_id=subscription.stripe_subscription_id,
            created_at=subscription.created_at,
        )

    # ===================
    # Sync from Stripe webhooks
    # ===================

    async def sync_subscription_from_stripe(self, stripe_subscription_id: str, status: str) -> None:
        """Sync subscription status from Stripe webhook."""
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.status = stripe_status_to_proto(status)
            await self.db.commit()


async def get_billing_service(
    db: AsyncSession = Depends(get_db),
    stripe_client: StripeClient = Depends(get_stripe_client),
) -> BillingService:
    """Dependency to get billing service."""
    return BillingService(db, stripe_client)
