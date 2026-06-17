# MVP Release Plan — LlamaTrade

> **STATUS: DRAFT for product team (2026-06-16).** Defines the path from current
> state to a shippable MVP and the fast-follows after it. Framed around *what each
> milestone unlocks for testing* and *who can use it*, so product can plan beta
> cohorts and validation against each stage.
>
> This is a hub doc. It references the detailed engineering plans rather than
> duplicating them — see §8.

---

## 1. Locked scope decisions

These were decided with the product owner and shape everything below:

| Decision | Choice | Consequence |
|---|---|---|
| **Trading scope at launch** | **Paper-first, live as fast-follow** | MVP carries zero real-money risk. Real-money (M6) is gated on extra hardening + legal disclosures and ships *after* the beta proves the loop. |
| **Launch audience** | **Closed / invite-only beta** | Self-serve billing and email verification drop *out* of the MVP gate — invited testers are provisioned manually. Security hardening only needs to be "safe for invited externals," not the open internet. |
| **Non-core surfaces** | **AI copilot IN; notifications, manual trading, corp-actions deferred** | The Agent service (LLM strategy copilot) is part of the MVP differentiator and gets wired into the builder. Everything else is post-MVP. |

**Brokerage model** (per [`broker-setup-individual-traders.md`](./broker-setup-individual-traders.md)):
bring-your-own Alpaca keys. LlamaTrade automates the user's *own* brokerage account
and never custodies funds. Firm-trades-customer-money (Alpaca Broker API, KYC/AML, RIA
posture) is a **separate legally-gated program**, explicitly out of scope for MVP.

---

## 2. Where we are today

The hard parts are built and tested. The MVP gap is mostly **UI surface + security
hardening + onboarding polish** — not core trading logic.

**Maturity by product capability** (✅ ready · 🟡 partial · 🔴 stub):

| Capability | State | Notes |
|---|---|---|
| Sign up / login / multi-tenant | 🟡 60% | JWT + bcrypt + tenant isolation work. No email verify / password reset / token revoke. |
| Connect Alpaca (BYO keys) | 🟡 85% backend, 🔴 0% UI | Encrypted creds + per-session clients fully built; **no UI exists** to enter/manage keys. |
| Build strategy (visual + code) | ✅ ~80% | Block builder + S-expression DSL + validation + save/load. Engine supports 16+ indicators, multi-symbol, live=backtest parity. |
| Backtest end-to-end | ✅ ~80% | Celery exec, metrics (Sharpe/Sortino/drawdown/etc.), benchmark, live progress streaming, cancel. |
| Market data | ✅ 95% | TimescaleDB store + Alpaca + streaming + resilient client. |
| Live/paper execution (backend) | ✅ ~85% | Sessions, all order types, fills, deterministic crash-safe order IDs, risk checks. **No UI.** |
| Portfolio ledger | ✅ ~80% | Double-entry, sleeves, FIFO, reconciliation. Read-side cutover behind `LEDGER_READS`, pending soak. |
| Portfolio UI | 🟡 70% | Equity curves + positions + P&L. Silently falls back to demo data on API error (must fix). |
| AI copilot (Agent) | 🟡 45% | LLM chat + DSL/backtest tools. Not wired into the builder UI. |
| Billing (Stripe) | 🟡 55% | Subs/payments/webhooks work; usage limits not enforced; no UI plan-gating. *(Not on MVP critical path.)* |
| Trading page (UI) | 🔴 10% | Placeholder only. Biggest single product gap. |
| Dashboard (UI) | 🔴 10% | Empty placeholder. |
| Notifications / alerts | 🔴 ~20% | CRUD only; no channel sends. *(Deferred.)* |
| Infra / security | 🟡 50% | Docker/K8s/Terraform/CI/migrations solid. Gaps: TLS cert, inter-service auth, secrets-in-git, deploy automation, trace/log shipping. |

---

## 3. The MVP, defined

> **MVP = a closed, invite-only, paper-trading beta in which an invited user can:
> sign up → connect their Alpaca paper account → build a strategy (visually, in code,
> or via the AI copilot) → backtest it → deploy it in paper mode → and watch orders,
> positions, and P&L update live — all on a deployment that's safe to expose to
> invited external testers.**

The MVP is reached after **M1 + M2 + M3 + M4** below. M5 and M6 are post-MVP
fast-follows toward public self-serve and real money.

**Effort legend** (single engineer, calibrate with your team): **S** ≈ a few days ·
**M** ≈ 1–2 weeks · **L** ≈ 2–4 weeks. These are *relative sizes*, not a committed
calendar.

---

## 4. Milestones to MVP

### M1 — "Build & Backtest" → *Internal Alpha (dogfood)*

**Unlocks for testing:** an internal user signs up, builds a strategy, runs a backtest,
and sees real metrics + equity curves. First validation of the core value prop — the
builder UX and backtest output — with **zero brokerage involvement**.

**Audience:** internal team + a handful of friendly users, on staging.

**Scope:**
- Verify/repair backtest **results data-binding** in the UI — trades table, monthly
  returns grid, metrics cards against real `GetBacktest` output. (M)
- Build a real **Dashboard** (currently empty): portfolio snapshot, recent backtests,
  "connect broker" / "create strategy" empty-states. (M)
- Remove the **silent demo-data fallback** in Portfolio so API failures surface as
  errors, not fake numbers. (S)
- Seed **3–5 strategy templates** (60/40, momentum top-N, tactical RSI) so the builder
  isn't a blank page. (S)

**Acceptance:** a user with no prior data can register, open a template, edit it, save,
run a backtest, and read correct results — with no mock data anywhere in the path.

**Dependencies:** none (≈90% already works).

---

### M2 — "Paper Trading Live" → *Closed Beta core*

**Unlocks for testing:** an invited user connects an Alpaca **paper** account, funds a
strategy, deploys it, and watches orders fill and positions/P&L update in real time.
This is the **first end-to-end test of the entire live loop** (execution → fills →
ledger → portfolio) with **no real money**. This is the heart of the beta.

**Audience:** invited beta testers on paper accounts.

**Scope:**
- **Broker credential UI** ([broker-setup](./broker-setup-individual-traders.md)
  Phases 0–1): a "Broker" settings tab to add/list/delete keys, paper/live badge,
  "test connection" — and the **Phase 0 security fixes** that gate any external
  exposure (make secrets write-only, validate keys against Alpaca on entry). (M)
- **Trading UI built from scratch**: session start/stop, credential + strategy picker,
  live order/position/fill stream, sleeve funding flow. (L)
- Wire the frontend to `StartSession` + **Redis-Streams subscriptions** for live
  order/position updates. (M)
- Complete the **`LEDGER_READS` soak** and cut portfolio reads fully onto the ledger
  ([completion plan](./portfolio-ledger-completion-plan.md) stages H→I). (M)
- Onboarding nudge + disclosures: "history begins at onboarding; performance metrics
  need ~30 days of data." (S)

**Acceptance:** an invited user connects a paper account, deploys a strategy, sees a
real order fill in the UI within seconds, and sees the position + P&L reflected in
Portfolio — with ledger reconciliation green against the broker.

**Dependencies:** M1 (strategies must be buildable); broker-setup Phase 0 (security)
is a hard gate.

---

### M3 — "AI Copilot in the Builder" → *Closed Beta differentiator*

**Unlocks for testing:** a user describes a strategy in plain language and the copilot
generates/edits the DSL, validates it, and can run a backtest on it — inside the
builder. Tests whether conversational strategy creation lowers the build barrier (a
key product bet).

**Audience:** same invited beta cohort as M2.

**Scope:**
- Wire the existing **Agent service** into the strategy builder UI: chat panel,
  stream responses, apply generated DSL into the visual/code editor. (M)
- Close the Agent's **tool-result feedback loop** (tool calls execute but don't fully
  feed results back into the streaming response today). (M)
- Guardrails: validate every copilot-produced strategy through the same DSL validator
  before it can be saved/deployed. (S)

**Acceptance:** a user types "build me a momentum rotation across tech ETFs, rebalance
monthly," gets a valid strategy in the builder, and can backtest it without hand-editing.

**Dependencies:** M1 (builder + backtest). Can run **in parallel** with M2.

---

### M4 — "Beta Hardening" → *Safe to invite external testers*

**Unlocks for testing:** the platform can be put in front of non-employee invited
users without a security incident. Not user-visible, but it's the gate that turns
M1–M3 from "demo on staging" into "beta people can actually log into."

**Audience:** prerequisite for anyone outside the building.

**Scope** (scaled to *invited beta*, not open internet):
- **TLS** on ingress (provision the missing `ManagedCertificate`). (S)
- **Inter-service auth** — service-to-service gRPC calls are currently unauthenticated;
  add application-level bearer tokens (lighter than full mTLS for beta). (M)
- **Secrets out of git** — move K8s secrets to External Secrets Operator / Secret
  Manager; today they're committed with placeholder values. (M)
- **Credential encryption** — at minimum per-value salts + rotation path; KMS envelope
  encryption if/when M6 (real money) lands (broker-setup B2). (M)
- **Deploy automation** — fix workflows to roll all 9 services + await DB migrations
  (currently only patches auth + frontend). (S)
- **Observability** — ship traces to Cloud Trace and logs to Cloud Logging (today they
  go nowhere); finish SLO alerts. (S)
- Add the **Agent service K8s manifests** (exists in compose, missing from K8s). (S)

**Acceptance:** staging is reachable over HTTPS, no secrets in git, services
authenticate to each other, a single deploy command rolls the whole stack after
migrations, and a tester's traffic is visible in traces/logs/dashboards.

**Dependencies:** independent of M1–M3; **run in parallel**. Must be done before the
beta opens to external invitees.

---

### ✅ MVP GATE — Closed Invite-Only Paper Beta

Reached when M1+M2+M3+M4 are complete. **What the beta validates:**
the build→backtest→paper-trade→monitor loop, the AI-copilot build path, ledger
correctness against a live broker, and onboarding friction — all with real users and
zero financial risk. This is the data that should inform whether/when to invest in M5
and M6.

---

## 5. Post-MVP fast-follows

### M5 — "Self-Serve & Billing" → *Public signup*

**Unlocks:** strangers can sign up, verify email, subscribe with a card, and have plan
limits enforced — turning the beta into a public product.

**Scope:** email verification + password reset (M); auto-create Free subscription on
signup (S); enforce plan entitlements server-side **and** reflect them as locked/disabled
UI (M); usage metering for backtest/strategy limits (M); basic dunning on failed
payments (S).

**Dependencies:** MVP gate. Billing backend is ~55% done already.

---

### M6 — "Real-Money Live Trading" → *General Availability*

**Unlocks:** users flip from paper to **real-money** trading — the full product.

**Scope:** enable live mode behind paid-plan gating + explicit confirmation/guardrails
(broker-setup Phase 3, D2) (S); **upgrade credential encryption to KMS envelope**
(broker-setup B2) (M); load-test the reconciliation loop + ledger at realistic account
counts (M); failover/DR test — Cloud SQL HA, backup restore (M); support runbooks +
on-call dashboards + SLO burn-rate alerts (M); **risk/legal disclosures for live
trading** (S engineering, but needs product + legal sign-off).

**Dependencies:** MVP gate + M5 (real billing). The legal disclosure work is the long
pole and should start early.

> **Not M6 / separate program:** trading *customers'* money via the Alpaca Broker API
> (per-customer accounts, KYC/AML, RIA/BD posture). That's a business + legal decision,
> not an engineering increment — see broker-setup §5.

---

## 6. Sequencing & parallelization

```
            ┌──────────────────────────── MVP GATE ────────────────────────────┐
            │                                                                   │
M1 Build&Backtest ──► M2 Paper Trading Live ──────────────────────────────────►│──► M5 Self-Serve ──► M6 Real Money
   (alpha)              (closed beta core)                                      │     (public)          (GA)
            │                                                                   │
            └──► M3 AI Copilot ──────────────────────────────────────────────►│
                                                                                │
M4 Beta Hardening (independent — start immediately, must finish before beta) ──►│
```

- **M1 is the unblocker** — fastest to real feedback, ~90% built.
- **M2, M3, M4 run in parallel** after M1 (M4 can even start now). M2 is the largest
  (UI-bound); M3 and M4 are medium.
- **M5 and M6 do not block the MVP** and should be scoped only once beta feedback is in.

Rough relative weight to the MVP gate: **M2 (L) > M4 (M–L) ≈ M3 (M) > M1 (M)**.

---

## 7. Cross-cutting risks & open decisions

**Risks**
- **Trading UI is greenfield** (M2) — the backend is ready but the entire live surface
  is new; this is the schedule's long pole to the gate.
- **Ledger read soak** (`LEDGER_READS`) must prove parity in staging before M2 can
  trust portfolio numbers; budget time for the soak, not just the code.
- **Copilot quality bar** (M3) — LLM-generated strategies must always pass the DSL
  validator; a bad generation that silently saves is a trust killer.
- **Docs lag code** — several `.docs` describe services as more stubbed than they are
  (backtest especially was rebuilt). Treat code as source of truth.

**Open decisions (need product/eng calls)**
- **Broker connect UX:** manual API-key paste (recommended for v1) vs. **Alpaca OAuth**
  (cleaner, no raw secret stored, natural bridge to advisor-on-client later) — broker-setup §6.
- **Credential encryption bar for beta:** app-layer hardened (salt+rotation) is enough
  for *paper* beta; **KMS envelope encryption is required before M6 (real money)**.
- **Multi-user tenants in beta?** Credentials are tenant-scoped with no per-user ACL or
  audit today (broker-setup C1). Fine for single-operator beta; needs a decision before
  multi-seat firms.
- **Notifications in beta?** Currently deferred. If testers need fill/drift alerts,
  email-only delivery is the minimum add (small, but currently stubbed).

---

## 8. References

- [`broker-setup-individual-traders.md`](./broker-setup-individual-traders.md) — BYO-keys
  design, security gaps, phased plan (feeds M2 + M4 + M6).
- [`CONTRACTS.md`](./CONTRACTS.md) — locked trading↔ledger fill/reservation contract.
- [`trading-ledger-implementation-plan.md`](./trading-ledger-implementation-plan.md) —
  6-phase ledger write-side (implemented).
- [`portfolio-ledger-completion-plan.md`](./portfolio-ledger-completion-plan.md) —
  ledger read-side cutover + soak (feeds M2).
- [`redis-streams-migration.md`](./redis-streams-migration.md) — durable event transport
  (powers live UI streams in M2).
- [`telemetry.md`](../telemetry.md) — observability lib (feeds M4).
- [`individual-asset-trading.md`](./individual-asset-trading.md) — manual trading
  (deferred, post-MVP).
