"""Billing Connect servicer implementation."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import jwt
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Type alias for generic request context (accepts any request/response types)
type AnyContext = RequestContext[object, object]

from llamatrade_db import get_session_maker, system_session, tenant_session
from llamatrade_db.models import Invoice
from llamatrade_proto.generated import billing_pb2, common_pb2

from src.models import (
    PaymentMethodResponse,
    PlanResponse,
    SubscriptionResponse,
)
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
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    def _maker(self) -> async_sessionmaker[AsyncSession]:
        """The session factory (lazily created; tests inject a test-DB factory)."""
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        return self._session_maker

    def _get_tenant_id(self, ctx: AnyContext) -> UUID:
        """Extract tenant_id from JWT token in Authorization header."""
        auth_header: str = ctx.request_headers().get("authorization", "")
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
        ctx: AnyContext,
    ) -> billing_pb2.GetSubscriptionResponse:
        """Get the current subscription for a tenant."""
        from src.services.billing_service import BillingService

        tenant_id = self._get_tenant_id(ctx)

        async with tenant_session(tenant_id, self._maker()) as db:
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
        ctx: AnyContext,
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
            payment_method_id=request.payment_method_id if request.payment_method_id else "",
        )

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
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
        ctx: AnyContext,
    ) -> billing_pb2.UpdateSubscriptionResponse:
        """Update subscription (change plan)."""
        from src.services.billing_service import BillingService

        tenant_id = self._get_tenant_id(ctx)

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
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
        ctx: AnyContext,
    ) -> billing_pb2.CancelSubscriptionResponse:
        """Cancel subscription."""
        from src.services.billing_service import BillingService

        tenant_id = self._get_tenant_id(ctx)

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
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
        ctx: AnyContext,
    ) -> billing_pb2.ResumeSubscriptionResponse:
        """Resume a cancelled subscription."""
        from src.services.billing_service import BillingService

        tenant_id = self._get_tenant_id(ctx)

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
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
        ctx: AnyContext,
    ) -> billing_pb2.GetUsageResponse:
        """Get usage metrics for a tenant.

        Counts are lifetime-to-date, computed server-side from the shared DB, and
        mirror the meters the web app derives client-side (see
        ``apps/web/src/store/billing.ts::fetchUsageCounts``) so the numbers agree:

        - ``strategies_created`` — non-archived strategies (matches ``listStrategies``)
        - ``active_strategies`` — RUNNING strategy executions (matches the RUNNING
          filter over ``listStrategyPerformance``)
        - ``backtests_run`` — all backtests for the tenant (matches ``listBacktests``)
        - ``live_sessions`` — currently RUNNING trading sessions
        - ``api_calls`` — total Copilot messages across agent sessions

        ``period_start``/``period_end`` reflect the current subscription period when
        a subscription exists, else the calendar month. Fields not tracked in the DB
        (``backtest_compute_minutes``, ``market_data_requests``, ``storage_bytes``,
        ``orders_placed``) are left at 0.
        """
        from llamatrade_db.models import (
            AgentSession,
            Backtest,
            Strategy,
            StrategyExecution,
            TradingSession,
        )
        from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_RUNNING
        from llamatrade_proto.generated.strategy_pb2 import STRATEGY_STATUS_ARCHIVED

        tenant_id = self._get_tenant_id(ctx)

        async with tenant_session(tenant_id, self._maker()) as db:
            strategies_created = (
                await db.scalar(
                    select(func.count())
                    .select_from(Strategy)
                    .where(
                        Strategy.tenant_id == tenant_id,
                        Strategy.status != STRATEGY_STATUS_ARCHIVED,
                    )
                )
            ) or 0
            active_strategies = (
                await db.scalar(
                    select(func.count())
                    .select_from(StrategyExecution)
                    .where(
                        StrategyExecution.tenant_id == tenant_id,
                        StrategyExecution.status == EXECUTION_STATUS_RUNNING,
                    )
                )
            ) or 0
            backtests_run = (
                await db.scalar(
                    select(func.count())
                    .select_from(Backtest)
                    .where(Backtest.tenant_id == tenant_id)
                )
            ) or 0
            live_sessions = (
                await db.scalar(
                    select(func.count())
                    .select_from(TradingSession)
                    .where(
                        TradingSession.tenant_id == tenant_id,
                        TradingSession.status == EXECUTION_STATUS_RUNNING,
                    )
                )
            ) or 0
            api_calls = (
                await db.scalar(
                    select(func.coalesce(func.sum(AgentSession.message_count), 0)).where(
                        AgentSession.tenant_id == tenant_id
                    )
                )
            ) or 0

            period_start, period_end, period_id = await self._resolve_period(
                db, tenant_id, request.period_id
            )

        return billing_pb2.GetUsageResponse(
            usage=billing_pb2.Usage(
                tenant_id=str(tenant_id),
                period_id=period_id,
                strategies_created=strategies_created,
                active_strategies=active_strategies,
                backtests_run=backtests_run,
                backtest_compute_minutes=0,
                live_sessions=live_sessions,
                orders_placed=0,
                market_data_requests=0,
                storage_bytes=0,
                api_calls=api_calls,
                period_start=common_pb2.Timestamp(seconds=int(period_start.timestamp())),
                period_end=common_pb2.Timestamp(seconds=int(period_end.timestamp())),
            ),
        )

    async def _resolve_period(
        self, db: AsyncSession, tenant_id: UUID, requested_period_id: str
    ) -> tuple[datetime, datetime, str]:
        """Resolve the reporting window: current subscription period, else month."""
        from llamatrade_db.models import Subscription

        subscription = await db.scalar(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        if subscription is not None:
            period_start = subscription.current_period_start
            period_end = subscription.current_period_end
        else:
            now = datetime.now(UTC)
            period_start = datetime(now.year, now.month, 1, tzinfo=UTC)
            period_end = (
                datetime(now.year + 1, 1, 1, tzinfo=UTC)
                if now.month == 12
                else datetime(now.year, now.month + 1, 1, tzinfo=UTC)
            )

        if requested_period_id and requested_period_id != "current":
            period_id = requested_period_id
        else:
            period_id = period_start.strftime("%Y-%m")
        return period_start, period_end, period_id

    async def list_invoices(
        self,
        request: billing_pb2.ListInvoicesRequest,
        ctx: AnyContext,
    ) -> billing_pb2.ListInvoicesResponse:
        """List a tenant's invoices, newest first."""
        tenant_id = self._get_tenant_id(ctx)
        page = request.pagination.page or 1
        page_size = request.pagination.page_size or 20

        async with tenant_session(tenant_id, self._maker()) as db:
            total = (
                await db.scalar(
                    select(func.count()).select_from(Invoice).where(Invoice.tenant_id == tenant_id)
                )
            ) or 0
            rows = (
                (
                    await db.execute(
                        select(Invoice)
                        .where(Invoice.tenant_id == tenant_id)
                        .order_by(Invoice.created_at.desc())
                        .limit(page_size)
                        .offset((page - 1) * page_size)
                    )
                )
                .scalars()
                .all()
            )

        total_pages = (total + page_size - 1) // page_size if total else 1
        return billing_pb2.ListInvoicesResponse(
            invoices=[self._to_proto_invoice(inv) for inv in rows],
            pagination=common_pb2.PaginationResponse(
                total_items=total,
                total_pages=total_pages,
                current_page=page,
                page_size=page_size,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )

    async def get_invoice(
        self,
        request: billing_pb2.GetInvoiceRequest,
        ctx: AnyContext,
    ) -> billing_pb2.GetInvoiceResponse:
        """Get a specific invoice, tenant-scoped."""
        tenant_id = self._get_tenant_id(ctx)

        try:
            invoice_id = UUID(request.invoice_id)
        except ValueError, AttributeError:
            raise ConnectError(Code.NOT_FOUND, f"Invoice not found: {request.invoice_id}")

        async with tenant_session(tenant_id, self._maker()) as db:
            invoice = await db.scalar(
                select(Invoice).where(
                    Invoice.id == invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
            )

        if invoice is None:
            raise ConnectError(Code.NOT_FOUND, f"Invoice not found: {request.invoice_id}")

        return billing_pb2.GetInvoiceResponse(invoice=self._to_proto_invoice(invoice))

    async def list_plans(
        self,
        request: billing_pb2.ListPlansRequest,
        ctx: AnyContext,
    ) -> billing_pb2.ListPlansResponse:
        """List available plans (global catalog — not tenant-scoped)."""
        from src.services.billing_service import BillingService

        async with system_session(self._maker()) as db:
            stripe_client = get_stripe_client()
            service = BillingService(db, stripe_client)
            plans = await service.list_plans()

            return billing_pb2.ListPlansResponse(
                plans=[self._to_proto_plan(p) for p in plans],
            )

    async def list_payment_methods(
        self,
        request: billing_pb2.ListPaymentMethodsRequest,
        ctx: AnyContext,
    ) -> billing_pb2.ListPaymentMethodsResponse:
        """List payment methods for a tenant."""
        from src.services.billing_service import BillingService
        from src.services.payment_method_service import PaymentMethodService

        tenant_id = self._get_tenant_id(ctx)

        async with tenant_session(tenant_id, self._maker()) as db:
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
        ctx: AnyContext,
    ) -> billing_pb2.AddPaymentMethodResponse:
        """Add a payment method."""
        from src.services.billing_service import BillingService
        from src.services.payment_method_service import PaymentMethodService

        tenant_id = self._get_tenant_id(ctx)
        email = f"user-{tenant_id}@llamatrade.example"

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
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
        ctx: AnyContext,
    ) -> billing_pb2.RemovePaymentMethodResponse:
        """Remove a payment method."""
        from src.services.billing_service import BillingService
        from src.services.payment_method_service import PaymentMethodService

        tenant_id = self._get_tenant_id(ctx)
        payment_method_id = UUID(request.payment_method_id)

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
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
        ctx: AnyContext,
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
        ctx: AnyContext,
    ) -> billing_pb2.CreatePortalSessionResponse:
        """Create a Stripe customer portal session."""
        tenant_id = self._get_tenant_id(ctx)

        # This would integrate with Stripe Customer Portal
        return billing_pb2.CreatePortalSessionResponse(
            portal_url=f"https://billing.stripe.com/placeholder/{tenant_id}",
        )

    # Helper methods

    def _to_proto_invoice(self, inv: Invoice) -> billing_pb2.Invoice:
        """Convert a DB invoice to proto."""
        cur = (inv.currency or "usd").upper()

        def money(amount: Decimal) -> common_pb2.Money:
            return common_pb2.Money(currency=cur, amount=str(amount))

        def ts(value: datetime | None) -> common_pb2.Timestamp | None:
            return common_pb2.Timestamp(seconds=int(value.timestamp())) if value else None

        items = [
            billing_pb2.InvoiceItem(
                description=str(li.get("description", "")),
                amount=common_pb2.Money(currency=cur, amount=str(li.get("amount", "0"))),
            )
            for li in (inv.line_items or [])
        ]
        return billing_pb2.Invoice(
            id=str(inv.id),
            tenant_id=str(inv.tenant_id),
            subscription_id=str(inv.subscription_id) if inv.subscription_id else "",
            amount=money(inv.amount_due),
            amount_paid=money(inv.amount_paid),
            amount_remaining=money(inv.amount_due - inv.amount_paid),
            status=cast("billing_pb2.InvoiceStatus.ValueType", inv.status),
            period_start=ts(inv.period_start),
            period_end=ts(inv.period_end),
            due_date=ts(inv.due_date),
            paid_at=ts(inv.paid_at),
            pdf_url=inv.invoice_pdf or "",
            stripe_invoice_id=inv.stripe_invoice_id,
            items=items,
        )

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
                    if subscription.billing_cycle == billing_pb2.BILLING_INTERVAL_MONTHLY
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

    def _to_proto_payment_method(self, pm: PaymentMethodResponse) -> billing_pb2.PaymentMethod:
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

    def _to_proto_status(
        self, status: billing_pb2.SubscriptionStatus.ValueType
    ) -> billing_pb2.SubscriptionStatus.ValueType:
        """Return proto status value (already proto ValueType)."""
        return status

    def _to_proto_tier(
        self, tier: billing_pb2.PlanTier.ValueType
    ) -> billing_pb2.PlanTier.ValueType:
        """Return proto tier value (already proto ValueType)."""
        return tier

    def _to_proto_interval(
        self, interval: billing_pb2.BillingInterval.ValueType
    ) -> billing_pb2.BillingInterval.ValueType:
        """Return proto interval value (already proto ValueType)."""
        return interval

    def _from_proto_interval(
        self, interval: billing_pb2.BillingInterval.ValueType
    ) -> billing_pb2.BillingInterval.ValueType:
        """Return proto interval value (already proto ValueType)."""
        return interval
