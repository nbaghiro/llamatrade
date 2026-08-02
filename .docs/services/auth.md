# Auth Service

## Overview

The Auth Service is LlamaTrade's identity authority. It authenticates users, mints and revokes JWT sessions, enforces multi-tenant isolation, drives email verification and password reset, and stores broker credentials encrypted at rest. Every request to the platform is verified against tokens this service issues.

**Core Responsibilities:**

- User registration and authentication (login/logout with server-side revocation)
- JWT access and refresh token management (RS256 user tokens, refresh rotation, jti denylist)
- Email verification and password reset via single-use hashed tokens
- Multi-tenant isolation (tenant_id propagation)
- Role-based access control (RBAC)
- Encrypted Alpaca broker credential storage (+ Alpaca OAuth link / sign-in)
- API-key validation for programmatic access
- Fail-closed rate limiting on credential-taking endpoints
- Security notifications (welcome, verification, reset, password changed, lockout) onto the notification stream

---

## Architecture Overview

```
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                                      FastAPI :8810                                       ║
╠══════════════════════════════════════════════════════════════════════════════════════════╣
║ AuthMiddleware (fail-closed, revocation-checked) · Connect / gRPC ASGI app · CORS        ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝
                                              │
                                              ▼
╭──────────────────────────────────────────────────────────────────────────────────────────╮
│                                 AuthServicer  ·  20 RPCs                                 │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Auth · Login · Register · Logout · ChangePassword                                        │
│ Recovery · RequestPasswordReset · ResetPassword · VerifyEmail · ResendVerification       │
│ Token · RefreshToken · ValidateToken · ValidateAPIKey                                    │
│ User · GetCurrentUser · GetUser · GetTenant                                              │
│ RBAC · CheckPermission                                                                   │
│ Alpaca creds · Create · Get · List · Delete · Validate                                   │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ + Alpaca OAuth (HTTP routes, routers/oauth.py, not RPCs):                                │
│   /start · /authorize · /callback · /exchange · /complete-signup                         │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
                                              │
                                              ▼
    ╭──────────────────╮ ╭─────────────────────╮ ╭────────────────────╮ ╭─────────────────╮
    │   session.py     │ │   TenantService     │ │  routers/oauth.py  │ │ services/tokens │
    ├──────────────────┤ ├─────────────────────┤ ├────────────────────┤ ├─────────────────┤
    │ mint_access_     │ │ Alpaca creds:       │ │ Alpaca OAuth       │ │ single-use      │
    │  refresh (RS256) │ │  create/get/list/   │ │  link + sign-in    │ │  email tokens   │
    │ password policy  │ │  delete (Fernet,    │ │ oauth_state.py:    │ │  (sha256 rows,  │
    │ create_tenant_   │ │  deletion guard)    │ │  signed-JWT state  │ │  FOR UPDATE)    │
    │  and_user        │ ╰─────────────────────╯ ╰────────────────────╯ ╰─────────────────╯
    ╰──────────────────╯
                                              │
                                              ▼
╭──────────────────────────────────────────────────────────────────────────────────────────╮
│                            Security backends · llamatrade_common                         │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ JWT sign/verify: RS256 keypair (prod), HS256 dev fallback · bcrypt password hashing      │
│ encrypt_value / decrypt_value (Fernet: AES-128-CBC + HMAC, PBKDF2 key)                   │
│ RateLimiter (fail-closed, Redis) · RevocationStore (jti denylist + per-user cutoff)      │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
                     │                        │                        │
                     ▼                        ▼                        ▼
┌────────────────────────────────┐ ┌───────────────────┐ ┌────────────────────────────────┐
│          PostgreSQL            │ │       Redis       │ │       Kafka (events)           │
├────────────────────────────────┤ ├───────────────────┤ ├────────────────────────────────┤
│ tenants · users · api_keys     │ │ rate-limit        │ │ lt.notifications stream        │
│ auth_tokens (sha256, one-use)  │ │  counters ·       │ │ (welcome, verification, reset, │
│ oauth_identities ·             │ │ revoked jtis ·    │ │  password changed, lockout)    │
│ oauth_pending_signups ·        │ │ per-user cutoffs ·│ └────────────────────────────────┘
│ alpaca_credentials (Fernet)    │ │ one-time handoffs │
└────────────────────────────────┘ └───────────────────┘
```

### JWT Token Flow

```
╭────────────╮          ╭────────────────╮          ╭────────────────╮
│   Client   │          │   Auth :8810   │          │ Other services │
├────────────┤          ├────────────────┤          ├────────────────┤
│ browser    │          │ bcrypt · RS256 │          │ verify with    │
╰────────────╯          │ signing (HS256 │          │ the public key │
       │                │ dev fallback)  │          ╰────────────────╯
       │                ╰────────────────╯                   │
       │   1 login (email, pw)   │                           │
       ├─────────────────────────►                           │
       │                         ├─ 2 verify pw (bcrypt)     │
       │   3 access + refresh    │                           │
       ◄─────────────────────────┤                           │
       │                         │                           │
       │            4 API request + Bearer token             │
       ├─────────────────────────────────────────────────────►
       │     5 validate (RS256 verify + revocation check) ───┤
       │                     6 response                      │
       ◄─────────────────────────────────────────────────────┤
       │                         │                           │
 7 refresh (after 30-min access expiry; presented refresh    │
       │  token is revoked and a new pair minted)            │
       ├─────────────────────────►                           │
       │      8 new tokens       │                           │
       ◄─────────────────────────┤                           │
       │                         │                           │
 9 logout: access jti revoked; refresh jti revoked too when  │
       │  supplied via the x-refresh-token header            │
       ├─────────────────────────►                           │
```

---

## Directory Structure

```
services/auth/
├── src/
│   ├── main.py                 # FastAPI app, AuthMiddleware, Connect mount, health checks
│   ├── models.py               # Pydantic schemas: only the 3 Alpaca-credential schemas
│   ├── session.py              # Token mint, password policy, create_tenant_and_user, OAuth handoff
│   ├── oauth_state.py          # Signed-JWT CSRF state for the OAuth redirect
│   ├── client_ip.py            # Trusted-position client IP from X-Forwarded-For
│   ├── redis_client.py         # Shared async Redis client (None when REDIS_URL is unset)
│   ├── grpc/
│   │   └── servicer.py         # AuthServicer, 20 RPC methods
│   ├── routers/
│   │   └── oauth.py            # Alpaca OAuth 2.0 HTTP routes (browser redirects)
│   └── services/
│       ├── tenant_service.py   # Alpaca credential CRUD + encryption + deletion guard
│       └── tokens.py           # Single-use email tokens: issue/consume + notification links
├── tests/
├── pyproject.toml
└── Dockerfile
```

There is **no** `user_service.py`, `api_key_service.py`, or `database.py`; user/tenant reads
and token mint live directly in the servicer and `session.py`.

---

## Core Components

| Component           | File                         | Purpose                                                                      |
| ------------------- | ---------------------------- | ---------------------------------------------------------------------------- |
| **AuthServicer**    | `grpc/servicer.py`           | Connect servicer, implements 20 RPC methods                                  |
| **TenantService**   | `services/tenant_service.py` | Alpaca credential CRUD, Fernet encryption, in-use deletion guard             |
| **email tokens**    | `services/tokens.py`         | Single-use sha256-hashed tokens for password reset and email verification    |
| **session helpers** | `session.py`                 | `mint_access_refresh`, `validate_password_strength`, `create_tenant_and_user`, OAuth handoff |
| **OAuth router**    | `routers/oauth.py`           | Alpaca OAuth 2.0 link + sign-in/sign-up (HTTP routes)                        |
| **client IP**       | `client_ip.py`               | `trusted_client_ip` from a trusted `X-Forwarded-For` position for rate keys  |

---

## RPC Endpoints (20 Connect RPCs)

### Authentication

| Method           | Request                 | Response                 | Description                                                                       |
| ---------------- | ----------------------- | ------------------------ | --------------------------------------------------------------------------------- |
| `Login`          | `LoginRequest`          | `LoginResponse`          | Authenticate with email/password, returns JWT tokens; dual-bucket rate limited    |
| `Register`       | `RegisterRequest`       | `RegisterResponse`       | Create a new tenant and its first (admin) user; returns user + tenant (no tokens); emits welcome + verification emails |
| `Logout`         | `LogoutRequest`         | `LogoutResponse`         | Revoke the presented access token's `jti`; also revokes the paired refresh token's `jti` when supplied via the `x-refresh-token` header |
| `ChangePassword` | `ChangePasswordRequest` | `ChangePasswordResponse` | Update password with current-password verification; revokes every live session for the user |

### Account Recovery / Email Verification (public)

| Method                 | Request                       | Response                       | Description                                                                    |
| ---------------------- | ----------------------------- | ------------------------------ | ------------------------------------------------------------------------------ |
| `RequestPasswordReset` | `RequestPasswordResetRequest` | `RequestPasswordResetResponse` | Issue a reset token and email a link; uniform response, never reveals account existence |
| `ResetPassword`        | `ResetPasswordRequest`        | `ResetPasswordResponse`        | Redeem a reset token, set the new password, revoke every session               |
| `VerifyEmail`          | `VerifyEmailRequest`          | `VerifyEmailResponse`          | Redeem a verification token and set `is_verified`                              |
| `ResendVerification`   | `ResendVerificationRequest`   | `ResendVerificationResponse`   | Re-send the verification email (active, unverified accounts only); uniform response |

### Token Management

| Method           | Request                 | Response                 | Description                                                                                     |
| ---------------- | ----------------------- | ------------------------ | ----------------------------------------------------------------------------------------------- |
| `RefreshToken`   | `RefreshTokenRequest`   | `RefreshTokenResponse`   | Rotate: check revocation, revoke the presented refresh token's `jti`, mint a new access + refresh pair |
| `ValidateToken`  | `ValidateTokenRequest`  | `ValidateTokenResponse`  | Verify a JWT and extract claims; only user access tokens report valid (refresh/service tokens do not) |
| `ValidateAPIKey` | `ValidateAPIKeyRequest` | `ValidateAPIKeyResponse` | Validate an API key: prefix lookup, constant-time full-key hash verify, then active/expiry/scopes; updates `last_used_at` |

### User / Tenant

| Method           | Request                 | Response                 | Description                                                        |
| ---------------- | ----------------------- | ------------------------ | ------------------------------------------------------------------ |
| `GetCurrentUser` | `GetCurrentUserRequest` | `GetCurrentUserResponse` | Authenticated user's profile + tenant (resolved from the token)    |
| `GetUser`        | `GetUserRequest`        | `GetUserResponse`        | Get a user by id (tenant-scoped; service tokens may cross tenants) |
| `GetTenant`      | `GetTenantRequest`      | `GetTenantResponse`      | Get a tenant by id (tenant-scoped; service tokens may cross tenants) |

### RBAC / Permissions

| Method            | Request                  | Response                  | Description                                                                             |
| ----------------- | ------------------------ | ------------------------- | --------------------------------------------------------------------------------------- |
| `CheckPermission` | `CheckPermissionRequest` | `CheckPermissionResponse` | Advisory role→resource/action check; roles come from the verified context, not the body |

### Alpaca Credentials

| Method                      | Request                            | Response                            | Description                                                        |
| --------------------------- | ---------------------------------- | ----------------------------------- | ------------------------------------------------------------------ |
| `CreateAlpacaCredentials`   | `CreateAlpacaCredentialsRequest`   | `CreateAlpacaCredentialsResponse`   | Store encrypted credentials; response is **write-only** (masked 8-char key prefix, empty secret) |
| `GetAlpacaCredentials`      | `GetAlpacaCredentialsRequest`      | `GetAlpacaCredentialsResponse`      | Fetch by id; response is **write-only** (stored key prefix, empty secret), never decrypted over the wire |
| `ListAlpacaCredentials`     | `ListAlpacaCredentialsRequest`     | `ListAlpacaCredentialsResponse`     | List active credentials (masked key prefix)                        |
| `DeleteAlpacaCredentials`   | `DeleteAlpacaCredentialsRequest`   | `DeleteAlpacaCredentialsResponse`   | Soft-delete (`is_active=False`); refuses with `FAILED_PRECONDITION` while live trading sessions, funded sleeves, or strategy executions still reference the credentials |
| `ValidateAlpacaCredentials` | `ValidateAlpacaCredentialsRequest` | `ValidateAlpacaCredentialsResponse` | Probe Alpaca `get_account()` without persisting; returns account status/buying-power; flags a paper/live mismatch; per-tenant rate limited |

> Credentials are write-only end to end at the auth API: no RPC returns the secret,
> and `Get` returns only the stored key prefix. Services that need the plaintext
> (trading, portfolio) read the encrypted rows from the shared database and decrypt
> with the `llamatrade_common` encryption helpers.

### Alpaca OAuth (HTTP routes, not RPCs)

OAuth is redirect-based, so these live in `routers/oauth.py`, mounted alongside the Connect app:

| Route                                | Auth   | Purpose                                                              |
| ------------------------------------ | ------ | -------------------------------------------------------------------- |
| `POST /oauth/alpaca/start`           | user   | Mint the Alpaca authorize URL for a Settings "connect" (link intent) |
| `GET  /oauth/alpaca/authorize`       | public | Entry for "sign in / sign up with Alpaca" (302 to Alpaca)            |
| `GET  /oauth/alpaca/callback`        | public | Alpaca's redirect target; exchanges the code, then links or authenticates |
| `POST /oauth/alpaca/exchange`        | public | Exchange a one-time login handoff for a session (tokens + user)      |
| `POST /oauth/alpaca/complete-signup` | public | Finish sign-up-with-Alpaca (email + password) and store the connection |

CSRF `state` is a signed short-TTL JWT (`oauth_state.py`, HS256 over `JWT_SECRET`) carrying the
flow intent (`link`/`auth`) and, for a link, the initiating tenant/user. See "Alpaca OAuth Flow"
below.

---

## Data Models

### Pydantic Schemas

`models.py` defines **only** the three Alpaca-credential schemas below. User, tenant, token,
and registration payloads are the auth **proto** messages (`auth_pb2`); there are no
`UserCreate` / `UserResponse` / `TokenResponse` / `RegisterRequest` Pydantic classes, and no
Pydantic password validator (the policy lives in `session.py`, see Security).

```python
# Alpaca Credentials (services/auth/src/models.py)
class AlpacaCredentialsCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=20)
    api_secret: str = Field(..., min_length=40)
    is_paper: bool = True

class AlpacaCredentialsResponse(BaseModel):   # full values on create (in-process only);
    id: UUID                                  # on get: stored key prefix + empty secret
    name: str
    api_key: str
    api_secret: str
    is_paper: bool
    is_active: bool = True
    created_at: datetime

class AlpacaCredentialsListItem(BaseModel):
    id: UUID
    name: str
    api_key_prefix: str  # First 8 characters only (masked)
    is_paper: bool
    is_active: bool
    created_at: datetime
```

The JWT access token carries `sub`, `tenant_id`, `email`, `roles`, `type`, and a unique `jti`
(30-min access / 7-day refresh); tokens are minted by `session.py::mint_access_refresh`.

### Database Models (via llamatrade_db)

| Table                   | Key Fields                                                                                                                                  | Notes                                                       |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `tenants`               | `id`, `name`, `slug`, `settings`                                                                                                            | Multi-tenant parent entity                                  |
| `users`                 | `id`, `tenant_id`, `email`, `password_hash`, `role`, `is_verified`, `avatar_url`                                                            | `tenant_id` FK for isolation; `is_verified` set by `VerifyEmail` |
| `auth_tokens`           | `id`, `tenant_id`, `user_id`, `token_hash`, `purpose`, `expires_at`, `used_at`                                                              | Single-use email tokens; only the SHA-256 is stored (unique index); consumed under a row lock |
| `alpaca_credentials`    | `id`, `tenant_id`, `auth_type`, `api_key_encrypted`, `api_secret_encrypted`, `api_key_prefix`, `access_token_encrypted`, `alpaca_account_id` | Fernet-encrypted; `auth_type` = `api_key` or `oauth`        |
| `api_keys`              | `id`, `tenant_id`, `user_id`, `key_prefix`, `key_hash`, `scopes`, `last_used_at`                                                            | Prefix lookup then constant-time full-key `key_hash` verify |
| `oauth_identities`      | `id`, `tenant_id`, `user_id`, `provider`, `provider_account_id`                                                                             | Unique `(provider, provider_account_id)`; login anchor      |
| `oauth_pending_signups` | `id`, `provider`, `provider_account_id`, encrypted token, `expires_at`                                                                      | Staged sign-up-with-Alpaca ticket                           |

---

## Security

### Password Handling

Passwords are hashed with **bcrypt** (`bcrypt.hashpw` / `bcrypt.checkpw`, offloaded via
`asyncio.to_thread`). The strength policy is `validate_password_strength` in
`src/session.py`: at least 8 characters, with at least one letter and one digit. It raises
`PasswordPolicyError`, mapped to `INVALID_ARGUMENT` (RPCs) or HTTP 400 (OAuth
complete-signup), and applies on register, change-password, reset-password, and
OAuth sign-up. Login burns a bcrypt check against a precomputed dummy hash when the user
lookup misses, so a miss and a wrong password take comparable time (no enumeration
timing oracle).

### JWT Token Configuration

| Parameter         | Value                            | Rationale                                             |
| ----------------- | -------------------------------- | ----------------------------------------------------- |
| Access Token TTL  | 30 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`) | Short-lived to limit exposure if stolen     |
| Refresh Token TTL | 7 days (`REFRESH_TOKEN_EXPIRE_DAYS`)       | Balance between security and UX             |
| Algorithm         | RS256 (HS256 dev fallback)       | Asymmetric so other services verify with the public key only |
| Token Type        | Bearer                           | Standard OAuth 2.0 token type                         |

**Signing key selection** (`llamatrade_common.auth.user_token_signing_key`): user tokens are
signed **RS256** over the `AUTH_JWT_PRIVATE_KEY` / `AUTH_JWT_PUBLIC_KEY` PEM pair when
configured. In production/staging the pair is required: importing `session.py` resolves the
signing key, so the service fails at startup without it, and a half-configured pair (one of
the two vars) is always an error. Without the pair (local dev, tests) tokens fall back to
**HS256** over `JWT_SECRET`. Internal **service tokens** (`mint_service_token`) stay HS256 over
`JWT_SECRET` regardless. Verification pins the algorithm to the configured key material, never
to the token header: with a public key configured, user tokens are accepted only as RS256, and
HS256 is reserved for service tokens (`type=service` + `aud=llamatrade-internal`), so a service
token can never authenticate as a user, and alg-confusion attacks fail.

**JWT Payload Structure:**

```json
{
  "sub": "user-uuid",
  "tenant_id": "tenant-uuid",
  "email": "user@example.com",
  "roles": ["admin"],
  "type": "access",
  "jti": "per-token-hex",
  "iat": 1710000000,
  "exp": 1710001800
}
```

Refresh tokens carry `sub`, `tenant_id`, `type: "refresh"`, `jti`, `iat`, `exp` (no email/roles).

### Token Revocation

`RevocationStore` (Redis) implements two mechanisms, both consulted by the fail-closed
`AuthMiddleware` on every protected request:

- a per-token denylist keyed on `jti` (SETEX until the token's own expiry), and
- a per-user cutoff timestamp: any token whose `iat` predates it is dead.

Revocation writes:

- **Logout** revokes the presented access token's `jti`, and the paired refresh token's `jti`
  when the client supplies it in the `x-refresh-token` header (`LogoutRequest` is empty).
- **RefreshToken** rotates: the presented refresh token is single-use, its `jti` revoked
  before the new pair is minted; a revoked refresh token is rejected.
- **ChangePassword** and **ResetPassword** call `revoke_all_for_user`, killing every session
  issued before the change.

The store fails **open** on a Redis outage (token expiry still bounds exposure) and revocation
is disabled entirely when `REDIS_URL` is unset; `AuthMiddleware` refuses to start in
production/staging without a revocation backend.

### Rate Limiting

`RateLimiter` (`llamatrade_common.ratelimit`) is a Redis fixed-window counter. The auth
service constructs it with `fail_closed=True`: a Redis error **refuses** the request
(`RESOURCE_EXHAUSTED` on RPCs, HTTP 429 on OAuth routes) rather than allowing it, so
brute-force protection cannot be disabled by an outage. When `REDIS_URL` is unset (unit
tests, minimal deploys) there is no limiter at all.

Credential-taking RPCs use **dual buckets**: a per-email bucket that always applies (a
rotated or spoofed source IP cannot lift the per-target-email limit) plus a per-IP bucket
applied only when a trusted client IP is derivable. The client IP is read from a trusted
position in `X-Forwarded-For` (`client_ip.py`): the entry immediately left of the
`TRUSTED_PROXY_HOPS` trailing infrastructure entries (default 1, matching the GCP L7 LB),
because the leftmost hops are attacker-controlled.

| Surface                              | Buckets            | Rules (limit / window)   |
| ------------------------------------ | ------------------ | ------------------------ |
| `Login`                              | per-email + per-IP | 10 / 60s and 30 / 900s   |
| `Register`                           | per-email + per-IP | 5 / 60s and 20 / 3600s   |
| `RequestPasswordReset`               | per-email + per-IP | 5 / 60s and 20 / 3600s   |
| `ResendVerification`                 | per-email + per-IP | 5 / 60s and 20 / 3600s   |
| `ValidateAlpacaCredentials`          | per-tenant         | 10 / 60s                 |
| `POST /oauth/alpaca/exchange`        | per-IP             | 10 / 60s and 30 / 900s   |
| `POST /oauth/alpaca/complete-signup` | per-IP             | 5 / 60s and 20 / 3600s   |

A `Login` rate-limit trip additionally notifies the real account owner (`ACCOUNT_LOCKED`
notification, deduped per hour; a lockout on a nonexistent email notifies nobody).

### Single-Use Email Tokens (auth_tokens)

`services/tokens.py` backs the four public recovery/verification RPCs:

- **Issue** (`issue_token`): a `secrets.token_urlsafe(32)` value whose **SHA-256 only** is
  stored in `auth_tokens` with a purpose (`password_reset`, TTL 1 hour; `email_verify`,
  TTL 7 days). Issuing marks every earlier unused token for the same user + purpose as used,
  so reissue invalidates prior links.
- **Consume** (`consume_token`): the row is selected `FOR UPDATE`, checked for expiry and
  prior use, and `used_at` is set under the lock, so a token can never redeem twice.
- **Links**: built as `{APP_BASE_URL}/reset-password?token=…` or
  `{APP_BASE_URL}/verify-email?token=…` and carried to the notification service in
  `event.extra["link"]`. The links point at the SPA, which calls the corresponding RPC.

### Alpaca Credential Encryption

Broker credentials are encrypted at rest via `llamatrade_common.utils`
(`async_encrypt_value` / `async_decrypt_value`), which use **Fernet** (AES-128-CBC +
HMAC-SHA256) with a key derived from `ENCRYPTION_KEY` via PBKDF2-HMAC-SHA256.

**Security Properties:**

- **Fernet (AES-128-CBC + HMAC)**: authenticated encryption (confidentiality + integrity).
- **Key derivation**: PBKDF2-HMAC-SHA256 from `ENCRYPTION_KEY` with a random per-value salt;
  each ciphertext is a base64 envelope of `salt || fernet_token`. One global `ENCRYPTION_KEY`
  protects every tenant's credentials; a KMS / envelope scheme with key rotation is a future
  enhancement.
- **Write-only responses**: `Create`/`Get` RPCs return a masked 8-char key prefix and an empty
  secret; `List` returns only the stored prefix. Decryption failures are recorded as a metric.
- **Deletion guard**: `DeleteAlpacaCredentials` raises `CredentialsInUseError`
  (`FAILED_PRECONDITION`) while live trading sessions, funded ledger sleeves, or strategy
  executions still reference the credential set, naming each blocker.

### RBAC Roles

| Role     | Permissions                           | Use Case                      |
| -------- | ------------------------------------- | ----------------------------- |
| `admin`  | Full access to tenant resources       | Account owner, manages users  |
| `trader` | Create/run strategies, view portfolio | Day-to-day trading operations |
| `viewer` | Read-only access                      | Auditors, observers           |
| `api`    | Programmatic access, scope-limited    | External integrations         |

`register` assigns the first user `role="admin"`. No RPC currently promotes a user to
`trader`/`viewer`, so those roles are defined in `check_permission` but not yet assignable.
`check_permission` is advisory and reads roles from the verified context.

### Alpaca OAuth Flow

`state` (signed JWT, `oauth_state.py`, 10-minute TTL) carries the flow `intent`; the
authorization `code` is exchanged **server-side** (`llamatrade_alpaca.exchange_code`), and no
session JWT is ever placed in a URL.

- **Link** (`POST /oauth/alpaca/start`, authenticated → `GET /callback`): stores an OAuth
  `alpaca_credentials` row (encrypted bearer token, `auth_type="oauth"`, `alpaca_account_id`) and an
  `oauth_identities` row for the caller's tenant/user; redirects to `/settings?tab=broker&connected=1`.
  Re-linking an Alpaca account already owned by another user is rejected (409).
- **Sign-in** (`GET /authorize?intent=auth` → `GET /callback`): if the Alpaca `account_id` maps to an
  existing `oauth_identities` row, mint a one-time **handoff** (signed JWT, 120s TTL); the browser
  posts it to `POST /oauth/alpaca/exchange`, where it is consumed exactly once (Redis `SET NX`)
  before a session is issued.
- **Sign-up** (no identity match): stage an `oauth_pending_signups` ticket; the browser completes at
  `POST /oauth/alpaca/complete-signup` (email + password, same password policy), which atomically
  claims the single-use ticket and creates the tenant/user, the OAuth credential, and the identity.

### Tenant Isolation

- **Fail-closed edge**: `AuthMiddleware` verifies the bearer token (RS256-pinned for user
  tokens), checks revocation, and stashes the principal (`current_context()`). The public
  RPC suffixes are `/Login`, `/Register`, `/RefreshToken`, `/RequestPasswordReset`,
  `/ResetPassword`, `/VerifyEmail`, `/ResendVerification`, plus the four OAuth entry/return
  routes (`/oauth/alpaca/authorize`, `/callback`, `/exchange`, `/complete-signup`);
  `/oauth/alpaca/start` stays protected so the linking tenant/user is known. `/health*`,
  `/metrics`, `/docs`, `/openapi.json`, and CORS preflight are public paths.
- **Identity authority**: auth legitimately operates pre-tenant (login by email) and cross-tenant (S2S
  lookups), so its DB session runs with the RLS **system bypass** (`set_rls_bypass`). Per-request
  scoping is enforced in the app layer: `get_user`/`get_tenant` return `NOT_FOUND` for an id outside
  the caller's tenant (so cross-tenant existence is not leaked) unless the caller is a service token;
  `check_permission` authorizes off the verified roles, not the body; user RPCs reject service
  principals (`_authenticated_principal` requires a user token).

---

## Notifications

Auth publishes security notifications onto the `lt.notifications` Kafka stream via
`shared_notification_events().publish_safe` (`llamatrade_events`). Publishing is
fire-and-forget: it never raises into the auth path, has a 5-second ceiling, and events carry
a deterministic id derived from category + tenant + dedup parts, so retries and repeats
collapse. Links, where present, travel in `event.extra["link"]`.

| Category                                   | Trigger                                                                | Link |
| ------------------------------------------ | ---------------------------------------------------------------------- | ---- |
| `NOTIFICATION_CATEGORY_WELCOME`            | Successful `Register`                                                  | no   |
| `NOTIFICATION_CATEGORY_EMAIL_VERIFICATION` | `Register` (initial verification email)                                | yes  |
| `NOTIFICATION_CATEGORY_EMAIL_VERIFICATION` | `ResendVerification` (active, unverified accounts only)                | yes  |
| `NOTIFICATION_CATEGORY_PASSWORD_RESET`     | `RequestPasswordReset` (existing active accounts only)                 | yes  |
| `NOTIFICATION_CATEGORY_PASSWORD_CHANGED`   | `ChangePassword`                                                       | no   |
| `NOTIFICATION_CATEGORY_PASSWORD_CHANGED`   | `ResetPassword` redemption                                             | no   |
| `NOTIFICATION_CATEGORY_ACCOUNT_LOCKED`     | `Login` rate-limit trip for a real account (deduped per hour)          | no   |

---

## Configuration

### Environment Variables

| Variable                       | Required            | Default                           | Description                                                    |
| ------------------------------ | ------------------- | --------------------------------- | -------------------------------------------------------------- |
| `DATABASE_URL`                 | Yes                 | -                                 | PostgreSQL connection string                                   |
| `ENVIRONMENT`                  | No                  | `development`                     | `production`/`staging` make secrets, the RS256 pair, and the RLS check fail-closed |
| `AUTH_JWT_PRIVATE_KEY`         | Prod/staging        | -                                 | RS256 PEM private key for user-token signing (set with the public key) |
| `AUTH_JWT_PUBLIC_KEY`          | Prod/staging        | -                                 | RS256 PEM public key for user-token verification               |
| `JWT_SECRET`                   | Yes                 | `dev-secret-change-in-production` | HS256 secret: dev fallback for user tokens; always signs service tokens and OAuth `state` |
| `ENCRYPTION_KEY`               | Yes                 | `default-dev-key-change-me`       | Fernet key material (PBKDF2 → AES-128-CBC + HMAC)              |
| `REDIS_URL`                    | Recommended         | -                                 | Backs revocation, rate limits, and one-time OAuth handoffs; those features are off when unset |
| `KAFKA_BOOTSTRAP_SERVERS`      | For notifications   | `localhost:9092`                  | Kafka brokers for the `lt.notifications` stream                |
| `APP_BASE_URL`                 | No                  | `http://localhost:8800`           | Base URL for reset/verification links in emails               |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | No                  | `30`                              | Access token TTL                                               |
| `REFRESH_TOKEN_EXPIRE_DAYS`    | No                  | `7`                               | Refresh token TTL                                              |
| `TRUSTED_PROXY_HOPS`           | No                  | `1`                               | Trailing `X-Forwarded-For` entries appended by trusted infrastructure |
| `CORS_ORIGINS`                 | No                  | localhost origins                 | Allowed CORS origins                                           |
| `WEB_APP_URL`                  | No                  | `http://localhost:8800`           | Web app base for OAuth redirects                               |
| `ALPACA_OAUTH_CLIENT_ID`       | For OAuth           | -                                 | Alpaca OAuth app client id                                     |
| `ALPACA_OAUTH_CLIENT_SECRET`   | For OAuth           | -                                 | Alpaca OAuth app client secret (server-side exchange)          |
| `ALPACA_OAUTH_REDIRECT_URI`    | For OAuth           | -                                 | Public auth callback URL                                       |
| `ALPACA_OAUTH_SCOPE`           | No                  | `trading`                         | Requested OAuth scope                                          |

`JWT_SECRET` and `ENCRYPTION_KEY` are resolved via `llamatrade_common.utils.require_secret`,
which is **fail-closed**: when `ENVIRONMENT` is `production` or `staging`, an unset secret
raises at startup rather than falling back to the development default. The RS256 pair follows
the same posture, and configuring only one of the two key vars is an error in any environment.

### Port Assignment

| Service | Port |
| ------- | ---- |
| Auth    | 8810 |

The port is fixed in the Dockerfile (`uvicorn --port 8810`); there is no port env var.

---

## Health Check

`HealthChecker` (`llamatrade_common.health`) provides three endpoints:

- `GET /health`: full check; 503 when a critical dependency is unhealthy, 200 (`degraded`)
  when only non-critical checks fail.
- `GET /health/live`: liveness probe, always 200.
- `GET /health/ready`: readiness probe; 503 + `not_ready` when a critical check fails.

Registered checks: **database** (critical, cached engine connectivity probe) and **redis**
(non-critical; reported healthy when `REDIS_URL` is unset, since auth runs without it).

```http
GET /health
```

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2026-07-31T00:00:00Z",
  "service": "auth",
  "version": "0.1.0",
  "checks": {
    "database": { "healthy": true, "latency_ms": 1.2, "critical": true },
    "redis": { "healthy": true, "latency_ms": 0.4, "critical": false }
  }
}
```

---

## Internal Service Connections

### Who Calls Auth Service

| Service          | Methods Used                                                       | Purpose                                   |
| ---------------- | ------------------------------------------------------------------ | ----------------------------------------- |
| **Web Frontend** | `Login`, `Register`, `Logout`, `RefreshToken`, recovery/verification RPCs, Alpaca OAuth routes | User authentication and account lifecycle |
| **Web Frontend** | `CreateAlpacaCredentials`, `ListAlpacaCredentials`, `DeleteAlpacaCredentials`, `ValidateAlpacaCredentials` | Broker credential management (write-only) |
| **All Services** | `ValidateToken`, `GetUser`, `GetTenant` (service tokens)           | Verify requests, resolve identities       |

Trading and portfolio do not fetch broker secrets through auth RPCs; they read the
Fernet-encrypted `alpaca_credentials` rows from the shared database and decrypt them with
the shared `ENCRYPTION_KEY` helpers.

### What Auth Service Calls

| Target             | Purpose                                                          |
| ------------------ | ---------------------------------------------------------------- |
| **PostgreSQL**     | User/tenant/credential/auth-token storage                        |
| **Redis**          | Rate-limit counters, token revocation, one-time OAuth handoffs   |
| **Kafka**          | `lt.notifications` stream (security notification emails)         |
| **Alpaca**         | Credential validation probe; OAuth code exchange + account lookup (via `llamatrade_alpaca`) |

---

## Complete Data Flow Example

### User Registration Flow

```
1. User submits registration form
   - tenant_name: "Acme Trading"
   - email: "alice@acme.com"
   - password: "SecurePass123"

2. Auth Service receives RegisterRequest
   └─> Rate limit: per-email always, per-IP when derivable (5/60s, 20/3600s)
   └─> Validates password strength (8+ chars, at least one letter and one digit)
   └─> Checks email doesn't already exist

3. create_tenant_and_user (session.py)
   └─> Creates tenant with slug "acme-trading-<8 hex chars>"
   └─> Hashes password with bcrypt (offloaded to a thread)
   └─> INSERT INTO users (tenant_id = new tenant, role = "admin")

4. Notifications
   └─> WELCOME event published
   └─> Email-verify token issued into auth_tokens (sha256 only)
   └─> EMAIL_VERIFICATION event published with the /verify-email link

5. Return RegisterResponse
   └─> user: { id, tenant_id, email, roles: ["admin"], ... }
   └─> tenant: { id, name, is_active, ... }
   └─> No tokens are returned; the client signs in via Login
```

### Login Flow

```
1. User submits login form
   - email: "alice@acme.com"
   - password: "SecurePass123"

2. Auth Service receives LoginRequest
   └─> Rate limit: per-email always, per-IP when derivable (10/60s, 30/900s)
   └─> On a trip: ACCOUNT_LOCKED notification to the real owner, then RESOURCE_EXHAUSTED

3. Verify password
   └─> User lookup by email; on a miss, a dummy bcrypt check runs (timing pad)
   └─> bcrypt.checkpw(password, stored_hash) in a thread
   └─> If mismatch: UNAUTHENTICATED error

4. Check user status
   └─> is_active must be True; if inactive: PERMISSION_DENIED error
   └─> last_login updated

5. Generate JWT tokens (mint_access_refresh)
   └─> Access token (30 min) with { sub, tenant_id, email, roles, type, jti }
   └─> Refresh token (7 days) with { sub, tenant_id, type: "refresh", jti }

6. Return LoginResponse
   └─> access_token, refresh_token, both expiry timestamps, user
```

### Adding Alpaca Credentials

```
1. Authenticated user calls CreateAlpacaCredentials
   - name: "Paper Trading"
   - api_key: "PK..."
   - api_secret: "..."
   - is_paper: true

2. Resolve identity from the verified token
   └─> tenant_id from the JWT (AuthMiddleware / current_context)

3. TenantService.create_alpaca_credentials()
   └─> async_encrypt_value(api_key) -> api_key_encrypted
   └─> async_encrypt_value(api_secret) -> api_secret_encrypted
   └─> api_key_prefix stored (first 8 chars) for later display
   └─> INSERT INTO alpaca_credentials (tenant_id, ...)

4. Return a write-only response
   - id, name, api_key = masked 8-char prefix, api_secret = "", is_paper
   - The full key/secret is never returned to the client (create or get)

5. LIST requests show the stored api_key_prefix
   - "PK1A2B3C" (first 8 chars only)
```

---

## Error Handling

### Connect/gRPC Error Codes

| Error                 | Code | When Raised                                                    |
| --------------------- | ---- | -------------------------------------------------------------- |
| `UNAUTHENTICATED`     | 16   | Invalid/expired/revoked token, wrong password                  |
| `PERMISSION_DENIED`   | 7    | Inactive account, user lacks required role/permission          |
| `INVALID_ARGUMENT`    | 3    | Password policy failure, invalid/expired reset or verification link, wrong current password |
| `ALREADY_EXISTS`      | 6    | Email already registered                                       |
| `NOT_FOUND`           | 5    | User/tenant/credentials not found (also masks cross-tenant ids) |
| `RESOURCE_EXHAUSTED`  | 8    | Rate limit tripped (or the limiter backend is down: fail-closed) |
| `FAILED_PRECONDITION` | 9    | Credential deletion refused while dependents exist             |
| `UNAVAILABLE`         | 14   | Alpaca unreachable during credential validation                |
| `INTERNAL`            | 13   | Database errors, encryption failures                           |

### Error Response Example

```python
raise ConnectError(
    Code.UNAUTHENTICATED,
    "Invalid email or password"
)

# Client receives:
# {
#   "code": "unauthenticated",
#   "message": "Invalid email or password"
# }
```

---

## Testing

### Test Structure

```
tests/
├── __init__.py
├── conftest.py                        # In-memory notification stream fixture (autouse)
├── test_auth_tokens_pg.py             # auth_tokens semantics over real Postgres: single-use, expiry, invalidation
├── test_client_ip.py                  # Trusted-position client-IP derivation from X-Forwarded-For
├── test_credential_deletion_guard.py  # Deletion refusal with live dependents (real SQL over SQLite schema)
├── test_grpc_auth.py                  # AuthServicer RPC tests (no HTTP layer)
├── test_health.py                     # /health, /health/live, /health/ready
├── test_oauth_router.py               # OAuth start URL, callback guards, exchange, complete-signup
├── test_oauth_state.py                # Signed OAuth state mint/verify
├── test_session.py                    # Token mint, user shape, handoff, tenant/user creation
└── test_tenant_service.py             # TenantService credential CRUD + encryption
```

### Running Tests

```bash
# Run all auth tests
cd services/auth && pytest

# Run with coverage
cd services/auth && pytest --cov=src --cov-report=term-missing

# Run specific test file
cd services/auth && pytest tests/test_grpc_auth.py -v
```

### Key Test Scenarios

- **Login**: Valid credentials, wrong password, inactive user, non-existent email, rate limiting
- **Registration**: Valid data, duplicate email, weak password, notification emissions
- **Token refresh**: Valid refresh token, expired token, invalid token, revoked token, rotation
- **Email tokens**: Single-use consumption, expiry, reissue invalidation (real Postgres)
- **Alpaca credentials**: Create, list (masked), get (prefix only), delete, in-use refusal, tenant isolation
- **OAuth**: State/handoff verification, single-use tickets, callback guards
- **RBAC**: Admin permissions, trader permissions, viewer restrictions

---

## Capabilities

### Authentication & Tokens

- User registration (create tenant + first admin user) with welcome + verification emails
- User login (email/password) with bcrypt verification, timing-safe misses, and fail-closed rate limits
- JWT access (30-min) + refresh (7-day) tokens, RS256-signed in production; refresh rotation; token validation
- Logout with server-side revocation of the access and refresh token jtis
- Change password (current-password verification; all prior sessions revoked)
- Password reset and email verification via single-use hashed tokens
- Sign in / sign up / connect with **Alpaca OAuth** (link, login, complete-signup)

### User & Tenant

- Get current user profile + tenant (from the token)
- Get a user / tenant by id, tenant-scoped (service tokens may cross tenants)
- Tenant creation with slug generation
- Multi-tenant isolation via the verified token + Postgres RLS

### Credentials & API Keys

- Alpaca credential CRUD (create / get / list / soft-delete), Fernet-encrypted, write-only responses, in-use deletion guard
- Validate Alpaca credentials against the broker (`ValidateAlpacaCredentials`), with paper/live mismatch detection
- API-key validation (`ValidateAPIKey`)
- RBAC permission check (`CheckPermission`, roles from the verified context)

## Planned / Not implemented

- **User/tenant management RPCs**: no update/list/delete users, no tenant-settings update, no API-key create/list/delete.
- **Non-Alpaca social login** (e.g. Google/GitHub).
- **KMS / envelope encryption and key rotation** for credentials (currently one global `ENCRYPTION_KEY` with per-value salts).

---

## Startup / Shutdown Sequence

### Startup

```
1. FastAPI app created with lifespan handler
2. lifespan.__aenter__():
   └─> verify_rls_enforcement() - assert the DB role cannot bypass RLS
       (raises in production/staging, warns in development)
   └─> Load AuthServiceASGIApplication from proto-generated code
       (import failure fails startup rather than silently serving no RPCs)
   └─> Create AuthServicer instance (rate limiter + revocation store when Redis is configured)
   └─> Mount Connect app at root path
3. AuthMiddleware added before CORS (CORS stays outermost for preflight + headers on 401s)
4. init_telemetry: /metrics with DB connection-pool stats
5. OAuth router + health router included
6. Service ready to accept requests
```

Importing `session.py` resolves the user-token signing key, so a production/staging
deployment without the RS256 keypair fails here rather than serving HS256 tokens.

### Shutdown

```
1. lifespan.__aexit__():
   └─> close_db() - Dispose SQLAlchemy engine
2. Graceful connection draining
```

---

## Summary

The Auth Service is the security foundation of LlamaTrade, handling user authentication, multi-tenant isolation, account recovery, and broker credential management. It signs user JWTs with RS256 in production (HS256 only as a zero-config dev fallback), enforces server-side revocation (logout, refresh rotation, password change), applies fail-closed dual-bucket rate limits to credential-taking endpoints, and drives email verification and password reset through single-use sha256-hashed tokens consumed under a row lock. Alpaca API credentials are Fernet-encrypted at rest and write-only at the API boundary.

It exposes 20 RPC methods over the Connect protocol plus five Alpaca OAuth HTTP routes, and publishes security notifications (welcome, verification, reset, password changed, lockout) onto the `lt.notifications` stream.

Identity is derived from the verified token (`current_context` / `resolve_identity`) with app-layer cross-tenant guards; the auth DB session runs with the RLS system bypass because auth is the platform's pre-/cross-tenant identity authority.
