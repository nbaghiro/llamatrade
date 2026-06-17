# Broker Setup (Individual Traders / BYO Keys) — Design & Gap Doc

> **STATUS: DRAFT for review (2026-06-16).** Scopes the work to release "connect
> your own Alpaca account" for individual self-directed traders. The backend is
> already built end-to-end; the work is a frontend surface plus security hardening.
> Firm-trades-customer-money (Alpaca Broker API) is explicitly **out of scope** here
> — see §5.

## 0. Scope & model

**In scope — "bring your own keys" (BYO).** The end user creates their own account
at Alpaca, generates an API key/secret, and connects it to LlamaTrade. LlamaTrade is
*software automating the user's own brokerage account*; it never custodies funds and
takes on no new broker/advisor registration. This model also fully covers a **small
firm trading its own (single) account** with multiple staff logins — one tenant, one
credential set, several users (see Phase 4).

**Not in scope — customer money.** A firm trading *its end-clients'* money needs the
Alpaca **Broker API** (per-customer sub-accounts, KYC/AML onboarding, funding) and an
RIA/broker-dealer regulatory posture. That is a separate program gated on a legal
decision, not an engineering increment on top of this. See §5.

## 1. Current state — the backend already exists

The BYO credential path is built and wired; the only true product gap is the UI.

- **Data model:** `AlpacaCredentials` — `tenant_id`, `name`, `api_key_encrypted`,
  `api_secret_encrypted`, `is_paper`, `is_active`
  (`libs/db/llamatrade_db/models/auth.py:56`). Encrypted at rest via Fernet
  (`libs/common/llamatrade_common/utils.py:46`). Multiple named credential sets per
  tenant; soft-delete via `is_active`.
- **API:** full create/get/list/delete on the auth service
  (`auth.proto:203`, implemented `services/auth/src/grpc/servicer.py:720`), all
  tenant-isolated. List returns masked key prefixes; Create/Get return decrypted keys
  (see gap B1).
- **Library:** `llamatrade_alpaca` accepts per-session credentials and a `paper` flag;
  the trading service constructs fresh clients per session from decrypted DB
  credentials (`services/trading/src/services/live_session_service.py:331`,
  `_get_credentials_by_id` at `:523`) — not a process-wide singleton, so per-tenant
  isolation already holds.
- **Identity threading:** each credential set lazily mints one `ledger_accounts` row
  (`account_id`, unique per `credentials_id`,
  `libs/db/llamatrade_db/models/ledger.py:118`); `StartTradingSessionRequest`
  already requires `credentials_id` (`trading.proto`, field 6).
- **JWT:** carries `sub` (user_id), `tenant_id`, `roles`
  (`services/auth/src/services/auth_service.py:156`); `credentials_id`/`account_id`
  are resolved server-side, not in the token.

## 2. Gaps

### A. Frontend (the primary gap) — *no UI exists*
- **A1.** Settings has only Account + Billing tabs; no credential entry/management
  (`apps/web/src/pages/settings/SettingsPage.tsx`).
- **A2.** No post-registration onboarding/"connect your broker" step
  (`apps/web/src/pages/auth/RegisterPage.tsx`, `pages/dashboard/DashboardPage.tsx`).
- **A3.** No credential picker when starting a live/paper session (the proto requires
  `credentials_id`, but nothing in the UI supplies it).
- **A4.** No guidance on obtaining Alpaca keys / paper-vs-live explanation.

### B. Security & hardening (release blockers — real money + secrets)
- **B1. Secrets are read back in plaintext.** Create/Get return the decrypted
  `api_secret` to the client (`services/auth/src/models.py:208`,
  `AlpacaCredentialsResponse.api_secret`). Credentials should be **write-only** from
  the UI's perspective — never returned after creation. This is the single biggest
  smell to fix before launch.
- **B2. Dev-grade encryption.** One global `ENCRYPTION_KEY` + a **static salt**
  (`utils.py:46`) protects every tenant's live keys. Compromise of one env var = all
  customers' brokerage keys. Needs a managed KMS / secrets manager with envelope
  encryption + rotation for real money.
- **B3. No credential validation.** Keys are stored/used without ever calling Alpaca
  to confirm they're valid and match the declared paper/live environment.

### C. Multi-user authorization (firm-own-account)
- **C1.** Credentials are tenant-scoped with **no `user_id`/`created_by`** and no ACL
  (`models/auth.py:56`). The moment a tenant has multiple seats, any user can trade
  with — and the API returns (per B1) — the firm's live keys. No audit trail of who
  added/used a credential.

### D. Lifecycle & UX
- **D1.** No credential rotation (must delete + re-add).
- **D2.** No paper→live promotion guardrail; nothing prevents fat-fingering into live
  trading. (`.env` fallback is paper-only, which is good, but the live path is
  unguarded.)

## 3. Phased plan

Each phase is independently shippable; B (security) gates any production launch.

### Phase 0 — Harden the credential contract (backend; release blocker)
- **B1:** drop `api_secret` (and ideally `api_key`) from `AlpacaCredentialsResponse`
  and the `Get`/`Create` proto responses; make credentials write-only. Audit
  `auth.proto:51` (`AlpacaCredentials` message) + `models.py:208`. List already masks.
- **B3:** add `ValidateAlpacaCredentials` (or validate inline on create) — a
  `llamatrade_alpaca` `get_account()` call against the declared environment; reject on
  failure and surface the Alpaca account status.
- **B2 (decision-gated, see §6):** move encryption to KMS/secrets-manager envelope
  encryption, or at minimum per-value random salts + a rotation path.
- Tests: write-only response (secret never serialized); validation rejects bad keys
  and paper/live mismatch; tenant isolation preserved.

### Phase 1 — Credential management UI
- New "Broker" tab on `SettingsPage` → `BrokerCredentialsPage`: list (masked) + add +
  delete, paper/live badge, "test connection" button (Phase 0 validation).
- Add form: name, API key, secret (write-only), paper/live toggle, link to Alpaca key
  docs. Wire to the existing auth gRPC client (`apps/web/src/services/`).
- Tests: create/list/delete happy path; validation errors; secret never echoed back.

### Phase 2 — Post-registration onboarding
- After register/first login with zero active credentials, route to a "Connect your
  broker" step (reuse Phase 1 form) with a "skip for now / paper later" path; surface
  a dashboard empty-state nudging connection.

### Phase 3 — Session credential selection + live guardrails
- Credential picker in the start-session / start-execution flow (supplies the required
  `credentials_id`). Default to paper.
- **D2:** explicit confirmation step + visible mode banner when a live credential is
  selected; block live sessions unless the credential validated (Phase 0).

### Phase 4 — Multi-user authorization & audit (firm-own-account)
- **C1:** add `created_by` (FK→User) to `AlpacaCredentials` (+ migration); record
  add/use in an audit log; decide tenant-shared vs per-user ACL (see §6) and enforce
  in the auth + trading service-layer checks.
- Tests: non-owner access controlled per chosen ACL model; audit entries written.

## 4. Definition of done
- A new user can connect a paper account from the UI, validate it, and run a paper
  session selecting that credential — with the secret never returned after entry.
- Live trading requires a validated credential and an explicit confirmation.
- A multi-seat tenant has a defined, enforced authorization model and an audit trail.
- Secrets-at-rest meet the agreed bar (§6 B2 decision).
- ≥80% coverage on new real code; ruff/pyright/eslint/tsc; `./scripts/ci-local.sh`.

## 5. Explicitly out of scope (separate program)
- **Alpaca Broker API** — per-customer account creation, KYC/AML, omnibus/fully-
  disclosed structures, ACH/JIT funding. Requires its own data model (a *Customer*/
  end-investor entity, which does not exist today) and a regulatory posture decision
  (RIA / broker-dealer / under Alpaca's umbrella). Trading other people's money is a
  business+legal decision, not an engineering increment.
- **Funding / money movement** of any kind.

## 6. Open decisions (need your call before Phase 0/4)
- **B2 — secrets at rest:** managed KMS/secrets-manager envelope encryption (heavier,
  correct for real money) vs. hardened app-layer encryption (per-value salt + rotation)?
  *Recommend KMS if launch includes live trading.*
- **Connect UX:** manual API-key paste vs. **Alpaca OAuth** (scoped connect, no raw
  secret stored). OAuth is cleaner and is also the natural bridge to advisor-on-client-
  account later — but it's a bigger Phase 1. *Recommend manual keys for v1, OAuth as a
  fast-follow.*
- **C1 — authorization model:** tenant-shared credentials with `created_by` + audit
  (simplest, fits firm-own-account) vs. per-user credential ownership/ACL (needed if
  one tenant ever maps to many independent traders). *Recommend shared + audit for v1.*
- **Launch surface:** paper-only at launch, live as a fast-follow, or both day one?
