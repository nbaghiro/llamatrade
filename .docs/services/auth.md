# Auth Service

## Overview

The Auth Service is the security backbone of LlamaTrade, responsible for authenticating users, managing multi-tenant isolation, and securely storing broker credentials. Every request to the platform flows through authentication, making this service critical for both security and user experience.

**Why This Service Matters:**

- **Multi-Tenancy Foundation**: In a SaaS platform, tenant isolation is non-negotiable. The Auth Service ensures that traders can never access each other's strategies, portfolios, or credentials—even if there's a bug elsewhere in the system.
- **Broker Credential Security**: Traders entrust LlamaTrade with their Alpaca API keys. These credentials could drain their brokerage accounts if compromised, so we encrypt them at rest with Fernet (AES-128-CBC + HMAC) and never return raw secrets to the client — create/get responses are write-only (masked key prefix, empty secret).
- **Stateless Scaling**: JWT-based authentication allows the platform to scale horizontally without session state, critical for handling market open spikes when thousands of strategies may trigger simultaneously.

**Core Responsibilities:**

- User registration and authentication (login/logout)
- JWT access and refresh token management
- Multi-tenant isolation (tenant_id propagation)
- Role-based access control (RBAC)
- Encrypted Alpaca broker credential storage (+ Alpaca OAuth link / sign-in)
- API-key validation for programmatic access

---

## Architecture Overview

```
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                                      FastAPI :8810                                       ║
╠══════════════════════════════════════════════════════════════════════════════════════════╣
║ Connect / gRPC ASGI app  ·  browser-compatible  ·  CORS  ·  tenant_id ctx                ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝
                                              │
                                              ▼
╭──────────────────────────────────────────────────────────────────────────────────────────╮
│                                 AuthServicer  ·  16 RPCs                                 │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Auth · Login · Register · Logout · ChangePassword                                        │
│ Token · RefreshToken · ValidateToken · ValidateAPIKey                                    │
│ User · GetCurrentUser · GetUser · GetTenant                                              │
│ RBAC · CheckPermission                                                                   │
│ Alpaca creds · Create · Get · List · Delete · Validate                                   │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ + Alpaca OAuth (HTTP routes, routers/oauth.py — not RPCs):                                │
│   /start · /authorize · /callback · /exchange · /complete-signup                         │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
                                              │
                                              ▼
                  ╭──────────────────╮  ╭─────────────────────╮  ╭────────────────────╮
                  │   session.py     │  │   TenantService     │  │  routers/oauth.py  │
                  ├──────────────────┤  ├─────────────────────┤  ├────────────────────┤
                  │ mint_access_     │  │ Alpaca creds:       │  │ Alpaca OAuth       │
                  │  refresh         │  │  create/get/list/   │  │  link + sign-in    │
                  │ create_tenant_   │  │  delete (Fernet     │  │ oauth_state.py:    │
                  │  and_user        │  │  encrypt at rest)   │  │  signed-JWT state  │
                  ╰──────────────────╯  ╰─────────────────────╯  ╰────────────────────╯
                                              │
                                              ▼
╭──────────────────────────────────────────────────────────────────────────────────────────╮
│                               Security · llamatrade_common                               │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ encrypt_value / decrypt_value  (Fernet: AES-128-CBC + HMAC, PBKDF2 key)                  │
│ bcrypt password hashing  ·  JWT sign / verify (HS256)                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
                                              │
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                        PostgreSQL                                        │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ tenants · users · api_keys · oauth_identities · oauth_pending_signups                    │
│ alpaca_credentials  (Fernet-encrypted; api_key/secret or OAuth bearer token)             │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### JWT Token Flow

```
╭────────────╮          ╭────────────────╮          ╭────────────────╮
│   Client   │          │   Auth :8810   │          │ Other services │
├────────────┤          ├────────────────┤          ├────────────────┤
│ browser    │          │ bcrypt · JWT   │          │ validate       │
╰────────────╯          │ HS256 signing  │          │ every request  │
                        ╰────────────────╯          ╰────────────────╯
       │                         │                           │
       │   1 login (email, pw)   │                           │
       ├─────────────────────────►                           │
       │                         ├─ 2 verify pw (bcrypt)     │
       │   3 access + refresh    │                           │
       ◄─────────────────────────┤                           │
       │                         │                           │
       │            4 API request + Bearer token             │
       ├─────────────────────────────────────────────────────►
       │                   5 validate (JWT decode + verify) ─┤
       │                     6 response                      │
       ◄─────────────────────────────────────────────────────┤
       │                         │                           │
 8 refresh (after 30-min access expiry)                      │
       ├─────────────────────────►                           │
       │      9 new tokens       │                           │
       ◄─────────────────────────┤                           │
       │                         │                           │
```

---

## Directory Structure

```
services/auth/
├── src/
│   ├── main.py                 # FastAPI app, Connect mount, OAuth router, health check
│   ├── models.py               # Pydantic schemas — only the 3 Alpaca-credential schemas
│   ├── session.py              # Shared token mint + create_tenant_and_user + OAuth handoff
│   ├── oauth_state.py          # Signed-JWT CSRF state for the OAuth redirect
│   ├── grpc/
│   │   └── servicer.py         # AuthServicer - 16 RPC methods
│   ├── routers/
│   │   └── oauth.py            # Alpaca OAuth 2.0 HTTP routes (browser redirects)
│   └── services/
│       └── tenant_service.py   # Alpaca credential CRUD + encryption
├── tests/
├── pyproject.toml
└── Dockerfile
```

There is **no** `user_service.py`, `api_key_service.py`, or `database.py`; user/tenant reads
and token mint live directly in the servicer and `session.py`.

---

## Core Components

| Component         | File                          | Purpose                                              |
| ----------------- | ----------------------------- | ---------------------------------------------------- |
| **AuthServicer**  | `grpc/servicer.py`            | Connect servicer, implements 16 RPC methods          |
| **TenantService** | `services/tenant_service.py`  | Alpaca credential CRUD + Fernet encryption           |
| **session helpers** | `session.py`                | Token mint (`mint_access_refresh`), `create_tenant_and_user`, OAuth handoff |
| **OAuth router**  | `routers/oauth.py`            | Alpaca OAuth 2.0 link + sign-in/sign-up (HTTP routes) |

---

## RPC Endpoints (16 Connect RPCs)

### Authentication

| Method           | Request                 | Response                 | Description                                          |
| ---------------- | ----------------------- | ------------------------ | ---------------------------------------------------- |
| `Login`          | `LoginRequest`          | `LoginResponse`          | Authenticate with email/password, returns JWT tokens |
| `Register`       | `RegisterRequest`       | `RegisterResponse`       | Create a new tenant and its first (admin) user       |
| `Logout`         | `LogoutRequest`         | `LogoutResponse`         | Decode the token and return success — no server-side revocation (see Known gaps) |
| `ChangePassword` | `ChangePasswordRequest` | `ChangePasswordResponse` | Update password with current-password verification   |

### Token Management

| Method           | Request                 | Response                 | Description                                              |
| ---------------- | ----------------------- | ------------------------ | ------------------------------------------------------- |
| `RefreshToken`   | `RefreshTokenRequest`   | `RefreshTokenResponse`   | Exchange a refresh token for new access + refresh tokens |
| `ValidateToken`  | `ValidateTokenRequest`  | `ValidateTokenResponse`  | Verify a JWT and extract claims                          |
| `ValidateAPIKey` | `ValidateAPIKeyRequest` | `ValidateAPIKeyResponse` | Validate an API key: prefix lookup, then constant-time full-key hash verify, then active/expiry/scopes |

### User / Tenant

| Method           | Request                 | Response                 | Description                                                     |
| ---------------- | ----------------------- | ------------------------ | -------------------------------------------------------------- |
| `GetCurrentUser` | `GetCurrentUserRequest` | `GetCurrentUserResponse` | Authenticated user's profile + tenant (resolved from the token) |
| `GetUser`        | `GetUserRequest`        | `GetUserResponse`        | Get a user by id (tenant-scoped; service tokens may cross tenants) |
| `GetTenant`      | `GetTenantRequest`      | `GetTenantResponse`      | Get a tenant by id (tenant-scoped; service tokens may cross tenants) |

### RBAC / Permissions

| Method            | Request                  | Response                  | Description                                                          |
| ----------------- | ------------------------ | ------------------------- | ------------------------------------------------------------------- |
| `CheckPermission` | `CheckPermissionRequest` | `CheckPermissionResponse` | Advisory role→resource/action check; roles come from the verified context, not the body |

### Alpaca Credentials

| Method                      | Request                            | Response                            | Description                                                        |
| --------------------------- | ---------------------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| `CreateAlpacaCredentials`   | `CreateAlpacaCredentialsRequest`   | `CreateAlpacaCredentialsResponse`   | Store encrypted credentials; response is **write-only** (masked 8-char key prefix, empty secret) |
| `GetAlpacaCredentials`      | `GetAlpacaCredentialsRequest`      | `GetAlpacaCredentialsResponse`      | Fetch by id; response is **write-only** (masked prefix, empty secret) — not decrypted over the wire |
| `ListAlpacaCredentials`     | `ListAlpacaCredentialsRequest`     | `ListAlpacaCredentialsResponse`     | List active credentials (masked key prefix)                       |
| `DeleteAlpacaCredentials`   | `DeleteAlpacaCredentialsRequest`   | `DeleteAlpacaCredentialsResponse`   | Soft-delete (`is_active=False`)                                    |
| `ValidateAlpacaCredentials` | `ValidateAlpacaCredentialsRequest` | `ValidateAlpacaCredentialsResponse` | Probe Alpaca `get_account()` without persisting; returns account status/buying-power; flags a paper/live mismatch |

> The full key/secret is decrypted only **service-side** (via `TenantService`) for S2S callers
> such as trading and market-data. It is never returned to the browser.

### Alpaca OAuth (HTTP routes, not RPCs)

OAuth is redirect-based, so these live in `routers/oauth.py`, mounted alongside the Connect app:

| Route                                | Auth   | Purpose                                                              |
| ------------------------------------ | ------ | ------------------------------------------------------------------- |
| `POST /oauth/alpaca/start`           | user   | Mint the Alpaca authorize URL for a Settings "connect" (link intent) |
| `GET  /oauth/alpaca/authorize`       | public | Entry for "sign in / sign up with Alpaca" (302 to Alpaca)            |
| `GET  /oauth/alpaca/callback`        | public | Alpaca's redirect target; exchanges the code, then links or authenticates |
| `POST /oauth/alpaca/exchange`        | public | Exchange a one-time login handoff for a session (tokens + user)     |
| `POST /oauth/alpaca/complete-signup` | public | Finish sign-up-with-Alpaca (email + password) and store the connection |

CSRF `state` is a signed short-TTL JWT (`oauth_state.py`, HS256 over `JWT_SECRET`) carrying the
flow intent (`link`/`auth`) and, for a link, the initiating tenant/user. There is no Redis. See
"Alpaca OAuth Flow" below.

---

## Data Models

### Pydantic Schemas

`models.py` defines **only** the three Alpaca-credential schemas below. User, tenant, token,
and registration payloads are the auth **proto** messages (`auth_pb2`) — there are no
`UserCreate` / `UserResponse` / `TokenResponse` / `RegisterRequest` Pydantic classes, and no
Pydantic password validator.

```python
# Alpaca Credentials (services/auth/src/models.py)
class AlpacaCredentialsCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=20)
    api_secret: str = Field(..., min_length=40)
    is_paper: bool = True

class AlpacaCredentialsResponse(BaseModel):   # decrypted values — service-side/S2S use only
    id: UUID
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

The JWT access token carries `sub`, `tenant_id`, `email`, `roles`, and `type` (30-min access /
7-day refresh); tokens are minted by `session.py::mint_access_refresh`.

### Database Models (via llamatrade_db)

| Table                   | Key Fields                                                                                                                | Notes                                                    |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| `tenants`               | `id`, `name`, `slug`, `settings`                                                                                          | Multi-tenant parent entity                               |
| `users`                 | `id`, `tenant_id`, `email`, `password_hash`, `role`, `avatar_url`                                                          | `tenant_id` FK for isolation; `password_hash` NOT NULL   |
| `alpaca_credentials`    | `id`, `tenant_id`, `auth_type`, `api_key_encrypted`, `api_secret_encrypted`, `access_token_encrypted`, `alpaca_account_id` | Fernet-encrypted; `auth_type` = `api_key` or `oauth`     |
| `api_keys`              | `id`, `tenant_id`, `user_id`, `key_prefix`, `key_hash`, `scopes`, `last_used_at`                                           | Prefix lookup then constant-time full-key `key_hash` verify |
| `oauth_identities`      | `id`, `tenant_id`, `user_id`, `provider`, `provider_account_id`                                                            | Unique `(provider, provider_account_id)`; login anchor   |
| `oauth_pending_signups` | `id`, `provider`, `provider_account_id`, encrypted token, `expires_at`                                                     | Staged sign-up-with-Alpaca ticket                        |

---

## Security

### Password Handling

Passwords are hashed with **bcrypt** (`bcrypt.hashpw` / `bcrypt.checkpw`) on register, login,
and change-password. `register` and `change_password` enforce a minimum strength via
`_validate_password_strength` (≥8 characters and at least one letter and one digit), raising
`INVALID_ARGUMENT` otherwise; the check lives in the servicer, not a Pydantic validator.

### JWT Token Configuration

| Parameter         | Value      | Rationale                                      |
| ----------------- | ---------- | ---------------------------------------------- |
| Access Token TTL  | 30 minutes | Short-lived to limit exposure if stolen        |
| Refresh Token TTL | 7 days     | Balance between security and UX                |
| Algorithm         | HS256      | Symmetric, suitable for single-service signing |
| Token Type        | Bearer     | Standard OAuth 2.0 token type                  |

**JWT Payload Structure:**

```json
{
  "sub": "user-uuid",
  "tenant_id": "tenant-uuid",
  "email": "user@example.com",
  "role": "admin",
  "type": "access", // or "refresh"
  "exp": 1710000000,
  "iat": 1709998200
}
```

### Alpaca Credential Encryption

Broker credentials are encrypted at rest via `llamatrade_common.utils.encrypt_value` /
`decrypt_value`, which use **Fernet** (AES-128-CBC + HMAC-SHA256) with a key derived from
`ENCRYPTION_KEY` via PBKDF2-HMAC-SHA256.

```python
from llamatrade_common.utils import encrypt_value, decrypt_value

# On store (TenantService.create_alpaca_credentials)
api_key_encrypted = encrypt_value(data.api_key)
api_secret_encrypted = encrypt_value(data.api_secret)

# On S2S retrieve (TenantService.get_alpaca_credentials) — service-side only
api_key = decrypt_value(creds.api_key_encrypted)
api_secret = decrypt_value(creds.api_secret_encrypted)
```

**Security Properties:**

- **Fernet (AES-128-CBC + HMAC)**: authenticated encryption (confidentiality + integrity).
- **Key derivation**: PBKDF2-HMAC-SHA256 from `ENCRYPTION_KEY` with a **random per-value salt**;
  each ciphertext is a base64 envelope of `salt || fernet_token`, so every value carries its own
  salt. One global `ENCRYPTION_KEY` protects every tenant's credentials — a KMS / envelope scheme
  with key rotation is a future enhancement.
- **Write-only responses**: `Create`/`Get` RPCs return a masked 8-char key prefix and an empty
  secret; `List` returns only the prefix. The decrypted secret leaves the service only over S2S.

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

`state` (signed JWT, `oauth_state.py`) carries the flow `intent`; the authorization `code` is
exchanged **server-side** (`llamatrade_alpaca.exchange_code`), and no JWT is ever placed in a URL.

- **Link** (`POST /oauth/alpaca/start`, authenticated → `GET /callback`): stores an OAuth
  `alpaca_credentials` row (encrypted bearer token, `auth_type="oauth"`, `alpaca_account_id`) and an
  `oauth_identities` row for the caller's tenant/user; redirects to `/settings?tab=broker&connected=1`.
  Re-linking an Alpaca account already owned by another user is rejected (409).
- **Sign-in** (`GET /authorize?intent=auth` → `GET /callback`): if the Alpaca `account_id` maps to an
  existing `oauth_identities` row, mint a one-time **handoff** (signed JWT); the browser posts it to
  `POST /oauth/alpaca/exchange` for a real session.
- **Sign-up** (no identity match): stage an `oauth_pending_signups` ticket; the browser completes at
  `POST /oauth/alpaca/complete-signup` (email + password), which creates the tenant/user, the OAuth
  credential, and the identity.

### Tenant Isolation

- **Fail-closed edge**: `AuthMiddleware` verifies the bearer token and stashes the principal
  (`current_context()`); `Login`/`Register`/`RefreshToken` and the OAuth entry/return routes are public.
- **Identity authority**: auth legitimately operates pre-tenant (login by email) and cross-tenant (S2S
  lookups), so its DB session runs with the RLS **system bypass** (`set_rls_bypass`). Per-request
  scoping is enforced in the app layer: `get_user`/`get_tenant` reject an id outside the caller's tenant
  unless the caller is a service token; `check_permission` authorizes off the verified roles, not the body.

---

## Configuration

### Environment Variables

| Variable                     | Required     | Default                           | Description                                 |
| ---------------------------- | ------------ | --------------------------------- | ------------------------------------------- |
| `DATABASE_URL`               | Yes          | -                                 | PostgreSQL connection string                |
| `JWT_SECRET`                 | Yes          | `dev-secret-change-in-production` | Secret for JWT signing (also signs OAuth `state`/handoff) |
| `JWT_ALGORITHM`              | No           | `HS256`                           | JWT signing algorithm                       |
| `ENCRYPTION_KEY`             | Yes          | -                                 | Fernet key material (PBKDF2 → AES-128-CBC + HMAC) |
| `CORS_ORIGINS`               | No           | localhost origins                 | Allowed CORS origins                        |
| `AUTH_PORT`                  | No           | `8810`                            | Service port                                |
| `ALPACA_OAUTH_CLIENT_ID`     | For OAuth    | -                                 | Alpaca OAuth app client id                  |
| `ALPACA_OAUTH_CLIENT_SECRET` | For OAuth    | -                                 | Alpaca OAuth app client secret (server-side exchange) |
| `ALPACA_OAUTH_REDIRECT_URI`  | For OAuth    | -                                 | Public auth callback URL                    |
| `ALPACA_OAUTH_SCOPE`         | No           | `trading`                         | Requested OAuth scope                       |
| `WEB_APP_URL`                | No           | `http://localhost:8800`           | Web app base for OAuth redirects            |

`JWT_SECRET` and `ENCRYPTION_KEY` are resolved via `llamatrade_common.utils.require_secret`, which
is **fail-closed**: when `ENVIRONMENT` is `production` or `staging`, an unset secret raises at
startup rather than falling back to the development default. The listed defaults apply only to local
dev and tests.

### Port Assignment

| Service | Port |
| ------- | ---- |
| Auth    | 8810 |

---

## Health Check

```http
GET /health
```

**Response:**

```json
{
  "status": "healthy",
  "service": "auth",
  "version": "0.1.0"
}
```

---

## Internal Service Connections

### Who Calls Auth Service

| Service          | Methods Used                                   | Purpose                                  |
| ---------------- | ---------------------------------------------- | ---------------------------------------- |
| **Web Frontend** | `Login`, `Register`, `RefreshToken`, Alpaca OAuth routes | User authentication flow             |
| **Web Frontend** | `CreateAlpacaCredentials`, `ListAlpacaCredentials`, `ValidateAlpacaCredentials` | Broker credential management (write-only) |
| **Trading**      | Alpaca credentials (decrypted service-side)    | Build broker clients for order execution |
| **Market-Data**  | Alpaca credentials (decrypted service-side)    | Build broker clients for data access     |
| **All Services** | `ValidateToken`                                | Verify incoming requests                 |

### What Auth Service Calls

| Target         | Purpose                        |
| -------------- | ------------------------------ |
| **PostgreSQL** | User/tenant/credential storage |

---

## Complete Data Flow Example

### User Registration Flow

```
1. User submits registration form
   - tenant_name: "Acme Trading"
   - email: "alice@acme.com"
   - password: "SecurePass123"

2. Auth Service receives RegisterRequest
   └─> Validates password strength (8+ chars, upper, lower, digit)
   └─> Checks email doesn't already exist

3. TenantService.create_tenant()
   └─> Generates UUID for tenant
   └─> Creates slug: "acme-trading-a1b2c3d4"
   └─> INSERT INTO tenants

4. UserService.create_user()
   └─> Generates UUID for user
   └─> Hashes password with bcrypt (cost factor 12)
   └─> INSERT INTO users (tenant_id = new tenant)

5. Generate JWT tokens
   └─> Access token (30 min expiry)
   └─> Refresh token (7 day expiry)

6. Return RegisterResponse
   └─> user: { id, tenant_id, email, role: "admin" }
   └─> tokens: { access_token, refresh_token, expires_in: 1800 }
```

### Login Flow

```
1. User submits login form
   - email: "alice@acme.com"
   - password: "SecurePass123"

2. Auth Service receives LoginRequest
   └─> UserService.get_user_by_email()
   └─> Returns UserWithPassword (includes hash)

3. Verify password
   └─> bcrypt.checkpw(password, stored_hash)
   └─> If mismatch: return UNAUTHENTICATED error

4. Check user status
   └─> is_active must be True
   └─> If inactive: return PERMISSION_DENIED error

5. Generate JWT tokens
   └─> Access token with claims: { sub, tenant_id, email, role }
   └─> Refresh token with claims: { sub, tenant_id, type: "refresh" }

6. Return LoginResponse
   └─> access_token, refresh_token, expires_in: 1800
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
   └─> encrypt_value(api_key) -> api_key_encrypted
   └─> encrypt_value(api_secret) -> api_secret_encrypted
   └─> INSERT INTO alpaca_credentials (tenant_id, ...)

4. Return a write-only response
   - id, name, api_key = masked 8-char prefix, api_secret = "", is_paper
   - The full key/secret is never returned to the client (create or get)

5. LIST requests show the masked api_key_prefix
   - "PK1A2B3C" (first 8 chars only)
```

---

## Error Handling

### Connect/gRPC Error Codes

| Error               | Code | When Raised                           |
| ------------------- | ---- | ------------------------------------- |
| `UNAUTHENTICATED`   | 16   | Invalid/expired token, wrong password |
| `PERMISSION_DENIED` | 7    | User lacks required role/permission   |
| `INVALID_ARGUMENT`  | 3    | Password doesn't meet requirements    |
| `ALREADY_EXISTS`    | 6    | Email already registered              |
| `NOT_FOUND`         | 5    | User/credentials not found            |
| `INTERNAL`          | 13   | Database errors, encryption failures  |

### Error Response Example

```python
raise ConnectError(
    Code.UNAUTHENTICATED,
    "Invalid credentials"
)

# Client receives:
# {
#   "code": "unauthenticated",
#   "message": "Invalid credentials"
# }
```

---

## Testing

### Test Structure

```
tests/
├── __init__.py
├── test_auth_unit.py           # Unit tests for auth logic
├── test_grpc_auth.py           # gRPC servicer integration tests
├── test_user_service.py        # User service unit tests
├── test_tenant_service.py      # Tenant + credentials tests
└── test_api_key_service.py     # API key tests
```

### Running Tests

```bash
# Run all auth tests
cd services/auth && pytest

# Run with coverage
cd services/auth && pytest --cov=src --cov-report=term-missing

# Run specific test file
cd services/auth && pytest tests/test_user_service.py -v
```

### Key Test Scenarios

- **Login**: Valid credentials, wrong password, inactive user, non-existent email
- **Registration**: Valid data, duplicate email, weak password, password validation
- **Token refresh**: Valid refresh token, expired token, invalid token
- **Alpaca credentials**: Create, list (masked), get (decrypted), delete, tenant isolation
- **RBAC**: Admin permissions, trader permissions, viewer restrictions

---

## Capabilities

### Authentication & Tokens

- User registration (create tenant + first admin user)
- User login (email/password) with bcrypt verification
- JWT access (30-min) + refresh (7-day) tokens; refresh flow; token validation
- Sign in / sign up / connect with **Alpaca OAuth** (link, login, complete-signup)
- Change password (current-password verification)

### User & Tenant

- Get current user profile + tenant (from the token)
- Get a user / tenant by id, tenant-scoped (service tokens may cross tenants)
- Tenant creation with slug generation
- Multi-tenant isolation via the verified token + Postgres RLS

### Credentials & API Keys

- Alpaca credential CRUD (create / get / list / soft-delete), Fernet-encrypted, write-only responses
- Validate Alpaca credentials against the broker (`ValidateAlpacaCredentials`)
- API-key validation (`ValidateAPIKey`)
- RBAC permission check (`CheckPermission`, roles from the verified context)

## Planned / Not implemented

- **Token revocation / blacklist on logout** — `logout` is a no-op token decode (JWTs are stateless).
- **User/tenant management RPCs** — no update/list/delete users, no tenant-settings update, no API-key create/list/delete.
- **Email verification, password reset, and non-Alpaca social login** (e.g. Google/GitHub).
- **KMS / envelope encryption and key rotation** for credentials (currently one global `ENCRYPTION_KEY` with per-value salts).

---

## Startup / Shutdown Sequence

### Startup

```
1. FastAPI app created with lifespan handler
2. lifespan.__aenter__():
   └─> init_db() - Initialize SQLAlchemy async engine
   └─> Load AuthServiceASGIApplication from proto-generated code
   └─> Create AuthServicer instance
   └─> Mount Connect app at root path
3. CORS middleware configured
4. Service ready to accept requests
```

### Shutdown

```
1. lifespan.__aexit__():
   └─> close_db() - Dispose SQLAlchemy engine
2. Graceful connection draining
```

---

## Summary

The Auth Service is the security foundation of LlamaTrade, handling user authentication, multi-tenant isolation, and broker credential management. It uses JWT tokens for stateless authentication (30-minute access tokens, 7-day refresh tokens), bcrypt for password hashing, and Fernet (AES-128-CBC + HMAC) for encrypting Alpaca API credentials at rest.

It exposes 16 RPC methods over the Connect protocol plus five Alpaca OAuth HTTP routes, serving both web browsers and backend services.

Identity is derived from the verified token (`current_context` / `resolve_identity`) with app-layer cross-tenant guards; the auth DB session runs with the RLS system bypass because auth is the platform's pre-/cross-tenant identity authority.
