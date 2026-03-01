# Service Communication

This document shows how services communicate with each other through real-life user flows.

---

## Service Architecture Overview

```
                                    ┌────────────────────────────────────────────────────────────┐
                                    │                     EXTERNAL APIS                          │
                                    │  ┌───────────┐    ┌───────────┐    ┌───────────┐           │
                                    │  │  Alpaca   │    │  Stripe   │    │  Twilio   │           │
                                    │  │  Markets  │    │  Payments │    │  SMS/Email│           │
                                    │  └─────┬─────┘    └─────┬─────┘    └─────┬─────┘           │
                                    └────────┼────────────────┼────────────────┼─────────────────┘
                                             │                │                │
┌────────────────────────────────────────────┼────────────────┼────────────────┼───────────────────────────┐
│                                            │                │                │           BACKEND         │
│                                            │                │                │                           │
│    ┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐      │
│    │   AUTH   ││ STRATEGY ││ BACKTEST ││ MARKET   ││ TRADING  ││PORTFOLIO ││  NOTIF   ││ BILLING  │      │
│    │  :8810   ││  :8820   ││  :8830   ││  DATA    ││  :8850   ││  :8860   ││  :8870   ││  :8880   │      │
│    │          ││          ││          ││  :8840   ││          ││          ││          ││          │      │
│    │ • Login  ││ • CRUD   ││ • Run    ││ • Bars   ││ • Orders ││ • Summary││ • Alerts ││ • Plans  │      │
│    │ • JWT    ││ • DSL    ││ • Stream ││ • Quotes ││ • Fills  ││ • P&L    ││ • Email  ││ • Stripe │      │
│    │ • APIKey ││ • Version││ • Celery ││ • Stream ││ • Risk   ││ • Alloc  ││ • SMS    ││ • Webhook│      │
│    └────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘      │
│         │           │           │           │           │           │           │           │            │
│         └───────────┴───────────┴───────────┴───────────┴───────────┴───────────┴───────────┘            │
│                                     Service-to-Service: gRPC                                             │
│                                              │                                                           │
│    ┌─────────────────────────────────────────┼───────────────────────────────────────────────────────┐   │
│    │                                 SHARED INFRASTRUCTURE                                           │   │
│    │  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐                           │   │
│    │  │   PostgreSQL     │    │      Redis       │    │     Celery       │                           │   │
│    │  │  (All Services)  │    │  (Cache/Queue)   │    │   (Backtest)     │                           │   │
│    │  └──────────────────┘    └──────────────────┘    └──────────────────┘                           │   │
│    └─────────────────────────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                         ▲          ▲          ▲          ▲          ▲          ▲          ▲          ▲
                         │          │          │          │          │          │          │          │
                         └──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
                                              Connect Protocol (Direct)
                                                        │
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           FRONTEND                                                      │
│    ┌────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│    │                              React Web App (:8800)                                             │   │
│    │  • Connect Protocol (Direct to Services)  • Zustand State  • Tailwind CSS  • TypeScript        │   │
│    │  • Auth Interceptor (JWT)  • No Gateway Required                                               │   │
│    └────────────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Key Architecture Points:**

- Frontend connects **directly** to each service via Connect protocol (no API gateway)
- Each service validates JWT tokens via its own auth middleware
- Services communicate with each other via internal gRPC
- Production uses GCP L7 Load Balancer for SSL termination and routing

---

## Flow 1: User Authentication (Login)

```
┌─────────────┐                                             ┌─────────────┐
│   Browser   │                                             │    Auth     │
│  (React)    │                                             │  Service    │
└──────┬──────┘                                             └──────┬──────┘
       │                                                           │
       │  1. Connect: AuthService.Login()                          │
       │  {email, password}                                        │
       │──────────────────────────────────────────────────────────▶│
       │                                                           │
       │                                                   ┌───────┴───────┐
       │                                                   │ 2. Lookup user│
       │                                                   │    in DB      │
       │                                                   │               │
       │                                                   │ 3. bcrypt     │
       │                                                   │    verify     │
       │                                                   │               │
       │                                                   │ 4. Generate   │
       │                                                   │    JWT tokens │
       │                                                   └───────┬───────┘
       │                                                           │
       │  5. LoginResponse                                         │
       │  {access_token, refresh_token, user, tenant}              │
       │◀──────────────────────────────────────────────────────────│
       │                                                           │
┌──────┴──────┐                                                    │
│ 6. Store    │                                                    │
│    tokens   │                                                    │
│    in       │                                                    │
│    Zustand  │                                                    │
└─────────────┘                                                    │

JWT Token Payload:
{
  "sub": "user_id",
  "tenant_id": "tenant_uuid",
  "email": "user@example.com",
  "roles": ["admin"],
  "type": "access",
  "exp": 1234567890
}
```

---

## Flow 2: Create & Save Strategy

```
┌─────────────┐                                             ┌─────────────┐
│   Browser   │                                             │  Strategy   │
│  (Editor)   │                                             │  Service    │
└──────┬──────┘                                             └──────┬──────┘
       │                                                           │
       │  1. Connect: StrategyService.CreateStrategy()             │
       │  Authorization: Bearer <token>                            │
       │  {name, dsl_code}                                         │
       │──────────────────────────────────────────────────────────▶│
       │                                                           │
       │                                                   ┌───────┴───────┐
       │                                                   │ 2. Validate   │
       │                                                   │    JWT token  │
       │                                                   │    (middleware)│
       │                                                   │               │
       │                                                   │ 3. Parse DSL  │
       │                                                   │    (validate) │
       │                                                   │               │
       │                                                   │ 4. Compile to │
       │                                                   │    JSON       │
       │                                                   │               │
       │                                                   │ 5. Create     │
       │                                                   │    Strategy   │
       │                                                   │    + Version  │
       │                                                   │    in DB      │
       │                                                   └───────┬───────┘
       │                                                           │
       │  6. StrategyResponse                                      │
       │  {id, name, version, compiled_json}                       │
       │◀──────────────────────────────────────────────────────────│
       │                                                           │

DSL Example:
(strategy "MA Crossover"
  (when (crosses-above (sma close 20) (sma close 50))
    (buy 100))
  (when (crosses-below (sma close 20) (sma close 50))
    (sell 100)))
```

---

## Flow 3: Run Backtest

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Browser   │    │  Backtest   │    │ Market Data │    │   Celery    │    │   Redis     │
│             │    │  Service    │    │  Service    │    │   Worker    │    │   Queue     │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │                  │                  │
       │  1. Connect:     │                  │                  │                  │
       │  RunBacktest()   │                  │                  │                  │
       │  {strategy_id,   │                  │                  │                  │
       │   date_range,    │                  │                  │                  │
       │   capital}       │                  │                  │                  │
       │─────────────────▶│                  │                  │                  │
       │                  │                  │                  │                  │
       │                  │  2. gRPC:        │                  │                  │
       │                  │  GetStrategy()   │                  │                  │
       │                  │  (to Strategy    │                  │                  │
       │                  │   Service)       │                  │                  │
       │                  │                  │                  │                  │
       │                  │  3. Create Backtest record (PENDING)                   │
       │                  │───────────────────────────────────────────────────────▶│
       │                  │                  │                  │                  │
       │                  │  4. Enqueue task │                  │                  │
       │                  │  {backtest_id}   │                  │                  │
       │                  │───────────────────────────────────────────────────────▶│
       │                  │                  │                  │                  │
       │  5. BacktestRun  │                  │                  │                  │
       │  {id: "...",     │                  │                  │                  │
       │   status: PENDING}                  │                  │                  │
       │◀─────────────────│                  │                  │                  │
       │                  │                  │                  │                  │
       │                  │                  │  6. Pick task    │                  │
       │                  │                  │◀─────────────────┼──────────────────│
       │                  │                  │                  │                  │
       │                  │                  │  7. gRPC:        │                  │
       │                  │                  │  GetBars()       │                  │
       │                  │                  │  {symbols,       │                  │
       │                  │                  │   date_range}    │                  │
       │                  │◀─────────────────┼──────────────────│                  │
       │                  │                  │                  │                  │
       │                  │                  │  8. Historical   │                  │
       │                  │                  │  bars data       │                  │
       │                  │─────────────────▶│─────────────────▶│                  │
       │                  │                  │                  │                  │
       │  9. Connect Stream: Progress        │                  │                  │
       │◀═══════════════════════════════════════════════════════│                  │
       │  {progress: 25%, date: "2024-01-15", partial_metrics}  │                  │
       │                  │                  │                  │                  │
       │  ...             │                  │  10. Execute     │                  │
       │                  │                  │  strategy loop   │                  │
       │  {progress: 100%}│                  │  for each bar    │                  │
       │◀═══════════════════════════════════════════════════════│                  │
       │                  │                  │                  │                  │
       │                  │                  │  11. Save        │                  │
       │                  │                  │  BacktestResult  │                  │
       │                  │                  │  {metrics,       │                  │
       │                  │                  │   trades,        │                  │
       │                  │                  │   equity_curve}  │                  │
       │                  │                  │─────────────────▶│                  │
       │                  │                  │                  │                  │

Backtest Result Metrics:
{
  total_return: 15.4%,
  sharpe_ratio: 1.82,
  max_drawdown: -8.2%,
  win_rate: 62%,
  profit_factor: 2.1,
  total_trades: 47
}
```

---

## Flow 4: Live Trading Session

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Browser   │    │  Trading    │    │ Market Data │    │  Portfolio  │    │   Alpaca    │
│             │    │  Service    │    │  Service    │    │  Service    │    │    API      │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │                  │                  │
       │  1. Connect:     │                  │                  │                  │
       │  SubmitOrder()   │                  │                  │                  │
       │  {symbol: AAPL,  │                  │                  │                  │
       │   side: BUY,     │                  │                  │                  │
       │   qty: 100}      │                  │                  │                  │
       │─────────────────▶│                  │                  │                  │
       │                  │                  │                  │                  │
       │                  │  2. gRPC:        │                  │                  │
       │                  │  GetQuote()      │                  │                  │
       │                  │  {symbol: AAPL}  │                  │                  │
       │                  │─────────────────▶│                  │                  │
       │                  │                  │                  │                  │
       │                  │  3. Quote        │                  │                  │
       │                  │  {bid, ask, last}│                  │                  │
       │                  │◀─────────────────│                  │                  │
       │                  │                  │                  │                  │
       │                  │  4. Validate     │                  │                  │
       │                  │  risk limits     │                  │                  │
       │                  │  (internal)      │                  │                  │
       │                  │                  │                  │                  │
       │                  │  5. POST /orders │                  │                  │
       │                  │  {symbol, qty,   │                  │                  │
       │                  │   side, type}    │                  │                  │
       │                  │───────────────────────────────────────────────────────▶│
       │                  │                  │                  │                  │
       │                  │  6. Order        │                  │                  │
       │                  │  {id, status:    │                  │                  │
       │                  │   PENDING}       │                  │                  │
       │                  │◀───────────────────────────────────────────────────────│
       │                  │                  │                  │                  │
       │  7. Order        │                  │                  │                  │
       │  {id, status}    │                  │                  │                  │
       │◀─────────────────│                  │                  │                  │
       │                  │                  │                  │                  │
       │                  │                  │                  │                  │
       │═══════════════════════════════════════════════════════════════════════════│
       │  8. Connect Stream: Order Updates                                         │
       │  {order_id, status: FILLED, filled_qty: 100, avg_price: 175.50}           │
       │◀══════════════════════════════════════════════════════════════════════════│
       │                  │                  │                  │                  │
       │                  │                  │                  │                  │
       │                  │  9. gRPC:        │                  │                  │
       │                  │  UpdatePosition()│                  │                  │
       │                  │  {AAPL: +100}    │                  │                  │
       │                  │────────────────────────────────────▶│                  │
       │                  │                  │                  │                  │
       │  10. Connect:    │                  │                  │                  │
       │  GetPortfolio()  │                  │                  │                  │
       │───────────────────────────────────────────────────────▶│                  │
       │                  │                  │                  │                  │
       │  11. Portfolio   │                  │                  │                  │
       │  {positions,     │                  │                  │                  │
       │   equity,        │                  │                  │                  │
       │   unrealized_pnl}│                  │                  │                  │
       │◀───────────────────────────────────────────────────────│                  │

Order Lifecycle:
PENDING → ACCEPTED → PARTIALLY_FILLED → FILLED
                  ↘ REJECTED
                  ↘ CANCELLED
```

---

## Flow 5: Real-Time Market Data Streaming

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Browser   │    │ Market Data │    │   Stream    │    │   Alpaca    │
│  (Charts)   │    │  Service    │    │   Manager   │    │  WebSocket  │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │                  │
       │  1. Connect:     │                  │                  │
       │  StreamBars()    │                  │                  │
       │  {symbols: [AAPL,│                  │                  │
       │   GOOGL, MSFT]}  │                  │                  │
       │─────────────────▶│                  │                  │
       │                  │                  │                  │
       │                  │  2. subscribe    │                  │
       │                  │  {client_id,     │                  │
       │                  │   symbols}       │                  │
       │                  │─────────────────▶│                  │
       │                  │                  │                  │
       │                  │                  │  3. First client │
       │                  │                  │  for AAPL?       │
       │                  │                  │  Subscribe!      │
       │                  │                  │                  │
       │                  │                  │  4. WSS subscribe│
       │                  │                  │  {"action":      │
       │                  │                  │   "subscribe",   │
       │                  │                  │   "bars": [...]} │
       │                  │                  │─────────────────▶│
       │                  │                  │                  │
       │                  │                  │  5. Subscription │
       │                  │                  │  confirmed       │
       │                  │                  │◀─────────────────│
       │                  │                  │                  │
       │                  │                  │                  │
       │                  │                  │  6. Bar data     │
       │                  │                  │  {symbol, o,h,   │
       │                  │                  │   l,c,v,t}       │
       │                  │                  │◀═════════════════│
       │                  │                  │                  │ (continuous)
       │                  │  7. Broadcast    │                  │
       │                  │  to all clients  │                  │
       │                  │◀═════════════════│                  │
       │                  │                  │                  │
       │  8. Bar (stream) │                  │                  │
       │  {symbol: AAPL,  │                  │                  │
       │   open, high,    │                  │                  │
       │   low, close,    │                  │                  │
       │   volume, time}  │                  │                  │
       │◀═════════════════│                  │                  │
       │                  │                  │                  │
       │  ... continuous  │                  │                  │
       │                  │                  │                  │
       │  9. Client       │                  │                  │
       │  disconnects     │                  │                  │
       │────────X         │                  │                  │
       │                  │                  │                  │
       │                  │  10. unsubscribe │                  │
       │                  │  {client_id}     │                  │
       │                  │─────────────────▶│                  │
       │                  │                  │                  │
       │                  │                  │  11. Last client │
       │                  │                  │  for AAPL?       │
       │                  │                  │  Unsubscribe!    │
       │                  │                  │                  │
       │                  │                  │  12. WSS unsub   │
       │                  │                  │─────────────────▶│

Reference Counting Pattern:
┌──────────────────────────────────────────┐
│ Symbol    │ Client Count │ Alpaca Sub    │
├──────────────────────────────────────────┤
│ AAPL      │     3        │     YES       │
│ GOOGL     │     1        │     YES       │
│ MSFT      │     0        │     NO        │
└──────────────────────────────────────────┘
```

---

## Flow 6: Billing & Subscription

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Browser   │    │  Billing    │    │   Stripe    │    │    Auth     │
│             │    │  Service    │    │    API      │    │  Service    │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │                  │
       │  1. Connect:     │                  │                  │
       │  Subscribe()     │                  │                  │
       │  {plan: "pro"}   │                  │                  │
       │─────────────────▶│                  │                  │
       │                  │                  │                  │
       │                  │  2. Create       │                  │
       │                  │  Checkout Session│                  │
       │                  │─────────────────▶│                  │
       │                  │                  │                  │
       │                  │  3. Session URL  │                  │
       │                  │◀─────────────────│                  │
       │                  │                  │                  │
       │  4. Redirect to  │                  │                  │
       │  Stripe Checkout │                  │                  │
       │◀─────────────────│                  │                  │
       │                  │                  │                  │
       │────────────────────────────────────▶│                  │
       │  5. User enters payment details     │                  │
       │                  │                  │                  │
       │  6. Payment success redirect        │                  │
       │◀────────────────────────────────────│                  │
       │                  │                  │                  │
       │                  │                  │                  │
       │                  │  7. Webhook:     │                  │
       │                  │  checkout.       │                  │
       │                  │  completed       │                  │
       │                  │  (HTTP :8881)    │                  │
       │                  │◀═════════════════│                  │
       │                  │                  │                  │
       │                  │  8. Create       │                  │
       │                  │  Subscription    │                  │
       │                  │  record in DB    │                  │
       │                  │                  │                  │
       │                  │  9. gRPC:        │                  │
       │                  │  UpdateTenant()  │                  │
       │                  │────────────────────────────────────▶│
       │                  │                  │                  │
       │  10. Plan active │                  │                  │
       │◀─────────────────│                  │                  │

Webhook Events Handled (HTTP port 8881):
• checkout.session.completed → Create subscription
• customer.subscription.updated → Sync status
• customer.subscription.deleted → Mark cancelled
• invoice.payment_succeeded → Record invoice
• invoice.payment_failed → Mark past_due
```

---

## Flow 7: Notification Alert Trigger

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Trading    │    │Notification │    │   Email     │    │    SMS      │    │   Slack     │
│  Service    │    │  Service    │    │  (SendGrid) │    │  (Twilio)   │    │   Webhook   │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │                  │                  │
       │  1. Order filled │                  │                  │                  │
       │  internally      │                  │                  │                  │
       │                  │                  │                  │                  │
       │  2. gRPC:        │                  │                  │                  │
       │  SendAlert()     │                  │                  │                  │
       │  {type: ORDER_   │                  │                  │                  │
       │   FILLED,        │                  │                  │                  │
       │   symbol: AAPL,  │                  │                  │                  │
       │   data: {...}}   │                  │                  │                  │
       │─────────────────▶│                  │                  │                  │
       │                  │                  │                  │                  │
       │                  │  3. Lookup user  │                  │                  │
       │                  │  notification    │                  │                  │
       │                  │  preferences     │                  │                  │
       │                  │                  │                  │                  │
       │                  │  4. User wants:  │                  │                  │
       │                  │  Email + Slack   │                  │                  │
       │                  │                  │                  │                  │
       │                  │  5. Send email   │                  │                  │
       │                  │─────────────────▶│                  │                  │
       │                  │                  │                  │                  │
       │                  │  6. Email sent   │                  │                  │
       │                  │◀─────────────────│                  │                  │
       │                  │                  │                  │                  │
       │                  │  7. Post to Slack webhook                              │
       │                  │───────────────────────────────────────────────────────▶│
       │                  │                  │                  │                  │
       │                  │  8. Posted       │                  │                  │
       │                  │◀───────────────────────────────────────────────────────│
       │                  │                  │                  │                  │
       │  9. Alert sent   │                  │                  │                  │
       │◀─────────────────│                  │                  │                  │

Notification Channels:
┌───────────────────────────────────────────────────────────┐
│ Channel    │ Provider   │ Use Case                        │
├───────────────────────────────────────────────────────────┤
│ Email      │ SendGrid   │ Daily summaries, alerts         │
│ SMS        │ Twilio     │ Critical alerts only            │
│ Slack      │ Webhook    │ Real-time trade updates         │
│ Discord    │ Webhook    │ Community notifications         │
│ Telegram   │ Bot API    │ Mobile alerts                   │
│ Push       │ FCM/APNS   │ Mobile app (future)             │
│ Webhook    │ Custom URL │ Integration with other systems  │
└───────────────────────────────────────────────────────────┘
```

---

## Service Dependency Matrix

```
                    ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
                    │Auth │Strat│Back │Mkt  │Trade│Port │Notif│Bill │
                    │     │     │test │Data │     │     │     │     │
┌───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ Auth Service      │  -  │     │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ Strategy Service  │  ●  │  -  │     │     │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ Backtest Service  │  ●  │  ●  │  -  │  ●  │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ Market Data Svc   │  ●  │     │     │  -  │     │     │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ Trading Service   │  ●  │     │     │  ●  │  -  │     │  ○  │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ Portfolio Service │  ●  │     │     │  ●  │  ●  │  -  │     │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ Notification Svc  │  ●  │     │     │     │     │     │  -  │     │
├───────────────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
│ Billing Service   │  ●  │     │     │     │     │     │     │  -  │
└───────────────────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘

● = Required dependency (gRPC call)
○ = Optional dependency (sends notifications)
```

---

## Communication Protocols Summary

| Pattern             | Protocol                | Use Case                    |
| ------------------- | ----------------------- | --------------------------- |
| Frontend → Services | Connect (HTTP/1.1+JSON) | All API calls (direct)      |
| Service → Service   | gRPC                    | Internal communication      |
| Market Data Ingest  | WebSocket               | Alpaca real-time data       |
| Client Streaming    | Connect Server Stream   | Bars, quotes, order updates |
| Async Jobs          | Celery + Redis          | Backtest execution          |
| Webhooks            | HTTP POST               | Stripe events (:8881)       |
| Notifications       | SMTP/HTTP               | Email, Slack, SMS           |

**Note:** No API Gateway in local development. Frontend uses Connect protocol to communicate
directly with each service. Each service validates JWT tokens via auth middleware.
Production deployments use GCP L7 Load Balancer for SSL termination and routing.

---

## Verification

To verify these flows work:

1. **Auth Flow**: Login at `/login`, check JWT in browser devtools
2. **Strategy Flow**: Create strategy in editor, check DB for `strategies` table
3. **Backtest Flow**: Run backtest, monitor Celery worker logs
4. **Trading Flow**: Submit paper trade, check Alpaca dashboard
5. **Streaming**: Open chart, verify Connect stream in Network tab (look for HTTP streams)
