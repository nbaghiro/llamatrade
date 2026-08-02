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
from llamatrade_common.connect import (
    handle_service_errors,
    parse_uuid,
    resolve_identity_connect,
)
from llamatrade_common.health import (
    HealthChecker,
    HealthCheckResponse,
    HealthStatus,
    cached_engine_check,
    check_kafka,
    check_postgres,
    check_redis,
)
from llamatrade_common.ratelimit import RateLimiter
from llamatrade_common.revocation import RevocationStore, consume_once
from llamatrade_common.supervisor import supervise
from llamatrade_common.utils import (
    PaginatedResult,
    PaginationRequestLike,
    PaginationResponseData,
    async_decrypt_value,
    async_encrypt_value,
    async_reencrypt_value,
    decrypt_value,
    encrypt_value,
    generate_uuid,
    paginate,
    pagination_response,
    reencrypt_value,
    resolve_pagination,
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
    "resolve_identity_connect",
    "handle_service_errors",
    "parse_uuid",
    "verify_credential",
    "mint_service_token",
    "RateLimiter",
    "RevocationStore",
    "consume_once",
    # Utils
    "generate_uuid",
    "utc_now",
    "encrypt_value",
    "decrypt_value",
    "reencrypt_value",
    "async_encrypt_value",
    "async_decrypt_value",
    "async_reencrypt_value",
    "paginate",
    "PaginatedResult",
    "resolve_pagination",
    "pagination_response",
    "PaginationRequestLike",
    "PaginationResponseData",
    # Health
    "HealthChecker",
    "supervise",
    "HealthCheckResponse",
    "HealthStatus",
    "cached_engine_check",
    "check_kafka",
    "check_postgres",
    "check_redis",
]
