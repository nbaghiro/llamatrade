# Security Model

This document describes LlamaTrade's security architecture, covering authentication, authorization, tenant isolation, and data protection.

---

## Overview

LlamaTrade is a multi-tenant SaaS platform handling sensitive financial operations. Security is enforced at multiple layers:

1. **Authentication** — Verify user identity (JWT, API keys)
2. **Authorization** — Control access to resources (roles, permissions)
3. **Tenant Isolation** — Prevent cross-tenant data access (RLS, middleware)
4. **Data Protection** — Secure sensitive data (encryption, secrets management)
5. **Network Security** — Protect communication (TLS, firewalls)

---

## Authentication

### JWT Tokens

Users authenticate via JWT access tokens:

**Token Structure:**

```json
{
  "sub": "user-uuid",
  "tenant_id": "tenant-uuid",
  "roles": ["admin"],
  "iat": 1705312200,
  "exp": 1705314000,
  "type": "access"
}
```

**Token Lifecycle:**

| Token Type | Lifetime | Storage | Usage |
|------------|----------|---------|-------|
| Access Token | 30 minutes | Memory only | API requests |
| Refresh Token | 7 days | HttpOnly cookie | Get new access token |

**Token Flow:**

```
1. User logs in with email/password
2. Auth service validates credentials
3. Returns access token + sets refresh cookie
4. Client includes access token in Authorization header
5. Gateway validates token, extracts tenant context
6. When access token expires, use refresh token to get new one
```

**Token Validation:**

```python
# All services validate tokens via Auth Service gRPC
async def validate_token(token: str) -> TenantContext:
    response = await auth_client.validate_token(token)
    if not response.valid:
        raise HTTPException(401, "Invalid token")
    return response.context
```

### API Keys

For programmatic access (CLI tools, integrations):

**Key Format:** `lt_<prefix>_<random>`
- `lt_` — LlamaTrade prefix
- `<prefix>` — First 8 chars for identification
- `<random>` — 32-byte random string

**Key Storage:**
- Only SHA-256 hash stored in database
- Full key shown only once at creation
- Keys can have scopes and expiration

**Key Validation:**

```python
async def validate_api_key(key: str, required_scopes: list[str]):
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    api_key = await db.query(APIKey).filter_by(key_hash=key_hash).first()

    if not api_key or not api_key.is_active:
        raise HTTPException(401, "Invalid API key")

    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        raise HTTPException(401, "API key expired")

    if not all(scope in api_key.scopes for scope in required_scopes):
        raise HTTPException(403, "Insufficient scopes")

    return TenantContext(tenant_id=api_key.tenant_id, ...)
```

### Password Security

Passwords are hashed with bcrypt:

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hash: str) -> bool:
    return pwd_context.verify(password, hash)
```

**Password Requirements:**
- Minimum 8 characters
- At least one uppercase, lowercase, number
- Not in common password list

---

## Authorization

### Role-Based Access Control (RBAC)

Users have roles that determine permissions:

| Role | Description | Permissions |
|------|-------------|-------------|
| `owner` | Tenant owner | Full access, billing, user management |
| `admin` | Administrator | All except billing changes |
| `user` | Regular user | CRUD own strategies, view portfolio |
| `viewer` | Read-only | View strategies, backtests, portfolio |

### Permission Checks

```python
def require_role(allowed_roles: list[str]):
    async def check(ctx: TenantContext = Depends(require_auth)):
        if not any(role in allowed_roles for role in ctx.roles):
            raise HTTPException(403, "Insufficient permissions")
        return ctx
    return check

# Usage
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    ctx: TenantContext = Depends(require_role(["owner", "admin"]))
):
    ...
```

### Resource-Level Permissions

Some resources have additional ownership checks:

```python
async def get_strategy(strategy_id: UUID, ctx: TenantContext):
    strategy = await db.query(Strategy).filter_by(
        id=strategy_id,
        tenant_id=ctx.tenant_id  # Tenant isolation
    ).first()

    if not strategy:
        raise HTTPException(404, "Strategy not found")

    # Owner or admin can modify, others can only view
    if ctx.user_id != strategy.created_by and "admin" not in ctx.roles:
        raise HTTPException(403, "Not authorized to modify this strategy")

    return strategy
```

---

## Tenant Isolation

### Database Layer (RLS)

All tenant-scoped tables include `tenant_id`:

```sql
-- Every query is filtered by tenant
SELECT * FROM strategies WHERE tenant_id = 'tenant-uuid' AND id = 'strategy-uuid';
```

**Row-Level Security Policy:**

```sql
-- Enable RLS
ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see their tenant's data
CREATE POLICY tenant_isolation ON strategies
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

### Application Layer

Middleware extracts and propagates tenant context:

```python
async def require_auth(request: Request) -> TenantContext:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "Missing authentication")

    ctx = await validate_token(token)

    # Set for RLS (if using database-level RLS)
    await db.execute(f"SET app.tenant_id = '{ctx.tenant_id}'")

    return ctx
```

**All database queries MUST use tenant_id:**

```python
# CORRECT
strategies = await db.query(Strategy).filter_by(tenant_id=ctx.tenant_id).all()

# WRONG - Never do this
strategies = await db.query(Strategy).all()  # Leaks all tenants' data!
```

### Service-to-Service Communication

Tenant context propagated via headers:

```python
# Calling another service
headers = {
    "X-Tenant-ID": ctx.tenant_id,
    "X-User-ID": ctx.user_id,
    "X-Request-ID": request_id
}
response = await client.get("/strategies", headers=headers)
```

---

## Data Protection

### Encryption at Rest

**Alpaca Credentials:**

User's Alpaca API keys are encrypted with AES-256-GCM:

```python
from cryptography.fernet import Fernet

# Key from environment (32-byte base64)
ENCRYPTION_KEY = os.environ["ENCRYPTION_KEY"]
fernet = Fernet(ENCRYPTION_KEY)

def encrypt_credential(plaintext: str) -> str:
    return fernet.encrypt(plaintext.encode()).decode()

def decrypt_credential(ciphertext: str) -> str:
    return fernet.decrypt(ciphertext.encode()).decode()
```

**Database Encryption:**

Cloud SQL encrypts data at rest by default (AES-256).

### Encryption in Transit

- All external traffic uses TLS 1.3
- Internal gRPC uses TLS (mTLS in production)
- Database connections use SSL

### Secrets Management

Secrets stored in GCP Secret Manager:

| Secret | Description |
|--------|-------------|
| `jwt-secret` | JWT signing key |
| `encryption-key` | Alpaca credential encryption |
| `stripe-api-key` | Stripe secret key |
| `sendgrid-api-key` | SendGrid API key |
| `db-password` | Database password |

**Accessing Secrets:**

```python
from google.cloud import secretmanager

def get_secret(secret_id: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(name=name)
    return response.payload.data.decode()
```

---

## Network Security

### API Gateway

Kong handles:
- JWT validation
- Rate limiting (per-tenant)
- IP allowlisting (optional)
- Request/response logging

**Rate Limits:**

| Plan | Requests/minute | Concurrent connections |
|------|-----------------|------------------------|
| Free | 60 | 10 |
| Pro | 300 | 50 |
| Enterprise | Custom | Custom |

### Firewall Rules

- Public access only to Load Balancer
- Services communicate on internal network only
- Database accessible only from GKE cluster
- Egress limited to required destinations (Alpaca, Stripe, etc.)

### CORS

Strict CORS policy:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.llamatrade.com"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)
```

---

## Audit Logging

All security-relevant events are logged:

```python
async def audit_log(
    tenant_id: UUID,
    user_id: UUID,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict = None,
    ip_address: str = None
):
    await db.execute(
        AuditLog.insert().values(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            created_at=datetime.utcnow()
        )
    )
```

**Logged Events:**

| Action | Description |
|--------|-------------|
| `user.login` | User logged in |
| `user.logout` | User logged out |
| `user.login_failed` | Failed login attempt |
| `user.password_changed` | Password changed |
| `api_key.created` | API key created |
| `api_key.revoked` | API key revoked |
| `strategy.created` | Strategy created |
| `strategy.deployed` | Strategy deployed to live |
| `order.submitted` | Order submitted to Alpaca |
| `credentials.added` | Alpaca credentials added |

---

## Security Best Practices

### For Developers

1. **Never log sensitive data** (passwords, tokens, API keys)
2. **Always use parameterized queries** (SQLAlchemy handles this)
3. **Validate all input** (Pydantic models)
4. **Check tenant_id on every query**
5. **Use HTTPS for external calls**
6. **Don't commit secrets to git**

### For Operations

1. **Rotate secrets regularly** (especially JWT key)
2. **Monitor failed login attempts**
3. **Review audit logs weekly**
4. **Keep dependencies updated**
5. **Run security scans in CI**

---

## Incident Response

### If Credentials Are Compromised

1. **Rotate affected secrets immediately**
2. **Invalidate all sessions** (change JWT secret)
3. **Notify affected tenants**
4. **Review audit logs for unauthorized access**
5. **Document incident and remediation**

### If Data Breach Suspected

1. **Isolate affected systems**
2. **Preserve logs and evidence**
3. **Notify security team**
4. **Assess scope of breach**
5. **Notify affected users if required**
6. **Report to authorities if required (GDPR, etc.)**

---

## Compliance

### Data Handling

- User data retained only as long as needed
- Users can request data export (GDPR)
- Users can request account deletion
- PII is encrypted at rest

### SOC 2 Considerations

- Access controls documented and enforced
- Audit logs retained for 1 year
- Regular security assessments
- Incident response procedures documented
