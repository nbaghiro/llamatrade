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
from llamatrade_common.errors import (
    DSLError,
    DSLErrorCode,
    classify_error,
    create_dsl_error,
    grpc_status_from_dsl_code,
)
from llamatrade_common.health import HealthChecker, HealthStatus, check_postgres, check_redis
from llamatrade_common.middleware import TenantMiddleware, get_tenant_context
from llamatrade_common.utils import (
    decrypt_value,
    encrypt_value,
    generate_uuid,
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
    # Middleware (legacy tenant context + helpers)
    "TenantMiddleware",
    "get_tenant_context",
    # Errors
    "DSLError",
    "DSLErrorCode",
    "classify_error",
    "create_dsl_error",
    "grpc_status_from_dsl_code",
    # Utils
    "generate_uuid",
    "utc_now",
    "encrypt_value",
    "decrypt_value",
    # Health
    "HealthChecker",
    "HealthStatus",
    "check_postgres",
    "check_redis",
]
