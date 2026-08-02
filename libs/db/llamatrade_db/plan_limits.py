"""Read a tenant's plan limits from its active subscription (shared read helper).

Strategy and backtest gate creation on these limits; a tenant with no active
subscription falls back to the free tier.
"""

from __future__ import annotations

import sys
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Plan, Subscription
from llamatrade_proto.generated import billing_pb2

# Subscription states that entitle a tenant to its plan's limits.
_ENTITLED_STATUSES = (
    billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
    billing_pb2.SUBSCRIPTION_STATUS_TRIALING,
)

# Limits applied when a tenant has no active subscription.
FREE_TIER_LIMITS: dict[str, int] = {"live_strategies": 1, "backtests_per_month": 10}

# Plans encode an unlimited resource as null in their limits JSON.
UNLIMITED: int = sys.maxsize


class PlanLimitExceededError(Exception):
    """Raised when a tenant's usage has reached its plan limit for a resource."""

    def __init__(self, key: str, limit: int) -> None:
        self.key = key
        self.limit = limit
        super().__init__(f"plan limit reached: {limit} for {key}")


async def get_plan_limit(db: AsyncSession, tenant_id: UUID, key: str) -> int:
    """The tenant's numeric limit for ``key`` from its active plan, else the free tier."""
    limits = await db.scalar(
        select(Plan.limits)
        .join(Subscription, Subscription.plan_id == Plan.id)
        .where(
            Subscription.tenant_id == tenant_id,
            Subscription.status.in_(_ENTITLED_STATUSES),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    if isinstance(limits, dict) and key in limits:
        raw = limits[key]
        return UNLIMITED if raw is None else int(raw)
    return FREE_TIER_LIMITS.get(key, 0)


async def enforce_plan_limit(
    db: AsyncSession, tenant_id: UUID, key: str, current_count: int
) -> None:
    """Raise :class:`PlanLimitExceededError` when ``current_count`` is at the limit."""
    limit = await get_plan_limit(db, tenant_id, key)
    if current_count >= limit:
        raise PlanLimitExceededError(key, limit)
