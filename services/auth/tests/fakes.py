"""Shared test doubles for the auth suite.

``MockAsyncSession`` routes query results per queried model (FIFO queue per
model class, falling back to ``_query_result``), so multi-query RPC flows get
honest per-query answers instead of one preset row answering everything.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import bcrypt
import jwt

from llamatrade_events import EventEnvelope
from llamatrade_events.catalog import notifications as notifications_module
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import events_pb2

JWT_SECRET = "test-secret"
JWT_ALGORITHM = "HS256"

_STANDARD_TEST_API_KEY = "testkey_secretpart123"


def _default_key_hash() -> str:
    return hashlib.sha256(_STANDARD_TEST_API_KEY.encode()).hexdigest()


class MockUser:
    """Mock User database model."""

    def __init__(
        self,
        id: UUID | None = None,
        tenant_id: UUID | None = None,
        email: str = "test@example.com",
        password: str = "Test123!",
        first_name: str = "Test",
        last_name: str = "User",
        role: str = "admin",
        is_active: bool = True,
        is_verified: bool = False,
        avatar_url: str | None = None,
    ) -> None:
        self.id = id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.email = email
        self.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.is_active = is_active
        self.is_verified = is_verified
        self.avatar_url = avatar_url
        self.created_at = datetime.now(UTC)
        self.last_login: datetime | None = None


class MockTenant:
    """Mock Tenant database model."""

    def __init__(
        self,
        id: UUID | None = None,
        name: str = "Test Tenant",
        slug: str = "test-tenant",
        is_active: bool = True,
    ) -> None:
        self.id = id or uuid4()
        self.name = name
        self.slug = slug
        self.is_active = is_active
        self.created_at = datetime.now(UTC)
        self.settings: dict[str, str] = {}


class MockAPIKey:
    """Mock APIKey database model."""

    def __init__(
        self,
        id: UUID | None = None,
        tenant_id: UUID | None = None,
        user_id: UUID | None = None,
        name: str = "Test Key",
        key_prefix: str = "testkey_",
        key_hash: str | None = None,
        scopes: list[str] | None = None,
        is_active: bool = True,
        expires_at: datetime | None = None,
    ) -> None:
        self.id = id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.user_id = user_id
        self.name = name
        self.key_prefix = key_prefix
        self.key_hash = key_hash or _default_key_hash()
        self.scopes = scopes or ["read", "write"]
        self.is_active = is_active
        self.expires_at = expires_at
        self.last_used_at: datetime | None = None
        self.created_at = datetime.now(UTC)


class MockRequestContext:
    """Mock ConnectRPC RequestContext."""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}

    def request_headers(self) -> dict[str, str]:
        """Return request headers (ConnectRPC API)."""
        return self.headers


class FakeScalars:
    """Scalar view over a fake result: iterable and ``.all()``-able."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)

    def __iter__(self) -> Iterator[object]:
        return iter(self._rows)


class FakeResult:
    """Result of a ``MockAsyncSession.execute`` call."""

    def __init__(self, value: object | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object | None:
        return self._value

    def scalars(self) -> FakeScalars:
        return FakeScalars([] if self._value is None else [self._value])


class MockAsyncSession:
    """Mock async database session with per-model result routing.

    ``queue_result(Model, value)`` feeds the next query whose ``select()``
    entity is ``Model`` (FIFO per model); unrouted queries fall back to
    ``_query_result``. ``added`` records every ``add()`` in order.
    """

    def __init__(self) -> None:
        self._query_result: object | None = None
        self._queued: dict[type, list[object | None]] = {}
        self.added: list[object] = []

    def queue_result(self, model: type, value: object | None) -> None:
        self._queued.setdefault(model, []).append(value)

    @staticmethod
    def _query_entity(query: object) -> type | None:
        descriptions = getattr(query, "column_descriptions", None)
        if not descriptions:
            return None
        entity = descriptions[0].get("entity")
        return entity if isinstance(entity, type) else None

    def _next_result(self, query: object) -> object | None:
        entity = self._query_entity(query)
        if entity is not None:
            queue = self._queued.get(entity)
            if queue:
                return queue.pop(0)
        return self._query_result

    async def execute(self, query: object) -> FakeResult:
        return FakeResult(self._next_result(query))

    async def scalar(self, query: object) -> object | None:
        return self._next_result(query)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    def add(self, obj: object) -> None:
        if getattr(obj, "created_at", False) is None:
            setattr(obj, "created_at", datetime.now(UTC))
        self.added.append(obj)

    async def __aenter__(self) -> MockAsyncSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        pass


class FakeRateLimiter:
    """Records check_and_count calls and returns a fixed decision."""

    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, int, int]] = []

    async def check_and_count(self, key: str, limit: int, window_seconds: int) -> bool:
        self.calls.append((key, limit, window_seconds))
        return self.allowed


class FakeRevocationStore:
    """In-memory revocation store mirroring llamatrade_common.RevocationStore."""

    def __init__(self) -> None:
        self.revoked_jtis: dict[str, int] = {}
        self.user_cutoffs: dict[str, int] = {}

    async def revoke_token(self, jti: str, exp: int) -> None:
        self.revoked_jtis[jti] = exp

    async def revoke_all_for_user(self, user_id: str, now: int) -> None:
        self.user_cutoffs[user_id] = now

    async def is_revoked(self, claims: dict[str, object]) -> bool:
        if str(claims.get("jti", "")) in self.revoked_jtis:
            return True
        cutoff = self.user_cutoffs.get(str(claims.get("sub")))
        iat = claims.get("iat")
        return cutoff is not None and isinstance(iat, int | float) and iat < cutoff


def create_test_token(
    user_id: str,
    tenant_id: str,
    token_type: str = "access",
    expired: bool = False,
    jti: str | None = None,
) -> str:
    """Create a test JWT token."""
    now = datetime.now(UTC)
    if expired:
        exp = now - timedelta(hours=1)
    else:
        exp = now + timedelta(hours=1)

    payload: dict[str, object] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": "test@example.com",
        "roles": ["admin"],
        "type": token_type,
        "iat": now,
        "exp": exp,
    }
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _fake_notification_transport() -> FakeTransport:
    shared = notifications_module._shared
    assert shared is not None
    transport = shared.bus.transport
    assert isinstance(transport, FakeTransport)
    return transport


def published_envelopes() -> list[EventEnvelope]:
    """Envelopes captured by the FakeTransport-backed shared notification stream."""
    return [
        EventEnvelope.FromString(value) for _, value in _fake_notification_transport().published
    ]


def published_notifications() -> list[events_pb2.NotificationEvent]:
    """Decoded notification events, in publish order."""
    return [NotificationEvents.payload(env) for env in published_envelopes()]
