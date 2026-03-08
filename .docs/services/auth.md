# Auth Service

## Overview

The Auth Service is the security backbone of LlamaTrade, responsible for authenticating users, managing multi-tenant isolation, and securely storing broker credentials. Every request to the platform flows through authentication, making this service critical for both security and user experience.

**Why This Service Matters:**

- **Multi-Tenancy Foundation**: In a SaaS platform, tenant isolation is non-negotiable. The Auth Service ensures that traders can never access each other's strategies, portfolios, or credentials—even if there's a bug elsewhere in the system.
- **Broker Credential Security**: Traders entrust LlamaTrade with their Alpaca API keys. These credentials could drain their brokerage accounts if compromised, so we use AES-256-GCM encryption and never expose raw secrets after initial storage.
- **Stateless Scaling**: JWT-based authentication allows the platform to scale horizontally without session state, critical for handling market open spikes when thousands of strategies may trigger simultaneously.

**Core Responsibilities:**

- User registration and authentication (login/logout)
- JWT access and refresh token management
- Multi-tenant isolation (tenant_id propagation)
- Role-based access control (RBAC)
- Encrypted Alpaca broker credential storage
- API key management for programmatic access

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Auth Service                                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        Connect Protocol                             │    │
│  │                    (Browser-Compatible gRPC)                        │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│  ┌───────────────────────────────▼─────────────────────────────────────┐    │
│  │                         AuthServicer                                │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────────────────┐   │    │
│  │  │   Login     │  │  Register   │  │  Token Refresh/Validate    │   │    │
│  │  └─────────────┘  └─────────────┘  └────────────────────────────┘   │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────────────────┐   │    │
│  │  │ User CRUD   │  │ RBAC/Roles  │  │  Alpaca Credentials        │   │    │
│  │  └─────────────┘  └─────────────┘  └────────────────────────────┘   │    │
│  │  ┌─────────────┐                                                    │    │
│  │  │ API Keys    │                                                    │    │
│  │  └─────────────┘                                                    │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│  ┌───────────────────────────────▼─────────────────────────────────────┐    │
│  │                        Service Layer                                │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────────┐   │    │
│  │  │  UserService    │  │  TenantService  │  │  APIKeyService     │   │    │
│  │  │  - create_user  │  │  - create_tenant│  │  - create_key      │   │    │
│  │  │  - get_user     │  │  - get_tenant   │  │  - validate_key    │   │    │
│  │  │  - authenticate │  │  - update_settings│ │  - list_keys      │   │    │
│  │  └─────────────────┘  └─────────────────┘  └────────────────────┘   │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│  ┌───────────────────────────────▼─────────────────────────────────────┐    │
│  │                        Security Layer                               │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │  llamatrade_common                                          │    │    │
│  │  │  - encrypt_value() / decrypt_value() (AES-256-GCM)          │    │    │
│  │  │  - bcrypt password hashing                                  │    │    │
│  │  │  - JWT signing/verification (HS256)                         │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
└──────────────────────────────────┼──────────────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │        PostgreSQL           │
                    │  ┌─────────┐ ┌───────────┐  │
                    │  │ tenants │ │   users   │  │
                    │  └─────────┘ └───────────┘  │
                    │  ┌─────────────────────┐    │
                    │  │ alpaca_credentials  │    │
                    │  │ (AES-encrypted)     │    │
                    │  └─────────────────────┘    │
                    │  ┌─────────────────────┐    │
                    │  │     api_keys        │    │
                    │  └─────────────────────┘    │
                    └─────────────────────────────┘
```

### JWT Token Flow

```
┌──────────┐         ┌──────────────┐         ┌────────────────┐
│  Client  │         │ Auth Service │         │ Other Services │
└────┬─────┘         └──────┬───────┘         └───────┬────────┘
     │                      │                         │
     │  1. Login Request    │                         │
     │  (email, password)   │                         │
     │─────────────────────>│                         │
     │                      │                         │
     │                      │ 2. Verify password      │
     │                      │    (bcrypt)             │
     │                      │                         │
     │  3. TokenResponse    │                         │
     │  (access + refresh)  │                         │
     │<─────────────────────│                         │
     │                      │                         │
     │  4. API Request      │                         │
     │  + Bearer token      │                         │
     │────────────────────────────────────────────────>
     │                      │                         │
     │                      │  5. Validate token      │
     │                      │  (JWT decode + verify)  │
     │                      │                         │
     │  6. Response         │                         │
     │<────────────────────────────────────────────────
     │                      │                         │
     │  7. Token Expired    │                         │
     │  (30 min access)     │                         │
     │                      │                         │
     │  8. Refresh Request  │                         │
     │  (refresh token)     │                         │
     │─────────────────────>│                         │
     │                      │                         │
     │  9. New Tokens       │                         │
     │<─────────────────────│                         │
     │                      │                         │
```

---

## Directory Structure

```
services/auth/
├── src/
│   ├── main.py                 # FastAPI app setup, Connect mounting, health check
│   ├── models.py               # Pydantic schemas (UserCreate, TokenResponse, etc.)
│   ├── grpc/
│   │   └── servicer.py         # AuthServicer - 14 RPC methods (~870 lines)
│   └── services/
│       ├── database.py         # Async SQLAlchemy session management
│       ├── user_service.py     # User CRUD, password hashing
│       ├── tenant_service.py   # Tenant CRUD, Alpaca credential encryption
│       └── api_key_service.py  # API key generation and validation
├── tests/
│   ├── __init__.py
│   ├── test_auth_unit.py       # Unit tests for auth logic
│   ├── test_grpc_auth.py       # gRPC servicer integration tests
│   ├── test_user_service.py    # User service tests
│   ├── test_tenant_service.py  # Tenant service tests
│   └── test_api_key_service.py # API key service tests
├── pyproject.toml
└── Dockerfile
```

---

## Core Components

| Component         | File                          | Purpose                                              |
| ----------------- | ----------------------------- | ---------------------------------------------------- |
| **AuthServicer**  | `grpc/servicer.py`            | Connect protocol servicer, implements 14 RPC methods |
| **UserService**   | `services/user_service.py`    | User CRUD operations, password hashing with bcrypt   |
| **TenantService** | `services/tenant_service.py`  | Tenant management, Alpaca credential encryption      |
| **APIKeyService** | `services/api_key_service.py` | API key creation, validation, scoping                |

---

## RPC Endpoints

### Authentication

| Method           | Request                 | Response                 | Description                                          |
| ---------------- | ----------------------- | ------------------------ | ---------------------------------------------------- |
| `Login`          | `LoginRequest`          | `LoginResponse`          | Authenticate with email/password, returns JWT tokens |
| `Register`       | `RegisterRequest`       | `RegisterResponse`       | Create new tenant and admin user                     |
| `Logout`         | `LogoutRequest`         | `LogoutResponse`         | Invalidate refresh token (future: token blacklist)   |
| `ChangePassword` | `ChangePasswordRequest` | `ChangePasswordResponse` | Update password with current password verification   |

### Token Management

| Method          | Request                | Response                | Description                                 |
| --------------- | ---------------------- | ----------------------- | ------------------------------------------- |
| `RefreshToken`  | `RefreshTokenRequest`  | `RefreshTokenResponse`  | Exchange refresh token for new access token |
| `ValidateToken` | `ValidateTokenRequest` | `ValidateTokenResponse` | Verify token validity and extract claims    |

### User Management

| Method           | Request                 | Response                 | Description                         |
| ---------------- | ----------------------- | ------------------------ | ----------------------------------- |
| `GetCurrentUser` | `GetCurrentUserRequest` | `GetCurrentUserResponse` | Get authenticated user's profile    |
| `UpdateUser`     | `UpdateUserRequest`     | `UpdateUserResponse`     | Update user email or role (stubbed) |
| `ListUsers`      | `ListUsersRequest`      | `ListUsersResponse`      | List users in tenant (stubbed)      |

### RBAC / Permissions

| Method            | Request                  | Response                  | Description                         |
| ----------------- | ------------------------ | ------------------------- | ----------------------------------- |
| `CheckPermission` | `CheckPermissionRequest` | `CheckPermissionResponse` | Verify user has specific permission |

### Alpaca Credentials

| Method                    | Request                          | Response                          | Description                    |
| ------------------------- | -------------------------------- | --------------------------------- | ------------------------------ |
| `GetAlpacaCredentials`    | `GetAlpacaCredentialsRequest`    | `GetAlpacaCredentialsResponse`    | Retrieve decrypted credentials |
| `SetAlpacaCredentials`    | `SetAlpacaCredentialsRequest`    | `SetAlpacaCredentialsResponse`    | Store encrypted credentials    |
| `ListAlpacaCredentials`   | `ListAlpacaCredentialsRequest`   | `ListAlpacaCredentialsResponse`   | List credentials (keys masked) |
| `DeleteAlpacaCredentials` | `DeleteAlpacaCredentialsRequest` | `DeleteAlpacaCredentialsResponse` | Soft-delete credentials        |

### API Keys (Stubbed)

| Method           | Request                 | Response                 | Description                            |
| ---------------- | ----------------------- | ------------------------ | -------------------------------------- |
| `CreateAPIKey`   | `CreateAPIKeyRequest`   | `CreateAPIKeyResponse`   | Generate new API key with scopes       |
| `ListAPIKeys`    | `ListAPIKeysRequest`    | `ListAPIKeysResponse`    | List user's API keys                   |
| `DeleteAPIKey`   | `DeleteAPIKeyRequest`   | `DeleteAPIKeyResponse`   | Revoke an API key                      |
| `ValidateAPIKey` | `ValidateAPIKeyRequest` | `ValidateAPIKeyResponse` | Verify API key and extract permissions |

---

## Data Models

### Pydantic Schemas

```python
# User Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)  # Must contain upper, lower, digit
    role: str = "user"

class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime

# Token Schemas
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds until access token expires (1800 = 30 min)

# Registration
class RegisterRequest(BaseModel):
    tenant_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)

# Alpaca Credentials
class AlpacaCredentialsCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    api_key: str = Field(..., min_length=20)
    api_secret: str = Field(..., min_length=40)
    is_paper: bool = True

class AlpacaCredentialsListItem(BaseModel):
    id: UUID
    name: str
    api_key_prefix: str  # First 8 characters only (masked)
    is_paper: bool
    is_active: bool
    created_at: datetime
```

### Database Models (via llamatrade_db)

| Table                | Key Fields                                                     | Notes                        |
| -------------------- | -------------------------------------------------------------- | ---------------------------- |
| `tenants`            | `id`, `name`, `slug`, `settings`                               | Multi-tenant parent entity   |
| `users`              | `id`, `tenant_id`, `email`, `password_hash`, `role`            | `tenant_id` FK for isolation |
| `alpaca_credentials` | `id`, `tenant_id`, `api_key_encrypted`, `api_secret_encrypted` | AES-256-GCM encrypted        |
| `api_keys`           | `id`, `user_id`, `key_hash`, `scopes`, `last_used_at`          | Hashed, not encrypted        |

---

## Security

### Password Requirements

Passwords must meet all requirements:

- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit

```python
@field_validator("password")
def validate_password(cls, v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not any(c.isupper() for c in v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(c.islower() for c in v):
        raise ValueError("Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one digit")
    return v
```

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

Broker credentials are encrypted using AES-256-GCM via `llamatrade_common`:

```python
from llamatrade_common.utils import encrypt_value, decrypt_value

# Encryption (on store)
creds = AlpacaCredentialsModel(
    tenant_id=tenant_id,
    name=data.name,
    api_key_encrypted=encrypt_value(data.api_key),
    api_secret_encrypted=encrypt_value(data.api_secret),
    is_paper=data.is_paper,
)

# Decryption (on retrieve)
return AlpacaCredentialsResponse(
    id=creds.id,
    api_key=decrypt_value(creds.api_key_encrypted),
    api_secret=decrypt_value(creds.api_secret_encrypted),
    ...
)
```

**Security Properties:**

- **AES-256-GCM**: Authenticated encryption (confidentiality + integrity)
- **ENCRYPTION_KEY**: 32-byte key loaded from environment variable
- **Per-value nonce**: Each encryption uses a unique random nonce
- **Listing masks keys**: `list_alpaca_credentials` only returns first 8 characters

### RBAC Roles

| Role     | Permissions                           | Use Case                      |
| -------- | ------------------------------------- | ----------------------------- |
| `admin`  | Full access to tenant resources       | Account owner, manages users  |
| `trader` | Create/run strategies, view portfolio | Day-to-day trading operations |
| `viewer` | Read-only access                      | Auditors, observers           |
| `api`    | Programmatic access, scope-limited    | External integrations         |

---

## Configuration

### Environment Variables

| Variable         | Required | Default                           | Description                  |
| ---------------- | -------- | --------------------------------- | ---------------------------- |
| `DATABASE_URL`   | Yes      | -                                 | PostgreSQL connection string |
| `JWT_SECRET`     | Yes      | `dev-secret-change-in-production` | Secret for JWT signing       |
| `JWT_ALGORITHM`  | No       | `HS256`                           | JWT signing algorithm        |
| `ENCRYPTION_KEY` | Yes      | -                                 | 32-byte key for AES-256-GCM  |
| `CORS_ORIGINS`   | No       | `localhost`                       | Allowed CORS origins         |
| `AUTH_PORT`      | No       | `8810`                            | Service port                 |

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
| **Web Frontend** | `Login`, `Register`, `RefreshToken`            | User authentication flow                 |
| **Web Frontend** | `GetAlpacaCredentials`, `SetAlpacaCredentials` | Broker credential management             |
| **Trading**      | `GetAlpacaCredentials`                         | Retrieve credentials for order execution |
| **Market-Data**  | `GetAlpacaCredentials`                         | Retrieve credentials for data access     |
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
1. Authenticated user calls SetAlpacaCredentials
   - name: "Paper Trading"
   - api_key: "PK..."
   - api_secret: "..."
   - is_paper: true

2. Extract tenant_id from JWT
   └─> Decode Authorization header
   └─> Verify signature
   └─> Extract tenant_id claim

3. TenantService.create_alpaca_credentials()
   └─> encrypt_value(api_key) -> api_key_encrypted
   └─> encrypt_value(api_secret) -> api_secret_encrypted
   └─> INSERT INTO alpaca_credentials (tenant_id, ...)

4. Return credentials (with decrypted values for confirmation)
   - id, name, api_key (full), api_secret (full), is_paper
   - Note: Full values only returned on create

5. Subsequent LIST requests show masked api_key_prefix
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

## Current Implementation Status

> **Project Stage:** Early Development

### What's Real (Implemented)

- [x] User registration (create tenant + admin user)
- [x] User login (email/password authentication)
- [x] JWT access token generation (30 min TTL)
- [x] JWT refresh token generation (7 day TTL)
- [x] Token refresh flow
- [x] Token validation
- [x] Password hashing (bcrypt)
- [x] Password strength validation
- [x] Get current user profile
- [x] Alpaca credential encryption (AES-256-GCM)
- [x] Alpaca credential CRUD (create, get, list, delete)
- [x] Tenant creation with slug generation
- [x] Multi-tenant isolation via tenant_id

### What's Stubbed (TODO)

- [ ] User listing (returns empty list)
- [ ] User update (returns None)
- [ ] User deletion (returns False)
- [ ] Tenant settings update
- [ ] API key creation (returns mock key)
- [ ] API key listing (returns empty list)
- [ ] API key validation
- [ ] Token blacklisting for logout
- [ ] Email verification
- [ ] Password reset flow
- [ ] OAuth2 social login (Google, GitHub)

### Known Limitations

1. **No token revocation**: Logout doesn't invalidate tokens (would need Redis blacklist)
2. **Single-tenant JWT secret**: All tenants share the same signing key
3. **No rate limiting**: Vulnerable to brute-force attacks without external rate limiting
4. **Synchronous Stripe calls**: Some operations block the event loop

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

The Auth Service is the security foundation of LlamaTrade, handling user authentication, multi-tenant isolation, and broker credential management. It uses JWT tokens for stateless authentication (30-minute access tokens, 7-day refresh tokens), bcrypt for password hashing, and AES-256-GCM for encrypting sensitive Alpaca API credentials.

The service is approximately 60% implemented, with core authentication and credential management working, while user management CRUD and API key features remain stubbed. It exposes 14+ RPC methods via the Connect protocol, making it accessible from both web browsers and backend services.

All operations are tenant-scoped via `tenant_id` in JWT claims, ensuring complete isolation between trading organizations on the platform.
