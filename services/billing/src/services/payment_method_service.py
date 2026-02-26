"""Payment method service - card and payment method management."""

import logging
from uuid import UUID

from fastapi import Depends
from llamatrade_db.models import PaymentMethod
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import PaymentMethodResponse, SetupIntentResponse
from src.services.billing_service import BillingService, get_billing_service
from src.services.database import get_db
from src.stripe.client import StripeClient, StripeError, get_stripe_client

logger = logging.getLogger(__name__)


class PaymentMethodService:
    """Service for managing payment methods."""

    def __init__(
        self,
        db: AsyncSession,
        stripe_client: StripeClient,
        billing_service: BillingService,
    ):
        self.db = db
        self.stripe = stripe_client
        self.billing = billing_service

    async def create_setup_intent(self, tenant_id: UUID, email: str) -> SetupIntentResponse:
        """Create a SetupIntent for collecting card details."""
        # Ensure customer exists
        customer_id = await self.billing.ensure_stripe_customer(tenant_id, email)

        # Create SetupIntent
        try:
            result = await self.stripe.create_setup_intent(customer_id)
            return SetupIntentResponse(
                client_secret=result.client_secret,
                customer_id=result.customer_id,
            )
        except StripeError as e:
            logger.error(f"Failed to create setup intent: {e}")
            raise ValueError(f"Failed to initialize card setup: {e.message}")

    async def attach_payment_method(
        self,
        tenant_id: UUID,
        email: str,
        payment_method_id: str,
    ) -> PaymentMethodResponse:
        """Attach a payment method to the tenant's Stripe customer."""
        # Ensure customer exists
        customer_id = await self.billing.ensure_stripe_customer(tenant_id, email)

        # Attach payment method in Stripe
        try:
            stripe_pm = await self.stripe.attach_payment_method(
                customer_id=customer_id,
                payment_method_id=payment_method_id,
            )
        except StripeError as e:
            logger.error(f"Failed to attach payment method: {e}")
            raise ValueError(f"Failed to add card: {e.message}")

        # Check if this is the first payment method (make it default)
        existing = await self.list_payment_methods(tenant_id)
        is_default = len(existing) == 0

        if is_default:
            await self.stripe.set_default_payment_method(customer_id, payment_method_id)

        # Save to database
        payment_method = PaymentMethod(
            tenant_id=tenant_id,
            stripe_payment_method_id=stripe_pm.id,
            stripe_customer_id=customer_id,
            type=stripe_pm.type,
            card_brand=stripe_pm.card_brand,
            card_last4=stripe_pm.card_last4,
            card_exp_month=stripe_pm.card_exp_month,
            card_exp_year=stripe_pm.card_exp_year,
            is_default=is_default,
        )

        self.db.add(payment_method)
        await self.db.commit()
        await self.db.refresh(payment_method)

        return self._to_response(payment_method)

    async def list_payment_methods(self, tenant_id: UUID) -> list[PaymentMethodResponse]:
        """List all payment methods for a tenant."""
        result = await self.db.execute(
            select(PaymentMethod)
            .where(PaymentMethod.tenant_id == tenant_id)
            .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
        )
        methods = result.scalars().all()

        return [self._to_response(pm) for pm in methods]

    async def get_payment_method(
        self, tenant_id: UUID, payment_method_id: UUID
    ) -> PaymentMethodResponse | None:
        """Get a specific payment method."""
        result = await self.db.execute(
            select(PaymentMethod).where(
                PaymentMethod.tenant_id == tenant_id,
                PaymentMethod.id == payment_method_id,
            )
        )
        payment_method = result.scalar_one_or_none()

        if not payment_method:
            return None

        return self._to_response(payment_method)

    async def delete_payment_method(self, tenant_id: UUID, payment_method_id: UUID) -> bool:
        """Delete a payment method."""
        # Get the payment method
        result = await self.db.execute(
            select(PaymentMethod).where(
                PaymentMethod.tenant_id == tenant_id,
                PaymentMethod.id == payment_method_id,
            )
        )
        payment_method = result.scalar_one_or_none()

        if not payment_method:
            return False

        # Don't allow deleting the only default payment method if there's an active subscription
        if payment_method.is_default:
            # Check if there are other payment methods
            count_result = await self.db.execute(
                select(PaymentMethod)
                .where(PaymentMethod.tenant_id == tenant_id)
                .where(PaymentMethod.id != payment_method_id)
            )
            other_methods = count_result.scalars().all()

            if not other_methods:
                # Check for active subscription
                from llamatrade_db.models import Subscription

                sub_result = await self.db.execute(
                    select(Subscription).where(
                        Subscription.tenant_id == tenant_id,
                        Subscription.status.in_(["active", "trialing"]),
                        Subscription.stripe_subscription_id.isnot(None),
                    )
                )
                has_subscription = sub_result.scalar_one_or_none() is not None

                if has_subscription:
                    raise ValueError(
                        "Cannot delete the only payment method while you have "
                        "an active subscription"
                    )

        # Detach from Stripe
        try:
            await self.stripe.detach_payment_method(payment_method.stripe_payment_method_id)
        except StripeError as e:
            logger.error(f"Failed to detach payment method from Stripe: {e}")
            # Continue to delete from database even if Stripe fails

        # Delete from database
        await self.db.execute(delete(PaymentMethod).where(PaymentMethod.id == payment_method_id))
        await self.db.commit()

        # If this was the default, set a new default
        if payment_method.is_default:
            result = await self.db.execute(
                select(PaymentMethod)
                .where(PaymentMethod.tenant_id == tenant_id)
                .order_by(PaymentMethod.created_at.desc())
                .limit(1)
            )
            new_default = result.scalar_one_or_none()
            if new_default:
                new_default.is_default = True
                # Also update in Stripe
                try:
                    await self.stripe.set_default_payment_method(
                        new_default.stripe_customer_id,
                        new_default.stripe_payment_method_id,
                    )
                except StripeError:
                    pass  # Non-critical
                await self.db.commit()

        return True

    async def set_default_payment_method(
        self, tenant_id: UUID, payment_method_id: UUID
    ) -> PaymentMethodResponse:
        """Set a payment method as the default."""
        # Get the payment method
        result = await self.db.execute(
            select(PaymentMethod).where(
                PaymentMethod.tenant_id == tenant_id,
                PaymentMethod.id == payment_method_id,
            )
        )
        payment_method = result.scalar_one_or_none()

        if not payment_method:
            raise ValueError("Payment method not found")

        # Update in Stripe
        try:
            await self.stripe.set_default_payment_method(
                payment_method.stripe_customer_id,
                payment_method.stripe_payment_method_id,
            )
        except StripeError as e:
            logger.error(f"Failed to set default in Stripe: {e}")
            raise ValueError(f"Failed to set default: {e.message}")

        # Clear existing default
        await self.db.execute(
            update(PaymentMethod)
            .where(PaymentMethod.tenant_id == tenant_id)
            .values(is_default=False)
        )

        # Set new default
        payment_method.is_default = True
        await self.db.commit()
        await self.db.refresh(payment_method)

        return self._to_response(payment_method)

    # ===================
    # Sync from Stripe webhooks
    # ===================

    async def sync_payment_method_attached(
        self,
        tenant_id: UUID,
        stripe_payment_method_id: str,
        stripe_customer_id: str,
        pm_type: str,
        card_brand: str | None,
        card_last4: str | None,
        card_exp_month: int | None,
        card_exp_year: int | None,
    ) -> None:
        """Sync a payment method attachment from Stripe webhook."""
        # Check if already exists
        result = await self.db.execute(
            select(PaymentMethod).where(
                PaymentMethod.stripe_payment_method_id == stripe_payment_method_id
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            return  # Already synced

        # Check if this should be default
        result = await self.db.execute(
            select(PaymentMethod).where(PaymentMethod.tenant_id == tenant_id)
        )
        existing_methods = result.scalars().all()
        is_default = len(existing_methods) == 0

        payment_method = PaymentMethod(
            tenant_id=tenant_id,
            stripe_payment_method_id=stripe_payment_method_id,
            stripe_customer_id=stripe_customer_id,
            type=pm_type,
            card_brand=card_brand,
            card_last4=card_last4,
            card_exp_month=card_exp_month,
            card_exp_year=card_exp_year,
            is_default=is_default,
        )

        self.db.add(payment_method)
        await self.db.commit()

    async def sync_payment_method_detached(self, stripe_payment_method_id: str) -> None:
        """Sync a payment method detachment from Stripe webhook."""
        await self.db.execute(
            delete(PaymentMethod).where(
                PaymentMethod.stripe_payment_method_id == stripe_payment_method_id
            )
        )
        await self.db.commit()

    def _to_response(self, pm: PaymentMethod) -> PaymentMethodResponse:
        """Convert PaymentMethod model to response."""
        return PaymentMethodResponse(
            id=pm.id,
            type=pm.type,
            card_brand=pm.card_brand,
            card_last4=pm.card_last4,
            card_exp_month=pm.card_exp_month,
            card_exp_year=pm.card_exp_year,
            is_default=pm.is_default,
        )


async def get_payment_method_service(
    db: AsyncSession = Depends(get_db),
    stripe_client: StripeClient = Depends(get_stripe_client),
    billing_service: BillingService = Depends(get_billing_service),
) -> PaymentMethodService:
    """Dependency to get payment method service."""
    return PaymentMethodService(db, stripe_client, billing_service)
