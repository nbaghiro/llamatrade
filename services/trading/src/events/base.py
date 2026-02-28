"""Base event classes for event sourcing."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4


@dataclass(kw_only=True)
class TradingEvent:
    """Base class for all trading events.

    Events are immutable facts that have occurred. They are stored
    in an append-only event store and used to reconstruct state.

    Attributes:
        event_id: Unique identifier for this event instance.
        event_type: String identifier for the event type (set by subclass).
        tenant_id: Tenant this event belongs to.
        session_id: Trading session this event belongs to.
        timestamp: When the event occurred.
        sequence: Global ordering sequence (set by event store on append).
        metadata: Optional additional data for debugging/audit.
    """

    # Class variable - each subclass sets its own event type
    EVENT_TYPE: ClassVar[str] = "base_event"

    event_id: UUID = field(default_factory=uuid4)
    tenant_id: UUID
    session_id: UUID
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    sequence: int | None = None  # Set by event store on append
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        """Get the event type identifier."""
        return self.__class__.EVENT_TYPE

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary for storage."""
        data = {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "tenant_id": str(self.tenant_id),
            "session_id": str(self.session_id),
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }
        # Add subclass-specific fields
        for key, value in self.__dict__.items():
            if key not in data and not key.startswith("_"):
                if isinstance(value, UUID):
                    data[key] = str(value)
                elif isinstance(value, datetime):
                    data[key] = value.isoformat()
                elif hasattr(value, "__dataclass_fields__"):
                    data[key] = value.to_dict() if hasattr(value, "to_dict") else str(value)
                else:
                    data[key] = value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TradingEvent":
        """Deserialize event from dictionary.

        Note: This base implementation only works for the base class.
        Subclasses should be deserialized via the event registry.
        """
        return cls(
            event_id=UUID(data["event_id"]),
            tenant_id=UUID(data["tenant_id"]),
            session_id=UUID(data["session_id"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            sequence=data.get("sequence"),
            metadata=data.get("metadata", {}),
        )


# Registry of event types for deserialization
_EVENT_REGISTRY: dict[str, type[TradingEvent]] = {}


def register_event(event_class: type[TradingEvent]) -> type[TradingEvent]:
    """Decorator to register an event class for deserialization."""
    _EVENT_REGISTRY[event_class.EVENT_TYPE] = event_class
    return event_class


def get_event_class(event_type: str) -> type[TradingEvent] | None:
    """Get the event class for a given event type."""
    return _EVENT_REGISTRY.get(event_type)


def deserialize_event(data: dict[str, Any]) -> TradingEvent:
    """Deserialize an event from stored data."""
    event_type = data.get("event_type")
    if not event_type:
        raise ValueError("Event data missing event_type")

    event_class = get_event_class(event_type)
    if not event_class:
        raise ValueError(f"Unknown event type: {event_type}")

    # Build kwargs for the specific event class
    kwargs: dict[str, Any] = {
        "event_id": UUID(data["event_id"]),
        "tenant_id": UUID(data["tenant_id"]),
        "session_id": UUID(data["session_id"]),
        "timestamp": datetime.fromisoformat(data["timestamp"]),
        "metadata": data.get("metadata", {}),
    }

    # Add sequence if present
    if "sequence" in data:
        kwargs["sequence"] = data["sequence"]

    # Get field names from the dataclass
    if hasattr(event_class, "__dataclass_fields__"):
        for field_name, field_info in event_class.__dataclass_fields__.items():
            if field_name in kwargs or field_name in ("EVENT_TYPE",):
                continue
            if field_name in data:
                value = data[field_name]
                # Handle UUID fields
                if field_info.type == UUID or str(field_info.type) == "uuid.UUID":
                    value = UUID(value) if isinstance(value, str) else value
                elif "UUID" in str(field_info.type):
                    # Optional[UUID] or UUID | None
                    value = UUID(value) if isinstance(value, str) and value else value
                kwargs[field_name] = value

    return event_class(**kwargs)
