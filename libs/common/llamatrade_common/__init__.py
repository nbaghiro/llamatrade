"""LlamaTrade Common Library - Shared utilities and models."""

from llamatrade_common.events import Event, EventType
from llamatrade_common.health import HealthChecker, HealthStatus, check_postgres, check_redis
from llamatrade_common.logging import (
    JSONFormatter,
    configure_logging,
    get_logger,
    set_request_context,
)
from llamatrade_common.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    MetricsTimer,
    get_metrics,
    init_service_info,
    record_http_request,
)
from llamatrade_common.middleware import TenantMiddleware, get_tenant_context
from llamatrade_common.models import (
    ErrorResponse,
    HealthResponse,
    PaginatedResponse,
    TenantContext,
    UserInfo,
)
from llamatrade_common.utils import (
    decrypt_value,
    encrypt_value,
    generate_uuid,
    utc_now,
)

__version__ = "0.1.0"
__all__ = [
    # Models
    "TenantContext",
    "UserInfo",
    "PaginatedResponse",
    "ErrorResponse",
    "HealthResponse",
    # Middleware
    "TenantMiddleware",
    "get_tenant_context",
    # Events
    "Event",
    "EventType",
    # Utils
    "generate_uuid",
    "utc_now",
    "encrypt_value",
    "decrypt_value",
    # Logging
    "configure_logging",
    "get_logger",
    "set_request_context",
    "JSONFormatter",
    # Metrics
    "get_metrics",
    "init_service_info",
    "record_http_request",
    "MetricsTimer",
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION_SECONDS",
    # Health
    "HealthChecker",
    "HealthStatus",
    "check_postgres",
    "check_redis",
]
