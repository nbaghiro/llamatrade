"""LlamaTrade Database - Shared ORM models and database utilities."""

from llamatrade_db.advisory import (
    advisory_unlock,
    holds_advisory_lock,
    try_advisory_lock,
)
from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from llamatrade_db.session import (
    PoolStats,
    bind_tenant_guc,
    close_db,
    get_database_url,
    get_db,
    get_engine,
    get_pool_stats,
    get_session_maker,
    init_db,
    set_rls_bypass,
    set_tenant_guc,
    system_session,
    tenant_session,
    unbind_tenant_guc,
    verify_rls_enforcement,
)

__all__ = [
    # Base and mixins
    "Base",
    "UUIDPrimaryKeyMixin",
    "TenantMixin",
    "TimestampMixin",
    # Session utilities
    "get_database_url",
    "get_engine",
    "get_session_maker",
    "get_db",
    "init_db",
    "close_db",
    # RLS tenant scoping
    "bind_tenant_guc",
    "set_tenant_guc",
    "unbind_tenant_guc",
    "verify_rls_enforcement",
    "set_rls_bypass",
    "tenant_session",
    "system_session",
    # Pool observability
    "PoolStats",
    "get_pool_stats",
    # Session-level advisory locks
    "try_advisory_lock",
    "advisory_unlock",
    "holds_advisory_lock",
]
