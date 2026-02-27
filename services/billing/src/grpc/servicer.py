"""Billing Connect servicer implementation."""

from __future__ import annotations

import logging
import os
from uuid import UUID

import jwt
from typing import Any

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade.v1 import billing_pb2, common_pb2

from src.models import (
    BillingCycle,
    PaymentMethodResponse,
    PlanResponse,
    PlanTier,
    SubscriptionResponse,
    SubscriptionStatus,
)
from src.services.database import get_session_maker
from src.stripe.client import get_stripe_client

logger = logging.getLogger(__name__)

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


class BillingServicer:
    """Connect servicer for the Billing service.

    Implements the BillingService Protocol defined in billing_connect.py.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: Any = None

    async def _get_db(self) -> AsyncSession:
        """Get a database session."""
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        session: AsyncSession = self._session_maker()
        return session

    def _get_tenant_id(self, ctx: Any) -> UUID:
        """Extract tenant_id from JWT token in Authorization header."""
        headers = getattr(ctx, "headers", {})
        auth_header: str = headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise ConnectError(
                Code.UNAUTHENTICATED,
                "Missing or invalid authorization header",
            )
        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise ConnectError(Code.UNAUTHENTICATED, "Token expired")
        except jwt.InvalidTokenError:
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid token")

        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise ConnectError(Code.UNAUTHENTICATED, "Token missing tenant_id")

        return UUID(tenant_id)

    async def get_subscription(
        self,
        request: billing_pb2.GetSubscriptionRequest,
        ctx: Any,
    ) -> billing_pb2.GetSubscriptionResponse:
        """Get the current subscription for a tenant."""
        from src.services.billing_service import BillingService

        tenant_id = self._get_tenant_id(ctx)

        async with await self._get_db() as db:
            stripe_client = get_stripe_client()
            service = BillingService(db, stripe_client)
            subscription = await service.get_subscription(tenant_id)

            if not subscription:
                raise ConnectError(Code.NOT_FOUND, "No active subscription found")

            return billing_pb2.GetSubscriptionResponse(
                subscription=self._to_proto_subscription(subscription),
            )

    async def create_subscription(
        self,
        request: billing_pb2.CreateSubscriptionRequest,
        ctx: Any,
    ) -> billing_pb2.CreateSubscriptionResponse:
        """Create a new subscription."""
        from src.models import SubscriptionCreateRequest
        from src.services.billing_service import BillingService

        tenant_id = self._get_tenant_id(ctx)

        # Map proto billing interval to internal
        interval = self._from_proto_interval(request.interval)

        create_request = SubscriptionCreateRequest(
            plan_id=request.plan_id,
            billing_cycle=interval,
            payment_method_id=request.payment_method_id if request.payment_method_id else None,
            promo_code=request.promo_code if request.promo_code else None,
        )

        try:
            async with await self._get_db() as db:
                stripe_client = get_stripe_client()
                service = BillingService(db, stripe_client)

                # We need email for Stripe - would need to fetch from auth service
                email = f"user-{tenant_id}@llamatrade.example"

                subscription = await service.create_subscription(
                    tenant_id=tenant_id,
                    email=email,
                    request=create_request,
                )

                return billing_pb2.CreateSubscriptionResponse(
                    subscription=self._to_proto_subscription(subscription),
                )
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def update_subscription(
        self,
        request: billing_pb2.UpdateSubscriptionRequest,
        ctx: Any,
    ) -> billing_pb2.UpdateSubscriptionResponse:
        """Update subscription (change plan)."""
        from src.services.billing_service import BillingService

        tenant_id = self._get_tenant_id(ctx)

        try:
            async with await self._get_db() as db:
                stripe_client = get_stripe_client()
                service = BillingService(db, stripe_client)
                subscription = await service.update_subscription(
                    tenant_id=tenant_id,
                    plan_id=request.plan_id,
                )

                return billing_pb2.UpdateSubscriptionResponse(
                    subscription=self._to_proto_subscription(subscription),
                )
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def cancel_subscription(
        self,
        request: billing_pb2.CancelSubscriptionRequest,
        ctx: Any,
    ) -> billing_pb2.CancelSubscriptionResponse:
        """Cancel subscription."""
        from src.services.billing_service import BillingService

        tenant_id = self._get_tenant_id(ctx)

        try:
            async with await self._get_db() as db:
                stripe_client = get_stripe_client()
                service = BillingService(db, stripe_client)
                subscription = await service.cancel_subscription(
                    tenant_id=tenant_id,
                    at_period_end=not request.cancel_immediately,
                )

                return billing_pb2.CancelSubscriptionResponse(
                    subscription=self._to_proto_subscription(subscription),
                )
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def resume_subscription(
        self,
        request: billing_pb2.ResumeSubscriptionRequest,
        ctx: Any,
    ) -> billing_pb2.ResumeSubscriptionResponse:
        """Resume a cancelled subscription."""
        from src.services.billing_service import BillingService

        tenant_id = self._get_tenant_id(ctx)

        try:
            async with await self._get_db() as db:
                stripe_client = get_stripe_client()
                service = BillingService(db, stripe_client)
                subscription = await service.reactivate_subscription(tenant_id)

                return billing_pb2.ResumeSubscriptionResponse(
                    subscription=self._to_proto_subscription(subscription),
                )
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def get_usage(
        self,
        request: billing_pb2.GetUsageRequest,
        ctx: Any,
    ) -> billing_pb2.GetUsageResponse:
        """Get usage metrics for a tenant."""
        tenant_id = self._get_tenant_id(ctx)

        # Usage tracking is stubbed for now
        return billing_pb2.GetUsageResponse(
            usage=billing_pb2.Usage(
                tenant_id=str(tenant_id),
                period_id=request.period_id or "current",
                strategies_created=0,
                active_strategies=0,
                backtests_run=0,
                backtest_compute_minutes=0,
                live_sessions=0,
                orders_placed=0,
                market_data_requests=0,
                storage_bytes=0,
                api_calls=0,
            ),
        )

    async def list_invoices(
        self,
        request: billing_pb2.ListInvoicesRequest,
        ctx: Any,
    ) -> billing_pb2.ListInvoicesResponse:
        """List invoices for a tenant."""
        # Invoices are managed through Stripe portal
        return billing_pb2.ListInvoicesResponse(
            invoices=[],
            pagination=common_pb2.PaginationResponse(
                total_items=0,
                total_pages=1,
                current_page=1,
                page_size=20,
                has_next=False,
                has_previous=False,
            ),
        )

    async def get_invoice(
        self,
        request: billing_pb2.GetInvoiceRequest,
        ctx: Any,
    ) -> billing_pb2.GetInvoiceResponse:
        """Get a specific invoice."""
        raise ConnectError(Code.NOT_FOUND, f"Invoice not found: {request.invoice_id}")

    async def list_plans(
        self,
        request: billing_pb2.ListPlansRequest,
        ctx: Any,
    ) -> billing_pb2.ListPlansResponse:
        """List available plans."""
        from src.services.billing_service import BillingService

        async with await self._get_db() as db:
            stripe_client = get_stripe_client()
            service = BillingService(db, stripe_client)
            plans = await service.list_plans()

            return billing_pb2.ListPlansResponse(
                plans=[self._to_proto_plan(p) for p in plans],
            )

    async def list_payment_methods(
        self,
        request: billing_pb2.ListPaymentMethodsRequest,
        ctx: Any,
    ) -> billing_pb2.ListPaymentMethodsResponse:
        """List payment methods for a tenant."""
        from src.services.billing_service import BillingService
        from src.services.payment_method_service import PaymentMethodService

        tenant_id = self._get_tenant_id(ctx)

        async with await self._get_db() as db:
            stripe_client = get_stripe_client()
            billing_service = BillingService(db, stripe_client)
            service = PaymentMethodService(db, stripe_client, billing_service)
            methods = await service.list_payment_methods(tenant_id)

            return billing_pb2.ListPaymentMethodsResponse(
                payment_methods=[self._to_proto_payment_method(pm) for pm in methods],
            )

    async def add_payment_method(
        self,
        request: billing_pb2.AddPaymentMethodRequest,
        ctx: Any,
    ) -> billing_pb2.AddPaymentMethodResponse:
        """Add a payment method."""
        from src.services.billing_service import BillingService
        from src.services.payment_method_service import PaymentMethodService

        tenant_id = self._get_tenant_id(ctx)
        email = f"user-{tenant_id}@llamatrade.example"

        try:
            async with await self._get_db() as db:
                stripe_client = get_stripe_client()
                billing_service = BillingService(db, stripe_client)
                service = PaymentMethodService(db, stripe_client, billing_service)
                payment_method = await service.attach_payment_method(
                    tenant_id=tenant_id,
                    email=email,
                    payment_method_id=request.setup_intent_id,
                )

                return billing_pb2.AddPaymentMethodResponse(
                    payment_method=self._to_proto_payment_method(payment_method),
                )
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def remove_payment_method(
        self,
        request: billing_pb2.RemovePaymentMethodRequest,
        ctx: Any,
    ) -> billing_pb2.RemovePaymentMethodResponse:
        """Remove a payment method."""
        from src.services.billing_service import BillingService
        from src.services.payment_method_service import PaymentMethodService

        tenant_id = self._get_tenant_id(ctx)
        payment_method_id = UUID(request.payment_method_id)

        try:
            async with await self._get_db() as db:
                stripe_client = get_stripe_client()
                billing_service = BillingService(db, stripe_client)
                service = PaymentMethodService(db, stripe_client, billing_service)
                success = await service.delete_payment_method(tenant_id, payment_method_id)

                if not success:
                    raise ConnectError(Code.NOT_FOUND, "Payment method not found")

                return billing_pb2.RemovePaymentMethodResponse(success=True)
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))

    async def create_checkout_session(
        self,
        request: billing_pb2.CreateCheckoutSessionRequest,
        ctx: Any,
    ) -> billing_pb2.CreateCheckoutSessionResponse:
        """Create a Stripe checkout session."""
        tenant_id = self._get_tenant_id(ctx)

        # This would integrate with Stripe Checkout
        return billing_pb2.CreateCheckoutSessionResponse(
            checkout_url=f"https://checkout.stripe.com/placeholder/{tenant_id}",
            session_id=f"cs_placeholder_{tenant_id}",
        )

    async def create_portal_session(
        self,
        request: billing_pb2.CreatePortalSessionRequest,
        ctx: Any,
    ) -> billing_pb2.CreatePortalSessionResponse:
        """Create a Stripe customer portal session."""
        tenant_id = self._get_tenant_id(ctx)

        # This would integrate with Stripe Customer Portal
        return billing_pb2.CreatePortalSessionResponse(
            portal_url=f"https://billing.stripe.com/placeholder/{tenant_id}",
        )

    # ===================
    # Helper methods
    # ===================

    def _to_proto_subscription(
        self, subscription: SubscriptionResponse
    ) -> billing_pb2.Subscription:
        """Convert internal subscription to proto Subscription."""
        return billing_pb2.Subscription(
            id=str(subscription.id),
            tenant_id=str(subscription.tenant_id),
            plan_id=subscription.plan.id,
            plan=self._to_proto_plan(subscription.plan),
            status=self._to_proto_status(subscription.status),
            interval=self._to_proto_interval(subscription.billing_cycle),
            current_price=common_pb2.Money(
                currency="USD",
                amount=str(
                    subscription.plan.price_monthly
                    if subscription.billing_cycle.value == "monthly"
                    else subscription.plan.price_yearly
                ),
            ),
            current_period_start=common_pb2.Timestamp(
                seconds=int(subscription.current_period_start.timestamp())
            )
            if subscription.current_period_start
            else None,
            current_period_end=common_pb2.Timestamp(
                seconds=int(subscription.current_period_end.timestamp())
            )
            if subscription.current_period_end
            else None,
            is_trial=subscription.trial_end is not None,
            trial_end=common_pb2.Timestamp(seconds=int(subscription.trial_end.timestamp()))
            if subscription.trial_end
            else None,
            cancel_at_period_end=subscription.cancel_at_period_end,
            stripe_subscription_id=subscription.stripe_subscription_id or "",
            created_at=common_pb2.Timestamp(seconds=int(subscription.created_at.timestamp())),
        )

    def _to_proto_plan(self, plan: PlanResponse) -> billing_pb2.Plan:
        """Convert internal plan to proto Plan."""
        return billing_pb2.Plan(
            id=plan.id,
            name=plan.name,
            tier=self._to_proto_tier(plan.tier),
            description="",
            monthly_price=common_pb2.Money(currency="USD", amount=str(plan.price_monthly)),
            yearly_price=common_pb2.Money(currency="USD", amount=str(plan.price_yearly)),
            max_strategies=plan.limits.get("live_strategies", 0) or 0,
            max_backtests_per_month=plan.limits.get("backtests_per_month", 0) or 0,
            max_live_sessions=plan.limits.get("live_strategies", 0) or 0,
            data_retention_days=90,
            features=[k for k, v in plan.features.items() if v],
            api_access=plan.features.get("api_access", False),
            priority_support=plan.features.get("priority_support", False),
        )

    def _to_proto_payment_method(
        self, pm: PaymentMethodResponse
    ) -> billing_pb2.PaymentMethod:
        """Convert internal payment method to proto PaymentMethod."""
        return billing_pb2.PaymentMethod(
            id=str(pm.id),
            type=pm.type,
            is_default=pm.is_default,
            card_brand=pm.card_brand or "",
            card_last4=pm.card_last4 or "",
            card_exp_month=pm.card_exp_month or 0,
            card_exp_year=pm.card_exp_year or 0,
        )

    def _to_proto_status(self, status: SubscriptionStatus) -> int:
        """Convert internal status to proto enum value."""
        status_map = {
            SubscriptionStatus.ACTIVE: billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
            SubscriptionStatus.TRIALING: billing_pb2.SUBSCRIPTION_STATUS_TRIALING,
            SubscriptionStatus.PAST_DUE: billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE,
            SubscriptionStatus.CANCELLED: billing_pb2.SUBSCRIPTION_STATUS_CANCELED,
            SubscriptionStatus.PAUSED: billing_pb2.SUBSCRIPTION_STATUS_PAUSED,
        }
        return status_map.get(status, billing_pb2.SUBSCRIPTION_STATUS_UNSPECIFIED)

    def _to_proto_tier(self, tier: PlanTier) -> int:
        """Convert internal tier to proto enum value."""
        tier_map = {
            PlanTier.FREE: billing_pb2.PLAN_TIER_FREE,
            PlanTier.STARTER: billing_pb2.PLAN_TIER_STARTER,
            PlanTier.PRO: billing_pb2.PLAN_TIER_PROFESSIONAL,
        }
        return tier_map.get(tier, billing_pb2.PLAN_TIER_UNSPECIFIED)

    def _to_proto_interval(self, interval: BillingCycle) -> int:
        """Convert internal billing cycle to proto enum value."""
        interval_map = {
            BillingCycle.MONTHLY: billing_pb2.BILLING_INTERVAL_MONTHLY,
            BillingCycle.YEARLY: billing_pb2.BILLING_INTERVAL_YEARLY,
        }
        return interval_map.get(interval, billing_pb2.BILLING_INTERVAL_UNSPECIFIED)

    def _from_proto_interval(self, interval: int) -> BillingCycle:
        """Convert proto interval to internal billing cycle."""
        interval_map = {
            billing_pb2.BILLING_INTERVAL_MONTHLY: BillingCycle.MONTHLY,
            billing_pb2.BILLING_INTERVAL_YEARLY: BillingCycle.YEARLY,
        }
        return interval_map.get(interval, BillingCycle.MONTHLY)
