"""Billing Service - Pydantic schemas (request/input validation types only).

Read/response shapes are the proto messages, mapped directly from DB rows in
``src/proto_mappers.py`` (decision 1A) — there are no read DTOs here.
"""

from pydantic import BaseModel

from llamatrade_proto.generated.billing_pb2 import (
    BILLING_INTERVAL_MONTHLY,
    BillingInterval,
)

# Subscription Schemas


class SubscriptionCreateRequest(BaseModel):
    """Request to create a subscription."""

    plan_id: str
    payment_method_id: str
    billing_cycle: BillingInterval.ValueType = BILLING_INTERVAL_MONTHLY


# Payment Method Schemas


class SetupIntentResponse(BaseModel):
    """Response from creating a SetupIntent for card collection."""

    client_secret: str
    customer_id: str
