# Mobile: Connect Broker + Plans & Billing — Implementation Plan

Two designed mobile surfaces are **not yet implemented**. Today the "You" tab
(`apps/mobile/app/(tabs)/account.tsx`) shows a text-only "Coming soon" broker
card (lines 304–316, no route, not even pressable) and displays the current
plan/payment **read-only** (`apps/mobile/src/stores/billing.ts` — "subscribe/
checkout/cancel stay on the desktop"). This plan builds both.

## Locked decisions

1. **Scope** — build **both** screens in parallel.
2. **Connect Broker** — add a `ValidateAlpacaCredentials` backend RPC **first**;
   the screen validates keys against Alpaca, then stores them (server-side,
   Fernet-encrypted, over TLS via the existing `CreateAlpacaCredentials`). Align
   security copy to server-side storage. Gate "Live" behind a paid plan.
3. **Plans & Billing** — **informational** in-app: plan comparison + monthly/
   yearly toggle + current-plan highlight. Free downgrade happens in-app (no
   payment); **paid upgrades route to web** (no native IAP, no Stripe-in-app).

## Backend readiness (why the two differ)

- **Connect Broker** — backend is built end-to-end: `authClient` exposes
  `CreateAlpacaCredentials` / `GetAlpacaCredentials` / `ListAlpacaCredentials` /
  `DeleteAlpacaCredentials` (`auth.proto:279-283`); keys encrypted at rest
  (Fernet, `libs/common/.../utils.py`); live sessions already require a
  `credentials_id` (`trading.proto` field 6). The one gap is validation.
- **Plans & Billing** — read RPCs exist (`ListPlans`, `GetSubscription`,
  `ListPaymentMethods`, `ListInvoices`); the mobile store already calls them.
  `CreateCheckoutSession`/`CreatePortalSession` handlers are **stubs**, and
  `@stripe/stripe-react-native` is not installed — which is exactly why paid
  checkout stays on web under decision (3).

---

## Phase 0 — Shared groundwork

### 0a. Backend: `ValidateAlpacaCredentials` RPC (auth service)
- **Proto** (`libs/proto/llamatrade_proto/protos/auth.proto`): add
  ```
  rpc ValidateAlpacaCredentials(ValidateAlpacaCredentialsRequest)
      returns (ValidateAlpacaCredentialsResponse);

  message ValidateAlpacaCredentialsRequest {
    string api_key = 1;
    string api_secret = 2;
    bool   is_paper  = 3;
  }
  message ValidateAlpacaCredentialsResponse {
    bool   valid          = 1;
    string account_status = 2;   // e.g. "ACTIVE"
    string buying_power   = 3;    // decimal string, informational
    string message        = 4;    // reason when !valid
  }
  ```
- **Service** (`services/auth/src/grpc/servicer.py`): construct a
  `llamatrade_alpaca` trading client with the supplied key/secret + `paper=is_paper`
  and call `get_account()`. Map results:
  - success → `valid=true`, echo `account_status`/`buying_power`.
  - Alpaca 401/403 → `valid=false`, `message="Invalid API key or secret"`.
  - paper/live mismatch (auth works on the *other* environment) → `valid=false`,
    `message="These look like <paper|live> keys — toggle the environment"`.
  - network/timeout → `HTTPException`-equivalent Connect error (don't swallow).
- **Never persists** anything; pure validation. Requires auth (tenant from JWT),
  no `TenantContext` arg (matches the other Alpaca RPCs).
- **Regenerate**: `make proto` (updates `apps/core/src/proto/auth_pb.ts`).
- **Tests** (`services/auth/tests/`): valid keys, invalid keys, paper/live
  mismatch, upstream error. Mock `llamatrade_alpaca` get_account.
- **Companion hardening (recommended, small):** make `CreateAlpacaCredentials`/
  `GetAlpacaCredentials` responses **write-only** — stop returning the decrypted
  secret (security gap B1 in `broker-setup-individual-traders.md`). Do it now
  while touching these RPCs, or track as a fast-follow.

### 0b. Shared plan-tier config → `@llamatrade/core`
- Move web `apps/web/src/data/planTiers.ts` (Free $0 / Pro $49 / Enterprise $199,
  `YEARLY_DISCOUNT = 0.17`, per-tier features + `maxLiveSessions`) into
  `@llamatrade/core` (e.g. `apps/core/src/billing/planTiers.ts`), mirroring how
  the markets/dashboard stores were promoted to core. Re-point the web import.
  Both apps then share one source of truth (DRY). Enterprise stays a
  **contact-sales** tier (no self-serve proto plan row — proto `PlanTier` only has
  FREE/STARTER/PRO).

### 0c. Mobile primitives (neither exists today)
- `apps/mobile/src/ui/Button.tsx` — variants `primary` (orange) / `secondary`
  (ink outline) / `danger`, Monolith hard-border + offset shadow, `loading` +
  `disabled` states. Replaces the inline `Pressable`s in `account.tsx`.
- `apps/mobile/src/ui/SegmentedToggle.tsx` — 2–3 segment control (active =
  ink fill / bone text). Used by **paper/live** and **monthly/yearly**.
- Compose from existing tokens (`@llamatrade/core/theme`) + `Card`/`Badge`/`Mono`
  in `apps/mobile/src/ui/index.tsx`. Reuse `Field` (`apps/mobile/src/auth/ui.tsx`)
  for the key inputs.

### 0d. Routes (Expo Router)
- Add `apps/mobile/app/account/connect-broker.tsx` and
  `apps/mobile/app/account/plans.tsx` as stack routes pushed from the YOU tab
  (register in the root `<Stack>` at `apps/mobile/app/_layout.tsx`). Standard
  header with a back affordance, matching `strategy/[id]`.

---

## Phase 1 — Connect Broker (Link Alpaca)

**Route:** `app/account/connect-broker.tsx`

**Store:** `apps/mobile/src/stores/broker.ts` (new)
- state: `credentials: AlpacaCredentialsListItem[]`, `connecting`, `validating`,
  `error`, `loaded`.
- `fetch()` → `authClient.listAlpacaCredentials({})` (tenant from JWT).
- `connect({ name, apiKey, apiSecret, isPaper })`:
  1. `authClient.validateAlpacaCredentials({ apiKey, apiSecret, isPaper })`.
  2. if `!valid` → set inline error, stop.
  3. `authClient.createAlpacaCredentials({ name, apiKey, apiSecret, isPaper })`.
  4. refresh list; clear the secret from memory.
- `remove(id)` → `authClient.deleteAlpacaCredentials({ credentialsId: id })`.
- Do **not** persist the raw secret on device. Optionally cache the returned
  `credentials.id` via `expo-secure-store`.

**UI (matches the design):**
- LINK ALPACA hero card (ink, orange warehouse glyph): "The exact strategy you
  backtest is what trades. Bring your own broker keys."
- `SegmentedToggle` **PAPER / LIVE** — LIVE disabled when the current plan has
  `maxLiveSessions === 0`; show "LIVE TRADING REQUIRES A PRO PLAN" that links to
  the Plans screen.
- `Field` **API Key ID**, `Field` **Secret Key** (`secureTextEntry`).
- Security note (aligned copy): "Keys are validated with Alpaca, encrypted, and
  sent only over TLS — never stored in plaintext."
- `Button` **CONNECT & VERIFY →** (`loading` during validate+create).
- Connected state: list existing credential sets (name, `api_key_prefix`,
  paper/live, active) with a remove action.

**Entry point:** replace the placeholder card in `account.tsx:304-316` with a
pressable that navigates to the screen and reflects connected state ("Connected ·
paper" / "Connect broker →") from the broker store.

---

## Phase 2 — Plans & Billing

**Route:** `app/account/plans.tsx`

**Store:** extend `apps/mobile/src/stores/billing.ts`
- add `plans` + `fetchPlans()` → `billingClient.listPlans({ context })`.
- add `downgradeToFree()` → `billingClient.createSubscription`/`updateSubscription`
  to the Free plan id (no payment needed) with a confirm.
- keep all paid checkout **out of the app**.

**UI (matches the design):**
- `SegmentedToggle` **MONTHLY / YEARLY −17%** (local state; drives displayed price
  via the shared plan-tier config).
- Plan cards Free / Pro / Enterprise from the shared config: feature bullets,
  "MOST POPULAR" on Pro, current-plan highlight from `getSubscription` →
  resolved tier.
- Buttons per card:
  - current tier → disabled **CURRENT PLAN ✓**.
  - Free (when on a paid tier) → **DOWNGRADE** → in-app `downgradeToFree()` +
    confirm.
  - paid tier (upgrade) → **MANAGE ON WEB →** → `Linking.openURL(${WEB_URL}/billing)`.
- Copy stays informational/account-management; no in-app "buy" CTA for paid tiers.

**Entry point:** make the account "CURRENT PLAN" card pressable → navigate to Plans.

---

## IAP compliance

Decision (3) keeps the app **outside** App Store IAP rules: no digital goods are
purchased in-app. A Free downgrade is not a purchase; paid upgrades occur on the
web. Keep in-app wording as account management ("Manage on web"), avoid buttons
that read as in-app purchase CTAs for paid tiers, and don't deep-link straight
into a hosted Stripe checkout with a hard-sell. Revisit only if we later choose
native IAP (a separate epic: StoreKit/Play products + receipt-validation RPC +
billing reconciliation).

## Testing

- **Backend:** `ValidateAlpacaCredentials` — valid / invalid / paper-live mismatch
  / upstream error (mock `llamatrade_alpaca`). Target the 80% bar for the new code.
- **Mobile stores:** `broker` (validate→create happy path, invalid-key error,
  remove) and `billing` (fetchPlans, downgradeToFree) — mock the Connect clients
  the way the web store tests do.
- **Manual:** run the Expo app and drive both screens (paper connect, live gating,
  toggle, downgrade, web hand-off).

## Milestones

- **M0** — backend `ValidateAlpacaCredentials` (+ optional B1 write-only) & proto
  regen; move plan-tier config to core; add `Button` + `SegmentedToggle`; add routes.
- **M1** — Connect Broker screen + `broker` store + account entry point.
- **M2** — Plans & Billing screen + billing store writes + account entry point.
- **M3** — tests + simulator verification + copy pass.

M1 and M2 can proceed in parallel once M0 lands (M0 unblocks both).

## Risks / open items

- **Apple 3.1.1/3.1.3 wording** — keep the paid-upgrade hand-off as web account
  management; safest phrasing is "Manage your subscription on the web."
- **Security B1** — returning decrypted secrets is a real gap; fix while in these
  RPCs if possible.
- **Web checkout stub** — `CreateCheckoutSession` is a placeholder; the web
  upgrade path it lands on must be functional before we point mobile users at it.
- **Enterprise** — config-only contact-sales tier; no self-serve subscribe.
