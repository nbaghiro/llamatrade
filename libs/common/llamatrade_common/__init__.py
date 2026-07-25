"""LlamaTrade Common Library - Shared utilities and models."""

from llamatrade_common.auth import (
    AuthError,
    AuthMiddleware,
    TenantContext,
    current_context,
    mint_service_token,
    reset_context,
    resolve_identity,
    set_context,
    verify_credential,
)
from llamatrade_common.health import (
    HealthChecker,
    HealthCheckResponse,
    HealthStatus,
    check_postgres,
    check_redis,
)
from llamatrade_common.utils import (
    PaginatedResult,
    decrypt_value,
    encrypt_value,
    generate_uuid,
    paginate,
    utc_now,
)

__version__ = "0.1.0"
__all__ = [
    # Auth (shared platform mechanism)
    "AuthMiddleware",
    "AuthError",
    "TenantContext",
    "current_context",
    "set_context",
    "reset_context",
    "resolve_identity",
    "verify_credential",
    "mint_service_token",
    # Utils
    "generate_uuid",
    "utc_now",
    "encrypt_value",
    "decrypt_value",
    "paginate",
    "PaginatedResult",
    # Health
    "HealthChecker",
    "HealthCheckResponse",
    "HealthStatus",
    "check_postgres",
    "check_redis",
]
