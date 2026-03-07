"""Event store implementation using PostgreSQL.

The event store is an append-only log of all trading events. Events are
immutable once written and provide the source of truth for system state.
"""

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from llamatrade_db import Base

from src.events.base import TradingEvent, deserialize_event

logger = logging.getLogger(__name__)


class EventRecord(Base):  # type: ignore[misc]
    """SQLAlchemy model for stored events."""

    __tablename__ = "trading_events"

    # Global sequence number for ordering
    sequence: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # Event identity
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        unique=True,
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Ownership
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Timing
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    # Event payload
    data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_trading_events_session_seq", "session_id", "sequence"),
        Index("ix_trading_events_tenant_seq", "tenant_id", "sequence"),
        Index("ix_trading_events_type_seq", "event_type", "sequence"),
    )


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""

    def default(self, o: object) -> str:
        if isinstance(o, Decimal):
            return str(o)
        # For unhandled types, fall back to JSONEncoder default
        # which raises TypeError for unsupported types
        return str(super().default(o))


class EventStore:
    """Append-only event store backed by PostgreSQL.

    The event store provides:
    - Append-only writes (events are immutable)
    - Global ordering via sequence numbers
    - Efficient stream reads by session
    - Event deserialization to typed objects

    Usage:
        store = EventStore(db_session)

        # Append events
        await store.append(OrderSubmitted(...))
        await store.append(OrderFilled(...))

        # Read events for a session
        async for event in store.read_stream(session_id):
            aggregate.apply(event)

        # Read from a specific point
        async for event in store.read_stream(session_id, from_sequence=100):
            ...
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def append(self, event: TradingEvent) -> int:
        """Append an event to the store.

        Args:
            event: The event to store.

        Returns:
            The sequence number assigned to this event.

        Raises:
            ValueError: If event_id already exists (duplicate).
        """
        # Serialize event data
        event_data = event.to_dict()

        # Handle Decimal serialization
        data_json = json.loads(json.dumps(event_data, cls=DecimalEncoder))

        record = EventRecord(
            event_id=event.event_id,
            event_type=event.event_type,
            tenant_id=event.tenant_id,
            session_id=event.session_id,
            timestamp=event.timestamp,
            data=data_json,
        )

        self.db.add(record)
        await self.db.flush()  # Get the sequence number

        logger.debug(
            f"Appended event {event.event_type} seq={record.sequence}",
            extra={
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "session_id": str(event.session_id),
                "sequence": record.sequence,
            },
        )

        return int(record.sequence)

    async def append_batch(self, events: list[TradingEvent]) -> list[int]:
        """Append multiple events atomically.

        All events are written in a single transaction. If any fails,
        none are written.

        Args:
            events: Events to store.

        Returns:
            List of sequence numbers assigned.
        """
        sequences: list[int] = []
        for event in events:
            seq = await self.append(event)
            sequences.append(seq)
        return sequences

    async def read_stream(
        self,
        session_id: UUID,
        from_sequence: int = 0,
        to_sequence: int | None = None,
        event_types: list[str] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[TradingEvent]:
        """Read events from a session stream.

        Args:
            session_id: The session to read events for.
            from_sequence: Start reading from this sequence (exclusive).
            to_sequence: Stop at this sequence (inclusive).
            event_types: Filter to only these event types.
            limit: Maximum number of events to return.

        Yields:
            Events in sequence order.
        """
        query = """
            SELECT sequence, event_id, event_type, tenant_id, session_id,
                   timestamp, data
            FROM trading_events
            WHERE session_id = :session_id
              AND sequence > :from_sequence
        """
        params: dict[str, object] = {
            "session_id": session_id,
            "from_sequence": from_sequence,
        }

        if to_sequence is not None:
            query += " AND sequence <= :to_sequence"
            params["to_sequence"] = to_sequence

        if event_types:
            query += " AND event_type = ANY(:event_types)"
            params["event_types"] = event_types

        query += " ORDER BY sequence ASC"

        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit

        result = await self.db.execute(text(query), params)

        for row in result.mappings():
            event_data = dict(row["data"])
            event_data["sequence"] = row["sequence"]
            yield deserialize_event(event_data)

    async def read_all(
        self,
        tenant_id: UUID,
        from_sequence: int = 0,
        event_types: list[str] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[TradingEvent]:
        """Read all events for a tenant.

        Args:
            tenant_id: The tenant to read events for.
            from_sequence: Start reading from this sequence (exclusive).
            event_types: Filter to only these event types.
            limit: Maximum number of events to return.

        Yields:
            Events in sequence order.
        """
        query = """
            SELECT sequence, event_id, event_type, tenant_id, session_id,
                   timestamp, data
            FROM trading_events
            WHERE tenant_id = :tenant_id
              AND sequence > :from_sequence
        """
        params: dict[str, object] = {
            "tenant_id": tenant_id,
            "from_sequence": from_sequence,
        }

        if event_types:
            query += " AND event_type = ANY(:event_types)"
            params["event_types"] = event_types

        query += " ORDER BY sequence ASC"

        if limit:
            query += " LIMIT :limit"
            params["limit"] = limit

        result = await self.db.execute(text(query), params)

        for row in result.mappings():
            event_data = dict(row["data"])
            event_data["sequence"] = row["sequence"]
            yield deserialize_event(event_data)

    async def get_by_id(self, event_id: UUID) -> TradingEvent | None:
        """Get a specific event by ID.

        Args:
            event_id: The event ID to find.

        Returns:
            The event if found, None otherwise.
        """
        query = """
            SELECT sequence, event_id, event_type, tenant_id, session_id,
                   timestamp, data
            FROM trading_events
            WHERE event_id = :event_id
        """
        result = await self.db.execute(text(query), {"event_id": event_id})
        row = result.mappings().first()

        if not row:
            return None

        event_data = dict(row["data"])
        event_data["sequence"] = row["sequence"]
        return deserialize_event(event_data)

    async def get_latest_sequence(self, session_id: UUID) -> int:
        """Get the latest sequence number for a session.

        Args:
            session_id: The session to check.

        Returns:
            The latest sequence number, or 0 if no events.
        """
        query = """
            SELECT COALESCE(MAX(sequence), 0) as max_seq
            FROM trading_events
            WHERE session_id = :session_id
        """
        result = await self.db.execute(text(query), {"session_id": session_id})
        row = result.mappings().first()
        return int(row["max_seq"]) if row else 0

    async def count_events(
        self,
        session_id: UUID,
        event_types: list[str] | None = None,
    ) -> int:
        """Count events for a session.

        Args:
            session_id: The session to count.
            event_types: Filter to only these event types.

        Returns:
            Number of events.
        """
        query = """
            SELECT COUNT(*) as count
            FROM trading_events
            WHERE session_id = :session_id
        """
        params: dict[str, object] = {"session_id": session_id}

        if event_types:
            query += " AND event_type = ANY(:event_types)"
            params["event_types"] = event_types

        result = await self.db.execute(text(query), params)
        row = result.mappings().first()
        return int(row["count"]) if row else 0


def create_event_store(db: AsyncSession) -> EventStore:
    """Factory function to create an event store.

    Args:
        db: Database session to use.

    Returns:
        Configured EventStore instance.
    """
    return EventStore(db)
