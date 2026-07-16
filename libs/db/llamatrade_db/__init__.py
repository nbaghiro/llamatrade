"""LlamaTrade Database - Shared ORM models and database utilities."""

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from llamatrade_db.session import (
    PoolStats,
    close_db,
    get_db,
    get_engine,
    get_pool_stats,
    get_session_maker,
    init_db,
    set_rls_bypass,
    set_tenant_guc,
    system_session,
    tenant_session,
)

__all__ = [
    # Base and mixins
    "Base",
    "UUIDPrimaryKeyMixin",
    "TenantMixin",
    "TimestampMixin",
    # Session utilities
    "get_engine",
    "get_session_maker",
    "get_db",
    "init_db",
    "close_db",
    # RLS tenant scoping
    "set_tenant_guc",
    "set_rls_bypass",
    "tenant_session",
    "system_session",
    # Pool observability
    "PoolStats",
    "get_pool_stats",
]
