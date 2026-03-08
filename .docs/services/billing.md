# Billing Service

## Overview

The Billing Service manages subscriptions, payment methods, and plan enforcement for LlamaTrade. It integrates with Stripe to handle the financial aspects of the SaaS platform while maintaining local state for fast permission checks.

**Why This Service Matters:**

- **Monetization Engine**: The billing service enables the business model, converting users from free trials to paying customers with different feature tiers.
- **Feature Gating**: Plan limits (e.g., "5 backtests/month on Free") are enforced by checking subscription status, preventing unauthorized feature access.
- **Stripe as Source of Truth**: Stripe handles PCI compliance, payment processing, and subscription lifecycle. We sync state locally for performance but Stripe webhooks are the authoritative source.

**Core Responsibilities:**

- Subscription lifecycle management (create, update, cancel, resume)
- Plan and pricing management (Free, Starter $29, Pro $99)
- Payment method handling (SetupIntents, card management)
- Stripe webhook processing for state synchronization
- Usage tracking and limit enforcement (stubbed)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Billing Service                                  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Connect Protocol (gRPC)                        │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│  ┌───────────────────────────────▼─────────────────────────────────────┐    │
│  │                       BillingServicer                               │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────┐    │    │
│  │  │ Subscriptions   │  │ Payment Methods │  │ Plans & Usage     │    │    │
│  │  │ - get/create    │  │ - list/add      │  │ - list_plans      │    │    │
│  │  │ - update/cancel │  │ - remove        │  │ - get_usage       │    │    │
│  │  │ - resume        │  │ - set_default   │  │                   │    │    │
│  │  └─────────────────┘  └─────────────────┘  └───────────────────┘    │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│  ┌───────────────────────────────▼─────────────────────────────────────┐    │
│  │                        Service Layer                                │    │
│  │  ┌──────────────────┐  ┌────────────────────┐  ┌────────────────┐   │    │
│  │  │  BillingService  │  │PaymentMethodService│  │  StripeClient  │   │    │
│  │  │  - subscriptions │  │  - attach/detach   │  │  - API wrapper │   │    │
│  │  │  - plans         │  │  - list/default    │  │  - webhooks    │   │    │
│  │  └──────────────────┘  └────────────────────┘  └────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Webhook Handler (FastAPI)                      │    │
│  │           POST /webhooks/stripe → verify signature → process        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└──────────────────────────────────┼──────────────────────────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   PostgreSQL    │      │     Stripe      │      │  Auth Service   │
│  - plans        │      │  - customers    │      │  - tenant_id    │
│  - subscriptions│ ◄───►│  - subscriptions│      │  - JWT verify   │
│  - payment_methods│    │  - payments     │      └─────────────────┘
└─────────────────┘      │  - invoices     │
                         └─────────────────┘
```

### Stripe Integration Flow

```
┌──────────┐         ┌──────────────┐         ┌────────────┐
│  Client  │         │   Billing    │         │   Stripe   │
└────┬─────┘         └──────┬───────┘         └─────┬──────┘
     │                      │                       │
     │ 1. Create SetupIntent│                       │
     │─────────────────────>│                       │
     │                      │ 2. SetupIntent.create │
     │                      │──────────────────────>│
     │                      │                       │
     │                      │ 3. client_secret      │
     │<─────────────────────│<──────────────────────│
     │                      │                       │
     │ 4. Stripe.js collects│                       │
     │    card details      │                       │
     │─────────────────────────────────────────────>│
     │                      │                       │
     │ 5. pm_xxx returned   │                       │
     │<─────────────────────────────────────────────│
     │                      │                       │
     │ 6. Add payment method│                       │
     │─────────────────────>│                       │
     │                      │ 7. Attach to customer │
     │                      │──────────────────────>│
     │                      │                       │
     │ 8. Create subscription                       │
     │─────────────────────>│                       │
     │                      │ 9. Subscription.create│
     │                      │──────────────────────>│
     │                      │                       │
     │                      │ 10. Webhook: sub.created
     │                      │<──────────────────────│
     │                      │                       │
     │ 11. Subscription active                      │
     │<─────────────────────│                       │
```

---

## Directory Structure

```
services/billing/
├── src/
│   ├── main.py                     # FastAPI app, health check
│   ├── models.py                   # Pydantic schemas (236 lines)
│   ├── grpc/
│   │   └── servicer.py             # BillingServicer (469 lines)
│   ├── services/
│   │   ├── database.py             # Async SQLAlchemy sessions
│   │   ├── billing_service.py      # Subscription/plan logic (502 lines)
│   │   └── payment_method_service.py # Payment method CRUD
│   ├── stripe/
│   │   └── client.py               # Stripe API wrapper (387 lines)
│   └── routers/
│       └── webhooks.py             # Stripe webhook endpoint
├── tests/
│   ├── conftest.py                 # Fixtures, mocks
│   ├── test_services.py            # Service layer tests
│   ├── test_stripe_client.py       # Stripe client tests
│   ├── test_grpc_billing.py        # gRPC servicer tests
│   ├── test_grpc_servicer_extended.py
│   ├── test_billing_service_extended.py
│   ├── test_payment_method_extended.py
│   ├── test_webhooks.py            # Webhook handler tests
│   └── test_webhook_handlers.py
├── pyproject.toml
└── Dockerfile
```

---

## Core Components

| Component                | File                                 | Purpose                                   |
| ------------------------ | ------------------------------------ | ----------------------------------------- |
| **BillingServicer**      | `grpc/servicer.py`                   | Connect protocol servicer, 14 RPC methods |
| **BillingService**       | `services/billing_service.py`        | Subscription and plan management          |
| **PaymentMethodService** | `services/payment_method_service.py` | Payment method CRUD                       |
| **StripeClient**         | `stripe/client.py`                   | Stripe API wrapper with typed results     |

---

## RPC Endpoints

### Subscriptions

| Method               | Request                     | Response                     | Description                                      |
| -------------------- | --------------------------- | ---------------------------- | ------------------------------------------------ |
| `GetSubscription`    | `GetSubscriptionRequest`    | `GetSubscriptionResponse`    | Get current subscription for tenant              |
| `CreateSubscription` | `CreateSubscriptionRequest` | `CreateSubscriptionResponse` | Start new subscription                           |
| `UpdateSubscription` | `UpdateSubscriptionRequest` | `UpdateSubscriptionResponse` | Change to different plan                         |
| `CancelSubscription` | `CancelSubscriptionRequest` | `CancelSubscriptionResponse` | Cancel subscription (immediate or at period end) |
| `ResumeSubscription` | `ResumeSubscriptionRequest` | `ResumeSubscriptionResponse` | Reactivate cancelled subscription                |

### Payment Methods

| Method                | Request                      | Response                      | Description               |
| --------------------- | ---------------------------- | ----------------------------- | ------------------------- |
| `ListPaymentMethods`  | `ListPaymentMethodsRequest`  | `ListPaymentMethodsResponse`  | List all cards on file    |
| `AddPaymentMethod`    | `AddPaymentMethodRequest`    | `AddPaymentMethodResponse`    | Attach new payment method |
| `RemovePaymentMethod` | `RemovePaymentMethodRequest` | `RemovePaymentMethodResponse` | Detach payment method     |

### Plans

| Method      | Request            | Response            | Description                       |
| ----------- | ------------------ | ------------------- | --------------------------------- |
| `ListPlans` | `ListPlansRequest` | `ListPlansResponse` | List available subscription tiers |

### Usage (Stubbed)

| Method     | Request           | Response           | Description                      |
| ---------- | ----------------- | ------------------ | -------------------------------- |
| `GetUsage` | `GetUsageRequest` | `GetUsageResponse` | Get current period usage metrics |

### Invoices (Stubbed)

| Method         | Request               | Response               | Description          |
| -------------- | --------------------- | ---------------------- | -------------------- |
| `ListInvoices` | `ListInvoicesRequest` | `ListInvoicesResponse` | List past invoices   |
| `GetInvoice`   | `GetInvoiceRequest`   | `GetInvoiceResponse`   | Get specific invoice |

### Portal Sessions (Stubbed)

| Method                  | Request                        | Response                        | Description                    |
| ----------------------- | ------------------------------ | ------------------------------- | ------------------------------ |
| `CreateCheckoutSession` | `CreateCheckoutSessionRequest` | `CreateCheckoutSessionResponse` | Create Stripe Checkout session |
| `CreatePortalSession`   | `CreatePortalSessionRequest`   | `CreatePortalSessionResponse`   | Create customer portal session |

---

## Data Models

### Plan Tiers

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SUBSCRIPTION TIERS                               │
├─────────────┬─────────────────┬────────────────┬────────────────────────┤
│    FREE     │    STARTER      │      PRO       │     (Future)           │
│   $0/mo     │    $29/mo       │    $99/mo      │                        │
├─────────────┼─────────────────┼────────────────┼────────────────────────┤
│ 5 backtests │ 50 backtests    │ Unlimited      │                        │
│ Paper only  │ 1 live strategy │ 5 strategies   │                        │
│ Basic ind.  │ All indicators  │ All + support  │                        │
│ No alerts   │ Email alerts    │ All channels   │                        │
└─────────────┴─────────────────┴────────────────┴────────────────────────┘
```

### Pydantic Schemas

```python
# Plan Response
class PlanResponse(BaseModel):
    id: str                     # "free", "starter", "pro"
    name: str                   # "Free", "Starter", "Pro"
    tier: int                   # Proto enum: PLAN_TIER_FREE, etc.
    price_monthly: float        # 0, 29, 99
    price_yearly: float         # 0, 290, 990
    features: dict[str, bool]   # {"backtests": True, "live_trading": False, ...}
    limits: dict[str, int | None]  # {"backtests_per_month": 5, ...}
    trial_days: int             # 0 (free), 14 (paid plans)

# Subscription Response
class SubscriptionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    plan: PlanResponse
    status: int                 # SUBSCRIPTION_STATUS_ACTIVE, etc.
    billing_cycle: int          # BILLING_INTERVAL_MONTHLY/YEARLY
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    trial_start: datetime | None
    trial_end: datetime | None
    stripe_subscription_id: str | None
    created_at: datetime

# Payment Method Response
class PaymentMethodResponse(BaseModel):
    id: UUID
    type: str                   # "card"
    card_brand: str | None      # "visa", "mastercard"
    card_last4: str | None      # "4242"
    card_exp_month: int | None  # 12
    card_exp_year: int | None   # 2025
    is_default: bool
```

### Default Plans

When no plans exist in the database, these defaults are used:

```python
DEFAULT_PLANS = [
    PlanResponse(
        id="free",
        name="Free",
        tier=PLAN_TIER_FREE,
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
        tier=PLAN_TIER_STARTER,
        price_monthly=29,
        price_yearly=290,
        features={...},
        limits={"backtests_per_month": 50, "live_strategies": 1, ...},
        trial_days=14,
    ),
    PlanResponse(
        id="pro",
        name="Pro",
        tier=PLAN_TIER_PRO,
        price_monthly=99,
        price_yearly=990,
        features={..., "priority_support": True},
        limits={"backtests_per_month": None, "live_strategies": 5, ...},
        trial_days=14,
    ),
]
```

---

## Stripe Integration

### StripeClient Methods

| Method                                                          | Description                                       |
| --------------------------------------------------------------- | ------------------------------------------------- |
| `get_or_create_customer(tenant_id, email)`                      | Find or create Stripe customer by tenant metadata |
| `create_setup_intent(customer_id)`                              | Create SetupIntent for card collection            |
| `attach_payment_method(customer_id, pm_id)`                     | Link payment method to customer                   |
| `detach_payment_method(pm_id)`                                  | Remove payment method from customer               |
| `list_payment_methods(customer_id)`                             | List customer's payment methods                   |
| `set_default_payment_method(customer_id, pm_id)`                | Set default for invoices                          |
| `create_subscription(customer_id, price_id, pm_id, trial_days)` | Start subscription                                |
| `update_subscription(sub_id, price_id)`                         | Change subscription price/plan                    |
| `cancel_subscription(sub_id, at_period_end)`                    | Cancel immediately or at period end               |
| `reactivate_subscription(sub_id)`                               | Remove cancel_at_period_end flag                  |
| `verify_webhook_signature(payload, sig, secret)`                | Verify Stripe webhook authenticity                |

### Webhook Events Handled

| Event Type                      | Action                           |
| ------------------------------- | -------------------------------- |
| `customer.subscription.created` | Create local subscription record |
| `customer.subscription.updated` | Sync status, period dates        |
| `customer.subscription.deleted` | Mark subscription as cancelled   |
| `invoice.paid`                  | Log successful payment           |
| `invoice.payment_failed`        | Update subscription to past_due  |
| `payment_method.attached`       | Sync payment method              |
| `payment_method.detached`       | Remove from local DB             |

### Webhook Signature Verification

```python
def verify_webhook_signature(
    self, payload: bytes, sig_header: str, webhook_secret: str
) -> Event:
    """Verify webhook signature and return the event."""
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        return event
    except stripe.SignatureVerificationError:
        raise StripeError("Invalid webhook signature")
```

---

## Configuration

### Environment Variables

| Variable                | Required | Default | Description                  |
| ----------------------- | -------- | ------- | ---------------------------- |
| `DATABASE_URL`          | Yes      | -       | PostgreSQL connection string |
| `STRIPE_SECRET_KEY`     | Yes      | -       | Stripe API secret key        |
| `STRIPE_WEBHOOK_SECRET` | Yes      | -       | Webhook signing secret       |
| `JWT_SECRET`            | Yes      | -       | For token validation         |
| `BILLING_PORT`          | No       | `8880`  | Service port                 |

### Port Assignment

| Service | Port |
| ------- | ---- |
| Billing | 8880 |

---

## Health Check

```http
GET /health
```

**Response:**

```json
{
  "status": "healthy",
  "service": "billing",
  "version": "0.1.0"
}
```

---

## Internal Service Connections

### Who Calls Billing Service

| Service          | Methods Used                               | Purpose                                      |
| ---------------- | ------------------------------------------ | -------------------------------------------- |
| **Web Frontend** | `GetSubscription`, `ListPlans`             | Display subscription status                  |
| **Web Frontend** | `CreateSubscription`, `CancelSubscription` | Manage subscription                          |
| **Web Frontend** | `ListPaymentMethods`, `AddPaymentMethod`   | Manage payment methods                       |
| **Strategy**     | `GetSubscription`                          | Check plan limits before creating strategies |
| **Backtest**     | `GetSubscription`                          | Enforce backtest quotas                      |

### What Billing Service Calls

| Target           | Purpose                                     |
| ---------------- | ------------------------------------------- |
| **PostgreSQL**   | Plan, subscription, payment method storage  |
| **Stripe API**   | Payment processing, subscription management |
| **Auth Service** | JWT token validation                        |

---

## Complete Data Flow Example

### Subscribing to a Paid Plan

```
1. User clicks "Upgrade to Starter" on billing page

2. Frontend calls CreateSetupIntent (if no payment method exists)
   └─> BillingServicer.create_setup_intent()
   └─> StripeClient.get_or_create_customer(tenant_id, email)
   └─> StripeClient.create_setup_intent(customer_id)
   └─> Returns client_secret

3. Frontend uses Stripe.js to collect card
   └─> stripe.confirmCardSetup(client_secret, {payment_method: {card}})
   └─> Returns payment_method_id (pm_xxx)

4. Frontend calls AddPaymentMethod
   └─> BillingServicer.add_payment_method(pm_id)
   └─> PaymentMethodService.attach_payment_method()
   └─> StripeClient.attach_payment_method(customer_id, pm_id)
   └─> Insert into payment_methods table

5. Frontend calls CreateSubscription
   └─> BillingServicer.create_subscription(plan_id="starter", pm_id)
   └─> BillingService.create_subscription()
       └─> Get plan from DB or DEFAULT_PLANS
       └─> Get Stripe price_id for plan
       └─> StripeClient.create_subscription(customer_id, price_id, pm_id, trial_days=14)
       └─> Insert into subscriptions table
   └─> Return SubscriptionResponse with status=trialing

6. Stripe sends webhook: customer.subscription.created
   └─> POST /webhooks/stripe
   └─> Verify signature
   └─> BillingService.sync_subscription_from_stripe()
   └─> Confirm local record matches Stripe

7. After 14 days, Stripe charges the card
   └─> Webhook: invoice.paid
   └─> Subscription status becomes "active"
```

### Cancelling a Subscription

```
1. User clicks "Cancel Subscription"

2. Frontend shows confirmation:
   "Your subscription will remain active until [period_end]"

3. Frontend calls CancelSubscription(cancel_immediately=false)
   └─> BillingServicer.cancel_subscription()
   └─> BillingService.cancel_subscription(at_period_end=True)
   └─> StripeClient.cancel_subscription(sub_id, at_period_end=True)
   └─> Stripe sets cancel_at_period_end=True
   └─> Update local: subscription.cancel_at_period_end = True

4. Return SubscriptionResponse
   └─> status: "active"
   └─> cancel_at_period_end: true
   └─> current_period_end: "2024-04-15T..."

5. At period end, Stripe automatically cancels
   └─> Webhook: customer.subscription.deleted
   └─> BillingService.sync_subscription_from_stripe(status="canceled")
```

---

## Error Handling

### Connect/gRPC Error Codes

| Error                 | Code | When Raised                                |
| --------------------- | ---- | ------------------------------------------ |
| `UNAUTHENTICATED`     | 16   | Missing/invalid JWT token                  |
| `NOT_FOUND`           | 5    | Subscription/plan/payment method not found |
| `INVALID_ARGUMENT`    | 3    | Invalid plan_id, missing payment method    |
| `FAILED_PRECONDITION` | 9    | No active subscription to cancel/resume    |
| `INTERNAL`            | 13   | Stripe API errors, database errors         |

### Stripe Error Handling

```python
class StripeError(Exception):
    """Custom exception for Stripe API errors."""
    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code

# In service layer:
try:
    stripe_sub = await self.stripe.create_subscription(...)
except StripeError as e:
    logger.error(f"Failed to create Stripe subscription: {e}")
    raise ValueError(f"Payment failed: {e.message}")
```

---

## Testing

### Test Structure

```
tests/
├── conftest.py                     # Fixtures, mock StripeClient
├── test_services.py                # BillingService unit tests
├── test_stripe_client.py           # StripeClient tests (mocked Stripe API)
├── test_grpc_billing.py            # gRPC servicer tests
├── test_grpc_servicer_extended.py  # Extended gRPC scenarios
├── test_billing_service_extended.py # Edge cases
├── test_payment_method_extended.py  # Payment method scenarios
├── test_webhooks.py                # Webhook endpoint tests
└── test_webhook_handlers.py        # Webhook processing tests
```

### Running Tests

```bash
# Run all billing tests
cd services/billing && pytest

# Run with coverage
cd services/billing && pytest --cov=src --cov-report=term-missing

# Run specific test
cd services/billing && pytest tests/test_stripe_client.py -v
```

### Key Test Scenarios

- **Subscriptions**: Create, update, cancel, resume, free plan handling
- **Payment methods**: Attach, detach, set default, list
- **Plans**: List plans, default fallback, database plans
- **Webhooks**: Signature verification, event handling, idempotency
- **Stripe errors**: API failures, invalid responses, network issues

---

## Current Implementation Status

> **Project Stage:** Early Development

### What's Real (Implemented)

- [x] Stripe customer creation/lookup by tenant_id
- [x] SetupIntent creation for card collection
- [x] Payment method attach/detach/list
- [x] Set default payment method
- [x] Subscription create (with Stripe integration)
- [x] Subscription update (plan change with proration)
- [x] Subscription cancel (immediate or at period end)
- [x] Subscription resume (reactivate pending cancellation)
- [x] Plan listing (DB + DEFAULT_PLANS fallback)
- [x] Free subscription creation (no Stripe)
- [x] Webhook signature verification
- [x] Subscription status sync from webhooks

### What's Stubbed (TODO)

- [ ] Usage tracking (returns zeros)
- [ ] Invoice listing (returns empty)
- [ ] Invoice retrieval (returns NOT_FOUND)
- [ ] Checkout session creation (returns placeholder URL)
- [ ] Portal session creation (returns placeholder URL)
- [ ] Plan enforcement in other services
- [ ] Proration previews
- [ ] Coupon/discount support

### Known Limitations

1. **Usage not tracked**: `GetUsage` always returns zeros
2. **Invoices via portal**: Users must use Stripe portal for invoice history
3. **Email placeholder**: Subscription creation uses `user-{tenant_id}@llamatrade.example`
4. **No webhook idempotency**: Events could be processed multiple times on retry

---

## Summary

The Billing Service handles LlamaTrade's subscription and payment infrastructure through tight integration with Stripe. It manages three subscription tiers (Free, Starter $29, Pro $99), payment method lifecycle, and subscription state synchronization via webhooks.

The service is approximately 70% implemented, with real Stripe integration for subscriptions and payment methods, while usage tracking, invoices, and portal sessions remain stubbed. All subscription operations flow through Stripe as the source of truth, with local database records maintained for fast permission checks by other services.

The webhook endpoint (`POST /webhooks/stripe`) receives real-time updates from Stripe, ensuring the local database stays synchronized with payment events, subscription changes, and invoice status.
