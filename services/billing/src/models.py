"""Billing Service - Pydantic schemas."""

from datetime import datetime
from typing import TypedDict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from llamatrade_proto.generated import billing_pb2

# ===================
# Conversion helpers: proto int -> str (for display/API)
# ===================

_PLAN_TIER_TO_STR: dict[int, str] = {
    billing_pb2.PLAN_TIER_UNSPECIFIED: "unspecified",
    billing_pb2.PLAN_TIER_FREE: "free",
    billing_pb2.PLAN_TIER_STARTER: "starter",
    billing_pb2.PLAN_TIER_PRO: "pro",
}

_SUBSCRIPTION_STATUS_TO_STR: dict[int, str] = {
    billing_pb2.SUBSCRIPTION_STATUS_UNSPECIFIED: "unspecified",
    billing_pb2.SUBSCRIPTION_STATUS_ACTIVE: "active",
    billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE: "past_due",
    billing_pb2.SUBSCRIPTION_STATUS_CANCELED: "canceled",
    billing_pb2.SUBSCRIPTION_STATUS_TRIALING: "trialing",
    billing_pb2.SUBSCRIPTION_STATUS_PAUSED: "paused",
}

_BILLING_INTERVAL_TO_STR: dict[int, str] = {
    billing_pb2.BILLING_INTERVAL_UNSPECIFIED: "unspecified",
    billing_pb2.BILLING_INTERVAL_MONTHLY: "monthly",
    billing_pb2.BILLING_INTERVAL_YEARLY: "yearly",
}


def plan_tier_to_str(value: int) -> str:
    """Convert PlanTier proto int to string."""
    return _PLAN_TIER_TO_STR.get(value, "unspecified")


def subscription_status_to_str(value: int) -> str:
    """Convert SubscriptionStatus proto int to string."""
    return _SUBSCRIPTION_STATUS_TO_STR.get(value, "unspecified")


def billing_interval_to_str(value: int) -> str:
    """Convert BillingInterval proto int to string."""
    return _BILLING_INTERVAL_TO_STR.get(value, "unspecified")


class PlanLimits(TypedDict, total=False):
    """Plan limits configuration."""

    backtests_per_month: int
    live_strategies: int
    api_calls_per_day: int
    data_requests_per_day: int
    historical_data_years: int
    priority_support: bool


# ===================
# Plan Schemas
# ===================


class PlanFeatures(TypedDict, total=False):
    """Plan features configuration."""

    backtests: bool
    paper_trading: bool
    live_trading: bool
    basic_indicators: bool
    all_indicators: bool
    email_alerts: bool
    sms_alerts: bool
    webhook_alerts: bool
    priority_support: bool


class PlanResponse(BaseModel):
    """Plan details response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    tier: int  # PlanTier proto int
    price_monthly: float
    price_yearly: float
    features: dict[str, bool]
    limits: dict[str, int | None]
    trial_days: int = 0


# ===================
# Subscription Schemas
# ===================


class SubscriptionResponse(BaseModel):
    """Subscription details response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    plan: PlanResponse
    status: int  # SubscriptionStatus proto int
    billing_cycle: int  # BillingInterval proto int
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
    billing_cycle: int = billing_pb2.BILLING_INTERVAL_MONTHLY


class SubscriptionUpdateRequest(BaseModel):
    """Request to update/change subscription plan."""

    plan_id: str


class SubscriptionCancelRequest(BaseModel):
    """Request to cancel subscription."""

    at_period_end: bool = True


# ===================
# Payment Method Schemas
# ===================


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


# ===================
# Usage Schemas
# ===================


class UsageRecord(BaseModel):
    """Usage record for a single metric."""

    metric: str
    value: float
    limit: float | None
    percent_used: float | None
    period_start: datetime
    period_end: datetime


class UsageSummary(BaseModel):
    """Summary of usage across all metrics."""

    backtests_count: int
    backtests_limit: int | None
    live_strategies_count: int
    live_strategies_limit: int | None
    api_calls_count: int
    api_calls_limit: int | None
    data_requests_count: int
    period_start: datetime
    period_end: datetime


# ===================
# Invoice Schemas
# ===================


class InvoiceResponse(BaseModel):
    """Invoice details response."""

    id: str
    amount: float
    currency: str
    status: str
    period_start: datetime
    period_end: datetime
    paid_at: datetime | None = None
    invoice_pdf: str | None = None
    hosted_invoice_url: str | None = None


# ===================
# Webhook Schemas
# ===================


class WebhookEvent(BaseModel):
    """Stripe webhook event."""

    id: str
    type: str
    data: dict[str, object]
