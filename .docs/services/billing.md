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
- Usage tracking and limit enforcement

---

## Architecture Overview

```
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                                      FastAPI :8880                                       ║
╠══════════════════════════════════════════════════════════════════════════════════════════╣
║ Connect / gRPC ASGI  ·  POST /webhooks/stripe (verify signature)  ·  tenant_id           ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝
                                              │
                                              ▼
╭──────────────────────────────────────────────────────────────────────────────────────────╮
│                               BillingServicer  ·  15 RPCs                                │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Subscriptions · Get · Create · Update · Cancel · Resume                                  │
│ Payment methods · List · SetupIntent · Add · Remove                                      │
│ Plans · ListPlans   ·   Usage · GetUsage                                                 │
│ Invoices · List · Get   ·   Portal · CreateCheckout · CreatePortal                       │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
                                              │
                                              ▼
                ╭────────────────╮  ╭──────────────────╮  ╭────────────────╮
                │ BillingService │  │ PaymentMethodSvc │  │  StripeClient  │
                ├────────────────┤  ├──────────────────┤  ├────────────────┤
                │ subscriptions  │  │ attach / detach  │  │ API wrapper    │
                │ plans · sync   │  │ list / default   │  │ webhook verify │
                ╰────────────────╯  ╰──────────────────╯  ╰────────────────╯
                                              │
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                        PostgreSQL                                        │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ plans  ·  subscriptions  ·  payment_methods                                              │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                              ║
                                   ╔══════════╩══════════════════╗ external systems
                                   ▼                             ▼
                     ┌───────────────────────────┐        ┌────────────┐
                     │        Stripe ↔ API       │        │ Auth :8810 │
                     ├───────────────────────────┤        ├────────────┤
                     │ customers · subscriptions │        │ JWT verify │
                     │ payments · invoices       │        │ tenant_id  │
                     └───────────────────────────┘        └────────────┘
```

### Stripe Integration Flow

```
╭─────────────╮          ╭────────────────╮            ╭───────────────╮
│    Client   │          │ Billing :8880  │            │     Stripe    │
├─────────────┤          ├────────────────┤            ├───────────────┤
│ + Stripe.js │          │ servicer       │            │ customers     │
╰─────────────╯          │ + StripeClient │            │ subscriptions │
                         ╰────────────────╯            ╰───────────────╯
       │                          │                            │
       │   1 CreateSetupIntent    │                            │
       ├──────────────────────────►                            │
       │                          │   2 SetupIntent.create     │
       │                          ╠════════════════════════════►
       │                    3 client_secret                    │
       ◄───────────────────────────────────────────────────────┤
       │                          │                            │
       │               4 Stripe.js collects card               │
       ╠═══════════════════════════════════════════════════════►
       │                       5 pm_xxx                        │
       ◄═══════════════════════════════════════════════════════╣
       │                          │                            │
       │   6 AddPaymentMethod     │                            │
       ├──────────────────────────►                            │
       │                          │   7 attach to customer     │
       │                          ╠════════════════════════════►
       │                          │                            │
       │  8 CreateSubscription    │                            │
       ├──────────────────────────►                            │
       │                          │   9 Subscription.create    │
       │                          ╠════════════════════════════►
       │                          │  10 webhook sub.created    │
       │                          ◄════════════════════════════╣
    11 subscription active (trialing)                          │
       ◄──────────────────────────┤                            │
       │                          │                            │
```

---

## Directory Structure

```
services/billing/
├── src/
│   ├── main.py                     # FastAPI app, health check
│   ├── models.py                   # Pydantic request schemas
│   ├── proto_mappers.py            # DB model → proto converters
│   ├── grpc/
│   │   └── servicer.py             # BillingServicer (15 RPCs)
│   ├── services/
│   │   ├── billing_service.py      # Subscription/plan logic
│   │   └── payment_method_service.py # Payment method CRUD
│   ├── stripe/
│   │   └── client.py               # Stripe API wrapper
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
| **BillingServicer**      | `grpc/servicer.py`                   | Connect protocol servicer, 15 RPC methods |
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

| Method                | Request                      | Response                      | Description                                        |
| --------------------- | ---------------------------- | ----------------------------- | -------------------------------------------------- |
| `ListPaymentMethods`  | `ListPaymentMethodsRequest`  | `ListPaymentMethodsResponse`  | List all cards on file                             |
| `CreateSetupIntent`   | `CreateSetupIntentRequest`   | `CreateSetupIntentResponse`   | Return a `client_secret` for Stripe.js card collection |
| `AddPaymentMethod`    | `AddPaymentMethodRequest`    | `AddPaymentMethodResponse`    | Attach new payment method                          |
| `RemovePaymentMethod` | `RemovePaymentMethodRequest` | `RemovePaymentMethodResponse` | Detach payment method                              |

### Plans

| Method      | Request            | Response            | Description                       |
| ----------- | ------------------ | ------------------- | --------------------------------- |
| `ListPlans` | `ListPlansRequest` | `ListPlansResponse` | List available subscription tiers |

### Usage

| Method     | Request           | Response           | Description                      |
| ---------- | ----------------- | ------------------ | -------------------------------- |
| `GetUsage` | `GetUsageRequest` | `GetUsageResponse` | Get current period usage metrics |

`GetUsage` is real: counts are computed live from the shared DB — non-archived strategies,
RUNNING strategy executions, backtests, RUNNING live trading sessions, and summed Copilot
message counts. Fields not tracked in the DB (`backtest_compute_minutes`,
`market_data_requests`, `storage_bytes`, `orders_placed`) are returned as 0.

### Invoices

| Method         | Request               | Response               | Description          |
| -------------- | --------------------- | ---------------------- | -------------------- |
| `ListInvoices` | `ListInvoicesRequest` | `ListInvoicesResponse` | List past invoices   |
| `GetInvoice`   | `GetInvoiceRequest`   | `GetInvoiceResponse`   | Get specific invoice |

### Checkout & Portal Sessions

| Method                  | Request                        | Response                        | Description                                    |
| ----------------------- | ------------------------------ | ------------------------------- | ---------------------------------------------- |
| `CreateCheckoutSession` | `CreateCheckoutSessionRequest` | `CreateCheckoutSessionResponse` | Stripe-hosted subscription Checkout Session    |
| `CreatePortalSession`   | `CreatePortalSessionRequest`   | `CreatePortalSessionResponse`   | Stripe Customer Portal session for self-service |

`CreateCheckoutSession` builds a `mode=subscription` Stripe Checkout Session: it resolves the
plan's Stripe price from `get_plan_db(plan_id)` and the request `interval`
(`stripe_price_id_monthly` / `stripe_price_id_yearly`), calls `get_or_create_customer`, and
passes the request `success_url` / `cancel_url` plus the plan's `trial_days`. It deliberately
does **not** set `payment_method_types` — Stripe selects dynamic payment methods per its
current best practice. `CreatePortalSession` opens a Stripe Customer Portal session (against the
tenant's customer and `return_url`) for self-service subscription and card management.

---

## Data Models

### Plan Tiers

```
┌─────────────────────────────────────────────────┐
│                 SUBSCRIPTION TIERS                │
├─────────────┬─────────────────┬───────────────────┤
│    FREE     │    STARTER      │       PRO         │
│   $0/mo     │    $29/mo       │     $99/mo        │
├─────────────┼─────────────────┼───────────────────┤
│ 5 backtests │ 50 backtests    │ Unlimited         │
│ Paper only  │ 1 live strategy │ 5 strategies      │
│ Basic ind.  │ All indicators  │ All + support     │
│ No alerts   │ Email alerts    │ All channels      │
└─────────────┴─────────────────┴───────────────────┘
```

### Wire shape

Billing does not define `…Response` Pydantic schemas. Responses are built by mapping
SQLAlchemy ORM rows (`Plan`, `Subscription`, `PaymentMethod`, `Invoice`) directly to their
proto messages in `proto_mappers.py` (`plan_to_proto`, `subscription_to_proto`,
`payment_method_to_proto`, `invoice_to_proto`). Request bodies use small Pydantic schemas in
`models.py` (e.g. `SubscriptionCreateRequest`). Subscription `status` and `billing_cycle` are
stored as proto integer enums.

### Default Plans

When no plans exist in the database, `list_plans` falls back to `DEFAULT_PLANS` — transient
SQLAlchemy `Plan` rows defined in `billing_service.py` (not Pydantic):

| Plan    | Tier             | Monthly | Yearly | Backtests/mo | Live strategies | Trial |
| ------- | ---------------- | ------- | ------ | ------------ | --------------- | ----- |
| Free    | `PLAN_TIER_FREE` | 0       | 0      | 5            | 0               | 0     |
| Starter | `PLAN_TIER_STARTER` | 29   | 290    | 50           | 1               | 14    |
| Pro     | `PLAN_TIER_PRO`  | 99      | 990    | unlimited    | 5               | 14    |

`features`/`limits` are JSON columns on the `Plan` model (e.g. `live_trading`,
`all_indicators`, `email_alerts`, `priority_support`; `api_calls_per_day`).

---

## Stripe Integration

### StripeClient Methods

| Method                                                          | Description                                       |
| --------------------------------------------------------------- | ------------------------------------------------- |
| `get_or_create_customer(tenant_id, email)`                      | Find or create Stripe customer by tenant metadata |
| `create_setup_intent(customer_id)`                              | Create SetupIntent for card collection            |
| `create_checkout_session(customer_id, price_id, urls, trial_days)` | Stripe-hosted subscription Checkout Session    |
| `create_portal_session(customer_id, return_url)`                | Customer Portal session for self-service          |
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
| **Strategy**     | (shared DB) `plan_limits`                  | Gate live executions on `live_strategies`    |
| **Backtest**     | (shared DB) `plan_limits`                  | Gate runs on `backtests_per_month`           |

Strategy and Backtest do not call a billing RPC for enforcement; they read the tenant's
`Plan.limits` directly from the shared DB via `llamatrade_db.plan_limits` (see "Plan limits &
enforcement").

### What Billing Service Calls

| Target           | Purpose                                     |
| ---------------- | ------------------------------------------- |
| **PostgreSQL**   | Plan, subscription, payment method storage  |
| **Stripe API**   | Payment processing, subscription management |

Billing does **not** call the auth service. It verifies the bearer JWT itself with the shared
`JWT_SECRET` (`_get_tenant_id`), reads `tenant_id` from the token, and scopes every query with
`tenant_session(tenant_id)` (Postgres RLS). Because it re-decodes the token rather than using
the shared `resolve_identity`, it would reject an S2S service token (which carries no
`tenant_id`); today only user tokens call it.

---

## Complete Data Flow Example

### Subscribing to a Paid Plan

```
1. User clicks "Upgrade to Starter" on billing page

2. Frontend calls CreateSetupIntent
   └─> BillingServicer.create_setup_intent()
   └─> StripeClient.get_or_create_customer + create_setup_intent → returns client_secret

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
   └─> Return the subscription proto (status = trialing)

6. Stripe sends webhook: customer.subscription.created
   └─> POST /webhooks/stripe
   └─> Verify signature
   └─> _handle_subscription_created(db, subscription)  (routers/webhooks.py)
   └─> Sync status / billing period / trial onto the local subscription row

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

4. Return the subscription proto
   └─> status: "active"
   └─> cancel_at_period_end: true
   └─> current_period_end: "2024-04-15T..."

5. At period end, Stripe automatically cancels
   └─> Webhook: customer.subscription.deleted
   └─> _handle_subscription_deleted(db, subscription) sets status = CANCELED
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

## Capabilities

- Stripe customer creation/lookup by tenant_id (email from the verified token)
- SetupIntent creation for card collection (`CreateSetupIntent` RPC → `client_secret`)
- Payment method attach / detach / list, set default
- Subscription create (Stripe), free-plan subscription create (no Stripe)
- Subscription update (plan change), cancel (immediate or at period end), resume
- Stripe-hosted Checkout Session (`CreateCheckoutSession`) and Customer Portal session (`CreatePortalSession`)
- Plan listing (DB + `DEFAULT_PLANS` fallback)
- Plan limits published on `Plan.limits` for cross-service enforcement
- Usage metering (`GetUsage`, live DB counts)
- Invoice listing and retrieval
- Webhook signature verification, status/period sync, and idempotent replay

## Plan limits & enforcement

Per-plan limits live on the billing `Plan.limits` JSON column (e.g. `live_strategies`,
`backtests_per_month`). Billing owns the catalog; enforcement happens in the consuming services
via the shared `llamatrade_db.plan_limits` helper (`get_plan_limit` / `enforce_plan_limit`),
which reads the tenant's active (`ACTIVE`/`TRIALING`) `Subscription → Plan.limits` and falls
back to the free tier (`{live_strategies: 1, backtests_per_month: 10}`) when there is no active
subscription:

- **Strategy** gates live executions on `live_strategies` (counts RUNNING executions).
- **Backtest** gates runs on `backtests_per_month` (counts the current month's backtests).

At the limit both raise `PlanLimitExceededError`, surfaced to the client as
`RESOURCE_EXHAUSTED`. `GetUsage` still reports the counts.

## Planned / Not implemented

- **Proration previews** and **coupon / discount support**.

---

## Summary

The Billing Service handles LlamaTrade's subscription and payment infrastructure through tight integration with Stripe. It manages three subscription tiers (Free, Starter $29, Pro $99), payment method lifecycle, and subscription state synchronization via webhooks.

The service provides Stripe integration for subscriptions and payment methods, along with usage tracking, invoices, and portal sessions. All subscription operations flow through Stripe as the source of truth, with local database records maintained for fast permission checks by other services.

The webhook endpoint (`POST /webhooks/stripe`) receives real-time updates from Stripe, ensuring the local database stays synchronized with payment events, subscription changes, and invoice status.
