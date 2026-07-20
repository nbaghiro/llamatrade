# Alpaca OAuth — Implementation Plan (WS-C)

**Status:** Plan / not started. Paper-first beta scope.
**Goal:** Let a user **(1) sign up / log in to LlamaTrade with Alpaca** and **(2) link/disconnect an Alpaca account from Settings** — via Alpaca OAuth 2.0. Email+password stays the primary auth; Alpaca is an *additional* option (Alpaca-only auth is a later phase).
**Related:** `broker-api-legal-checklist.md` (WS-B, embedded is the *other* path), `broker-dual-model-plan.md` (memory).

---

## 1. The two hard constraints that shape everything

1. **OAuth gives an account, not an identity.** Alpaca OAuth returns an Alpaca **`account_id`** (via `GET /v2/account` with the token) but **no email or name** — the Trading API exposes account number/status/buying-power, not contact info. So "sign up with Alpaca" cannot mint a complete LlamaTrade user by itself; it needs a **"complete signup" step** to capture an email. "Log in with Alpaca" (returning user) matches `account_id → user` and just issues a JWT.

2. **`User.password_hash` is `NOT NULL`** (`libs/db/.../models/auth.py:43`), and email is unique **per tenant** (`ix_users_tenant_email`, `auth.py:37`). So an Alpaca-only (passwordless) user needs a schema change. **MVP decision: require email + password at complete-signup** (keeps the schema, gives the user a normal fallback login *and* one-click Alpaca login afterward). Passwordless/Alpaca-only is Phase 4 (nullable `password_hash` + lockout guards).

### One OAuth flow, two intents, two artifacts
An OAuth round-trip carries an **intent** in signed `state` and produces up to two artifacts:

| Intent | Entry point | Produces |
|---|---|---|
| `auth` | "Continue with Alpaca" on Login/Register | a **LlamaTrade session** (JWT) — via login (existing link) or signup (new user) |
| `link` | "Connect with Alpaca" in Settings | a **stored trading credential** (bearer token) on the authenticated user |

- **Identity link** = `oauth_identities(account_id → user)` — powers login/signup.
- **Trading credential** = an `alpaca_credentials` row holding the encrypted **bearer token** — powers trading.
- They're joined by `account_id`. `link` creates the credential (and, idempotently, the identity so the user can later also log in with Alpaca). `auth`-signup creates user+tenant+identity+credential.

---

## 2. ⚠️ Verify BEFORE building (Phase 0 gate)

These change scope materially:

1. **Streaming over OAuth (load-bearing).** The live runner needs `BarStreamClient` + `TradingStreamClient`, which auth via **key/secret** in a JSON `auth` payload (`streaming/base.py`). If the WS streams **don't accept a bearer/OAuth token**, OAuth-linked accounts **can't drive the live strategy runner** — OAuth would be usable for account connection + REST only. Verify first; it gates whether OAuth is viable for live trading vs connect-only.
2. **Token lifecycle.** Classic `authorization_code` response shows only `{access_token, token_type, scope}` (no `expires_in`/`refresh_token` → long-lived), but Alpaca's newer `authx` infra uses 15-min tokens + refresh for *admin*. Confirm what the end-user flow returns; design storage to optionally hold `refresh_token` + `expires_at`.
3. **Paper pre-approval.** Confirm `env=paper` OAuth works before Alpaca approves the app for live (so we can build/test the beta).
4. **PKCE support.** Use PKCE if Alpaca supports it (defense-in-depth for the public authorize redirect).

**Manual de-risk:** register the app (paper), then `curl` the full flow once to answer all four before writing code.

---

## 3. Data model — Alembic migration `029` (off head `028`)

Model the file on `libs/db/.../versions/20250321_000000_024_add_user_avatar_url.py`.

**a) Extend `alpaca_credentials`** (`models/auth.py:57-72`) for OAuth tokens:
- `auth_type: str` — `"api_key" | "oauth"`, default `"api_key"`.
- `access_token_encrypted: Text | None` (nullable).
- `refresh_token_encrypted: Text | None` (nullable).
- `token_expires_at: timestamptz | None` (nullable).
- `alpaca_account_id: str | None` (nullable) — the Alpaca `/v2/account` id.
- Make `api_key_encrypted` / `api_secret_encrypted` **nullable** (OAuth rows have no key/secret).
- Keep `is_paper`, `is_active`, `name`. Already RLS-enabled (`rls.py:59`) — no RLS change.

**b) New table `oauth_identities`** (login anchor, extensible to Google later):
- `id` (uuid pk), `user_id` FK→users, `tenant_id` FK→tenants, `provider: str` (`"alpaca"`), `provider_account_id: str`, timestamps.
- **Unique `(provider, provider_account_id)`** — one Alpaca account maps to exactly one LlamaTrade user.
- Register in `RLS_TABLES` (`rls.py:50-91`), export in `models/__init__.py`, import in `alembic/env.py` — the test `test_rls_tables_match_tenant_scoped_metadata` enforces the RLS list matches the models.

> Rejected alternative: a `users.alpaca_account_id` column. A separate `oauth_identities` table is cleaner, avoids nulls on every user row, and generalizes to future providers.

---

## 4. `libs/alpaca` — add a Bearer auth mode + an OAuth module

**a) Bearer support** (so an OAuth token can drive `TradingClient`):
- `AlpacaCredentials` (`config.py:55-98`): add optional `access_token: str | None`.
- `to_headers()`: if `access_token` → `{"Authorization": f"Bearer {access_token}"}`, else the existing `APCA-API-KEY-ID`/`APCA-API-SECRET-KEY`.
- `is_valid()`: `access_token` **or** (`api_key` and `api_secret`).
- `client_base.py:69` already calls `credentials.to_headers()` — no change there.

**b) New `llamatrade_alpaca/oauth.py`** (keeps *all* Alpaca calls in the lib, per CLAUDE.md):
- `build_authorize_url(client_id, redirect_uri, scope, state, *, paper) -> str` → `https://app.alpaca.markets/oauth/authorize?...&env=paper`.
- `async exchange_code(code, client_id, client_secret, redirect_uri) -> OAuthToken` → POST `https://api.alpaca.markets/oauth/token` (`grant_type=authorization_code`).
- `async refresh(refresh_token, ...) -> OAuthToken` (if refresh applies).
- `async revoke(token)` (for disconnect, if a revoke endpoint exists).
- `OAuthToken` dataclass: `access_token, token_type, scope, refresh_token?, expires_in?`.

**c) Streaming** (pending Phase-0 result): if Bearer is accepted, thread a token into the WS auth payload; else document the limitation on the streams.

---

## 5. Auth service — endpoints, state, branching

Auth service = FastAPI + Connect mounted at `/`. Add plain HTTP routes exactly like billing's webhook router (`services/billing/src/main.py:86`, `routers/webhooks.py`).

### New HTTP routes — `services/auth/src/routers/oauth.py` (`APIRouter`, `include_router` in `main.py` ~L79)
- `GET /oauth/alpaca/authorize?intent=auth` — **public**. Mint signed `state` (intent=auth, nonce), 302 → Alpaca authorize URL (`env=paper`).
- `GET /oauth/alpaca/callback?code=&state=` — **public**. The Alpaca redirect target (does the server-side secret exchange).

Add both to `AuthMiddleware(public_suffixes=[...])` (`main.py:63-66`; matcher is `path.endswith`, `common/auth.py:258`).

### New Connect RPCs (auth.proto + servicer)
- `StartAlpacaLink() -> {authorize_url}` — **authenticated**. For Settings "link": mints `state` embedding `tenant_id`/`user_id` from the caller's JWT (browser can't carry a bearer on a top-level redirect, so we mint the URL server-side and the frontend just navigates to it).
- `ExchangeOAuthHandoff(handoff) -> LoginResponse` — **public**. Login handoff → tokens+user.
- `CompleteAlpacaSignup(ticket, email, first_name, last_name, password) -> LoginResponse` — **public**. Finish signup.

### `state` (CSRF + replay)
Signed short-TTL JWT (HS256 over `JWT_SECRET`, ~10 min), like `mint_service_token` (`common/auth.py:102-119`). Carries `intent`, `nonce`, and for `link` the `tenant_id`/`user_id`. Store the `nonce` single-use in Redis (10-min TTL) to prevent replay; verify signature **and** consume nonce in the callback. (Fallback if auth has no Redis: nonce in a signed httpOnly cookie, double-submit.)

### Callback logic
1. Verify `state` (signature + single-use nonce) → extract `intent`.
2. `exchange_code(code)` → Alpaca token (server-side, uses `client_secret`).
3. `GET /v2/account` (Bearer) → `account_id`, status, `is_paper`.
4. Branch:
   - **`link`** (tenant/user from state): upsert an `alpaca_credentials` row (`auth_type="oauth"`, `access_token_encrypted`, `alpaca_account_id`, `is_paper=True`, `is_active=True`, `name="Alpaca (OAuth)"`); idempotently upsert `oauth_identities`. Redirect → `/settings?tab=broker&connected=1`.
   - **`auth`** → look up `oauth_identities` by `account_id`:
     - **found → login:** issue JWT (shared mint helper), stash a one-time `handoff` code (Redis), redirect → web `/oauth/alpaca/callback?handoff=…`.
     - **not found → signup:** stash `account_id` + encrypted token under a one-time `ticket` (Redis, ~15 min), redirect → web `/signup/complete?ticket=…`.
   - **error** → redirect → `/login?error=…` (or `/settings?...`).

### Token handoff (never put a JWT in a URL)
The callback lands in the browser; a JWT in the query string leaks via history/referrer. So the callback redirects with a **one-time `handoff`/`ticket` code**; the frontend exchanges it via a **POST RPC** (`ExchangeOAuthHandoff` / `CompleteAlpacaSignup`) for the real tokens. Codes are single-use, short-TTL.

### JWT issuance
Refactor the login token-mint block (`servicer.py:460-484`) into a **shared helper** so login, handoff-exchange, and complete-signup emit identical `access`(30m)/`refresh`(7d) tokens with claims `sub`/`tenant_id`/`email`/`roles`/`type=access` — `verify_credential` only accepts `type=access` (`common/auth.py:122-158`).

### Disconnect
Extend `DeleteAlpacaCredentials` (or a new RPC): `revoke()` the token at Alpaca, set `is_active=False`. **Guard:** if this is the user's only login method (Phase-4 passwordless users), require a password first so they can't lock themselves out. (MVP users always have a password → no lockout risk.)

---

## 6. Trading credential resolution

`build_trading_client(creds)` (`services/trading/src/providers.py`) branches on `auth_type`: OAuth → `TradingClient(access_token=…, paper=…)`; else key/secret. `DecryptedCredentials` (`services/trading/src/credentials.py`) gains an optional `access_token`; `resolve_credentials` decrypts the token for OAuth rows. (This is the anticipated evolution of the build functions — a credential *variant*, not a new client.)

---

## 7. Frontend (`apps/web` + `apps/core`)

- **Auth pages:** add an **Alpaca** button to `SocialAuthButtons.tsx` (`onAlpaca`), wired on Login/Register → `window.location.href = <StartAlpacaOAuth authorize_url>` (or `GET /oauth/alpaca/authorize?intent=auth` for the unauth entry).
- **Callback route** (public, before the catch-all in `App.tsx:91`): `/oauth/alpaca/callback` → read `?handoff` → `ExchangeOAuthHandoff` → `setSession(user, access, refresh)` (`apps/core/src/stores/auth.ts:31`) → `/dashboard`. `setSession` needs a full user object → the RPC returns it (mirror `LoginResponse`).
- **Signup-complete route** (public): `/signup/complete?ticket=…` → form (email, first/last name, password) → `CompleteAlpacaSignup` → `setSession` → `/dashboard`.
- **Settings:** add "Connect with Alpaca" in `BrokerTab` (`SettingsPage.tsx:404-620`) → calls `StartAlpacaLink` then redirects. The **existing "Connected Accounts" list needs no change** — an OAuth row persisted as `AlpacaCredentialsListItem` (`id,name,apiKeyPrefix,isPaper,isActive,createdAt`) shows automatically; give it a recognizable `name` and a null/blank `apiKeyPrefix` (or `"oauth"`). Disconnect reuses `remove(id)` → `DeleteAlpacaCredentials`.
- **Funding/Wallet consistency:** OAuth rows must be `isPaper=true` + `isActive=true` so `funding.resolveAccount()` (`stores/funding.ts:73`) and `WalletPage.tsx:42` pick them up.
- **Broker store:** add `startOAuthLink()` (calls `StartAlpacaLink`, redirects) to `stores/broker.ts`; re-`fetch()` on return.

---

## 8. Security checklist
- Signed, single-use, short-TTL `state` (CSRF + replay). PKCE if supported.
- Code→token exchange **server-side only** (`client_secret` never reaches the browser).
- **No tokens in URLs** — one-time handoff/ticket codes, exchanged via POST.
- Tokens encrypted at rest via `encrypt_value` (`common/utils.py`); KMS is a later hardening (shared with WS-D).
- Exact `redirect_uri` allowlist, per-env.
- Minimal scopes: `trading` (+ `data` if serving data via token; `account:write` only if needed).
- `env=paper` enforced for the beta.
- Tenant from `state`/JWT, never from a request body (matches existing servicer pattern).
- Disconnect = revoke + deactivate + (Phase-4) sole-login guard.

---

## 9. Config & ops
- **Register the app** in Alpaca's dashboard → "My Developed Apps"; whitelist redirect URIs per env; get `client_id`/`client_secret`. **Live needs Alpaca approval**; paper first.
- **Env:** `ALPACA_OAUTH_CLIENT_ID`, `ALPACA_OAUTH_CLIENT_SECRET`, `ALPACA_OAUTH_REDIRECT_URI`, `ALPACA_OAUTH_SCOPE` in `.env.example`; k8s `secretKeyRef`s on the auth deployment (`infrastructure/k8s/base/auth/deployment.yaml:26-41`).
- **Redirect URI = the AUTH service's public callback** (`https://<public-auth-host>/oauth/alpaca/callback`), because the callback does the server-side secret exchange, then redirects to the web app. **Confirm ingress/Caddy exposes `/oauth/alpaca/*` on auth publicly** (`Caddyfile` currently shows only a `web` upstream — this must be routed).

---

## 10. Testing
- **Unit:** state mint/verify (expiry, tamper, replay); `exchange_code` (httpx/respx mock); `account_id` extraction; `to_headers()` Bearer; login-vs-signup branching; `CompleteAlpacaSignup` creates tenant+user+identity+credential; disconnect revokes+deactivates; `build_trading_client` OAuth branch.
- **Integration:** full callback with mocked Alpaca → DB rows + JWT; tenant isolation (link uses state's tenant only); duplicate-account-link rejection.
- **Frontend:** Alpaca button → authorize redirect; callback page handoff → `setSession`; signup-complete form; settings connect shows in list + wallet/funding; disconnect removes.

---

## 11. Phased milestones
- **Phase 0 — De-risk:** register app (paper); curl the flow; answer the 4 open questions. **Gate:** if streaming-over-OAuth fails, decide connect/REST-only vs defer.
- **Phase 1 — Backend foundation (link, no UI):** lib Bearer + `oauth.py`; migration `029`; `StartAlpacaLink` + `/authorize` + `/callback` (link intent); `build_trading_client` branch; config/secrets. Test link via API.
- **Phase 2 — Settings UI:** "Connect with Alpaca" + disconnect; shows in list/wallet/funding.
- **Phase 3 — Auth-flow login/signup:** `intent=auth`; `oauth_identities` lookup; `ExchangeOAuthHandoff` + `CompleteAlpacaSignup`; frontend button + callback + signup-complete pages.
- **Phase 4 — Later:** passwordless/Alpaca-only (nullable `password_hash` + lockout guards); live approval; token-refresh loop; KMS.

---

## 12. Open decisions (confirm before Phase 1)
1. **Signup password:** ✅ **CONFIRMED (2026-07-19) — require email+password at complete-signup** (keeps `password_hash` NOT NULL, gives dual login). Email-only/passwordless deferred to Phase 4.
2. **Identity store:** `oauth_identities` table (**recommended**) vs `users.alpaca_account_id` column.
3. **Does `link` also create a login identity?** (**recommended yes** — so settings-linkers can later "log in with Alpaca"; reject if the account is already linked to another user.)
4. **Streaming-over-OAuth** (Phase-0 result) — determines whether OAuth accounts can trade live or connect-only.
