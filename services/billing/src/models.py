"""Billing Service - Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from llamatrade_proto.generated.billing_pb2 import (
    BILLING_INTERVAL_MONTHLY,
    BillingInterval,
    PlanTier,
    SubscriptionStatus,
)

# Plan Schemas


class PlanResponse(BaseModel):
    """Plan details response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    tier: PlanTier.ValueType
    price_monthly: float
    price_yearly: float
    features: dict[str, bool]
    limits: dict[str, int | None]
    trial_days: int = 0


# Subscription Schemas


class SubscriptionResponse(BaseModel):
    """Subscription details response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    plan: PlanResponse
    status: SubscriptionStatus.ValueType
    billing_cycle: BillingInterval.ValueType
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    trial_start: datetime | None = None
    trial_end: datetime | None = None
    stripe_subscription_id: str | None = None
    created_at: datetime


class SubscriptionCreateRequest(BaseModel):
    """Request to create a subscription."""

    plan_id: str
    payment_method_id: str
    billing_cycle: BillingInterval.ValueType = BILLING_INTERVAL_MONTHLY


class SubscriptionUpdateRequest(BaseModel):
    """Request to update/change subscription plan."""

    plan_id: str


class SubscriptionCancelRequest(BaseModel):
    """Request to cancel subscription."""

    at_period_end: bool = True


# Payment Method Schemas


class SetupIntentResponse(BaseModel):
    """Response from creating a SetupIntent for card collection."""

    client_secret: str
    customer_id: str


class PaymentMethodResponse(BaseModel):
    """Payment method details response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    card_brand: str | None = None
    card_last4: str | None = None
    card_exp_month: int | None = None
    card_exp_year: int | None = None
    is_default: bool


class PaymentMethodCreate(BaseModel):
    """Request to attach a payment method."""

    payment_method_id: str = Field(
        ..., description="Stripe PaymentMethod ID from frontend (pm_...)"
    )
