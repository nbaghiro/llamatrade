"""Database connection and session management.

Re-exports from the shared libs/db package for backward compatibility.
"""

from llamatrade_db import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    close_db,
    get_db,
    get_engine,
    get_session_maker,
    init_db,
)
from llamatrade_db.session import get_database_url

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
    "get_database_url",
]
