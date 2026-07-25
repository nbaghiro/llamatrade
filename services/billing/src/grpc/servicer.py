"""Billing Connect servicer implementation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Type alias for generic request context (accepts any request/response types)
type AnyContext = RequestContext[object, object]

from llamatrade_common import current_context
from llamatrade_common.connect import resolve_identity_connect
from llamatrade_db import get_session_maker, system_session, tenant_session
from llamatrade_db.models import Invoice
from llamatrade_proto.generated import billing_pb2, common_pb2

from src.proto_mappers import (
    invoice_to_proto,
    payment_method_to_proto,
    plan_to_proto,
    subscription_to_proto,
)
from src.stripe.client import StripeError, get_stripe_client

logger = logging.getLogger(__name__)


def _customer_email(tenant_id: UUID) -> str:
    """Real user email from the verified token, else a tenant placeholder."""
    ctx = current_context()
    if ctx is not None and ctx.email:
        return ctx.email
    return f"user-{tenant_id}@llamatrade.example"


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

    async def get_subscription(
        self,
        request: billing_pb2.GetSubscriptionRequest,
        ctx: AnyContext,
    ) -> billing_pb2.GetSubscriptionResponse:
        """Get the current subscription for a tenant."""
        from src.services.billing_service import BillingService

        tenant_id, _ = resolve_identity_connect(request.context)

        async with tenant_session(tenant_id, self._maker()) as db:
            stripe_client = get_stripe_client()
            service = BillingService(db, stripe_client)
            subscription = await service.get_subscription(tenant_id)

            if not subscription:
                raise ConnectError(Code.NOT_FOUND, "No active subscription found")

            return billing_pb2.GetSubscriptionResponse(
                subscription=subscription_to_proto(subscription),
            )

    async def create_subscription(
        self,
        request: billing_pb2.CreateSubscriptionRequest,
        ctx: AnyContext,
    ) -> billing_pb2.CreateSubscriptionResponse:
        """Create a new subscription."""
        from src.models import SubscriptionCreateRequest
        from src.services.billing_service import BillingService

        tenant_id, _ = resolve_identity_connect(request.context)

        # Map proto billing interval to internal
        interval = request.interval

        create_request = SubscriptionCreateRequest(
            plan_id=request.plan_id,
            billing_cycle=interval,
            payment_method_id=request.payment_method_id if request.payment_method_id else "",
        )

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
                stripe_client = get_stripe_client()
                service = BillingService(db, stripe_client)

                email = _customer_email(tenant_id)

                subscription = await service.create_subscription(
                    tenant_id=tenant_id,
                    email=email,
                    request=create_request,
                )

                return billing_pb2.CreateSubscriptionResponse(
                    subscription=subscription_to_proto(subscription),
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

        tenant_id, _ = resolve_identity_connect(request.context)

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
                stripe_client = get_stripe_client()
                service = BillingService(db, stripe_client)
                subscription = await service.update_subscription(
                    tenant_id=tenant_id,
                    plan_id=request.plan_id,
                )

                return billing_pb2.UpdateSubscriptionResponse(
                    subscription=subscription_to_proto(subscription),
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

        tenant_id, _ = resolve_identity_connect(request.context)

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
                stripe_client = get_stripe_client()
                service = BillingService(db, stripe_client)
                subscription = await service.cancel_subscription(
                    tenant_id=tenant_id,
                    at_period_end=not request.cancel_immediately,
                )

                return billing_pb2.CancelSubscriptionResponse(
                    subscription=subscription_to_proto(subscription),
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

        tenant_id, _ = resolve_identity_connect(request.context)

        try:
            async with tenant_session(tenant_id, self._maker()) as db:
                stripe_client = get_stripe_client()
                service = BillingService(db, stripe_client)
                subscription = await service.reactivate_subscription(tenant_id)

                return billing_pb2.ResumeSubscriptionResponse(
                    subscription=subscription_to_proto(subscription),
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

        tenant_id, _ = resolve_identity_connect(request.context)

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
        tenant_id, _ = resolve_identity_connect(request.context)
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
            invoices=[invoice_to_proto(inv) for inv in rows],
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
        tenant_id, _ = resolve_identity_connect(request.context)

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

        return billing_pb2.GetInvoiceResponse(invoice=invoice_to_proto(invoice))

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
                plans=[plan_to_proto(p) for p in plans],
            )

    async def list_payment_methods(
        self,
        request: billing_pb2.ListPaymentMethodsRequest,
        ctx: AnyContext,
    ) -> billing_pb2.ListPaymentMethodsResponse:
        """List payment methods for a tenant."""
        from src.services.billing_service import BillingService
        from src.services.payment_method_service import PaymentMethodService

        tenant_id, _ = resolve_identity_connect(request.context)

        async with tenant_session(tenant_id, self._maker()) as db:
            stripe_client = get_stripe_client()
            billing_service = BillingService(db, stripe_client)
            service = PaymentMethodService(db, stripe_client, billing_service)
            methods = await service.list_payment_methods(tenant_id)

            return billing_pb2.ListPaymentMethodsResponse(
                payment_methods=[payment_method_to_proto(pm) for pm in methods],
            )

    async def create_setup_intent(
        self,
        request: billing_pb2.CreateSetupIntentRequest,
        ctx: AnyContext,
    ) -> billing_pb2.CreateSetupIntentResponse:
        """Create a Stripe SetupIntent (client_secret drives Stripe.js card collection)."""
        tenant_id, _ = resolve_identity_connect(request.context)

        stripe_client = get_stripe_client()
        customer_id = await stripe_client.get_or_create_customer(
            str(tenant_id), _customer_email(tenant_id)
        )
        try:
            result = await stripe_client.create_setup_intent(customer_id)
        except StripeError as e:
            raise ConnectError(Code.INTERNAL, f"Stripe setup intent failed: {e.message}")

        return billing_pb2.CreateSetupIntentResponse(
            client_secret=result.client_secret,
            customer_id=result.customer_id,
        )

    async def add_payment_method(
        self,
        request: billing_pb2.AddPaymentMethodRequest,
        ctx: AnyContext,
    ) -> billing_pb2.AddPaymentMethodResponse:
        """Add a payment method."""
        from src.services.billing_service import BillingService
        from src.services.payment_method_service import PaymentMethodService

        tenant_id, _ = resolve_identity_connect(request.context)
        email = _customer_email(tenant_id)

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
                    payment_method=payment_method_to_proto(payment_method),
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

        tenant_id, _ = resolve_identity_connect(request.context)
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
        """Create a Stripe-hosted subscription Checkout Session."""
        from src.services.billing_service import BillingService

        tenant_id, _ = resolve_identity_connect(request.context)

        async with tenant_session(tenant_id, self._maker()) as db:
            stripe_client = get_stripe_client()
            plan = await BillingService(db, stripe_client).get_plan_db(request.plan_id)
            if plan is None:
                raise ConnectError(Code.NOT_FOUND, f"Plan {request.plan_id} not found")
            price_id = (
                plan.stripe_price_id_monthly
                if request.interval == billing_pb2.BILLING_INTERVAL_MONTHLY
                else plan.stripe_price_id_yearly
            )
            if not price_id:
                raise ConnectError(
                    Code.FAILED_PRECONDITION,
                    "No Stripe price configured for this plan and interval",
                )
            customer_id = await stripe_client.get_or_create_customer(
                str(tenant_id), _customer_email(tenant_id)
            )
            try:
                result = await stripe_client.create_checkout_session(
                    customer_id=customer_id,
                    price_id=price_id,
                    success_url=request.success_url,
                    cancel_url=request.cancel_url,
                    trial_days=plan.trial_days,
                )
            except StripeError as e:
                raise ConnectError(Code.INTERNAL, f"Stripe checkout failed: {e.message}")

            return billing_pb2.CreateCheckoutSessionResponse(
                checkout_url=result.url,
                session_id=result.session_id,
            )

    async def create_portal_session(
        self,
        request: billing_pb2.CreatePortalSessionRequest,
        ctx: AnyContext,
    ) -> billing_pb2.CreatePortalSessionResponse:
        """Create a Stripe Customer Portal session for self-service management."""
        tenant_id, _ = resolve_identity_connect(request.context)

        stripe_client = get_stripe_client()
        customer_id = await stripe_client.get_or_create_customer(
            str(tenant_id), _customer_email(tenant_id)
        )
        try:
            portal_url = await stripe_client.create_portal_session(customer_id, request.return_url)
        except StripeError as e:
            raise ConnectError(Code.INTERNAL, f"Stripe portal failed: {e.message}")

        return billing_pb2.CreatePortalSessionResponse(portal_url=portal_url)
