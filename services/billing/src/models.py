"""Billing Service - Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class PlanTier(StrEnum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    TRIALING = "trialing"
    PAUSED = "paused"


class PlanResponse(BaseModel):
    id: str
    name: str
    tier: PlanTier
    price_monthly: float
    price_yearly: float
    features: list[str]
    limits: dict[str, Any]


class SubscriptionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    plan: PlanResponse
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    stripe_subscription_id: str | None
    created_at: datetime


class SubscriptionCreate(BaseModel):
    plan_id: str
    payment_method_id: str | None = None
    billing_cycle: str = "monthly"  # monthly, yearly


class UsageRecord(BaseModel):
    metric: str
    value: float
    limit: float | None
    percent_used: float | None
    period_start: datetime
    period_end: datetime


class UsageSummary(BaseModel):
    backtests_count: int
    backtests_limit: int | None
    live_strategies_count: int
    live_strategies_limit: int | None
    api_calls_count: int
    api_calls_limit: int | None
    data_requests_count: int
    period_start: datetime
    period_end: datetime


class InvoiceResponse(BaseModel):
    id: str
    amount: float
    currency: str
    status: str
    period_start: datetime
    period_end: datetime
    paid_at: datetime | None
    invoice_pdf: str | None
